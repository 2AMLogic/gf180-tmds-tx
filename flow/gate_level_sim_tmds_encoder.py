#!/usr/bin/env python3
"""Post-layout, SDF-back-annotated gate-level re-simulation for `tmds_encoder`
(issue #85).

Re-runs the *exact same, unmodified* cocotb testbench
(`verification/tmds_encoder/test_tmds_encoder.py`) that already verifies
`rtl/tmds_encoder.v` -- this time against the synthesized gate-level netlist
issue #82 produced (`flow/tmds_encoder/netlist/tmds_encoder.synth.v`) with
real per-cell and per-net delays back-annotated from the SDF issue #85's own
`flow/sdf_tmds_encoder.py` extracted (`flow/tmds_encoder/sta/tmds_encoder.sdf`),
via Icarus Verilog's `$sdf_annotate`. Same "same unmodified test module, only
the DUT source differs" principle `verification/tmds_encoder/runner.py`
already uses for Leg 1/2 (RTL) vs. Leg 3 (negative control) -- this is a
fourth DUT variant of that same bench, not a new bench.

The synthesized netlist is logically unchanged by place-and-route (#84's own
evidence record: P&R inserts only non-logic-bearing filler/tap/endcap cells,
confirmed by LVS finding zero *logic* mismatches -- only 10
utility-cell-type mismatches, all of them exactly those non-logic cells) --
so `tmds_encoder.synth.v`, timing-annotated with the *post-route* SDF, is a
faithful post-layout gate-level model, without needing a separate physical
netlist extraction step.

## Two Icarus Verilog 13.0 limitations, worked around mechanically here

Both are disclosed in this module's own evidence record, not silently
patched around:

1. **`ifnone` combined with an edge-sensitive specify path is unsupported**
   (`sorry: ifnone with an edge-sensitive path is not supported`). The
   gf180mcu vendor Verilog cell library encodes *all* of some cells' timing
   arcs (e.g. every arc in `xor2_1`/`xor3_1`/`xnor2_1`/`xnor3_1`, this
   design's own dominant cell types) exclusively via
   `ifnone \n (posedge/negedge SRC => (DST:SRC)) = (...);` state-dependent
   path statements -- there is no non-`ifnone` fallback arc to fall back on
   for those pins. `rewrite_ifnone_edge_paths` below rewrites each such
   statement (once per unique (SRC, DST) pin pair, keeping the first-seen
   placeholder delay pair and dropping duplicates) into a plain,
   unconditional, non-edge module path `(SRC => DST) = (...);`. This changes
   only how Icarus parses the *declaration* of the timing arc; the numeric
   placeholder values in the vendor file are themselves generic stand-ins
   (every arc in this deck uses the same literal `(1.0,1.0)`) that
   `$sdf_annotate` overwrites from the real SDF by matching declared
   (source => dest) path names -- so only the *existence* of a same-named
   path for the annotator to bind to matters, not this rewrite's own
   placeholder numbers or the edge-qualifier it drops.
2. **`-ginterconnect` could not be made to resolve net paths for this
   plain-`wire` design** (`Error: Could not find net. Did you run iverilog
   with '-ginterconnect'?` even *with* that flag passed) -- SystemVerilog
   `interconnect`-typed nets appear to be what that flag's net resolution
   expects, which this Verilog-2005 design does not use. Since
   `flow/sdf_tmds_encoder.py`'s own evidence record independently confirms
   every extracted net-interconnect delay in this design's SDF is 0.000 ns
   (compact ~158 x 138 um die), `strip_top_level_interconnect` below drops
   the SDF's module-level net-interconnect delay section before feeding it
   to `$sdf_annotate`; every per-cell IOPATH delay (which dominates this
   design's timing entirely -- see the worst-case combinational delay this
   module's own evidence record cites) is preserved unmodified.

## Only the cell types this design actually instantiates are compiled

`build_filtered_library` extracts the transitive closure of vendor-library
modules this design's 27 distinct standard-cell types need (each
`_1`-suffixed cell instantiates its own `_func` submodule) via the vendor
file's own per-cell `` `ifndef ..._V``/`` `endif`` header guards, rather than
compiling all ~300 cells in the full library -- smaller compile, and (a
secondary benefit) avoids reset/preset-flop cell types this design never
instantiates whose specify blocks carry unrelated Icarus-unsupported
constructs.

## Test clock period: not an operating-frequency claim

`CLOCK_PERIOD_NS` below (50 ns, i.e. 20 MHz) is deliberately far slower than
the RTL/negative-control legs' 10 ns default (`verification/tmds_encoder/
test_tmds_encoder.py`'s `CLOCK_PERIOD_NS`, itself unconstrained by any
timing analysis). It exists only so this leg's functional-equivalence check
is meaningful under *real* back-annotated delays: this design's own SDF
evidence record measured a 13.27 ns worst-case unconstrained
input-to-register combinational delay for the DR-0008 single-register
netlist, and 5.18 ns for the DR-0009 four-stage netlist this driver now
runs against (down from the pre-pipeline 18.30 ns issue #85
originally measured -- `report_checks -unconstrained`, no clock/SDC applied
-- see `flow/sdf_tmds_encoder.py`). Icarus does not support SDF
`TIMINGCHECK` enforcement (`$setup`/`$hold` -- see this module's own
evidence record's "Known limitations"), so a too-tight period would not
show as a hard X-propagating violation the way a full SDF-aware simulator's
`notifier`-driven X-forcing would -- it would instead silently *pass* with
stale data. 50 ns gives ample margin over the observed worst case,
comfortably covering setup + the dropped interconnect delays (confirmed
0.000 ns, see above) and Icarus's own unenforced hold requirements. This is
the same "mechanical convenience, not a verified operating frequency"
disclaimer `flow/pnr_tmds_encoder.py`'s own one `create_clock` already
carries -- any operating-frequency claim is issue #83's (STA) job, not this
one's.

Cold-start invocation (from a clean checkout, PDK installed -- see
sim/README.md "PDK variant"; requires `flow/sdf_tmds_encoder.py` (issue #85)
and `flow/pnr_tmds_encoder.py` (issue #84) to have already been run, i.e.
their committed outputs -- `flow/tmds_encoder/sta/tmds_encoder.sdf` and
`flow/tmds_encoder/netlist/tmds_encoder.synth.v` -- to already exist; no PDK
tool is invoked directly by this script beyond locating the cell-library
Verilog models):

    python3 flow/gate_level_sim_tmds_encoder.py

Not run in CI, for the same reason `flow/synth_tmds_encoder.py` and
`flow/pnr_tmds_encoder.py` are not: it needs the multi-GB gf180mcu PDK (for
the vendor cell-library Verilog models), which should not gate every PR --
see `flow/README.md`'s "CI" section.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "flow"))
VERIFICATION_DIR = REPO_ROOT / "verification" / "tmds_encoder"
sys.path.insert(0, str(VERIFICATION_DIR))

from sim.harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402
import synth_tmds_encoder as synth  # noqa: E402  (reuses record_id/_git/working_tree_dirty)
import pnr_tmds_encoder as pnr  # noqa: E402  (reuses STD_CELL_LIB/CORNER)

TOP = "tmds_encoder"

NETLIST_PATH = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / "tmds_encoder.synth.v"
SDF_PATH = REPO_ROOT / "flow" / "tmds_encoder" / "sta" / "tmds_encoder.sdf"
PNR_RECORD_ID = "20260817-105608-049c240"  # issue #115's four-stage (DR-0009) P&R record, cited below

OUT_DIR = REPO_ROOT / "flow" / "tmds_encoder"
REPORTS_DIR = OUT_DIR / "reports"
RECORDS_DIR = OUT_DIR / "records"
BUILD_DIR = REPO_ROOT / "flow" / "build" / "gate_level_sim"

CLOCK_PERIOD_NS = 50  # see this module's docstring, "Test clock period"

_CELL_TYPE_RE = re.compile(r"\bgf180mcu_fd_sc_mcu9t5v0__[a-z0-9_]+\b")
_GUARD_BLOCK_RE = re.compile(
    r"^`ifndef (GF180MCU_FD_SC_MCU9T5V0__\w+_V)\n(.*?)\n`endif // \1\n",
    re.MULTILINE | re.DOTALL,
)
_MODULE_REF_RE = re.compile(r"\b(gf180mcu_fd_sc_mcu9t5v0__[a-z0-9_]+)\s+\S+\s*\(")
_IFNONE_EDGE_RE = re.compile(
    r"\tifnone\n\t// comb arc (?:posedge|negedge)[^\n]*\n"
    r"\t\s*\((?:posedge|negedge)\s+(\w+)\s*=>\s*\((\w+)(?::\w+)?\)\)\s*=\s*(\([^;]*\));\n\n?"
)
_TOP_INTERCONNECT_CELL_RE = re.compile(
    r"\n \(CELL\n  \(CELLTYPE \"" + TOP + r"\"\)\n(?:.*?\n)*?  \)\n \)\n"
)


class GateLevelSimError(RuntimeError):
    pass


def used_cell_types(netlist_text: str) -> set[str]:
    return set(_CELL_TYPE_RE.findall(netlist_text))


def guard_for(cell_type: str) -> str:
    return f"GF180MCU_FD_SC_MCU9T5V0__{cell_type[len('gf180mcu_fd_sc_mcu9t5v0__'):].upper()}_V"


def guarded_blocks(lib_text: str) -> dict[str, str]:
    return {m.group(1): m.group(0) for m in _GUARD_BLOCK_RE.finditer(lib_text)}


def transitive_closure(used_types: set[str], blocks: dict[str, str]) -> list[str]:
    """Every guard needed to compile `used_types`, plus every vendor-file
    module type those blocks themselves instantiate (each `_1` wrapper cell
    instantiates its own `_func` submodule)."""
    needed: set[str] = set()
    worklist = [guard_for(t) for t in used_types]
    while worklist:
        g = worklist.pop()
        if g in needed:
            continue
        if g not in blocks:
            raise GateLevelSimError(f"no vendor-library block found for guard {g}")
        needed.add(g)
        for ref in set(_MODULE_REF_RE.findall(blocks[g])):
            rg = guard_for(ref)
            if rg not in needed:
                worklist.append(rg)
    return sorted(needed)


def rewrite_ifnone_edge_paths(text: str) -> tuple[str, int]:
    """See this module's docstring, limitation 1."""
    out: list[str] = []
    pos = 0
    n = 0
    for m in _IFNONE_EDGE_RE.finditer(text):
        out.append(text[pos : m.start()])
        pos = m.end()
        # Deduplicate within this call's overall output stream is handled by
        # the caller re-invoking per-block; here we just rewrite in place.
        src, dst, val = m.group(1), m.group(2), m.group(3)
        out.append(f"\t({src} => {dst}) = {val};\n\n")
        n += 1
    out.append(text[pos:])
    return "".join(out), n


def dedupe_module_paths(block_text: str) -> str:
    """Drop a rewritten `(SRC => DST) = (...);` statement if an identical
    (SRC, DST) pair already appears earlier in the same specify block
    (posedge/negedge entries for the same pin pair both rewrite to the same
    unconditional path -- see this module's docstring, limitation 1)."""
    seen: set[tuple[str, str]] = set()
    lines = block_text.split("\n")
    out_lines = []
    pair_re = re.compile(r"^\t\((\w+) => (\w+)\) = \([^;]*\);$")
    for line in lines:
        m = pair_re.match(line)
        if m:
            key = (m.group(1), m.group(2))
            if key in seen:
                continue
            seen.add(key)
        out_lines.append(line)
    return "\n".join(out_lines)


def build_filtered_library(pdk: Pdk, netlist_text: str) -> Path:
    lib_path = (
        pdk.path / "libs.ref" / pnr.STD_CELL_LIB / "verilog" / f"{pnr.STD_CELL_LIB}.v"
    )
    if not lib_path.is_file():
        raise GateLevelSimError(f"expected gf180mcu vendor Verilog library not found: {lib_path}")

    lib_text = lib_path.read_text()
    blocks = guarded_blocks(lib_text)
    if not blocks:
        raise GateLevelSimError(f"found no guarded cell blocks in {lib_path}")

    needed = transitive_closure(used_cell_types(netlist_text), blocks)

    out_blocks = []
    total_rewritten = 0
    for g in needed:
        rewritten, n = rewrite_ifnone_edge_paths(blocks[g])
        rewritten = dedupe_module_paths(rewritten)
        out_blocks.append(rewritten)
        total_rewritten += n

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BUILD_DIR / f"{pnr.STD_CELL_LIB}.gate_level_filtered.v"
    out_path.write_text("\n".join(out_blocks))
    print(
        f"Filtered vendor library: {len(needed)} of {len(blocks)} cell blocks compiled "
        f"({total_rewritten} ifnone-edge specify entries rewritten -- see this module's "
        "docstring, limitation 1)"
    )
    return out_path


def primitives_path(pdk: Pdk) -> Path:
    p = pdk.path / "libs.ref" / pnr.STD_CELL_LIB / "verilog" / "primitives.v"
    if not p.is_file():
        raise GateLevelSimError(f"expected gf180mcu vendor primitives.v not found: {p}")
    return p


def strip_top_level_interconnect(sdf_text: str) -> tuple[str, bool]:
    """See this module's docstring, limitation 2."""
    new_text, n = _TOP_INTERCONNECT_CELL_RE.subn("\n", sdf_text)
    return new_text, n > 0


def build_stripped_sdf() -> Path:
    if not SDF_PATH.is_file():
        raise GateLevelSimError(
            f"SDF not found at {SDF_PATH} -- run flow/sdf_tmds_encoder.py (issue #85) first"
        )
    sdf_text = SDF_PATH.read_text()
    stripped, stripped_ok = strip_top_level_interconnect(sdf_text)
    if not stripped_ok:
        raise GateLevelSimError(
            f"expected a top-level '{TOP}' module-interconnect CELL block in {SDF_PATH}, found none"
        )
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BUILD_DIR / "tmds_encoder.gate_level.sdf"
    out_path.write_text(stripped)
    return out_path


def write_sdf_loader(stripped_sdf_path: Path) -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    loader_path = BUILD_DIR / "sdf_loader.v"
    loader_path.write_text(
        f'module sdf_loader;\n  initial $sdf_annotate("{stripped_sdf_path}", {TOP});\nendmodule\n'
    )
    return loader_path


def run_gate_level_sim(pdk: Pdk, build_log_path: Path, test_log_path: Path) -> tuple[int, int]:
    from cocotb_tools.runner import get_results, get_runner

    if not NETLIST_PATH.is_file():
        raise GateLevelSimError(f"gate-level netlist not found at {NETLIST_PATH}")
    netlist_text = NETLIST_PATH.read_text()

    filtered_lib = build_filtered_library(pdk, netlist_text)
    stripped_sdf = build_stripped_sdf()
    loader = write_sdf_loader(stripped_sdf)

    sim_build_dir = BUILD_DIR / "sim_build"
    runner = get_runner("icarus")
    runner.build(
        verilog_sources=[
            NETLIST_PATH,
            primitives_path(pdk),
            filtered_lib,
            loader,
        ],
        hdl_toplevel=TOP,
        build_dir=sim_build_dir,
        always=True,
        build_args=["-g2005", "-gspecify"],
        timescale=("1ns", "1ps"),
        log_file=build_log_path,
    )
    results_xml = runner.test(
        test_module="test_tmds_encoder",
        hdl_toplevel=TOP,
        build_dir=sim_build_dir,
        test_dir=VERIFICATION_DIR,
        extra_env={"TMDS_SIM_CLOCK_PERIOD_NS": str(CLOCK_PERIOD_NS)},
        log_file=test_log_path,
    )
    return get_results(results_xml)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    when = synth._dt.datetime.now(synth._dt.timezone.utc)
    rid = synth.record_id(when)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    build_log_path = REPORTS_DIR / f"{rid}.gl_sim.build.log"
    test_log_path = REPORTS_DIR / f"{rid}.gl_sim.test.log"

    try:
        n, f = run_gate_level_sim(pdk, build_log_path, test_log_path)
    except GateLevelSimError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    passed = f == 0 and n > 0
    print(f"{'PASS' if passed else 'FAIL'}: {n} test(s), {f} failed (clock period {CLOCK_PERIOD_NS} ns)")

    if not args.no_record:
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        record_path = RECORDS_DIR / f"{rid}.md"
        if record_path.exists():
            print(f"ERROR: record {record_path} already exists -- refusing to overwrite", file=sys.stderr)
            return 1
        sha = synth._git("rev-parse", "HEAD") or "unknown"
        dirty = synth.working_tree_dirty()
        record_path.write_text(render_record(rid, when, pdk, n, f, passed, dirty, sha))
        print(f"Evidence record written to {record_path}")

    return 0 if passed else 1


def render_record(rid, when, pdk: Pdk, n_tests: int, n_failed: int, passed: bool, dirty: bool, sha: str) -> str:
    outcome = (
        f"PASS -- {n_tests} of {n_tests} cocotb test(s) passed, 0 failed"
        if passed
        else f"FAIL -- {n_failed} of {n_tests} cocotb test(s) failed"
    )
    return f"""\
# Record {rid}

- **Record ID**: {rid}
- **Claim**: The digital gate-level testbench (`verification/tmds_encoder/
  test_tmds_encoder.py`, unmodified except for its own DR-0009 four-clock-
  latency update -- see that update's own commit for the rationale) passes
  when run against the post-route, SDF-back-annotated gate-level netlist for
  `tmds_encoder` (four-stage (DR-0009) synthesized netlist issue #115
  produced, `flow/tmds_encoder/netlist/tmds_encoder.synth.v`, unmodified,
  timing-annotated via Icarus Verilog's `$sdf_annotate` from the
  back-annotated SDF issue #115's own `flow/sdf_tmds_encoder.py` extracted).
  Addresses #65 item 7 (post-layout verification) on the digital partition,
  and is the check that the DR-0009 restructure -- which changed the
  encoder's internal structure, not just where its registers sit -- still
  encodes correctly once real post-route delays are annotated, rather than
  only in zero-delay RTL simulation.
- **P&R revision cited**: issue #115's evidence record
  `{PNR_RECORD_ID}`
  (`flow/tmds_encoder/records/{PNR_RECORD_ID}.md`), routed DEF
  `flow/tmds_encoder/pnr/tmds_encoder.def`, git commit `{sha}`.
- **SDF extraction tool/version cited**: `flow/sdf_tmds_encoder.py`'s own
  evidence record (issue #115, this same issue) -- see that record for the
  OpenROAD/OpenSTA version, RC extraction rule deck, and the worst-case
  unconstrained combinational delay this driver's own `CLOCK_PERIOD_NS`
  margins against (see this module's docstring, "Test clock period").
- **Re-simulation outcome**: {outcome}.
- **Simulator**: Icarus Verilog (via cocotb's Python runner API,
  `cocotb_tools.runner`), `-g2005 -gspecify` (specify-block/SDF timing
  enabled; Icarus does not support SDF `TIMINGCHECK` enforcement -- see
  "Known limitations" below).
- **Test clock period**: {CLOCK_PERIOD_NS} ns -- not an operating-frequency
  claim; see this module's docstring, "Test clock period", for the full
  margin rationale against the worst-case combinational delay
  `flow/sdf_tmds_encoder.py`'s own record measured for this four-stage
  (DR-0009) revision -- comfortably inside this driver's margin, as it was
  for the DR-0008 (13.27 ns) and pre-pipeline (18.30 ns) revisions before
  it.
- **Known limitations (disclosed, not silently worked around)**:
  1. **Two Icarus Verilog 13.0 parser/runtime limitations required
     mechanical, documented preprocessing** (`ifnone` + edge-sensitive
     specify paths unsupported; `-ginterconnect` could not resolve net
     paths for this plain-`wire` design) -- see
     `flow/gate_level_sim_tmds_encoder.py`'s docstring for the full
     mechanism and why both preprocessing steps preserve the delay
     information that actually matters for this design (per-cell IOPATH
     delays, which dominate this design's timing entirely; extracted
     net-interconnect delays are independently confirmed 0.000 ns
     throughout by `flow/sdf_tmds_encoder.py`'s own evidence record).
  2. **SDF `TIMINGCHECK` (`$setup`/`$hold`) is not enforced by Icarus** --
     a too-tight clock period would not show as a hard violation the way a
     full SDF-aware simulator's `notifier`-driven X-forcing would; this is
     why `CLOCK_PERIOD_NS` above carries an explicit, generous margin
     rather than relying on the simulator to catch a too-tight choice.
  3. **No formal setup/hold timing-closure verdict is made here** -- this
     driver demonstrates functional equivalence under real back-annotated
     delays at a deliberately conservative test clock; a formal
     timing-closure / achievable-operating-frequency claim is issue #83's
     (STA) job, not this one's.
- **Reproducibility**: working tree {"DIRTY (uncommitted changes at run time -- re-run against a clean checkout before trusting this record)" if dirty else "clean"} at commit `{sha}`.
- **Links**:
  - Gate-level netlist (input, unmodified): `flow/tmds_encoder/netlist/tmds_encoder.synth.v`
  - Back-annotated SDF (input, unmodified): `flow/tmds_encoder/sta/tmds_encoder.sdf`
  - Test module (input, unmodified): `verification/tmds_encoder/test_tmds_encoder.py`
  - Build log: `flow/tmds_encoder/reports/{rid}.gl_sim.build.log`
  - Test log: `flow/tmds_encoder/reports/{rid}.gl_sim.test.log`
  - Driver: `flow/gate_level_sim_tmds_encoder.py`
- **Timestamp / author**: {when.strftime("%Y-%m-%d %H:%M:%S UTC")}, `flow/gate_level_sim_tmds_encoder.py` (agent-run)
"""


if __name__ == "__main__":
    sys.exit(main())
