#!/usr/bin/env python3
"""Generate the ``klt pex`` testbench requests under ``sim/pex/requests/``.

``klt pex <layout> <testbench>...`` re-runs ``klt sim`` request JSON files
unmodified on a schematic leg and an extracted leg, swapping only each
body's single DUT ``.include`` for the freshly extracted netlist (issue
#371; the testbench half of #230's T1 item 7 evidence, prepared while the
#230 -> #222 -> #299 -> klayout-tools#5593 batch chain is parked). This
generator derives those requests from the *existing* eye-bench definitions
-- ``sim/harness``'s parameter/option helpers and the two benches' manifests
and netlist fragments -- rather than hand-copying them, so a bench edit
flows into the pex requests with one regen:

    python3 sim/pex/gen_requests.py            # (re)write requests + bodies
    python3 sim/pex/gen_requests.py --check    # offline freshness check

``--check`` needs no PDK and no network (run by ``npm run lint`` via
``.github/scripts/lint.sh``, beside the assembly-DUT freshness check): it
regenerates everything in memory, diffs it byte-for-byte against what is
committed, and re-asserts the structural contracts ``klt pex`` holds.

## What it emits, per source bench (sim/cml-driver-eye, sim/cml-driver-eye-mask)

One request per (supply, rate) pair of the bench's mandated axes -- 3
supplies x 2 rates = 6 requests per bench, 12 total, each sweeping the
bench's own process corner set x temperature axis inside the request
(5 x 3 = 15 units; 90 units per bench, the full mandated matrix). The
supply and rate are *baked into the body* as ``.param vdd_val=...`` /
``.param rate_val=...`` -- exactly what ``sim/harness/batch.compose_body``
does per PVT point -- rather than swept with ``corners.params``/
``alterparam``, because these benches' PWL stimuli expand ``{tbit_s}``-
style parameter expressions at deck-parse time: an ``alterparam``+``reset``
cannot re-time them. One body per request, committed beside the requests
under ``requests/bodies/``.

Each body carries:

- the bench's ``.param`` block and ``.options`` (from ``sim/harness.runner``'s
  shared assembly helpers, so the pex body and the harness deck cannot drift
  into describing different circuits; the harness's per-point ``temp_c``
  param is dropped -- temperature is a request axis here, ``klt sim`` emits
  ``.temp`` per corner, and no bench fragment reads the ``temp_c`` param);
- **exactly one** ``.include``/``.inc`` line -- the schematic assembly DUT
  ``sim/pex/gf180_tmds_pad_ring_assembly.spice`` (``klt pex``'s hard rule:
  the PDK parameter file must NOT be a second include; it moves to the
  request's ``models.param_file``). The path is relative to the body's own
  directory, which is how ngspice and every ``klt sim`` backend resolve a
  relative include;
- the shared six-pin ``cml_driver`` adapter (ideal ``vvdd_rail`` on the
  assembly's VDD ring, same adapter as
  ``layout/sim/gf180_tmds_pad_ring_assembly_dut.spice``), in the *body*
  because ``klt pex`` swaps only the DUT include: both legs must share the
  wrapper. It wires the assembly in the DUT's declared seven-pin order,
  positionally;
- the bench's netlist fragment, inlined verbatim.

And each request sets ``models.pdk``/``models.lib``/``models.param_file``
(the PDK design include as a request field, both legs get it), the bench's
process corner bundles and temperatures, its transient analysis, and its
``measure`` map translated into ``klt sim`` measurement entries -- see
``_translate_measurements`` for the dependency rules.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness.corners import CORNER_SETS, CORNERS, PvtPoint, resolve_corners, supply_points  # noqa: E402
from harness.klt_envelope import EnvelopeError, translate_measurements as _translate  # noqa: E402
from harness.runner import DEFAULT_TIMEOUT_S, _option_lines, _param_lines  # noqa: E402
from harness.testbench import load as load_testbench  # noqa: E402

PEX_DIR = SIM_DIR / "pex"
REQUESTS_DIR = PEX_DIR / "requests"
BODIES_DIR = REQUESTS_DIR / "bodies"

#: The schematic assembly DUT (issue #371 step 1). Its ``.SUBCKT`` header
#: must declare exactly this pin list, in this order: it is the order
#: ``klt extract --pins IBIAS,INN,INP,OUTN,OUTP,VDD,VSS`` writes, and the
#: order the shared wrapper wires positionally. A same-count permutation of
#: either side is a hard ``--check`` failure (and a ``klt pex``
#: ``pin_order_mismatch`` at run time).
DUT_FILE = PEX_DIR / "gf180_tmds_pad_ring_assembly.spice"
EXPECTED_PINS = ["IBIAS", "INN", "INP", "OUTN", "OUTP", "VDD", "VSS"]
DUT_SUBCKT = "gf180_tmds_pad_ring_assembly"

#: The benches whose rows the pex requests cover (DR-0013 rows 1, 2, 4, 5,
#: 6, 8, 9 -- see sim/pex/README.md's coverage table).
BENCHES = ("cml-driver-eye", "cml-driver-eye-mask")

#: DR-0010 pins the PDK variant for this block; committed requests must not
#: depend on which PDK install happened to generate them.
PDK_VARIANT = "gf180mcuD"
MODELS_LIB = "libs.tech/ngspice/sm141064.ngspice"
MODELS_PARAM_FILE = "libs.tech/ngspice/design.ngspice"

#: Host rule: every batch ``klt sim`` request carries a capacity wait.
CAPACITY_WAIT_S = 600

#: The bench manifests declare ``reltol=1e-06`` for the harness's own
#: records. The pex bodies deliberately override it with ngspice's own
#: default (1e-3): with 1e-6, every Linux ngspice build tested (42 apt,
#: 47 -- both this host's and the batch fleet's) collapses the transient
#: at the bench's FIRST stimulus edge (t = 9*tbit_s, "timestep too small"
#: on an ideal-source branch of one of the static DC copies) once the DUT
#: is the assembly -- the extra wrapper hierarchy is the trigger; the same
#: deck with the original flat 6-pin DUT converges at 1e-6, and macOS
#: builds converged the extracted assembly at 1e-6 (the 2026-09-05 eye
#: records). 1e-4 and 1e-5 still collapse; 1e-3 completes on ngspice 42
#: and 47. Both pex legs share this body byte-identically, so the
#: schematic-vs-extracted delta is unaffected, and the numbers stay sane:
#: swing_c0 = 0.5065 V at 1e-3 vs 0.5066 V at 1e-6 (flat DUT). The
#: harness's 1e-6 remains authoritative for its own records.
PEX_RELTOL = "1e-3"

#: The PDK's ngspice models bin on per-finger width (W/NF): the driver's
#: W=128u nf=64 devices (2 u/finger) only resolve a model bin when ngspice's
#: ``wnflag`` is 1 (distro builds set it via ``ngbehavior=hsa``; a bare build
#: does not, and the deck dies with "could not find a valid modelname" --
#: observed on the batch fleet's /usr/local/bin/ngspice-47, which reads no
#: ambient init). Declaring it here makes each request self-contained on
#: every backend (``options.ngspice_init`` REPLACES any $HOME/.spiceinit, so
#: the lines must be complete -- ``num_threads=1`` pins the same
#: single-threaded determinism this repo's host init files pin), and the
#: report's ``environment.ngspice_init`` records what was actually read.
NGSPICE_INIT = ("set wnflag=1", "set num_threads=1")

#: Each request sweeps 15 units (5 process corners x 3 temperatures). The
#: batch fleet's whole-job ceiling is 3600 s and a job's bound is
#: ``options.timeout_s`` x units + 120 s, so an unsplit 15-unit job bounds
#: at 4620 s and is refused/warned (``klt pex --dry-run`` says so). 11
#: units x 300 s + 120 s = 3420 s fits; ``klt sim`` splits the unit list
#: into jobs of at most this many units.
MAX_UNITS_PER_JOB = 11

#: Hierarchical-node translation through the shared wrapper. The eye bench's
#: device-stress probes read the ``xvhi`` copy's tail node, which the
#: schematic DUT exposes one level deeper than the old flat ``cml_driver``
#: fragment: inside the wrapper's ``xcore`` instance of the assembly. The
#: extracted leg resolves the same path -- the seven-pin extraction keeps a
#: plain ``TAIL`` star-hub node (``RTAIL_t<n> TAIL__t<n> TAIL``), so
#: ``xvhi.xcore.tail`` exists on BOTH legs and the row 8 probes survive.
NODE_REWRITES = (("xvhi.tail", "xvhi.xcore.tail"),)

_INCLUDE_RE = re.compile(r"^\s*\.inc(lude)?\b", re.IGNORECASE)
_SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)


def _dut_pins(dut_text: str) -> list[str]:
    """Parse the DUT's ``.SUBCKT <name> <pins...>`` header pin list."""
    for line in dut_text.splitlines():
        match = _SUBCKT_RE.match(line.strip())
        if match:
            if match.group(1).lower() != DUT_SUBCKT.lower():
                continue
            return match.group(2).split()
    raise SystemExit(f"{DUT_FILE.name}: no .SUBCKT {DUT_SUBCKT} header found")


def _wrapper_block(dut_rel: str) -> list[str]:
    """The shared six-pin adapter, wiring the assembly in pin order.

    Emitted into every body (``klt pex`` swaps only the DUT include, so the
    wrapper must live where both legs share it byte-identically).
    """
    return [
        "* ---- shared DUT adapter (identical on both pex legs) ---------------",
        "* The assembly's seven-pin boundary adapted to the six-pin `cml_driver`",
        "* interface the eye benches instantiate. The X line below wires the",
        f"* assembly POSITIONALLY in the DUT's declared pin order ({' '.join(EXPECTED_PINS)})",
        "* -- sim/pex/gen_requests.py --check asserts that order against the",
        "* DUT header, so a same-count permutation fails the lint, and klt pex",
        "* itself refuses a pin-order mismatch against the extraction.",
        "* The assembly's VDD ring net (VDD-side clamp cathodes + Nwell tap) is",
        "* held at the testbench core rail vdd_val by an ideal source inside the",
        "* wrapper, since the six-pin boundary has no VDD pin -- the same adapter",
        "* layout/sim/gf180_tmds_pad_ring_assembly_dut.spice documents.",
        ".subckt cml_driver OUTP OUTN INP INN IBIAS VSS",
        "vvdd_rail VDD 0 dc {vdd_val}",
        f"xcore {' '.join(EXPECTED_PINS)} {DUT_SUBCKT}",
        ".ends",
    ]


def _translate_measurements(tb) -> list[dict]:
    """The bench's ``measure`` map as ``klt sim`` measurement entries --
    ``harness.klt_envelope.translate_measurements`` (raw ``.meas`` cards,
    then ``PARAM`` cards over raw-card results, then dependency-ordered
    ``expr`` entries) with this generator's wrapper node rewrites. A
    ``SystemExit``, like every other generation failure here."""
    try:
        return _translate(tb, node_rewrites=NODE_REWRITES)
    except EnvelopeError as exc:
        raise SystemExit(str(exc)) from exc


def _compose_body(tb, vdd: float, rate: float, dut_rel: str) -> str:
    """One request body for (bench, supply, rate): harness param/options,
    the single DUT include, the shared wrapper, the inlined bench fragment.
    """
    point = PvtPoint(corner=CORNERS["tt"], temp_c=27.0, vdd=vdd, rate_mbps=rate)
    stem = f"{tb.name}_{vdd:g}v_{rate:g}mbps"
    lines = [
        f"* {stem} -- GENERATED by sim/pex/gen_requests.py, do not edit",
        f"* source bench : sim/{tb.name}/testbench (manifest + netlist fragment)",
        f"* baked point  : vdd_val={vdd:g} V  rate_val={rate:g} Mbps/lane",
        f"* corner grid  : {len(resolve_corners(list(tb.corners)))} process corners x"
        f" {len(tb.temperatures_c)} temperatures in the request JSON (supply and"
        " rate are baked here: the bench's PWL stimuli expand parameter"
        " expressions at deck-parse time, so they cannot be alterparam-swept)",
        f"* DUT          : {dut_rel} (schematic leg; klt pex swaps this one"
        " include for the extracted netlist on the extracted leg)",
    ]
    lines += [
        line
        for line in _param_lines(tb, point)
        if not line.startswith(".param temp_c=")
    ]
    # The bench's own reltol line is dropped and overridden below: see
    # PEX_RELTOL above for the full convergence matrix behind that.
    lines += [
        line
        for line in _option_lines(tb)
        if not line.lower().startswith(".options reltol")
    ]
    lines += [
        "* reltol: ngspice's default 1e-3, not this bench's 1e-6. With 1e-6 every",
        "* tested Linux ngspice build collapses the transient at the FIRST stimulus",
        "* edge (t = 9*tbit_s) once the DUT is this assembly (wrapper hierarchy);",
        "* 1e-4 and 1e-5 collapse too, 1e-3 completes (ngspice 42 and 47, local and",
        "* batch). Both pex legs share this body, so the schematic-vs-extracted",
        "* delta is unaffected; the harness's own 1e-6 records stay authoritative.",
        f".options reltol={PEX_RELTOL}",
    ]
    lines.append(f'.include "{dut_rel}"')
    lines += _wrapper_block(dut_rel)
    lines.append("")
    lines.append(f"* ---- {tb.name} netlist fragment, inlined verbatim --------------")
    fragment = tb.netlist.read_text().rstrip("\n")
    lines.append(fragment)
    return "\n".join(lines).rstrip("\n") + "\n"


def _build_request(tb, vdd: float, rate: float, measurements: list[dict]) -> dict:
    analysis = tb.analyses[0].split(None, 1)
    kind = analysis[0].lower()
    args = analysis[1] if len(analysis) > 1 else ""
    corners = resolve_corners(list(tb.corners))
    return {
        "netlist": None,  # filled by the caller, which knows the stem
        "engine": "ngspice",
        "backend": "batch",
        "models": {
            "pdk": PDK_VARIANT,
            "lib": MODELS_LIB,
            "param_file": MODELS_PARAM_FILE,
        },
        "corners": {
            "process": [
                {"name": corner.name, "sections": list(corner.sections)}
                for corner in corners
            ],
            "temperature_c": [float(t) for t in tb.temperatures_c],
        },
        "analysis": {"kind": kind, "args": args},
        "measurements": measurements,
        "options": {
            "timeout_s": DEFAULT_TIMEOUT_S,
            "keep_artifacts": True,
            "ngspice_init": list(NGSPICE_INIT),
        },
        "batch": {"capacity_wait_s": CAPACITY_WAIT_S, "max_units_per_job": MAX_UNITS_PER_JOB},
    }


def generate_all() -> dict[Path, str]:
    """Every generated file (path -> bytes-as-text), plus structural checks.

    The structural checks run at generation time too, so a regeneration that
    violates a ``klt pex`` contract fails loudly instead of committing a
    request #230 cannot use.
    """
    dut_text = DUT_FILE.read_text()
    pins = _dut_pins(dut_text)
    if pins != EXPECTED_PINS:
        raise SystemExit(
            f"{DUT_FILE.name}: .SUBCKT pins {pins} != expected {EXPECTED_PINS} "
            "(klt extract --pins writes this order; the wrapper wires it "
            "positionally -- fix the DUT header, not the expectation)"
        )

    files: dict[Path, str] = {}
    rates: dict[str, tuple[float, ...]] = {}
    for slug in BENCHES:
        tb = load_testbench(SIM_DIR / slug)
        if not tb.rates_mbps:
            raise SystemExit(f"{slug}: pex requests require a rate axis")
        rates[slug] = tb.rates_mbps
        measurements = _translate_measurements(tb)
        for vdd in supply_points(tb.nominal_supply_v, tb.supply_tolerance):
            for rate in tb.rates_mbps:
                stem = f"{tb.name}_{vdd:g}v_{rate:g}mbps"
                body_rel = f"bodies/{stem}.spice"
                dut_rel = os_rel(BODIES_DIR, DUT_FILE)
                body = _compose_body(tb, vdd, rate, dut_rel)
                request = _build_request(tb, vdd, rate, measurements)
                request["netlist"] = body_rel
                files[REQUESTS_DIR / f"{stem}.json"] = (
                    json.dumps(request, indent=2) + "\n"
                )
                files[BODIES_DIR / f"{stem}.spice"] = body

    _structural_checks(files, pins)
    return files


def os_rel(from_dir: Path, to_file: Path) -> str:
    """A portable forward-slash relative path from ``from_dir`` to ``to_file``."""
    return Path(os.path.relpath(to_file.resolve(), from_dir.resolve())).as_posix()


def _structural_checks(files: dict[Path, str], pins: list[str]) -> None:
    """The ``klt pex`` body contract, asserted on the generated set.

    - exactly one ``.include``/``.inc`` line per body, naming the schematic
      assembly DUT (resolved beside the body);
    - the wrapper's ``xcore`` X line wires the assembly positionally in the
      DUT's declared pin order -- the same-count-permutation guard;
    - every request names its own body, which exists in the generated set.
    """
    expected_x = f"xcore {' '.join(pins)} {DUT_SUBCKT}".lower()
    for path, text in files.items():
        if path.suffix != ".spice":
            continue
        includes = [
            line for line in text.splitlines() if _INCLUDE_RE.match(line)
        ]
        if len(includes) != 1:
            raise SystemExit(
                f"{path.name}: {len(includes)} .include/.inc lines (klt pex "
                "requires exactly one -- the DUT swap point)"
            )
        target = includes[0].split(None, 1)[1].strip().strip('"')
        resolved = (path.parent / target).resolve()
        if resolved != DUT_FILE.resolve():
            raise SystemExit(
                f"{path.name}: include target {target} does not resolve to "
                f"{DUT_FILE.name}"
            )
        if not any(
            line.strip().lower() == expected_x for line in text.splitlines()
        ):
            raise SystemExit(
                f"{path.name}: wrapper X line {expected_x!r} not found "
                "(pin order must match the DUT header positionally)"
            )
    for path, text in files.items():
        if path.suffix != ".json":
            continue
        request = json.loads(text)
        body = REQUESTS_DIR / request["netlist"]
        if body not in files:
            raise SystemExit(
                f"{path.name}: netlist {request['netlist']} has no generated body"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed files are current and structurally valid;"
        " change nothing (no PDK needed)",
    )
    args = parser.parse_args(argv)

    files = generate_all()

    if args.check:
        stale = 0
        for path, text in sorted(files.items()):
            rel = path.relative_to(REPO_ROOT)
            if not path.is_file():
                print(f"MISSING: {rel}")
                stale += 1
            elif path.read_text() != text:
                print(f"STALE:   {rel}")
                stale += 1
        for path in sorted(set(REQUESTS_DIR.glob("**/*")) - set(files)):
            if path.is_file():
                print(f"EXTRA:   {path.relative_to(REPO_ROOT)}")
                stale += 1
        if stale:
            print(
                f"FAIL: {stale} file(s) missing/stale/extra -- regenerate with:"
                " python3 sim/pex/gen_requests.py"
            )
            return 1
        print(
            f"PASS: {len(files)} generated pex request/body files current"
            f" ({len(BENCHES)} benches, structural checks clean)."
        )
        return 0

    for path, text in sorted(files.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(f"wrote {len(files)} files under {REQUESTS_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
