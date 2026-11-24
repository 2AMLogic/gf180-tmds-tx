"""Whole-grid ``klt sim`` envelope requests for T1 item 5 (issue #229).

``klt signoff`` grades an analog partition's "full corner verification vs a
ratified spec" (item 5) only from ``klt sim`` JSON envelopes: every cited
envelope must pass, must carry at least one limited measurement, and --
through ``measurements[].spec_row`` tags -- names the spec rows its graded
checks belong to (klayout-tools ``docs/design-evidence-tiers.md`` item 5 and
``docs/cli/signoff.md`` "Derived coverage"). The Markdown records under
``sim/*/records/`` are this repo's own evidence format and are rejected by
the grader however sound they are.

This module derives such a request from one *existing* testbench definition
-- ``tb.json``, its netlist fragment and its DUT, all unchanged -- so the
envelope grades the same circuit, the same measures and the same limits as
the bench's records:

- **One body, one request, the whole grid.** The circuit body is composed
  once per bench with the nominal ``.param`` values; the request's
  ``corners`` block sweeps process x temperature x (supply, rate) over it.
  ``corners.params`` applies ``alterparam`` + ``reset`` per corner, which
  re-expands the benches' ``{tbit_s}``-style PWL stimuli (checked after the
  run: :func:`grid_problems` re-applies the harness's own
  ``min_spread_pct`` check, which exists to prove the rate axis reached the
  stimulus). One report therefore covers the full mandated matrix and pins
  one netlist hash -- except for a bench in :data:`TRANSIENT_WINDOWS`, whose
  rates need different transient windows and get one request per rate.
- **Limits.** Every ``checks`` entry's ``min``/``max`` becomes its
  measurement's ``limits``. The grid-level spread checks have no per-corner
  meaning, so ``klt sim`` cannot grade them; :func:`grid_problems` re-applies
  the harness's own ``evaluate_checks`` to the collected report instead.
- **Row tags.** ``spec_rows`` maps measurement names to spec row ids; each
  is emitted as that measurement's ``spec_row``.
- **Fleet-safe init.** ``options.ngspice_init`` selects the per-finger width
  binning the driver's ``w=128u nf=64`` devices need. The batch fleet's
  ngspice reads no ambient init, and without it every corner aborts with
  ``could not find a valid modelname`` (klayout-tools#5593).

The body is composed for ``models.param_file`` (the PDK's design include as
a request field) and repo-relative ``.include``s, so a committed body carries
no host path, and ``sim/run_envelope.py`` can regenerate it byte for byte to
prove a cited envelope still matches its bench.
"""

from __future__ import annotations

import itertools
import os
import re
from collections import Counter
from pathlib import Path

from .batch import CAPACITY_WAIT_S, BatchError
from .corners import CORNERS, PvtPoint, build_grid, resolve_corners, supply_points
from .report import evaluate_checks, summarize
from .runner import PointResult, _is_raw_meas_expr, _option_lines, _param_lines
from .testbench import Testbench

#: DR-0010 pins the PDK variant for this block; a committed request must not
#: depend on which PDK install happened to generate it.
PDK_VARIANT = "gf180mcuD"
MODELS_LIB = "libs.tech/ngspice/sm141064.ngspice"
#: The PDK's design include (the globals its model sections reference) rides
#: as a request field rather than a body ``.include``, so the body names no
#: absolute PDK path.
MODELS_PARAM_FILE = "libs.tech/ngspice/design.ngspice"

#: The PDK's ngspice models bin on per-finger width (W/NF): the driver's
#: W=128u nf=64 devices (2 u/finger) only resolve a model bin when ngspice's
#: ``wnflag`` is 1. A distro build sets it via ``ngbehavior=hsa``; the batch
#: fleet's ngspice reads no ambient init, and a request without it aborts
#: every corner with ``could not find a valid modelname`` (measured
#: 2026-11-24 on the fleet: the same two-unit request fails without
#: ``options.ngspice_init`` and passes with it). ``options.ngspice_init``
#: REPLACES any ``$HOME/.spiceinit``, so the lines must be complete;
#: ``num_threads=1`` pins the single-threaded determinism this repo's host
#: init files pin. The same lines ``sim/pex/gen_requests.py`` declares.
NGSPICE_INIT = ("set wnflag=1", "set num_threads=1")

#: Per-unit wall-clock budget. The fleet's whole-job ceiling is 3600 s and a
#: job's conservative bound is ``options.timeout_s`` x units + 120 s, so 60 s
#: lets ``job_ceiling_check: "split"`` fit 58 of a bench's 90 units in one
#: job (two jobs per bench) while still standing ~6x above the slowest
#: measured unit (the PRBS7 mask bench, ~9 s).
TIMEOUT_S = 60

#: Harness parameters the request sweeps per corner (``corners.params`` /
#: ``corners.temperature_param``).
SUPPLY_PARAM = "vdd_val"
RATE_PARAM = "rate_val"
TEMP_PARAM = "temp_c"

#: Transient windows that differ from the manifest's single ``analyses``
#: line, per bench and rate. ``cml-driver-eye-mask`` declares one 560 ns
#: window for both rates -- 150 bits at 270 Mbps. At 742.5 Mbps the pattern
#: ends at 202 ns and every measurement window with it, and in the dead time
#: after it ngspice-47 as built for Linux (this repo's dispatch hosts and the
#: batch fleet; the macOS builds that took the bench's records complete the
#: window) fails to converge at exactly 300 x tbit = 404.04 ns ("timestep too
#: small", node ``vinn#branch``) at every corner, with reltol from 1e-6 to
#: 1e-3 and with every solver option tried. A window that stops before that
#: event measures exactly the same thing: all 150 bits are driven and all
#: windows closed 100 ns earlier (measured: identical eyemask values at
#: tstop 300 ns, 403 ns and in the aborted 560 ns run). The envelope request
#: for that rate therefore carries this window instead; the bench's own
#: manifest is unchanged, and its Linux runs still abort (filed separately).
TRANSIENT_WINDOWS = {
    "cml-driver-eye-mask": {742.5: "tran 20e-12 300e-9 0 40e-12"},
}

_M_REF_RE = re.compile(r"\bm_([A-Za-z_][A-Za-z0-9_]*)\b")


class EnvelopeError(BatchError):
    """The bench cannot be expressed as a whole-grid ``klt sim`` request."""


def analysis_of(tb) -> tuple[str, str]:
    """``(kind, args)`` of the bench's single analysis line."""
    analyses = getattr(tb, "analyses", ()) or ("tran",)
    if len(analyses) != 1:
        raise EnvelopeError(
            f"{tb.name}: an envelope request carries exactly one analysis; this "
            f"testbench declares {len(analyses)}"
        )
    parts = analyses[0].split(None, 1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


def _split_analysis(line: str) -> tuple[str, str]:
    parts = line.split(None, 1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


def analysis_for(tb, rate: float | None) -> tuple[str, str]:
    """``(kind, args)`` of the transient run at ``rate``: the manifest's own
    analysis, unless :data:`TRANSIENT_WINDOWS` names this bench and rate."""
    override = TRANSIENT_WINDOWS.get(tb.experiment, {}).get(rate)
    return _split_analysis(override) if override else analysis_of(tb)


def rates_of(tb) -> list[float | None]:
    """The bench's rate axis as a list (``[None]`` for a bench without one)."""
    return list(tb.rates_mbps) or [None]


def measurement_refs(expr: str) -> set[str]:
    """Harness measurement names an expression references via ``m_<name>``."""
    return set(_M_REF_RE.findall(expr))


def _node_re(node: str) -> re.Pattern[str]:
    """Match ``node`` as a complete SPICE node name: case-insensitive (SPICE
    node names are), and not embedded in a longer hierarchical name -- so
    ``xvhi.tail`` matches ``XVHI.TAIL`` but not ``xxvhi.tail`` (a separate
    instance's probe) or ``xvhi.tail2``."""
    return re.compile(rf"(?<![\w.]){re.escape(node)}(?![\w.])", re.IGNORECASE)


def rewrite_expr(expr: str, node_rewrites: tuple[tuple[str, str], ...] = ()) -> str:
    """One harness ``measure`` expression -> a ``klt sim`` expression.

    Two mechanical translations, both dictated by how ``klt sim`` evaluates
    measurements (the fixture results recorded on klayout-tools#371):

    - ``m_<name>`` -> ``<name>``: the harness prefixes every measurement
      vector with ``m_``; a ``klt sim`` measurement is declared under its
      bare name, and both a later ``.meas ... PARAM`` card and a later
      ``expr`` reference results by that bare name (``m_<name>`` errors as
      an unknown vector);
    - the caller's node rewrites, e.g. through a DUT wrapper hierarchy.
    """
    for old, new in node_rewrites:
        expr = _node_re(old).sub(new, expr)
    return _M_REF_RE.sub(r"\1", expr)


def translate_measurements(tb, *, node_rewrites: tuple[tuple[str, str], ...] = ()) -> list[dict]:
    """The bench's ``measure`` map as an ordered ``klt sim`` measurements list.

    Three forms, in emission order (order is load-bearing):

    1. Raw ``TRIG ... TARG ...`` entries become verbatim top-level
       ``.meas <kind> <name> <expr>`` cards (``spice`` form).
    2. An expression whose ``m_`` references are ALL raw-card results (the
       row-4 ``dj_ui_*`` and row-5 ``trise_ui_*`` formulas over
       ``spa_*``/``spb_*``/``trise_*``/``ui_ref``) cannot be a control-block
       ``expr`` -- a later expression cannot read a ``.meas`` card's result
       under either spelling -- so it is emitted as a FOLLOWING
       ``.meas <kind> <name> PARAM='<formula>'`` card, which does read
       earlier card results by bare name. Both behaviours are the
       fixture-verified patterns recorded on klayout-tools#371.
    3. Everything else (vector expressions, and expressions over OTHER
       expression results -- the row-6 ``height_*`` -> ``eyeh_max_*``/
       ``eyemask_margin_*`` chain) becomes an ``expr`` entry; ``klt sim``
       evaluates ``expr`` entries in declared order inside one control
       block, so a dependency-respecting order (topological, stable) lets
       each formula reference its inputs by name.

    Malformed shapes fail at generation time instead of emitting an entry
    that evaluates against an unknown vector at run time: an unknown ``m_``
    reference, a dependency cycle, an expression left in ``expr`` form
    whose dependencies reach a ``.meas`` card result -- raw or PARAM form
    (readable in neither form) -- and an un-rewritten node reference,
    asserted over every emitted form.

    Measurement names and dependency structure are preserved from the bench
    manifest; nothing is renamed except the ``m_`` prefix removal. Shared
    with ``sim/pex/gen_requests.py``, which passes its wrapper node
    rewrites.
    """
    kind, _args = analysis_of(tb)
    patterns = tuple((_node_re(old), old, new) for old, new in node_rewrites)

    raw: dict[str, str] = {}
    exprs: dict[str, str] = {}
    for name, expr in tb.measure.items():
        (raw if _is_raw_meas_expr(expr) else exprs)[name] = expr

    entries: list[dict] = [
        {"name": name, "spice": f".meas {kind} {name} {raw[name]}"} for name in raw
    ]

    param_form: dict[str, str] = {}
    for name, expr in exprs.items():
        deps = measurement_refs(expr)
        unknown = deps - raw.keys() - exprs.keys()
        if unknown:
            raise EnvelopeError(
                f"{tb.name}: measurement {name!r} references unknown "
                f"measurement(s) {sorted(unknown)}"
            )
        if deps and deps <= raw.keys():
            param_form[name] = rewrite_expr(expr, node_rewrites)
    for name, rewritten in param_form.items():
        entries.append({"name": name, "spice": f".meas {kind} {name} PARAM='{rewritten}'"})
        del exprs[name]

    # An expression left in expr form must depend only on OTHER expr-form
    # names: a control-block expression reads a .meas card's result under
    # neither spelling, raw card or PARAM card (the klayout-tools#371
    # fixture finding), so a dependency reaching either cannot be expressed
    # in either klt sim form.
    for name in exprs:
        deps = measurement_refs(exprs[name])
        unreadable = sorted((deps & raw.keys()) | (deps & param_form.keys()))
        if unreadable:
            raise EnvelopeError(
                f"{tb.name}: measurement {name!r} depends on {unreadable} "
                "(.meas card results, raw or PARAM form), which a "
                "control-block expression cannot read (klayout-tools#371 fixture "
                "finding) -- the dependency cannot be expressed in either "
                "klt sim form"
            )

    # Topological order over remaining exprs (deps on other exprs), stable:
    # declared order wherever it already satisfies the dependencies.
    ordered: list[str] = []
    remaining = list(exprs)
    while remaining:
        progressed = False
        for name in list(remaining):
            deps = measurement_refs(exprs[name]) & exprs.keys()
            if deps <= set(ordered):
                ordered.append(name)
                remaining.remove(name)
                progressed = True
        if not progressed:
            raise EnvelopeError(
                f"{tb.name}: cyclic measurement dependencies among {remaining}"
            )
    for name in ordered:
        entries.append({"name": name, "expr": rewrite_expr(exprs[name], node_rewrites)})

    # A node rewrite must hold for every emitted form that can carry a node
    # reference, not only expr entries: raw cards are emitted verbatim, so a
    # card probing a rewritten-away node fails HERE instead of dying on an
    # unknown node at run time, and a residual in a rewritten (PARAM or
    # expr) entry means the rewrite table did not cover it.
    for entry in entries:
        text = entry["spice"] if "spice" in entry else entry["expr"]
        for pattern, old, _new in patterns:
            if pattern.search(text):
                raise EnvelopeError(
                    f"{tb.name}: node rewrite for {old!r} incomplete in "
                    f"{entry['name']!r}"
                )

    names = [entry["name"] for entry in entries]
    if len(names) != len(set(names)):
        raise EnvelopeError(f"{tb.name}: duplicate measurement name after translation")
    return entries


def limits_of(check: dict) -> dict | None:
    """The per-corner ``limits`` of one harness ``checks`` entry -- its
    ``min``/``max`` only. The grid-level ``max_spread_pct``/``min_spread_pct``
    keys compare corners with each other and have no per-corner meaning, so
    ``klt sim`` cannot grade them (``grid_problems`` re-applies them to the
    collected report). ``None`` when the entry carries neither bound."""
    limits = {key: check[key] for key in ("min", "max") if check.get(key) is not None}
    return limits or None


def tag_measurements(
    entries: list[dict], tb: Testbench, spec_rows: dict[str, str] | None = None
) -> list[dict]:
    """``entries`` with each measurement's harness ``limits`` and ``spec_row``.

    ``tb.checks`` supplies ``limits`` (see :func:`limits_of`); ``spec_rows``
    maps a measurement name to the spec row it grades and is emitted as the
    measurement's ``spec_row``, from which ``klt signoff`` derives which
    rows a passing envelope covers. A check or a row tag naming no translated
    measurement, and a row tag naming an unchecked measurement (a tag
    without ``limits`` grades nothing), are refused here: each would
    silently drop a row from the envelope's coverage.
    """
    spec_rows = spec_rows or {}
    known = {entry["name"] for entry in entries}
    for name in tb.checks:
        if name not in known:
            raise EnvelopeError(f"{tb.name}: check {name!r} names no measurement")
    for name in spec_rows:
        if name not in known:
            raise EnvelopeError(
                f"{tb.name}: spec row tag names no measurement: {name!r}"
            )
        if limits_of(tb.checks.get(name) or {}) is None:
            raise EnvelopeError(
                f"{tb.name}: spec row tag on unchecked measurement {name!r} "
                "(a tag without limits grades nothing)"
            )
    out = []
    for entry in entries:
        tagged = dict(entry)
        limits = limits_of(tb.checks.get(entry["name"]) or {})
        if limits is not None:
            tagged["limits"] = limits
        if entry["name"] in spec_rows:
            tagged["spec_row"] = spec_rows[entry["name"]]
        out.append(tagged)
    return out


def grid_points(tb: Testbench, rate: float | None = None, *, slice_rate: bool = False) -> list[PvtPoint]:
    """The bench's mandated grid in harness order -- the same points
    ``sim/run_corners.py`` runs for the bench's Markdown records. With
    ``slice_rate`` only the ``rate`` slice (every process corner,
    temperature and supply at that bit rate) is returned."""
    rates = [rate] if slice_rate else (list(tb.rates_mbps) or None)
    if slice_rate and rate not in rates_of(tb):
        raise EnvelopeError(f"{tb.name}: {rate!r} is not one of its declared rates")
    return build_grid(
        resolve_corners(list(tb.corners)),
        list(tb.temperatures_c),
        supply_points(tb.nominal_supply_v, tb.supply_tolerance),
        rates,
    )


def corners_block(tb: Testbench, rate: float | None = None, *, slice_rate: bool = False) -> dict:
    """The request's ``corners`` block: process bundles, temperatures, and
    the (supply, rate) rows as one zipped ``params`` axis -- supply outer,
    rate inner, the harness's own grid order. With ``slice_rate`` the rows
    cover only ``rate``."""
    for name in (SUPPLY_PARAM, RATE_PARAM, TEMP_PARAM):
        if name in tb.params:
            raise EnvelopeError(
                f"{tb.name}: manifest 'params' already defines the swept parameter {name!r}"
            )
    rates = [rate] if slice_rate else rates_of(tb)
    rows = list(
        itertools.product(
            supply_points(tb.nominal_supply_v, tb.supply_tolerance), rates
        )
    )
    params = {SUPPLY_PARAM: [row[0] for row in rows]}
    if tb.rates_mbps:
        params[RATE_PARAM] = [row[1] for row in rows]
    return {
        "process": [
            {"name": corner.name, "sections": list(corner.sections)}
            for corner in resolve_corners(list(tb.corners))
        ],
        "temperature_c": [float(t) for t in tb.temperatures_c],
        "params": params,
        # The harness hands every deck `.param temp_c=<T>`; bind it to the
        # grid's temperature so an envelope deck carries the same parameter.
        "temperature_param": TEMP_PARAM,
    }


def _relative_to(path: Path, directory: Path) -> str:
    """A portable forward-slash relative path from ``directory`` to ``path``."""
    return os.path.relpath(path.resolve(), directory.resolve()).replace(os.sep, "/")


def compose_body(tb: Testbench, body_dir: Path, rate: float | None = None, *, slice_rate: bool = False) -> str:
    """The circuit body for ``tb``, with ``.include`` paths relative to
    ``body_dir`` (the directory the body will live in -- ngspice and every
    ``klt sim`` backend resolve a relative include beside the netlist).

    The ``.param`` block carries the nominal supply (and the first declared
    rate, or the sliced rate) as the defaults each corner overrides; the
    options block is the harness's own, so an envelope deck and the harness
    deck cannot drift into describing different circuits.
    """
    if tb.dut is None:
        raise EnvelopeError(f"{tb.name}: an envelope request needs the manifest's 'dut'")
    grid = grid_points(tb, rate, slice_rate=slice_rate)
    supplies = supply_points(tb.nominal_supply_v, tb.supply_tolerance)
    rates = [rate] if slice_rate else rates_of(tb)
    nominal = PvtPoint(
        corner=grid[0].corner,
        temp_c=float(tb.temperatures_c[0]),
        vdd=tb.nominal_supply_v,
        rate_mbps=rates[0],
    )
    dut_rel = _relative_to(tb.dut, body_dir)
    netlist_rel = _relative_to(tb.netlist, body_dir)
    analysis = analysis_for(tb, rates[0] if slice_rate else None)
    grid_note = (
        f" = {len(grid)} corners at {rate:g} Mbps/lane (one rate slice),"
        if slice_rate
        else f" x {len(rates)} rates = {len(grid)} corners,"
    )
    default_note = "the rate above" if slice_rate else "the first declared rate"
    lines = [
        f"* {tb.name} -- whole-grid klt sim body (T1 item 5 envelope)",
        f"* GENERATED by sim/run_envelope.py from {tb.experiment}/testbench/tb.json, do not edit",
        f"* grid: {len(resolve_corners(list(tb.corners)))} process corners x"
        f" {len(tb.temperatures_c)} temperatures x {len(supplies)} supplies" + grid_note,
        "* swept in the request JSON (corners.process / temperature_c / params) over this one",
        "* body; the .param lines below are the defaults each corner overrides with",
        f"* alterparam (nominal supply, {default_note}, first declared temperature).",
        f"* analysis  : {analysis[0]} {analysis[1]}"
        + ("" if analysis == analysis_of(tb) else " (TRANSIENT_WINDOWS override of the manifest's window)"),
        f"* DUT       : {dut_rel} ({tb.dut_provenance_class}, sha256 {tb.dut_sha256})",
        f"* testbench : {netlist_rel} (sha256 {tb.netlist_sha256})",
    ]
    lines += _param_lines(tb, nominal)
    lines += _option_lines(tb)
    lines.append(f'.include "{dut_rel}"')
    lines.append(f'.include "{netlist_rel}"')
    return "\n".join(lines) + "\n"


def build_request(
    tb: Testbench,
    body_name: str,
    *,
    spec_rows: dict[str, str] | None = None,
    timeout_s: int = TIMEOUT_S,
    rate: float | None = None,
    slice_rate: bool = False,
) -> dict:
    """The ``klt sim`` request document for ``tb``'s grid (or its ``rate``
    slice) over the body file ``body_name`` (resolved by ``klt sim`` beside
    the request)."""
    per_rate = tb.experiment in TRANSIENT_WINDOWS
    if per_rate and not slice_rate:
        raise EnvelopeError(
            f"{tb.name}: this bench has per-rate transient windows; build one"
            " request per rate (rate=..., slice_rate=True)"
        )
    if slice_rate and not per_rate:
        raise EnvelopeError(f"{tb.name}: single-request bench; there is no rate slice to build")
    kind, args = analysis_for(tb, rate if slice_rate else None)
    return {
        "netlist": body_name,
        "engine": "ngspice",
        "backend": "batch",
        "models": {
            "pdk": PDK_VARIANT,
            "lib": MODELS_LIB,
            "param_file": MODELS_PARAM_FILE,
        },
        "corners": corners_block(tb, rate, slice_rate=slice_rate),
        "analysis": {"kind": kind, "args": args},
        "measurements": tag_measurements(translate_measurements(tb), tb, spec_rows),
        "options": {
            "timeout_s": timeout_s,
            # Artifacts name the collecting host's scratch directory; the
            # committed envelope stays free of it (debug a failing corner
            # with a separate keep_artifacts run).
            "keep_artifacts": False,
            "ngspice_init": list(NGSPICE_INIT),
        },
        "batch": {
            "capacity_wait_s": CAPACITY_WAIT_S,
            "job_ceiling_check": "split",
        },
        "netlist_source": "schematic",
    }


def report_points(report: dict, tb: Testbench) -> list[PointResult]:
    """``report``'s corner entries as harness results, in report order.

    Each corner's process, temperature and ``params`` echo map back onto the
    bench's :class:`PvtPoint`; a corner's status is ``ok`` only when ``klt
    sim`` passed it and it reports every measurement of the bench."""
    results = []
    for entry in report.get("corners") or []:
        name = str(entry.get("process") or "")
        if name not in CORNERS:
            raise EnvelopeError(
                f"corner {entry.get('corner_id')!r}: unknown process corner {name!r}"
            )
        params = entry.get("params") or {}
        rate = params.get(RATE_PARAM)
        point = PvtPoint(
            corner=CORNERS[name],
            temp_c=float(entry.get("temperature_c")),
            vdd=float(params[SUPPLY_PARAM]),
            rate_mbps=float(rate) if rate is not None else None,
        )
        values = {}
        for m in entry.get("measurements") or []:
            value = m.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[m.get("name")] = float(value)
        missing = [n for n in tb.measure if n not in values]
        status = "ok" if entry.get("status") == "pass" and not missing else "error"
        results.append(
            PointResult(
                point=point,
                status=status,
                measurements=values,
                missing=missing,
                seconds=float(entry.get("runtime_s") or 0.0),
                message="; ".join(
                    str(d.get("message") or d.get("code")) for d in (entry.get("diagnostics") or [])[:3]
                ),
                backend="batch",
            )
        )
    return results


def _report_grid(report: dict, tb: Testbench, rate: float | None) -> tuple[list[str], list[PointResult]]:
    """Map one report onto exactly the grid its request declared."""
    problems: list[str] = []
    if report.get("status") != "pass":
        problems.append(f"klt sim status {report.get('status')!r}, not 'pass'")
    try:
        results = report_points(report, tb)
    except (EnvelopeError, KeyError, TypeError, ValueError) as exc:
        return problems + [f"a corner entry does not map onto the bench grid: {exc}"], []
    expected = [p.corner_id for p in grid_points(tb, rate, slice_rate=rate is not None)]
    counts = Counter(r.point.corner_id for r in results)
    grid = [
        f"point {cid}: {counts[cid]} report entries, expected exactly 1"
        for cid in expected
        if counts[cid] != 1
    ] + [f"unexpected point {cid}" for cid in sorted(set(counts) - set(expected))]
    if grid:
        return problems + grid, []
    by_id = {r.point.corner_id: r for r in results}
    ordered = [by_id[cid] for cid in expected]
    problems += [
        f"corner {r.point.corner_id}: klt sim status not 'pass'"
        + (f" ({r.message})" if r.message else "")
        for r in ordered
        if r.status != "ok"
    ]
    return problems, ordered


def grid_problems(reports: list[tuple[float | None, dict]], tb: Testbench) -> list[str]:
    """Verify the complete bench, including checks that span rate slices.

    Each pair names the request's rate (None for an unsliced request) and
    its collected report. Check each report against its own grid before
    applying the bench checks to the union of the measured points.
    """
    expected = list(tb.rates_mbps) if tb.experiment in TRANSIENT_WINDOWS else [None]
    counts = Counter(rate for rate, _ in reports)
    problems = [
        f"rate {rate}: {counts[rate]} reports, expected exactly 1"
        for rate in expected if counts[rate] != 1
    ]
    points = []
    for rate, report in reports:
        if rate not in expected:
            problems.append(f"unexpected report rate {rate!r}")
            continue
        errors, ordered = _report_grid(report, tb, rate)
        problems.extend(errors)
        points.extend(ordered)
    if problems:
        return problems
    summary = summarize(points, list(tb.measure))
    return [
        f"check {f['measurement']} {f['kind']}: observed {f['value']!r} at {f['at']} "
        f"(limit {f['limit']!r})"
        for f in evaluate_checks(tb.checks, points, summary)
    ]
