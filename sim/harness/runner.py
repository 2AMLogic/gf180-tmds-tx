"""Deck composition and ngspice execution for one PVT point.

Ported from `2AMLogic/gf180-bandgap` (sim/harness/runner.py). ``compose_deck``
gains two adaptations for this repo's transient/rate-axis claims (see
``sim/harness/corners.py`` and ``sim/harness/testbench.py``'s module
docstrings): it emits a ``rate_val``/``rate_nom`` parameter pair when the
point carries a bit rate, and it emits ``.options reltol=/abstol=/vntol=``
from the testbench's declared ``transient`` settings so those tolerances
actually take effect in the deck rather than being decorative metadata. The
measurement regex is also widened to accept ngspice's ``meas`` command
output (``m_trise  = 1.23e-09 targ=... trig=...``), not just the harness's
own ``let``/``print`` output (``m_vout = 1.23e-09``) -- a transient testbench
uses ``meas`` for threshold-crossing measurements (rise/fall time) that a
plain vector expression cannot express.

A ``tb.measure`` manifest entry whose value starts with ``TRIG `` (see
``_is_raw_meas_expr``) is rendered as a raw ``meas tran m_<name> <value>``
control-block command instead of a ``let m_<name> = <value>`` vector
expression -- e.g. ``"trise_10_90": "TRIG v(vdiff) VAL=-0.4 RISE=1 TARG
v(vdiff) VAL=0.4 RISE=1"``. Every other ``tb.measure`` entry (the
gf180-bandgap convention) is unaffected.

A third adaptation, added for issue #154 (Epic #542 Phase 3's assembled
driver+pad-ring+ESD block PVT run): ``compose_deck`` now emits an explicit
``.save`` line naming only the vectors ``tb.measure``'s expressions actually
reference (``_measure_vector_refs``), instead of relying on ngspice's
default of saving every node in the circuit. This changes no measured
result -- every ``v(...)``/``i(...)`` reference any ``measure`` expression
needs is still saved, so every ``let``/``meas`` line resolves identically --
it only stops ngspice from also storing the (unused) voltage of every other
node in the deck across every timestep. That default became a real problem
once a post-layout-extracted DUT much larger than the schematic (thousands
of internal parasitic-extraction nodes, not ~50) was swept over a multi-copy
transient testbench: ngspice's tran analysis pre-allocates storage for
*every* saved vector at *every* print step, and with no ``.save`` that is
every node in an 8-instance copy of the DUT, not just the ~29 nodes any
`measure` entry actually reads -- large enough to hit ngspice's own
"memory required ... is more than memory available" allocation guard
(confirmed while developing `sim/cml-driver-eye`'s
`gf180_tmds_pad_ring_assembly` post-layout record; the guard's own "memory
available" figure is an internal ngspice allocation-probe result, not this
machine's real free RAM, which is why the fix is fewer requested vectors,
not more memory).

A fourth adaptation, added for issue #305: both this module's
``compose_deck`` and ``batch.compose_body`` render their ``.options`` block
from one shared ``_option_lines``, which appends ``.options noinit`` so
ngspice stops printing its operating-point node table into every log. See
``_option_lines`` for what that removes (one block, nothing else), what it
provably does not change (every ``m_*`` line the records quote), and the two
manifest escape hatches.

A fifth adaptation, added for issue #317: the log write path filters out
ngspice's `` Reference value :  <float>`` transient solver progress trace --
not suppressible by any netlist directive, so the write path is the only
lever, and it carries no measurement anyway. See
``filter_progress_trace`` for what is dropped and what provably is not
(every other byte survives unchanged), the two raw-ngspice-text write sites
it is applied at, and the manifest escape hatch that keeps the trace.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .corners import PvtPoint
from .pdk import Pdk
from .testbench import Testbench

NGSPICE = "ngspice"
DEFAULT_TIMEOUT_S = 300

# Matches both this harness's own `let`/`print` output for a length-1 vector
# ("m_vout = 6.9043645202e-01", anchored to end of line) and ngspice's
# `meas` command output ("m_trise  = 8.00000e-10 targ=... trig=...",
# trailing text after the number) -- the leading `^\s*m_` anchor plus the
# unanchored tail is what lets one regex parse both without also matching
# `meas`'s own `targ=`/`trig=` sub-fields (neither starts with `m_`).
_MEAS_RE = re.compile(r"^\s*m_(\w+)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)")
_ERROR_RE = re.compile(r"^\s*(?:Error|ERROR|Fatal|fatal error|doAnalyses:)", re.MULTILINE)

# `v(node)` / `i(vsource)` / `v(node_a,node_b)` -- every vector-reference
# form used by this repo's `measure` expressions (both `let ... = <expr>`
# and raw `TRIG ...`/`TARG ...` fragments). Deliberately case-insensitive
# and comma-tolerant so a differential two-terminal probe `v(a,b)` is
# captured whole, not split.
_VECTOR_REF_RE = re.compile(r"\b[vi]\(([^)]*)\)", re.IGNORECASE)


def _measure_vector_refs(tb: Testbench) -> list[str]:
    """Every distinct `v(...)`/`i(...)` vector this testbench's `measure`
    expressions reference, in first-seen order. Feeds the `.save` line
    `compose_deck` emits so ngspice's tran analysis only pre-allocates
    storage for vectors something actually reads -- see this module's
    docstring for why that matters for a large post-layout-extracted DUT.
    """
    seen: dict[str, None] = {}
    for expr in tb.measure.values():
        for match in _VECTOR_REF_RE.finditer(expr):
            seen.setdefault(match.group(0), None)
    return list(seen.keys())


class NgspiceMissing(RuntimeError):
    pass


def ngspice_version() -> str:
    exe = shutil.which(NGSPICE)
    if not exe:
        raise NgspiceMissing(
            "ngspice not found on PATH.\n"
            "  macOS:  brew install ngspice\n"
            "  Debian: apt-get install ngspice"
        )
    out = subprocess.run(
        [exe, "--version"], capture_output=True, text=True, check=False
    ).stdout
    for line in out.splitlines():
        if "ngspice-" in line:
            return line.strip().lstrip("* ").strip()
    return out.strip().splitlines()[0] if out.strip() else "unknown"


# ---- shared netlist-assembly groups ---------------------------------------
#
# ``compose_deck`` (local backend, full deck) and ``batch.compose_body``
# (batch backend, circuit body for a ``klt sim`` request) must describe the
# same circuit. A divergence between them would not announce itself: both
# paths would still run, still measure, and still write a well-formed record
# -- of a *different* circuit (issue #308). Every directive the two composers
# share therefore lives in exactly one of the helpers below, and each composer
# adds only what is genuinely its own (the deck banners, ``.lib``, ``.temp``
# and the ``.control`` block for the full deck; the request fields for the
# batch body).
#
# These helpers emit no blank lines and no section banners -- whitespace and
# banners stay at the call sites. That is what lets both composers keep their
# existing output byte for byte while sharing one definition of the circuit.


def _rate_note(point: PvtPoint) -> str:
    """The ``rate=`` field of a composer's header comment."""
    return "n/a" if point.rate_mbps is None else f"{point.rate_mbps:g} Mbps/lane"


def _param_lines(tb: Testbench, point: PvtPoint) -> list[str]:
    """The ``.param`` block for one point: the PVT values, the optional rate
    parameter, then the testbench's own declared params.
    """
    lines = [
        f".param vdd_nom={tb.nominal_supply_v!r}",
        f".param vdd_val={point.vdd!r}",
        f".param temp_c={point.temp_c!r}",
    ]
    if point.rate_mbps is not None:
        # rate_nom is the nearest of the testbench's declared rates_mbps to
        # this point's own rate -- for the un-adapted single-rate case
        # (rates_mbps has one entry) it is simply that entry; a testbench
        # sweeping both spec rows (as sim/smoke-cml-pair does) gets a
        # ratio-style reference matching whichever row this point belongs to.
        lines.append(f".param rate_val={point.rate_mbps!r}")
    for key, value in tb.params.items():
        lines.append(f".param {key}={value}")
    return lines


def _pdk_include_lines(pdk: Pdk) -> list[str]:
    """The PDK design include (model definitions both backends need)."""
    return [f'.include "{pdk.design_include}"']


#: A manifest ``options`` entry of this spelling (whitespace- and
#: case-insensitive) means "keep ngspice's operating-point node table in this
#: bench's logs". It is a *harness-level* instruction, not an ngspice
#: directive, so it is consumed rather than emitted: ngspice treats ``noinit``
#: as a presence-only flag, and ``.options noinit=0`` suppresses the table
#: exactly as ``.options noinit`` does (verified on ngspice-47 on the dispatch
#: host), so the only way to keep the table is for no ``noinit`` to reach the
#: deck at all.
KEEP_OP_POINT_TABLE_OPTION = "noinit=0"

#: Suppresses ngspice's "Initial Transient Solution" node table -- one line
#: per node in the circuit, printed into every transient log by default.
NOINIT_OPTION = "noinit"

#: A manifest ``options`` entry of this spelling (whitespace- and
#: case-insensitive) means "keep ngspice's ``Reference value :`` transient
#: solver progress trace in this bench's logs" -- verbatim output, for a
#: debug bench reading the solver's step values out of the log. Like
#: ``KEEP_OP_POINT_TABLE_OPTION`` it is a *harness-level* instruction,
#: consumed rather than emitted: the trace is not controllable by any
#: ngspice directive (issue #317 -- on ngspice-47, ``noinit`` is
#: presence-only and touches only the node table), so emitting the entry
#: verbatim would only make ngspice reject the deck as an unknown option.
KEEP_PROGRESS_TRACE_OPTION = "reftrace=1"


def _normalized_option(option: str) -> str:
    """``" noinit = 0 "`` -> ``"noinit=0"`` -- for comparing a manifest
    ``options`` entry against a known spelling without caring about the
    spacing or case the manifest happened to use."""
    return "".join(str(option).split()).lower()


def _option_lines(tb: Testbench) -> list[str]:
    """The ``.options`` block a deck for this testbench carries: the
    testbench's own declared options, the tolerances its ``transient`` block
    declares, and ``.options noinit``.

    Shared by ``compose_deck`` (local backend) and ``batch.compose_body``
    (batch backend) so the two netlist-assembly paths cannot drift apart on
    what a deck asks ngspice for.

    ``.options noinit`` (issue #305) suppresses ngspice's operating-point
    node table. On a post-layout-extracted DUT that table is one line per
    parasitic node and almost the whole log -- 76.8 MB of the 92.7 MB this
    repo's 1211 committed logs hold, ~83% -- while nothing in the tree reads
    it: every value the records quote is parsed off the ``m_*`` lines
    (``_MEASURE_RE``). Suppressing it changes no measured result. It is the
    one block the directive removes, verified on ngspice-47: the title,
    ``.temp`` line, solver line, ``No. of Data Rows``, every ngspice warning
    and every ``m_*`` value are identical with and without it, and an ``op``
    or ``dc`` deck's output is byte-identical either way.

    Three escape hatches, all at the testbench's discretion; the first two
    keep the node table, the third keeps the solver progress trace:

    * ``"options": ["noinit=0"]`` -- keep the table (a debug bench reading
      node voltages out of the log rather than out of a ``measure`` entry).
      See ``KEEP_OP_POINT_TABLE_OPTION``.
    * any other ``options`` entry mentioning ``noinit`` -- the testbench is
      wording the directive itself, so the harness emits its entry verbatim
      and does not add a second one.
    * ``"options": ["reftrace=1"]`` -- keep the ``Reference value :``
      transient solver progress trace, which the log write path otherwise
      drops (see ``filter_progress_trace``). Consumed for the same reason
      as ``KEEP_OP_POINT_TABLE_OPTION``: there is no ngspice directive to
      word. See ``KEEP_PROGRESS_TRACE_OPTION``.
    """
    declared = [
        option
        for option in tb.options
        if _normalized_option(option)
        not in (KEEP_OP_POINT_TABLE_OPTION, KEEP_PROGRESS_TRACE_OPTION)
    ]
    keep_op_point_table = any(
        _normalized_option(option) == KEEP_OP_POINT_TABLE_OPTION
        for option in tb.options
    )

    lines = [f".options {option}" for option in declared]
    for key in ("reltol", "abstol", "vntol"):
        if key in tb.transient:
            lines.append(f".options {key}={tb.transient[key]!r}")
    already_worded = any(
        NOINIT_OPTION in _normalized_option(option) for option in declared
    )
    if not keep_op_point_table and not already_worded:
        lines.append(f".options {NOINIT_OPTION}")
    return lines


def _dut_lines(tb: Testbench) -> list[str]:
    """The DUT provenance comment and include -- empty when there is no DUT
    (a testbench that instantiates its devices inline).
    """
    if tb.dut is None:
        return []
    return [
        f"* provenance: {tb.dut_provenance_class}  sha256 {tb.dut_sha256}",
        f'.include "{tb.dut}"',
    ]


def _testbench_include_lines(tb: Testbench) -> list[str]:
    """The testbench netlist include."""
    return [f'.include "{tb.netlist}"']


# --------------------------------------------------------------------------
# The log write path's one shared filter (issue #317)
#
# ngspice's transient solver prints its progress as `` Reference value :
#  <float>`` lines into stdout -- one per accepted internal step, on every
# tran analysis, at a rate nothing in the deck asked for. Across this repo's
# 407,901 committed occurrences (13.05 MB of the 91.9 MB the committed logs
# hold, issue #317) the shape has zero variance beyond the digits: two
# spaces after the colon, a positive mantissa, nothing else on the line.
# The lines carry no measurement -- a bare step value whose time axis is
# already pinned by ``No. of Data Rows`` and the ``targ=``/``trig=`` times
# on the ``m_*`` lines -- and nothing in the tree reads them (``git grep
# "Reference value" -- ':!*.log'``: no matches), so both write sites through
# which raw ngspice text reaches a log -- ``run_point`` below and
# ``report.write_device_corner_log`` -- drop them through the one shared
# ``filter_progress_trace`` rather than each growing its own. The batch
# backend is deliberately not covered: its log is a klt CLI wrapper around
# klt's own JSON report, and raw ngspice text never reaches that write.
# --------------------------------------------------------------------------

#: Matches one progress-trace line *and its newline*, anchored on both ends:
#: the phrase must be the whole line for the match to fire, so a line that
#: merely contains it (a warning quoting the phrase, or any spacing
#: variation) survives untouched. The mantissa carries no sign -- the
#: committed corpus has no negative reference value, and a hypothetical one
#: would simply be preserved: the filter errs narrow, never wide.
_REFERENCE_VALUE_LINE_RE = re.compile(
    r"(?m)^ Reference value :  \d+\.\d+e[+-]\d+(?:\n|$)"
)


def _wants_progress_trace(tb: Testbench) -> bool:
    """Whether this testbench's manifest asked for the ngspice trace back --
    the ``KEEP_PROGRESS_TRACE_OPTION`` spelling in its ``options`` list,
    compared whitespace- and case-insensitively like every manifest option."""
    return any(
        _normalized_option(option) == KEEP_PROGRESS_TRACE_OPTION
        for option in tb.options
    )


def filter_progress_trace(text: str, *, keep: bool = False) -> str:
    """Drop ngspice's `` Reference value :  <float>`` solver progress lines.

    These are not suppressible by any netlist directive -- ``.options
    noinit`` touches only the operating-point node table (issue #305/#317,
    verified on ngspice-47) -- so the write path is the only lever. Applied
    at write time, after everything that *reads* the output has seen it:
    ``parse_measurements``, the exit-status handling and the ngspice-error
    extraction in ``run_point`` all still see the unfiltered text, and no
    ``m_*`` line can match the anchored pattern anyway.

    Only whole matching lines are removed -- matching line plus its
    newline -- so every other byte is preserved exactly: an output with no
    match comes back identical, and the file's trailing newline (or absence
    of one) is whatever ngspice produced.

    ``keep=True`` returns the text verbatim: the escape hatch for a debug
    bench that wants the trace back, driven by the manifest ``options``
    entry ``KEEP_PROGRESS_TRACE_OPTION`` (see ``_option_lines``, which
    consumes it the way it consumes ``KEEP_OP_POINT_TABLE_OPTION``).

    Degenerate inputs pass through as themselves. Empty text in, empty text
    out -- the same empty log the unfiltered write path would have written.
    A log consisting solely of trace lines filters to an empty string,
    which the evidence store's non-empty guard rejects loudly at ingest
    (``evidence_store.store_run``); ngspice's banner makes that case
    unreachable in practice, and a degenerate run has always been the
    store's business to reject, not the filter's to paper over.
    """
    if keep:
        return text
    return _REFERENCE_VALUE_LINE_RE.sub("", text)


def compose_deck(tb: Testbench, pdk: Pdk, point: PvtPoint) -> str:
    """Build the complete, self-contained ngspice deck for one PVT point.

    The directives this shares with the batch backend's ``compose_body`` come
    from the helpers above, not from a second copy -- see their comment.
    """
    lines: list[str] = [
        f"* {tb.name} @ {point.corner_id} -- GENERATED by sim/harness, do not edit",
        f"* corner={point.corner.name} ({point.corner.description})",
        f"* temp={point.temp_c} C  vdd={point.vdd} V  rate={_rate_note(point)}  pdk={pdk.variant}@{pdk.version}",
        "",
        "* ---- PVT parameters -------------------------------------------------",
    ]
    lines += _param_lines(tb, point)

    lines += [
        "",
        "* ---- gf180mcu models ------------------------------------------------",
    ]
    lines += _pdk_include_lines(pdk)
    for section in point.corner.sections:
        lines.append(f'.lib "{pdk.model_lib}" {section}')

    lines += [
        "",
        f".temp {point.temp_c!r}",
    ]
    lines += _option_lines(tb)

    dut_lines = _dut_lines(tb)
    if dut_lines:
        lines += [
            "",
            "* ---- device under test ----------------------------------------------",
        ]
        lines += dut_lines

    lines += [
        "",
        "* ---- testbench ------------------------------------------------------",
    ]
    lines += _testbench_include_lines(tb)
    lines += [
        "",
        "* ---- measurement ----------------------------------------------------",
        ".control",
        "set numdgt=10",
        "set noaskquit",
    ]
    save_targets = _measure_vector_refs(tb)
    if save_targets:
        lines.append("  save " + " ".join(save_targets))
    lines += [f"  {analysis}" for analysis in tb.analyses]
    for name, expr in tb.measure.items():
        if _is_raw_meas_expr(expr):
            # A raw ngspice `meas` fragment (threshold-crossing measurements
            # -- rise/fall time -- that a `let` vector expression cannot
            # express). `meas` prints "m_<name> = <value> ..." itself, so no
            # separate `print` line is emitted for it below.
            lines.append(f"  meas tran m_{name} {expr}")
        else:
            lines.append(f"  let m_{name} = {expr}")
    for name, expr in tb.measure.items():
        if not _is_raw_meas_expr(expr):
            lines.append(f"  print m_{name}")
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def _is_raw_meas_expr(expr: str) -> bool:
    """Is this ``measure`` manifest entry a raw ``meas`` fragment (starts
    with ``TRIG``, case-insensitive) rather than a ``let`` vector expression?

    See ``sim/harness/testbench.py``'s module docstring and
    ``sim/README.md``'s measurement-convention section.
    """
    return expr.strip().upper().startswith("TRIG ")


@dataclass
class PointResult:
    point: PvtPoint
    status: str                                   # "ok" | "failed" | "error"
    measurements: dict[str, float] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    seconds: float = 0.0
    deck: str = ""
    log: str = ""
    message: str = ""
    # Batch backend only (sim/harness/batch.py); empty for a local run.
    backend: str = "local"
    job_id: str = ""
    engine_version: str = ""

    def as_dict(self) -> dict:
        record = self.point.as_dict()
        record.update(
            {
                "status": self.status,
                "measurements": self.measurements,
                "seconds": round(self.seconds, 3),
                "deck": self.deck,
                "log": self.log,
            }
        )
        if self.missing:
            record["missing_measurements"] = self.missing
        if self.message:
            record["message"] = self.message
        if self.backend != "local":
            record["backend"] = self.backend
            record["batch_job_id"] = self.job_id
        return record


def parse_measurements(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in text.splitlines():
        match = _MEAS_RE.match(line)
        if match:
            try:
                found[match.group(1)] = float(match.group(2))
            except ValueError:  # pragma: no cover - regex already constrains this
                continue
    return found


def run_point(
    tb: Testbench,
    pdk: Pdk,
    point: PvtPoint,
    workdir: Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    log_dir: Path | None = None,
) -> PointResult:
    """Simulate one PVT point. Never raises for simulation failure.

    ``workdir`` holds the generated deck (scratch, disposable). ``log_dir``
    -- when given -- is where the ngspice output lands as
    ``<corner-id>.log``; that is the ``sim/<slug>/corners/<record-id>/``
    directory from ``sim/README.md``. It defaults to ``workdir`` so a
    throwaway run does not touch the evidence tree. The log is ngspice's
    output with the ``Reference value :`` solver progress trace dropped
    (see ``filter_progress_trace``; a manifest ``options`` entry
    ``"reftrace=1"`` keeps it) -- the deck's measurements, exit status and
    error extraction are all taken from the unfiltered text.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    log_dir = workdir if log_dir is None else log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    deck_path = workdir / f"{point.corner_id}.spice"
    log_path = log_dir / f"{point.corner_id}.log"
    deck_path.write_text(compose_deck(tb, pdk, point))

    started = time.monotonic()
    try:
        proc = subprocess.run(
            [NGSPICE, "-b", str(deck_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=workdir,
            check=False,
        )
        output = proc.stdout + "\n" + proc.stderr
        returncode = proc.returncode
    except FileNotFoundError as exc:
        raise NgspiceMissing(str(exc)) from exc
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        log_path.write_text(f"TIMEOUT after {timeout_s}s\n")
        return PointResult(
            point=point,
            status="error",
            seconds=elapsed,
            deck=deck_path.name,
            log=log_path.name,
            message=f"ngspice timed out after {timeout_s}s",
        )
    elapsed = time.monotonic() - started
    log_path.write_text(
        filter_progress_trace(output, keep=_wants_progress_trace(tb))
    )

    measurements = parse_measurements(output)
    missing = [name for name in tb.measure if name not in measurements]

    if missing:
        errors = "; ".join(_ERROR_RE.findall(output)[:3])
        first_error = next(
            (line.strip() for line in output.splitlines() if _ERROR_RE.match(line)), ""
        )
        return PointResult(
            point=point,
            status="failed",
            measurements=measurements,
            missing=missing,
            seconds=elapsed,
            deck=deck_path.name,
            log=log_path.name,
            message=first_error or errors or f"ngspice exit {returncode}, no measurements parsed",
        )

    return PointResult(
        point=point,
        status="ok",
        measurements=measurements,
        seconds=elapsed,
        deck=deck_path.name,
        log=log_path.name,
    )


def run_grid(
    tb: Testbench,
    pdk: Pdk,
    points: list[PvtPoint],
    workdir: Path,
    jobs: int = 1,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    on_result=None,
    log_dir: Path | None = None,
) -> list[PointResult]:
    """Run every PVT point; results come back in grid order regardless of jobs."""
    results: list[PointResult | None] = [None] * len(points)

    def _one(index_point):
        index, point = index_point
        result = run_point(tb, pdk, point, workdir, timeout_s=timeout_s, log_dir=log_dir)
        results[index] = result
        if on_result is not None:
            on_result(result)
        return result

    if jobs <= 1:
        for item in enumerate(points):
            _one(item)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(_one, enumerate(points)))

    return [r for r in results if r is not None]
