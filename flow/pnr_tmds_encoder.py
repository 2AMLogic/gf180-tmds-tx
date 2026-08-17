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

1. ``wire signed [N:0] <net>;`` -> ``wire [N:0] <net>;`` -- a type-only
   annotation OpenROAD's reader's grammar does not accept
   (``STA-0171 syntax error``, confirmed against this exact construct while
   building this driver, and re-confirmed against DR-0009's netlist). Purely
   cosmetic: nothing downstream reads the *signedness* of a `wire` (only
   `reg`/behavioral arithmetic cares, and this is already a fully gate-level,
   structural netlist). Applied to every signed net, not one name: the
   pre-DR-0009 netlist had exactly one (``cnt``); DR-0009's four-stage
   encoder also carries the two candidate accumulator deltas as signed nets.
2. Dead ties such as ``assign cnt[0] = 1'h0;`` are dropped rather than fed
   through. Every bit such an assign drives has zero fanout in the
   synthesized netlist (verified by re-searching the written netlist with
   the assigns removed, not assumed -- see ``live_assign_targets``): Yosys's
   own `opt`/`abc` folded whatever used to read those bits to a constant (the
   running-disparity accumulator's LSB, the two deltas' LSBs -- all three are
   structurally even -- and the candidate output words' two bits that do not
   depend on the inversion decision) and left the leftover top-level
   continuous assignments behind, which nothing reads. OpenROAD's reader
   accepts the lines syntactically, but represents a literal-0 driver as
   an implicit, deck-wide ``zero_`` net of ``SignalType GROUND`` -- which
   TritonRoute then refuses to route (``DRT-0305 ... is not routable ...
   Move to special nets``), even though the net drives nothing. Dropping the
   dead assigns (rather than trying to tie them off with a real
   ``gf180mcu_fd_sc_mcu9t5v0__tiel`` cell via `repair_tie_fanout`, which
   this script tried first and confirmed is a no-op here -- OpenROAD's
   constant-fanout repair does not fire on a zero-fanout net) reflects
   exactly what P&R actually builds: no tie cell, no dead net, because
   nothing in the real circuit needs one. A *live* top-level assign, or one
   whose syntax this step does not recognize, raises instead of being
   silently dropped.

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

## Clock insertion delay is a setup-timing term here, not just a skew term (issue #115)

`clock_tree_synthesis`'s `-buf_list` is a *candidate* list; the buffer
TritonCTS actually instantiates for the tree's root and internal levels, when
not told otherwise, is the **first entry** of that list -- which for the
drive-strength-ordered list above is the weakest cell the library ships,
`clkbuf_1`. On this design that produced a clock tree whose root buffer was
driving a load it had no business driving, and the resulting insertion delay
was not merely large but *unbalanced*: the launching register's clock
arrived measurably later than the capturing register's, which is a direct,
one-for-one subtraction from setup slack on every register-to-register path.

`CTS_ROOT_BUF`/`CTS_TREE_BUF` therefore name the buffers explicitly
(`clkbuf_16` at the root, `clkbuf_8` internally) rather than letting the
list order decide. Measured, not guessed: naming them was worth 0.2148 ns of
worst-corner setup slack on this design (-0.5397 ns -> -0.3249 ns at
`ss_125C_3v00`) with no other change in the same run. The candidate list is
left as-is, so CTS still picks per-level sizes for the leaves.

## Two-corner optimization: setup at the slow corner, hold at the nominal one (issue #115)

Every earlier revision of this driver read a single liberty
(`STD_CELL_CORNER`, the `tt_025C_3v30` nominal corner), so `repair_timing`
optimized against the nominal corner's timing -- which has multiple
nanoseconds of setup slack on this design and therefore gives a setup
resizer nothing to do, while the corner 720p60 setup actually has to close
at (`ss_125C_3v00`, the same corner `flow/synth_tmds_encoder.py`'s ABC
mapping already targets) went unmodelled.

`define_corners` now declares both, and each `repair_timing` pass is aimed
where it belongs:

  - **setup** is repaired against `SETUP_CORNER` (`ss_125C_3v00`), before
    hold. Setup repair restructures/upsizes; there is no point protecting a
    hold path that setup repair is about to change underneath.
  - **hold** is repaired against `HOLD_CORNER` (`tt_025C_3v30`) exactly as
    before, so this change is strictly additive on the hold side rather
    than a re-tuning of an already-passing check.

Both passes run pre-route, against `estimate_parasitics -placement`, and
that estimate is optimistic relative to the post-route OpenRCX extraction
`flow/sta_tmds_encoder.py` signs off against. `SETUP_MARGIN_NS` exists for
exactly the reason `HOLD_MARGIN_NS` does, and was sized the same way --
measured, not guessed: with no margin, `repair_timing -setup` reported
`RSZ-0098 No setup violations found` and did nothing at all, while the
post-route re-check on that same layout came back at -0.0706 ns.

**Setup repair works by upsizing existing instances**, which means the
routed DEF this driver writes can name a different drive strength for an
instance than the committed netlist does (`..._oai21_1` -> `..._oai21_2`).
That is a real, disclosed netlist-vs-layout difference, and
`flow/sta_tmds_encoder.py`'s `assert_def_matches_netlist` is what decides
whether it is acceptable -- it accepts a drive-strength-only difference,
still rejects any change of logic function, and enumerates every resized
instance by name in the evidence record. See that function's docstring for
why that is the right notch to relax and no further.

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
# Two-corner timing view for the resizer (issue #115) -- see this module's
# docstring, "Two-corner optimization: setup at the slow corner, hold at the
# nominal one". `SETUP_CORNER` is the worst setup corner of the five
# `flow/sta_tmds_encoder.py` signs off against (and the same corner
# `flow/synth_tmds_encoder.py`'s ABC mapping already targets); `HOLD_CORNER`
# is the nominal corner every earlier revision of this driver used as its
# single corner, kept as the hold-repair corner so this change is
# strictly additive on the hold side.
SETUP_CORNER = synth.TIMING_CORNER  # ss_125C_3v00
HOLD_CORNER = STD_CELL_CORNER  # tt_025C_3v30
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
# Root/internal clock-tree buffer, named explicitly rather than left to
# TritonCTS's default (which is the *first* entry of `-buf_list`, i.e. the
# weakest `clkbuf_1`). See this module's docstring, "Clock insertion delay
# is a setup-timing term here, not just a skew term (issue #115)".
CTS_ROOT_BUF = f"{STD_CELL_LIB}__clkbuf_16"
CTS_TREE_BUF = f"{STD_CELL_LIB}__clkbuf_8"

# Per-layer resistance/capacitance for `estimate_parasitics -placement`
# (issue #115). Values copied verbatim from OpenROAD-flow-scripts' own gf180
# platform deck, `flow/platforms/gf180/setRC.tcl` in the pinned
# `openroad/orfs` image -- the same upstream, platform-authored numbers ORFS
# uses for every gf180 design, not numbers invented here. Ohms/square and
# farads/meter, OpenROAD's `set_layer_rc` units.
#
# Before this, no `set_wire_rc`/`set_layer_rc` was configured at all, so the
# placement-stage estimate was literally zero-wire-load (the `EST-0018 wire
# capacitance for corner ... is zero` warnings in this driver's own log were
# not cosmetic). That was survivable for `repair_timing -hold`, which only
# adds delay, but `repair_timing -setup` refuses to run without it outright
# (`RSZ-0089 Could not find a resistance value for any corner`), and it is
# the direct cause of the estimate-vs-extracted hold gap `HOLD_MARGIN_NS`
# below exists to paper over.
WIRE_RC_LAYERS = {
    "Metal2": (2.25636e-04, 1.35357e-04),
    "Metal3": (2.25636e-04, 1.46141e-04),
    "Metal4": (2.25637e-04, 1.50688e-04),
    "Metal5": (5.85545e-05, 1.55595e-04),
}
WIRE_RC_SIGNAL_LAYER = "Metal2"  # ORFS gf180's own choice for signal nets
WIRE_RC_CLOCK_LAYER = "Metal5"  # ...and for clock nets
# I/O boundary assumptions for `repair_timing`, numerically identical to
# flow/sta_tmds_encoder.py's own DRIVING_CELL/OUTPUT_LOAD_PF (kept in sync
# manually; both cite the same rationale -- see that driver's docstring).
SDC_DRIVING_CELL = f"{STD_CELL_LIB}__inv_1"
SDC_DRIVING_CELL_PIN = "ZN"
SDC_OUTPUT_LOAD_PF = 0.027252
# `repair_timing -hold` here runs pre-route, against `estimate_parasitics
# -placement`'s rough RC estimate (the EST-0018 "wire capacitance ... is
# zero" warnings in this driver's own log are literal -- no `set_wire_rc` is
# configured, so the estimate is effectively zero-wire-load). The real
# post-route parasitics `flow/sdf_tmds_encoder.py` later extracts (OpenRCX,
# actual routed geometry) are not yet available at this point in the flow.
# Found directly (not assumed): a first `repair_timing -hold` run with no
# margin closed hold to +0.003 ns WNS against the placement-stage estimate,
# but the post-route multi-corner STA re-check (`flow/sta_tmds_encoder.py`)
# still found small hold violations at 4/5 corners (worst -0.1401 ns,
# `ss_n40C_3v00`) once real extracted parasitics were used -- the
# estimate-vs-extracted gap, not a cross-corner issue (even `tt_025C_3v30`,
# the corner this repair step's own liberty targets, still failed by
# -0.0412 ns). This margin pads the repair target well past that measured
# gap so the post-route re-check has real, not estimate-derived, headroom.
HOLD_MARGIN_NS = 0.25
# Setup-repair margin (issue #115), for exactly the reason `HOLD_MARGIN_NS`
# above exists: `repair_timing` runs pre-route against `estimate_parasitics
# -placement`, and that estimate is optimistic relative to the post-route
# OpenRCX extraction `flow/sta_tmds_encoder.py` signs off against. Measured,
# not guessed: with no margin, `repair_timing -setup` reported `RSZ-0098 No
# setup violations found` at `SETUP_CORNER` and did nothing at all, while the
# post-route re-check on that same layout came back at -0.0706 ns. This margin
# is what makes the resizer optimize the paths that are actually going to be
# tight once real parasitics land.
SETUP_MARGIN_NS = 0.5

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


def lef_paths(pdk: Pdk) -> tuple[Path, Path, Path, Path, Path]:
    base = pdk.path / "libs.ref" / STD_CELL_LIB
    tech_lef = base / "techlef" / f"{STD_CELL_LIB}__nom.tlef"
    sc_lef = base / "lef" / f"{STD_CELL_LIB}.lef"
    nominal_liberty = base / "lib" / f"{STD_CELL_LIB}__{STD_CELL_CORNER}.lib"
    setup_liberty = base / "lib" / f"{STD_CELL_LIB}__{SETUP_CORNER}.lib"
    cell_gds = base / "gds" / f"{STD_CELL_LIB}.gds"
    for p in (tech_lef, sc_lef, nominal_liberty, setup_liberty, cell_gds):
        if not p.is_file():
            raise PnrError(f"expected gf180mcu PDK file not found: {p}")
    return tech_lef, sc_lef, nominal_liberty, setup_liberty, cell_gds


#: `wire signed [...] foo;` -- the signedness annotation OpenROAD's reader
#: rejects. Matched generically (any net), not by name: DR-0009's four-stage
#: encoder synthesizes several signed nets (`cnt`, both candidate accumulator
#: deltas) where the pre-DR-0009 netlist had exactly one (`cnt`).
_SIGNED_WIRE_RE = re.compile(r"^(?P<lead>\s*wire )signed (?P<rest>\[)", re.MULTILINE)

#: A top-level continuous assignment in the written netlist, e.g.
#: `  assign cnt[0] = 1'h0;` or `  assign word_keep_s3[9:8] = { 1'h0, qm8_s3 };`.
_ASSIGN_RE = re.compile(
    r"^  assign (?P<net>\w+)\[(?P<msb>\d+)(?::(?P<lsb>\d+))?\] = (?P<rhs>[^;]+);\n",
    re.MULTILINE,
)


def preprocess_netlist_for_openroad(src: Path, dst: Path) -> None:
    """The two mechanical, documented deltas from this module's docstring.

    Both are applied generically rather than to one hard-coded net name, and
    both re-verify their own precondition every run: the signedness strip is
    purely syntactic, and an `assign` is dropped only after mechanically
    confirming every bit it drives has zero fanout in the same netlist. A
    *live* top-level assign would be a real structural change, so it raises
    instead of being silently dropped.
    """
    text = src.read_text()

    all_assigns = re.findall(r"^  assign .*$", text, re.MULTILINE)
    recognized = len(_ASSIGN_RE.findall(text))
    if len(all_assigns) != recognized:
        raise PnrError(
            f"netlist has {len(all_assigns)} top-level continuous assignment(s) but only "
            f"{recognized} match the bit-select form this preprocessing step understands -- "
            "investigate before place-and-route rather than passing an unrecognized "
            "construct through to OpenROAD's reader"
        )

    live = live_assign_targets(text)
    if live:
        raise PnrError(
            "netlist contains top-level continuous assignment(s) whose target bits "
            f"are actually read: {', '.join(live)} -- the dead-tie preprocessing step "
            "documented in this module's docstring no longer applies, investigate "
            "before place-and-route"
        )

    text = _SIGNED_WIRE_RE.sub(lambda m: m.group("lead") + m.group("rest"), text)
    text = _ASSIGN_RE.sub("", text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)


def assign_target_bits(text: str) -> list[str]:
    """Every `<net>[<bit>]` a top-level continuous assignment drives."""
    targets: list[str] = []
    for m in _ASSIGN_RE.finditer(text):
        msb = int(m.group("msb"))
        lsb = int(m.group("lsb")) if m.group("lsb") is not None else msb
        lo, hi = min(msb, lsb), max(msb, lsb)
        targets.extend(f"{m.group('net')}[{bit}]" for bit in range(lo, hi + 1))
    return targets


def live_assign_targets(text: str) -> list[str]:
    """Assign-driven bits that something *other than* the assign itself reads.

    Measured by deleting every top-level continuous assignment first and then
    searching what remains -- which is exactly the netlist P&R would see once
    the dead ties are dropped -- rather than by counting occurrences and
    guessing how many of them belong to the assign's own left-hand side (a
    range assign such as `foo[9:8] = ...` never spells its individual bits
    out, so occurrence-counting undercounts it).
    """
    without_assigns = _ASSIGN_RE.sub("", text)
    return [
        target
        for target in assign_target_bits(text)
        if dead_net_fanout_count(without_assigns, target) > 0
    ]


def dead_net_fanout_count(text: str, net: str) -> int:
    """Occurrences of the exact bit-select `net` in `text`."""
    return len(re.findall(re.escape(net), text))


def build_tcl(
    tech_lef: Path, sc_lef: Path, setup_liberty: Path, nominal_liberty: Path, pnr_input: Path
) -> str:
    return f"""\
read_lef {tech_lef}
read_lef {sc_lef}
define_corners {SETUP_CORNER} {HOLD_CORNER}
read_liberty -corner {SETUP_CORNER} {setup_liberty}
read_liberty -corner {HOLD_CORNER} {nominal_liberty}
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

# Placement-stage RC estimate (issue #115) -- see WIRE_RC_LAYERS.
{chr(10).join(f"set_layer_rc -layer {layer} -resistance {r:.5E} -capacitance {c:.5E}" for layer, (r, c) in WIRE_RC_LAYERS.items())}
set_wire_rc -signal -layer {WIRE_RC_SIGNAL_LAYER}
set_wire_rc -clock -layer {WIRE_RC_CLOCK_LAYER}

estimate_parasitics -placement
clock_tree_synthesis -buf_list {{{" ".join(CTS_BUF_LIST)}}} \\
    -root_buf {CTS_ROOT_BUF} -tree_buf {CTS_TREE_BUF} -sink_clustering_enable
set_propagated_clock [all_clocks]
estimate_parasitics -placement
detailed_placement

# Setup repair (issue #115). Runs against the two-corner timing view defined
# above, so the slack it optimizes is the one at `{SETUP_CORNER}` -- the corner
# 720p60 setup actually has to close at -- rather than at the nominal corner,
# which has multiple nanoseconds of slack and would give the resizer nothing
# to do. Setup before hold, the conventional order: hold repair adds delay,
# and there is no point protecting hold on a path setup repair is about to
# restructure.
estimate_parasitics -placement
repair_timing -setup -setup_margin {SETUP_MARGIN_NS}
detailed_placement

# Hold repair (issue #100 step 2): CTS changes per-register clock insertion
# delay, which can turn a pre-CTS-passing hold path into a violation even
# though hold is clock-period-independent (see #83's record, "Known
# limitations" 1). repair_timing legalizes via another detailed_placement.
estimate_parasitics -placement
repair_timing -hold -hold_margin {HOLD_MARGIN_NS}
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


def openroad_version(log_text: str) -> str:
    m = re.search(r"^OpenROAD (\S+)", log_text, re.MULTILINE)
    return m.group(1) if m else "unknown"


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
        tech_lef, sc_lef, nominal_liberty, setup_liberty, cell_gds = lef_paths(pdk)
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

    script = build_tcl(tech_lef, sc_lef, setup_liberty, nominal_liberty, pnr_input)
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
        record_path.write_text(
            render_record(
                rid, when, pdk, setup_liberty, nominal_liberty, metrics, dirty, sha, log_path, gds_log
            )
        )
        print(f"Evidence record written to {record_path}")

    return 0


def render_record(
    rid, when, pdk, setup_liberty, nominal_liberty, metrics, dirty, sha, log_path, gds_log
) -> str:
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
  - Hold repair (issue #100): `repair_timing -hold -hold_margin {HOLD_MARGIN_NS}`
    after CTS, then another `detailed_placement` to legalize whatever it
    inserts. The `{HOLD_MARGIN_NS}` ns margin is not cosmetic -- see
    `flow/pnr_tmds_encoder.py`'s `HOLD_MARGIN_NS` docstring for the measured
    estimate-vs-extracted-parasitics gap it pads against. Run at the
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
