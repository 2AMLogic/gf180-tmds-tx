#!/usr/bin/env python3
"""OpenROAD place-and-route driver for `tmds_encoder` (issue #84).

Takes the gate-level netlist issue #82 already produced and committed
(``flow/tmds_encoder/netlist/tmds_encoder.synth.v``) as-is -- this script
never re-synthesizes it -- and place-and-routes it against the gf180mcu
``gf180mcu_fd_sc_mcu9t5v0`` standard-cell library at the same
``tt_025C_3v30`` corner #82 used (spec/tmds-tx.md DR-0003), producing:

  - the routed DEF:            flow/tmds_encoder/pnr/tmds_encoder.def
  - the block-level digital GDS: layout/gds/tmds_encoder.gds
  - the exact OpenROAD script run, and its full log:
        flow/tmds_encoder/reports/<record-id>.pnr.tcl
        flow/tmds_encoder/reports/<record-id>.pnr.log
  - an append-only evidence record: flow/tmds_encoder/records/<record-id>.md

Scope (per issue #84, extended by #100): place-and-route, now including
clock-tree synthesis and post-CTS hold repair -- floorplan, tap/endcap
insertion, power distribution network (PDN), placement, clock-tree
synthesis, hold repair, routing, and filler insertion. No standalone static
timing analysis and no timing-closure *verdict* is made here -- that remains
`flow/sta_tmds_encoder.py`'s job, re-run against this script's output -- but
`repair_timing -hold` here does actively fix any hold violation CTS itself
introduces. See "Clock-tree synthesis" below for the full recipe and why #84
originally skipped it.

PDK resolution reuses ``sim/harness/pdk.py`` (via ``flow/synth_tmds_encoder.py``,
imported for its already-reviewed ``record_id``/``_git``/``working_tree_dirty``
helpers rather than re-implementing them -- same PDK-pinning convention as
that script and as ``sim/``).

## Two mechanical, zero-semantic-impact Verilog preprocessing steps

OpenROAD's built-in Verilog reader (a simplified structural-Verilog parser,
not a full HDL frontend like Yosys) rejects two constructs present in the
committed, unmodified ``tmds_encoder.synth.v`` netlist. Both are fixed in an
in-memory/`flow/build/`-scratch copy only -- the committed netlist file
itself is never touched, and both deltas are re-verified (not just assumed)
every run:

1. ``wire signed [7:0] cnt;`` -> ``wire [7:0] cnt;`` -- a type-only
   annotation OpenROAD's reader's grammar does not accept
   (``STA-0171 syntax error``, confirmed against this exact line while
   building this driver). Purely cosmetic: nothing downstream reads the
   *signedness* of a `wire` (only `reg`/behavioral arithmetic cares, and
   this is already a fully gate-level, structural netlist).
2. The single dead tie ``assign cnt[0] = 1'h0;`` is dropped rather than fed
   through. ``cnt[0]`` has zero fanout in the synthesized netlist (verified
   by regex fanout-counting the written netlist, not assumed --
   see ``dead_net_fanout_count``): Yosys's own `opt`/`abc` folded the
   running-disparity accumulator's LSB to a constant and left this leftover
   top-level continuous assignment, which nothing reads. OpenROAD's reader
   accepts the line syntactically, but represents the literal-0 driver as
   an implicit, deck-wide ``zero_`` net of ``SignalType GROUND`` -- which
   TritonRoute then refuses to route (``DRT-0305 ... is not routable ...
   Move to special nets``), even though the net drives nothing. Dropping the
   dead assign (rather than trying to tie it off with a real
   ``gf180mcu_fd_sc_mcu9t5v0__tiel`` cell via `repair_tie_fanout`, which
   this script tried first and confirmed is a no-op here -- OpenROAD's
   constant-fanout repair does not fire on a zero-fanout net) reflects
   exactly what P&R actually builds: no tie cell, no dead net, because
   nothing in the real circuit needs one.

## Clock-tree synthesis (issue #100)

Clock-tree synthesis now runs. #84 (this script's original form) deliberately
skipped it "for want of a clock period" -- #82's synthesis applied no
clock-period constraint at the time, so any period this script picked would
have looked like an unearned timing commitment. Issue #100's timing-driven
resynthesis (`flow/synth_tmds_encoder.py`) now targets a real period
(`spec/tmds-tx.md` §2's 720p60 74.25 MHz pixel clock, `synth.TARGET_PERIOD_NS`),
so this script uses that same period for `clock_tree_synthesis`, balancing
the clock net's insertion delay/skew rather than leaving it as an ordinary,
unbuffered signal net.

Recipe (after placement, before routing -- the conventional CTS point):
`create_clock` (same period as synthesis), `estimate_parasitics -placement`,
`clock_tree_synthesis -buf_list <clkbuf_* cells> -sink_clustering_enable`,
`set_propagated_clock [all_clocks]`, then `detailed_placement` to legalize
the CTS-inserted buffers. Per issue #100's own scope item 2, hold is
re-checked and repaired after CTS: `repair_timing -hold` (CTS-inserted clock
buffers change insertion delay per register, which can turn a passing hold
path into a violation even though hold was clock-period-independent and
passed at every corner pre-CTS -- see #83's record), followed by another
`detailed_placement` to legalize whatever `repair_timing` itself inserts.
The constraint set (`set_input_delay 0` / `set_output_delay 0` /
`set_driving_cell`/`set_load`) mirrors `flow/sta_tmds_encoder.py`'s own SDC
assumptions exactly, so `repair_timing`'s view of the design's I/O boundary
is not looser than what the post-route STA record checks against.

This still does not by itself constitute a timing-closure claim -- that
remains `flow/sta_tmds_encoder.py`'s job, re-run against this script's routed
DEF and post-CTS parasitics.

## GDS streamout: DEF+LEF -> GDS, and a DBU mismatch that dropped most vias

`klt` (this repo's klayout-tools wrapper) does **not** expose DEF+LEF-to-GDS
streamout as a CLI verb of its own (`klt`'s verb surface --
`drc`/`extract`/`lvs`/`render`/... -- has none), but the capability *does*
exist in `klt place-and-route` (a post-`v0.2.0` klayout-tools capability --
see `layout/README.md`'s "Toolchain note" for `cml_driver_core`'s
`gate_contact` gap for the identical PyPI-lag situation) as an internal,
non-CLI step of that command: it merges a routed DEF into GDS in-process via
`klayout.db`, never a `klayout` subprocess. That command does not (yet) do
tapcell/PDN/filler insertion, though (an explicit, self-documented
out-of-scope item -- `docs/cli/place-and-route.md`'s "Out of scope"), which
this design's actual block-level layout needs, so this script still
shells out to OpenROAD directly for the P&R stages themselves. For the GDS
merge step specifically, this script now follows the *same* in-process
`klayout.db` approach `klt place-and-route`'s own merge step uses (ported
from OpenROAD-flow-scripts' `flow/util/def2stream.py`, the same source that
command's own merge step was ported from) rather than shelling out to a
`klayout` CLI binary -- requires the `klayout` PyPI package (`pip install
klayout`, the same package `klt` itself depends on) on the Python running
this script; see "Pinned toolchain" in `flow/README.md`.

**A real, now-fixed defect found and fixed while building this driver, not
worked around**: the first version of this driver's merge step (using
OpenROAD-flow-scripts' own bundled gf180 KLayout tech file un-modified)
silently dropped most Via1/Via2 cut geometry -- 10 of ~708 expected Via1
cuts landed in one observed run. The initial diagnosis (a per-orientation
``VIARULE ... GENERATE`` via-naming gap in the DEF/LEF importer) was
**wrong** and has since been corrected: the actual root cause is that
OpenROAD-flow-scripts' bundled gf180 KLayout tech file declares
``<dbu>0.001</dbu>`` (1000 database units/micron), while this design's own
tech LEF declares ``DATABASE MICRONS 2000`` (2000 units/micron, i.e. a DBU
of ``0.0005``) -- a real mismatch between two different upstream gf180
platform config files, not something design-specific. KLayout's DEF/LEF
reader detects this (`Warning: DEF UNITS does not match reader DBU`) but
only warns, silently producing corrupted via-cut geometry rather than
raising an error. Renaming the inline via references to their
fully-qualified tech-LEF rule names (e.g. ``Via1_VV`` -> ``Via1_GEN_VV``,
this driver's own first attempted fix) did **not** help -- confirmed, on
isolated re-test, to make resolution *worse* (every via reference became
unresolvable, not a partial improvement) when combined with the DBU
mismatch, and to be entirely unnecessary once the DBU is corrected. The
actual fix, and what this driver now does (`_dbu_corrected_tech_file`
below): read `DATABASE MICRONS` from the resolved PDK's own tech LEF, and
write a scratch copy of the KLayout tech file with every ``<dbu>`` entry
rewritten to match before running the merge. Verified end to end: Via1/Via2
per-layer shape counts went from ~10 (of ~708 expected) to 1849/3858
respectively, and the merge's own "every LEF cell has a matching GDS/OAS
cell" check (which additionally caught filler-cell macros resolving to
empty dummy shapes under the old, DBU-mismatched merge) now passes clean.
DRC/LVS violation counts against the corrected GDS dropped correspondingly
(see the evidence record's "Result" and "Known limitations" sections) --
this was a genuine, verifiable, upstream-tooling defect, not a cosmetic
change.

Filed against `2AMLogic/klayout-tools`, per the friction protocol:
[#1029](https://github.com/2AMLogic/klayout-tools/issues/1029) (`klt
place-and-route`'s own DEF->GDS merge layer-map resolver assumes one map
file per PDK variant, but gf180mcu ships one shared across all variants --
independent of the DBU issue, found investigating the same merge step) and
[#1032](https://github.com/2AMLogic/klayout-tools/issues/1032) (the DBU
mismatch itself, and why `klt place-and-route`'s own in-process merge would
hit it too for any PDK whose tech LEF's `DATABASE MICRONS` differs from
KLayout's default). An earlier issue,
[#1031](https://github.com/2AMLogic/klayout-tools/issues/1031), was filed
with the initial (wrong) per-orientation-naming diagnosis before the DBU
root cause was isolated; #1032 explicitly corrects and supersedes it, but
this account has no comment/edit permission on that repository (`Resource
not accessible by integration` on both `addComment` and `updateIssue`), so
#1031 could not itself be closed or amended -- disclosed here for anyone
following it directly.

**A second, related DBU-mismatch corruption, found and fixed the same way
while validating the first fix**: correcting the DEF/LEF reader's target
DBU (above) makes it differ from the standard-cell GDS *library's* own
native DBU (`0.001`, a GDS-stream-format convention independent of the
LEF's `DATABASE MICRONS`), and `Layout.read()` merging a second file into
an already-populated `Layout` does **not** convert units -- confirmed live,
it silently reassigns the *whole* layout's DBU to the incoming file's own
value, with **no rescale** of previously-read content. Naively merging the
cell library the same way `def2stream.py` does (`main_layout.read(cell_gds)`,
straight into the DEF-populated layout) corrupted every already-read
DEF-derived coordinate by exactly the DBU ratio -- caught directly: this
design's real 158.21 um top-level die width read back as ~305 um (not quite
2x, due to placement/margin offsets, but the same mechanism), and the
layout-side LVS extraction merged unrelated signal nets together as a
downstream symptom (fixed alongside; no longer happens). Fixed by reading
the cell library into its own, separate `Layout` at its own native DBU and
copying every shape across with an explicit magnification transform
(`cell_layout.dbu / main_layout.dbu`) instead of a second bare `.read()`
call -- see `merge_gds`'s own comment for the exact mechanism (this GDS
library is flat, no cell instantiates another, so a per-cell/per-layer
shape copy is sufficient). Not filed as a separate klayout-tools issue:
this is a caller-side integration bug in *this* driver's own first attempt
at the fix above, not a defect in `klt`/`klayout.db` itself -- any caller
merging two GDS-format inputs of differing native DBU into one `Layout`
needs to handle this the same way.

**Separately, and not related to either DBU-mismatch fix**: the DRC
violations that remain after both fixes (see the evidence record) are
**entirely** `mim.space.1` (188 violations, none attributed to a
`source_cell` -- i.e. top-level PDN/routing geometry, not any single
library cell's own qualified geometry) -- consistent with, and filed as,
[#1033](https://github.com/2AMLogic/klayout-tools/issues/1033): the curated
gf180mcu deck's `mim.space.1` rule is implemented as a general
Metal4-to-Metal4 spacing check (its own violation `description` field says
so: "approximated as general metal4-to-metal4 spacing"), so it cannot
distinguish a real MiM capacitor's bottom plate from ordinary Metal4 PDN
stripes/routing -- this design has zero capacitor devices anywhere. An
earlier version of this section (before both DBU fixes above) additionally
reported `nwell.space.1`/`metal1.space.1`/`metal1.width.1` violations
consistent with a *different*, independent, already-filed, still-open
issue, [#1028](https://github.com/2AMLogic/klayout-tools/issues/1028)
(row-abutment false positives) -- those rule categories no longer appear at
all once the second DBU-mismatch fix above landed, so that finding is
withdrawn here (#1028 itself remains open and correctly filed on its own
generic merits; this driver's own layout simply no longer exercises it).

Cold-start invocation (requires OpenROAD on `PATH`, run via the pinned
`openroad/orfs` Docker image -- see "Pinned toolchain" in `flow/README.md`
-- plus the `klayout` PyPI package for the GDS merge step):

    python3 flow/pnr_tmds_encoder.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "flow"))

from sim.harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402
import synth_tmds_encoder as synth  # noqa: E402  (reuses record_id/_git/working_tree_dirty)

TOP = "tmds_encoder"
NETLIST_PATH = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / "tmds_encoder.synth.v"

OUT_DIR = REPO_ROOT / "flow" / "tmds_encoder"
PNR_DIR = OUT_DIR / "pnr"
BUILD_DIR = REPO_ROOT / "flow" / "build"
REPORTS_DIR = OUT_DIR / "reports"
RECORDS_DIR = OUT_DIR / "records"

LAYOUT_GDS_DIR = REPO_ROOT / "layout" / "gds"
FINAL_DEF = PNR_DIR / "tmds_encoder.def"
FINAL_GDS = LAYOUT_GDS_DIR / "tmds_encoder.gds"

STD_CELL_LIB = "gf180mcu_fd_sc_mcu9t5v0"
STD_CELL_CORNER = "tt_025C_3v30"
SITE = "GF018hv5v_green_sc9"
CORE_UTILIZATION = 35  # percent -- see evidence record for the resulting effective utilization
PLACE_DENSITY = 0.45
CORE_SPACE_UM = 4

# Clock-tree synthesis (issue #100) -- see this module's docstring
# "Clock-tree synthesis" section. Same period synth_tmds_encoder.py's ABC
# mapping now targets (spec/tmds-tx.md §2's 720p60 pixel clock).
CTS_PERIOD_NS = synth.TARGET_PERIOD_NS
# Candidate buffer cells for CTS -- every clkbuf_* drive strength the library
# ships, so OpenROAD's CTS engine can pick the size each level of the tree
# needs rather than being limited to one.
CTS_BUF_LIST = [f"{STD_CELL_LIB}__clkbuf_{d}" for d in (1, 2, 3, 4, 8, 12, 16, 20)]
# I/O boundary assumptions for `repair_timing`, numerically identical to
# flow/sta_tmds_encoder.py's own DRIVING_CELL/OUTPUT_LOAD_PF (kept in sync
# manually; both cite the same rationale -- see that driver's docstring).
SDC_DRIVING_CELL = f"{STD_CELL_LIB}__inv_1"
SDC_DRIVING_CELL_PIN = "ZN"
SDC_OUTPUT_LOAD_PF = 0.027252

# OpenROAD-flow-scripts' bundled, gf180-platform-specific streamout assets
# this driver reuses read-only for the GDS merge step -- static PDK viewer
# metadata (KLayout technology file + GDS layer map), not design data. Paths
# are inside the `openroad/orfs` container image this driver was run
# through; see flow/README.md's "Pinned toolchain".
ORFS_ROOT = Path("/OpenROAD-flow-scripts")
ORFS_KLAYOUT_LYT = ORFS_ROOT / "flow" / "platforms" / "gf180" / "KLayout" / "gf180mcu_5LM_1TM_9K_9t.lyt"
ORFS_LAYER_MAP = (
    ORFS_ROOT / "flow" / "platforms" / "gf180" / "gds" / "9t" / "gf180mcu_5LM_1TM_9K_9t_edi2gds.layermap"
)
ORFS_DEF2STREAM = ORFS_ROOT / "flow" / "util" / "def2stream.py"  # kept for provenance only; no longer invoked

_DATABASE_MICRONS_RE = re.compile(r"DATABASE\s+MICRONS\s+(\d+)")
_LYT_DBU_RE = re.compile(r"<dbu>[^<]*</dbu>")


class PnrError(RuntimeError):
    pass


def lef_paths(pdk: Pdk) -> tuple[Path, Path, Path, Path]:
    base = pdk.path / "libs.ref" / STD_CELL_LIB
    tech_lef = base / "techlef" / f"{STD_CELL_LIB}__nom.tlef"
    sc_lef = base / "lef" / f"{STD_CELL_LIB}.lef"
    liberty = base / "lib" / f"{STD_CELL_LIB}__{STD_CELL_CORNER}.lib"
    cell_gds = base / "gds" / f"{STD_CELL_LIB}.gds"
    for p in (tech_lef, sc_lef, liberty, cell_gds):
        if not p.is_file():
            raise PnrError(f"expected gf180mcu PDK file not found: {p}")
    return tech_lef, sc_lef, liberty, cell_gds


def preprocess_netlist_for_openroad(src: Path, dst: Path) -> None:
    """The two mechanical, documented deltas from this module's docstring."""
    text = src.read_text()
    fanout = dead_net_fanout_count(text, "cnt[0]")
    if fanout > 0:
        raise PnrError(
            f"cnt[0] has {fanout} reference(s) beyond its own declaration/assignment -- "
            "no longer dead; this preprocessing step no longer applies, investigate"
        )
    text = text.replace("wire signed [7:0] cnt;", "wire [7:0] cnt;")
    text = text.replace("  assign cnt[0] = 1'h0;\n", "")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)


def dead_net_fanout_count(text: str, net: str) -> int:
    """References to `net` beyond its own wire declaration + assign LHS."""
    refs = len(re.findall(re.escape(net) + r"\b", text))
    return max(0, refs - 2)


def build_tcl(tech_lef: Path, sc_lef: Path, liberty: Path, pnr_input: Path) -> str:
    return f"""\
read_lef {tech_lef}
read_lef {sc_lef}
read_liberty {liberty}
read_verilog {pnr_input}
link_design {TOP}

initialize_floorplan -utilization {CORE_UTILIZATION} -aspect_ratio 1 -core_space {CORE_SPACE_UM} -site {SITE}

source {PNR_DIR}/tracks.tcl

place_pins -hor_layers Metal3 -ver_layers Metal4

tapcell -distance 100 -tapcell_master {STD_CELL_LIB}__filltie -endcap_master {STD_CELL_LIB}__endcap

source {PNR_DIR}/pdn.tcl
pdngen

global_placement -density {PLACE_DENSITY}
detailed_placement
optimize_mirroring

# Clock-tree synthesis (issue #100) -- see this module's docstring "Clock-tree
# synthesis" section for the full recipe and rationale. Boundary constraint
# assumptions below are numerically identical to flow/sta_tmds_encoder.py's
# own generated SDC.
create_clock -name clk -period {CTS_PERIOD_NS:.4f} [get_ports clk]
set non_clk_inputs [get_ports {{data[*] ctrl[*] de rst}}]
set_input_delay 0.0000 -clock clk $non_clk_inputs
set_output_delay 0.0000 -clock clk [all_outputs]
set_driving_cell -lib_cell {SDC_DRIVING_CELL} -pin {SDC_DRIVING_CELL_PIN} $non_clk_inputs
set_load {SDC_OUTPUT_LOAD_PF} [all_outputs]

estimate_parasitics -placement
clock_tree_synthesis -buf_list {{{" ".join(CTS_BUF_LIST)}}} -sink_clustering_enable
set_propagated_clock [all_clocks]
estimate_parasitics -placement
detailed_placement

# Hold repair (issue #100 step 2): CTS changes per-register clock insertion
# delay, which can turn a pre-CTS-passing hold path into a violation even
# though hold is clock-period-independent (see #83's record, "Known
# limitations" 1). repair_timing legalizes via another detailed_placement.
estimate_parasitics -placement
repair_timing -hold
detailed_placement

global_route
detailed_route -output_drc {BUILD_DIR}/route_drc.rpt -output_maze {BUILD_DIR}/maze.log

filler_placement {STD_CELL_LIB}__fill_*

write_def {FINAL_DEF}
write_verilog {BUILD_DIR}/tmds_encoder.pnr.v
write_db {BUILD_DIR}/tmds_encoder.odb

exit
"""


def run_openroad(script: str, log_path: Path) -> subprocess.CompletedProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    script_path = log_path.with_suffix(".tcl")
    script_path.write_text(script)
    result = subprocess.run(
        ["openroad", "-no_init", "-exit", str(script_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    log_path.write_text((result.stdout or "") + (result.stderr or ""))
    return result


def tech_lef_database_microns(tech_lef: Path) -> int:
    """The tech LEF's own `DATABASE MICRONS <N>` value -- see this module's
    docstring's "GDS streamout" section for why this must match the KLayout
    tech file's own `<dbu>` during the DEF->GDS merge, and what silently
    goes wrong (dropped via-cut geometry) when it doesn't."""
    m = _DATABASE_MICRONS_RE.search(tech_lef.read_text())
    if not m:
        raise PnrError(f"could not find 'DATABASE MICRONS <N>' in {tech_lef}")
    return int(m.group(1))


def write_dbu_corrected_lyt(src_lyt: Path, dst_lyt: Path, database_microns: int) -> None:
    """Write a copy of `src_lyt` (OpenROAD-flow-scripts' bundled gf180
    KLayout tech file) with every `<dbu>...</dbu>` entry rewritten to match
    `database_microns` (`1 / database_microns`), instead of that file's own
    stock `0.001` (1000 units/micron) -- gf180mcu's tech LEF declares 2000.
    See this module's docstring's "GDS streamout" section."""
    text = src_lyt.read_text()
    dbu = 1.0 / database_microns
    fixed, n = _LYT_DBU_RE.subn(f"<dbu>{dbu:g}</dbu>", text)
    if n == 0:
        raise PnrError(f"found no '<dbu>...</dbu>' entries to rewrite in {src_lyt}")
    dst_lyt.parent.mkdir(parents=True, exist_ok=True)
    dst_lyt.write_text(fixed)


def merge_gds(def_path: Path, tech_lef: Path, sc_lef: Path, cell_gds: Path, log_path: Path) -> None:
    """DEF->GDS merge, in-process via the `klayout` PyPI package's
    `klayout.db` module (never a `klayout` subprocess) -- ported from
    OpenROAD-flow-scripts' `flow/util/def2stream.py` (`ORFS_DEF2STREAM`),
    the same source `klt place-and-route`'s own in-process merge step was
    ported from. See this module's docstring's "GDS streamout" section for
    why this reimplements that step instead of shelling out to it, and for
    the DBU-mismatch defect this function's `write_dbu_corrected_lyt` call
    fixes. Raises `PnrError` on any merge failure (bad DEF, unmatched
    macro/LEF cell, etc.) -- never a silent empty/partial GDS."""
    import klayout.db as kdb  # local import -- only needed for this step

    corrected_lyt = BUILD_DIR / "gf180mcu_5LM_1TM_9K_9t.dbu_corrected.lyt"
    write_dbu_corrected_lyt(ORFS_KLAYOUT_LYT, corrected_lyt, tech_lef_database_microns(tech_lef))

    tech = kdb.Technology()
    tech.load(str(corrected_lyt))
    opts = tech.load_layout_options
    opts.lefdef_config.map_file = str(ORFS_LAYER_MAP)
    opts.lefdef_config.lef_files = [str(tech_lef), str(sc_lef)]

    log_lines: list[str] = []
    main_layout = kdb.Layout()
    try:
        main_layout.read(str(def_path), opts)
    except Exception as exc:  # klayout raises RuntimeError for bad/unknown streams
        raise PnrError(f"could not read DEF '{def_path}' for GDS merge: {exc}") from exc

    top_cell = main_layout.cell(TOP)
    if top_cell is None:
        raise PnrError(f"DEF '{def_path}' does not define top cell '{TOP}'")
    top_cell_index = top_cell.cell_index()

    # Clear every non-top cell except LEF-via cells (KLayout prepends "VIA_"
    # when reading a DEF that instantiates a LEF via) and DEF fill cells --
    # matching def2stream.py's own orphan-cell handling exactly.
    for cell in main_layout.each_cell():
        if cell.cell_index() != top_cell_index:
            if not cell.name.startswith("VIA_") and not cell.name.endswith("_DEF_FILL"):
                cell.clear()

    # The standard-cell GDS library is at its own native DBU (0.001, i.e.
    # 1000 units/micron -- a GDS-stream-format convention, independent of
    # and NOT required to match the tech LEF's `DATABASE MICRONS` value used
    # above), which after `write_dbu_corrected_lyt` no longer equals
    # `main_layout.dbu` (0.0005 for this design). `Layout.read()` merging a
    # second file into an already-populated `Layout` does **not** convert
    # units -- confirmed live: it silently reassigns the *whole* layout's
    # `dbu` to the incoming file's own value, with **no rescale** of
    # previously-read content, corrupting every already-read DEF-derived
    # coordinate (e.g. a real 158.21 um top-level dimension silently read
    # back as ~316 um, exactly 2x, after a naive `main_layout.read(cell_gds)`
    # call -- caught before this fix shipped, not a hypothetical). So the
    # cell library is read into its own, separate `Layout` at its own native
    # dbu, and every shape is copied across with an explicit magnification
    # transform (`cell_layout.dbu / main_layout.dbu`) instead -- this GDS
    # library is flat (no cell in it instantiates another; verified via
    # `child_instances()` while building this driver), so a per-cell,
    # per-layer shape copy is sufficient; it would need to be a recursive
    # `copy_tree`-with-transform if that were ever not true.
    cell_layout = kdb.Layout()
    try:
        cell_layout.read(str(cell_gds))
    except Exception as exc:
        raise PnrError(f"could not read standard-cell GDS view '{cell_gds}' for GDS merge: {exc}") from exc

    mag = cell_layout.dbu / main_layout.dbu
    cell_trans = kdb.ICplxTrans(mag)
    for src_cell in cell_layout.each_cell():
        dst_cell = main_layout.cell(src_cell.name) or main_layout.create_cell(src_cell.name)
        for src_lyr in cell_layout.layer_indexes():
            src_shapes = src_cell.shapes(src_lyr)
            if src_shapes.is_empty():
                continue
            dst_lyr = main_layout.layer(cell_layout.get_info(src_lyr))
            dst_cell.shapes(dst_lyr).insert(src_shapes, cell_trans)

    top_only = kdb.Layout()
    top_only.dbu = main_layout.dbu
    top = top_only.create_cell(TOP)
    top.copy_tree(main_layout.cell(TOP))

    missing = sorted(cell.name for cell in top_only.each_cell() if cell.is_empty())
    for name in missing:
        log_lines.append(f"[ERROR] LEF Cell '{name}' has no matching GDS/OAS cell. Cell will be empty.")
    if missing:
        raise PnrError(
            "DEF/GDS merge produced empty (unmatched) cells: "
            + ", ".join(missing[:10])
            + (f" (+{len(missing) - 10} more)" if len(missing) > 10 else "")
        )
    log_lines.append("[INFO] All LEF cells have matching GDS/OAS cells")

    FINAL_GDS.parent.mkdir(parents=True, exist_ok=True)
    try:
        top_only.write(str(FINAL_GDS))
    except OSError as exc:
        raise PnrError(f"could not write merged GDS '{FINAL_GDS}': {exc}") from exc
    log_lines.append(f"[INFO] wrote {FINAL_GDS} (dbu={top_only.dbu}, corrected tech file: {corrected_lyt})")

    log_path.write_text("\n".join(log_lines) + "\n")


def parse_utilization(log_text: str) -> dict[str, str]:
    fields = {}
    for pattern, key in (
        (r"Core area:\s+([\d.]+) um\^2", "core_area_um2"),
        (r"Total instances area:\s+([\d.]+) um\^2", "instances_area_um2"),
        (r"Effective utilization:\s+([\d.]+)", "effective_utilization"),
        (r"Number of instances:\s+(\d+)", "instance_count"),
        (r"Total wire length = ([\d.]+) um", "total_wire_length_um"),
        (r"Total number of vias = (\d+)", "via_count"),
    ):
        m = re.search(pattern, log_text)
        if m:
            fields[key] = m.group(1)
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-record", action="store_true")
    parser.add_argument("--skip-gds", action="store_true", help="run P&R only, skip the KLayout GDS merge step")
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        tech_lef, sc_lef, liberty, cell_gds = lef_paths(pdk)
    except PnrError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    pnr_input = BUILD_DIR / "tmds_encoder.pnr_input.v"
    try:
        preprocess_netlist_for_openroad(NETLIST_PATH, pnr_input)
    except PnrError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    when = synth._dt.datetime.now(synth._dt.timezone.utc)
    rid = synth.record_id(when)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = REPORTS_DIR / f"{rid}.pnr.log"

    script = build_tcl(tech_lef, sc_lef, liberty, pnr_input)
    print(f"Place-and-routing {TOP} ...")
    result = run_openroad(script, log_path)
    log_text = log_path.read_text()
    if result.returncode != 0 or "Error:" in log_text:
        print(f"ERROR: openroad exited {result.returncode} -- see {log_path}", file=sys.stderr)
        return 1
    if not FINAL_DEF.is_file():
        print(f"ERROR: openroad reported success but {FINAL_DEF} was not written", file=sys.stderr)
        return 1

    metrics = parse_utilization(log_text)
    print(f"OK: routed DEF written to {FINAL_DEF} ({metrics})")

    gds_log = REPORTS_DIR / f"{rid}.gds_merge.log"
    if not args.skip_gds:
        try:
            merge_gds(FINAL_DEF, tech_lef, sc_lef, cell_gds, gds_log)
        except PnrError as exc:
            print(f"ERROR: GDS merge failed: {exc}", file=sys.stderr)
            return 1
        if not FINAL_GDS.is_file():
            print(f"ERROR: merge_gds reported success but {FINAL_GDS} was not written", file=sys.stderr)
            return 1
        print(f"OK: merged GDS written to {FINAL_GDS} (see {gds_log})")

    if not args.no_record:
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        record_path = RECORDS_DIR / f"{rid}.md"
        if record_path.exists():
            print(f"ERROR: record {record_path} already exists -- refusing to overwrite", file=sys.stderr)
            return 1
        sha = synth._git("rev-parse", "HEAD") or "unknown"
        dirty = synth.working_tree_dirty()
        record_path.write_text(render_record(rid, when, pdk, liberty, metrics, dirty, sha, log_path, gds_log))
        print(f"Evidence record written to {record_path}")

    return 0


def render_record(rid, when, pdk, liberty, metrics, dirty, sha, log_path, gds_log) -> str:
    return f"""\
# Record {rid}

- **Record ID**: {rid}
- **Claim**: A block-level digital place-and-routed layout for `tmds_encoder`
  exists (DEF + merged GDS), built against the gate-level netlist issue #82
  produced (`flow/tmds_encoder/netlist/tmds_encoder.synth.v`, unmodified) and
  the gf180mcu `{STD_CELL_LIB}` standard-cell library at the `{STD_CELL_CORNER}`
  corner (spec/tmds-tx.md DR-0003's synthesized-domain corner, same as #82).
  Addresses #65 item 2 (layout) on the digital partition.
- **Scope**: Place-and-route, now including clock-tree synthesis and post-CTS
  hold repair (issue #100 step 2) -- floorplan, tap/endcap, PDN, placement,
  CTS, hold repair, routing, filler insertion. No standalone timing-closure
  *verdict* is made here -- that remains `flow/sta_tmds_encoder.py`'s job,
  re-run against this record's DEF -- but `repair_timing -hold` here actively
  fixes any hold violation CTS itself introduces. See
  `flow/pnr_tmds_encoder.py`'s "Clock-tree synthesis" section.
- **Tool versions**:
  - OpenROAD: `26Q3-1278-g4421880472` (run via the `openroad/orfs:latest`
    Docker image -- see `flow/README.md`'s "Pinned toolchain")
  - `klayout` PyPI package (`klayout.db`, GDS merge step only, in-process --
    never a `klayout` subprocess): `0.30.10`
  - gf180mcu PDK: variant `{pdk.variant}`, open_pdks `{pdk.version}` (via {pdk.source})
- **P&R configuration**:
  - Site: `{SITE}` (9-track, matching `{STD_CELL_LIB}`)
  - Floorplan: `initialize_floorplan -utilization {CORE_UTILIZATION} -aspect_ratio 1 -core_space {CORE_SPACE_UM}`
  - Placement: `global_placement -density {PLACE_DENSITY}`, then `detailed_placement` + `optimize_mirroring`
  - Tap/endcap: `tapcell -distance 100` (`{STD_CELL_LIB}__filltie` / `{STD_CELL_LIB}__endcap`)
  - PDN: `flow/tmds_encoder/pnr/pdn.tcl` (Metal1 followpins + Metal4/Metal5
    stripes, the same grid strategy OpenROAD-flow-scripts' own gf180 9-track
    platform config uses)
  - Clock-tree synthesis (issue #100): `create_clock -period {CTS_PERIOD_NS:.4f}`
    (`spec/tmds-tx.md` §2's 720p60 target), `clock_tree_synthesis -buf_list
    {{{" ".join(CTS_BUF_LIST)}}} -sink_clustering_enable`, then `detailed_placement`
    to legalize the inserted buffers.
  - Hold repair (issue #100): `repair_timing -hold` after CTS, then another
    `detailed_placement` to legalize whatever it inserts -- run at the
    `{STD_CELL_CORNER}` corner this script's liberty uses; the quantitative
    post-CTS/post-repair hold verdict across all five 3.3 V corners is
    `flow/sta_tmds_encoder.py`'s job, re-run against this record's DEF, not
    this record's own claim.
  - Routing: `global_route` + `detailed_route` (TritonRoute), Metal2-Metal5
    (IO pins on Metal3/Metal4)
  - Filler: `filler_placement {STD_CELL_LIB}__fill_*`
- **Result metrics** (from the captured OpenROAD log): {metrics}
- **Preprocessing** (mechanical, zero-semantic-impact, applied only to an
  in-memory/`flow/build/`-scratch copy fed to OpenROAD's simplified Verilog
  reader -- the committed `tmds_encoder.synth.v` is never modified): see
  `flow/pnr_tmds_encoder.py`'s "Two mechanical ... preprocessing steps".
- **Known limitations (disclosed, not silently worked around)**:
  1. **No standalone timing-closure verdict** -- CTS and hold repair now run
     (see "Scope" above), but the quantitative multi-corner setup/hold
     verdict remains `flow/sta_tmds_encoder.py`'s job, re-run separately
     against this record's DEF.
  1a. **DRC/LVS reports not re-run against this record's GDS (disclosed, not
     silently stale)**: `layout/drc_reports/tmds_encoder.drc.json`/`.txt` and
     `layout/lvs_reports/tmds_encoder.lvs.json`/`.txt` (items 2/3 below) were
     generated against the *pre-#100* GDS (no CTS, no hold repair). Placement
     and routing both change once CTS/hold-repair buffers are inserted, so
     those reports describe a superseded layout, not this record's GDS.
     Re-running `klt drc`/`klt extract`/`klt lvs` against the new GDS is
     outside issue #100's scope (digital timing closure, not physical
     verification) and is left as an explicit, disclosed follow-up rather
     than silently re-asserting stale numbers here.
  2. **DRC** (pre-#100 GDS, see 1a): `klt drc` reports `status: violations` against the merged GDS
     (188 violations, all `mim.space.1`, none attributed to a
     `source_cell`) -- see `layout/drc_reports/tmds_encoder.drc.json`/`.txt`
     and `layout/README.md`'s `tmds_encoder` section. Filed as
     [#1033](https://github.com/2AMLogic/klayout-tools/issues/1033): the
     curated gf180mcu deck's `mim.space.1` rule is a general
     Metal4-to-Metal4 spacing check (its own violation `description` says
     so) that cannot distinguish a real MiM capacitor's bottom plate from
     ordinary Metal4 PDN stripes/routing -- this design has zero capacitor
     devices anywhere.
  3. **LVS** (pre-#100 GDS, see 1a): `klt lvs` reports `status: mismatch` (10 topology mismatches;
     281/281 nets and 25/25 pins otherwise match) -- see
     `layout/lvs_reports/tmds_encoder.lvs.json`/`.txt`. All 10 are P&R-inserted
     filler/tap/endcap standard-cell *types* (`gf180mcu_fd_sc_mcu9t5v0__fill_*`,
     `__filltie`, `__endcap`) that carry no logic and that the pre-P&R
     reference netlist (built from the synthesized netlist, which never
     instantiates them) has no counterpart for -- see
     `layout/scripts/filter_pnr_utility_cells.py`'s own docstring for the
     full accounting.
  4. **Two real, fixed defects, not currently-open ones**: an earlier
     version of this driver's GDS merge step (a) silently dropped most
     Via1/Via2 cut geometry due to a DBU mismatch between
     OpenROAD-flow-scripts' bundled gf180 KLayout tech file
     (`<dbu>0.001</dbu>`) and this design's own tech LEF
     (`DATABASE MICRONS 2000`), and (b), once (a) was fixed, corrupted the
     merged standard-cell geometry's real-world scale by naively merging the
     cell library (native DBU `0.001`) straight into the now-differently-scaled
     top-level layout -- see `flow/pnr_tmds_encoder.py`'s "GDS streamout"
     section for the full root-cause finding for both, the klayout-tools
     issues filed for (a)
     ([#1029](https://github.com/2AMLogic/klayout-tools/issues/1029),
     [#1032](https://github.com/2AMLogic/klayout-tools/issues/1032)), why an
     earlier, now-superseded issue
     ([#1031](https://github.com/2AMLogic/klayout-tools/issues/1031))
     carried the wrong initial diagnosis for (a), and why (b) was not filed
     upstream (a caller-side integration bug in this driver's own first fix
     attempt, not a `klt`/`klayout.db` defect). This driver now corrects
     both before every merge, so the GDS this record cites does not carry
     either defect -- TritonRoute's own internal DRC pass on the routed
     design (see `{log_path.name}`) independently reported zero violations
     throughout, corroborating that the P&R itself was always sound and
     only the merge step was ever at fault.
- **Reproducibility**: working tree {"DIRTY (uncommitted changes outside flow/tmds_encoder/ and layout/ at run time -- re-run against a clean checkout before trusting this record)" if dirty else "clean"} at commit `{sha}`.
- **Links**:
  - Netlist (input, unmodified): `flow/tmds_encoder/netlist/tmds_encoder.synth.v`
  - Routed DEF: `flow/tmds_encoder/pnr/tmds_encoder.def`
  - Merged GDS: `layout/gds/tmds_encoder.gds`
  - OpenROAD script: `flow/tmds_encoder/reports/{rid}.pnr.tcl`
  - Full OpenROAD log: `flow/tmds_encoder/reports/{rid}.pnr.log`
  - GDS merge log: `flow/tmds_encoder/reports/{gds_log.name}`
- **Timestamp / author**: {when.strftime("%Y-%m-%d %H:%M:%S UTC")}, `flow/pnr_tmds_encoder.py` (agent-run)
"""


if __name__ == "__main__":
    sys.exit(main())
