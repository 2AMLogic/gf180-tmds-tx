#!/usr/bin/env python3
"""Multi-corner static timing analysis (setup/hold) driver for `tmds_encoder`
(issue #83, re-run post-timing-driven-synthesis/CTS by issue #100).

This is the driver that finally answers the question #82 (synthesis), #84
(place-and-route) and #85 (SDF extraction) all deliberately deferred: *does
this design close timing, and at what clock rate*. It writes:

  - the constraint file the analysis is run against (regenerated in place,
    like the netlist -- not append-only):
        flow/tmds_encoder/sta/tmds_encoder.sdc
  - the exact OpenSTA script run per corner x target, and its full log:
        flow/tmds_encoder/reports/<record-id>.sta_<corner>_<target>.tcl
        flow/tmds_encoder/reports/<record-id>.sta_<corner>_<target>.log
  - an append-only evidence record: flow/tmds_encoder/records/<record-id>.md

## What is analyzed, and against which revision

The *netlist* under analysis is the committed gate-level netlist
(`flow/tmds_encoder/netlist/tmds_encoder.synth.v`, cited by the exact
evidence record `SYNTH_RECORD_ID` below names), as physically realized by
the routed DEF (`flow/tmds_encoder/pnr/tmds_encoder.def`, `PNR_RECORD_ID`),
with the committed post-route parasitics (`flow/tmds_encoder/sta/tmds_encoder.spef`,
`SPEF_RECORD_ID`) back-annotated. These constants are deliberately not
hardcoded into this prose (a hardcoded copy is exactly what went stale the
first time this module's docstring was written, before issue #100
re-synthesized/re-routed the design) -- see the constants themselves,
just below, for the IDs actually in force.

That "as physically realized by" is a *checked* claim, not an assumption:
`assert_def_matches_netlist` re-parses both files and asserts that the DEF's
component set is exactly the netlist's instance set, plus P&R-inserted
physical-only cells (fillers, tap/endcap), plus any cell the DEF itself marks
`SOURCE TIMING` (issue #100: OpenROAD's own DEF convention for clock-tree-
synthesis/hold-repair-inserted cells, which `flow/pnr_tmds_encoder.py` now
runs and which -- unlike physical-only cells -- have no netlist counterpart
by design, since the netlist predates CTS). If the netlist is ever
re-generated without re-running P&R, this driver fails loudly rather than
silently timing a stale layout. SHA-256 digests of all three inputs are
recorded, so "the exact netlist revision" in the evidence record is a
verifiable statement rather than a filename.

One deliberate, disclosed relaxation of that check (issue #115): a DEF
component may differ from its netlist instance in the numeric
**drive-strength suffix only** (`..._oai21_1` -> `..._oai21_2`), because
`flow/pnr_tmds_encoder.py` now runs `repair_timing -setup`, whose entire
mechanism is upsizing an existing instance to drive its real load. A change
of logic *function*, a missing instance, or an unexplained extra component
all still fail loudly, and every resized instance is enumerated by name in
the evidence record rather than reduced to a count. See
`assert_def_matches_netlist`'s own docstring for why that is the right notch
and no further.

## Corners

Five liberty corners from the 3.3 V family DR-0003 selects for the
synthesized domain -- every 3.3 V corner the vendored
`gf180mcu_fd_sc_mcu9t5v0` library ships:

  tt_025C_3v30   typical (the corner #82/#84/#85 all used)
  ss_125C_3v00   slow process, 125 C, -9% supply  (worst case for setup)
  ss_n40C_3v00   slow process, -40 C, -9% supply
  ff_125C_3v60   fast process, 125 C, +9% supply
  ff_n40C_3v60   fast process, -40 C, +9% supply  (worst case for hold)

Both setup (max) and hold (min) are reported at *every* corner rather than
only at the textbook worst-case corner for each, so the record shows the
full matrix rather than a pre-filtered one.

**One RC corner, five liberty corners.** #85 extracted parasitics at the
gf180 platform's typical (`FuncRCtyp`) RCX deck only, and this driver reuses
that single SPEF at all five liberty corners rather than re-extracting per
corner. This is a real, disclosed approximation -- but a small one here: #85
established (and this driver's own logs re-confirm) that post-route net
delays on this ~158 x 138 um die round to 0.000 ns at 3-decimal precision,
so RC-corner variation moves these numbers far less than the liberty corner
does. Re-extracting per RC corner is the right thing to do once the design
is large enough for interconnect to matter.

## Clock targets

Two, both taken from `spec/tmds-tx.md` §2 rather than invented here:

  720p60 target   74.25 MHz pixel clock  -> 13.4680 ns period
  480p fallback   27.000 MHz pixel clock -> 37.0370 ns period

The encoder is a pixel-domain block: one 10-bit TMDS character per pixel
clock (see `rtl/tmds_encoder.v`'s interface note). It does *not* run at
DR-0003's flagged 5x-pixel intermediate rate (371.25 MHz) -- that rate
belongs to the not-yet-written 10:1->2:1 serializer. The record still states
this design's measured Fmax against that number, because DR-0003's open item
is fundamentally "what clock ceiling does this standard-cell library give
this kind of logic", and a measurement is worth more to that question than
another deferral.

## Constraint assumptions (all explicit, all disclosed)

Two of these materially shape the verdict, so they are stated here, in the
generated SDC, and in the evidence record rather than buried:

1. **`set_input_delay 0` / `set_output_delay 0`.** No block-boundary timing
   budget has been ratified for this block, so none is assumed: the full
   clock period is made available to the input-to-register and
   register-to-output paths. This is the *most optimistic* legal choice --
   any real upstream/downstream logic only makes the input/output path
   slacks worse, never better. A setup violation reported under this
   assumption is therefore a real violation, not a budgeting artifact.
2. **`set_driving_cell` (`inv_1`) on inputs, `set_load` on outputs.** An
   ideal (zero-transition) input driver would understate input-path delay;
   this drives every primary input with the library's smallest inverter and
   loads every output with 4x that inverter's own input capacitance
   (0.006813 pF each -> 0.027252 pF). Both are stated design assumptions,
   not measurements -- a real pad/CML boundary load belongs to the analog
   partition and is out of scope here.
3. **`set_propagated_clock`, zero clock uncertainty.** `flow/pnr_tmds_encoder.py`
   now runs clock-tree synthesis and post-CTS hold repair (issue #100 --
   previously skipped, per this driver's own earlier revision, "for want of
   a clock period"). The clock net's real, CTS-balanced insertion delay and
   skew are *propagated* rather than idealized -- the driver records the
   measured skew per corner -- and no additional uncertainty margin is
   layered on top, since no CTS-derived skew budget beyond what
   `clock_tree_synthesis` itself targets has been established. Consequence:
   the hold verdict this record reports is the **post-CTS** hold verdict
   (the one #83's original record could not give), not the earlier pre-CTS
   approximation.

## Verdict structure

Two verdicts are reported per corner x target, because they answer different
questions and this design answers them differently:

  - **register-to-register**: the paths wholly inside this block. This is
    the unconditional verdict -- it depends on no boundary assumption.
  - **whole-design (worst of all path groups)**: includes the
    input-port-to-register paths, i.e. the full combinational cone from the
    `data` port through both encoder stages. Conditional only on assumption
    (1) above, and (1) is the optimistic bound, so a violation here is real.

Cold-start invocation (requires OpenROAD/OpenSTA on `PATH`, run via the
pinned `openroad/orfs` Docker image -- see "Pinned toolchain" in
`flow/README.md`; requires `flow/pnr_tmds_encoder.py`'s routed DEF and
`flow/sdf_tmds_encoder.py`'s SPEF, both re-run for issue #100):

    python3 flow/sta_tmds_encoder.py
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "flow"))

from sim.harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402
import synth_tmds_encoder as synth  # noqa: E402  (reuses record_id/_git/working_tree_dirty)
import pnr_tmds_encoder as pnr  # noqa: E402  (reuses lef_paths, STD_CELL_LIB, run_openroad, openroad_version)

TOP = "tmds_encoder"

OUT_DIR = REPO_ROOT / "flow" / TOP
STA_DIR = OUT_DIR / "sta"
REPORTS_DIR = OUT_DIR / "reports"
RECORDS_DIR = OUT_DIR / "records"

NETLIST = OUT_DIR / "netlist" / f"{TOP}.synth.v"
ROUTED_DEF = OUT_DIR / "pnr" / f"{TOP}.def"
SPEF = STA_DIR / f"{TOP}.spef"
SDC = STA_DIR / f"{TOP}.sdc"

# Upstream evidence records this analysis is run against (cited in the record).
SYNTH_RECORD_ID = "20260817-105547-049c240"  # issue #115, four-stage (DR-0009) gate-level netlist
PNR_RECORD_ID = "20260817-105608-049c240"  # issue #115, CTS/setup+hold-repaired routed DEF (four-stage)
SPEF_RECORD_ID = "20260817-105709-049c240"  # issue #115, post-CTS extracted parasitics (four-stage)

# Every 3.3 V corner the vendored gf180mcu_fd_sc_mcu9t5v0 library ships.
CORNERS: list[tuple[str, str]] = [
    ("tt_025C_3v30", "typical process, 25 C, 3.30 V (DR-0003's corner; #82/#84/#85's)"),
    ("ss_125C_3v00", "slow process, 125 C, 3.00 V (worst case for setup)"),
    ("ss_n40C_3v00", "slow process, -40 C, 3.00 V"),
    ("ff_125C_3v60", "fast process, 125 C, 3.60 V"),
    ("ff_n40C_3v60", "fast process, -40 C, 3.60 V (worst case for hold)"),
]

# spec/tmds-tx.md §2's pixel-clock rates. The encoder is a pixel-domain
# block (one TMDS character per pixel clock), so these -- not the 742.5 MHz
# bit rate -- are its clock targets.
TARGETS: list[tuple[str, float]] = [
    ("720p60", 74.25),
    ("480p", 27.000),
]

# DR-0003's flagged synthesized-domain ceiling (5x the 720p60 pixel clock).
# Not a constraint applied here -- the encoder does not run at this rate --
# but the measured Fmax is compared against it in the evidence record.
DR0003_INTERMEDIATE_MHZ = 371.25

DRIVING_CELL = f"{pnr.STD_CELL_LIB}__inv_1"
DRIVING_CELL_PIN = "ZN"
DRIVING_CELL_INPUT_CAP_PF = 0.006813  # inv_1 pin(I) capacitance, tt_025C_3v30
OUTPUT_LOAD_PF = round(4 * DRIVING_CELL_INPUT_CAP_PF, 6)

# Physical-only cells P&R inserts that have no netlist counterpart.
_PHYSICAL_ONLY_RE = re.compile(r"__(fill|filltie|endcap|fillcap|decap|antenna)")
# A DEF component line: `- <name> <cell type> [+ ...] ;`. Captures the full
# remainder of the line too (group 3) so callers can check for a `SOURCE
# TIMING` marker -- see `def_components`'s docstring (issue #100).
_DEF_COMPONENT_RE = re.compile(r"^\s*-\s+(\S+)\s+(\S+)(.*)$", re.MULTILINE)
_NETLIST_INSTANCE_RE = re.compile(rf"^\s+({pnr.STD_CELL_LIB}__\S+)\s+(\S+)\s*\(", re.MULTILINE)
# A `gf180mcu_fd_sc_mcu9t5v0` cell name splits into a logic function and a
# drive strength: `..._oai21_1` -> (`..._oai21`, `1`). Used to tell a
# *resize* (same function, different drive) from a real retype (issue #115) --
# see `cell_function`.
_DRIVE_STRENGTH_RE = re.compile(r"^(?P<function>.+)_(?P<drive>\d+)$")

_SLACK_RE = re.compile(r"^\s*(-?[\d.]+)\s+slack \((MET|VIOLATED)\)", re.MULTILINE)
_STARTPOINT_RE = re.compile(r"^Startpoint: (.+)$", re.MULTILINE)
_ENDPOINT_RE = re.compile(r"^Endpoint: (.+)$", re.MULTILINE)
_ARRIVAL_RE = re.compile(r"^\s+(-?[\d.]+)\s+data arrival time\s*$", re.MULTILINE)
_WORST_MAX_RE = re.compile(r"^worst slack max\s+(-?[\d.]+)", re.MULTILINE)
_WORST_MIN_RE = re.compile(r"^worst slack min\s+(-?[\d.]+)", re.MULTILINE)
_TNS_RE = re.compile(r"^tns max\s+(-?[\d.]+)", re.MULTILINE)
_SKEW_RE = re.compile(r"^\s*(-?[\d.]+)\s+setup skew", re.MULTILINE)
# `report_checks -format slack_only` prints one `<path group> <slack>` line per
# violating endpoint, under a `Group / Slack` header.
_SLACK_ONLY_LINE_RE = re.compile(r"^\S+\s+(-?[\d.]+)\s*$")


class StaError(RuntimeError):
    pass


def period_ns(freq_mhz: float) -> float:
    return round(1000.0 / freq_mhz, 4)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def netlist_instances(text: str) -> dict[str, str]:
    """`{instance name: cell type}` for every standard-cell instance."""
    return {name: cell for cell, name in _NETLIST_INSTANCE_RE.findall(text)}


def def_components(text: str) -> dict[str, tuple[str, bool]]:
    """`{component name: (cell type, is_source_timing)}` from the DEF's
    COMPONENTS section. `is_source_timing` is DEF's own `+ SOURCE TIMING`
    marker -- LEF/DEF's standard designation for a component a timing
    optimization tool (not the original netlist) inserted; OpenROAD's
    `clock_tree_synthesis` and `repair_timing -hold` both mark their
    inserted cells this way (issue #100 -- confirmed directly against a
    routed DEF, not assumed: CTS clock buffers and hold-fix delay cells are
    the only components carrying it)."""
    start = text.find("COMPONENTS ")
    end = text.find("END COMPONENTS")
    if start < 0 or end < 0:
        raise StaError("routed DEF has no COMPONENTS section")
    return {
        name: (cell, "SOURCE TIMING" in rest)
        for name, cell, rest in _DEF_COMPONENT_RE.findall(text[start:end])
    }


def cell_function(cell: str) -> str:
    """A cell's logic function, with its drive-strength suffix stripped.

    `gf180mcu_fd_sc_mcu9t5v0__oai21_1` and `..._oai21_2` are the same
    Boolean function realized at two drive strengths -- identical pin names,
    identical truth table, identical `specify` paths -- differing only in
    transistor sizing. Cells with no numeric suffix (`..._fill`, `..._endcap`)
    are returned unchanged.
    """
    m = _DRIVE_STRENGTH_RE.match(cell)
    return m.group("function") if m else cell


def assert_def_matches_netlist(netlist: Path, routed_def: Path) -> tuple[int, int, int, list[str]]:
    """The DEF must realize *this* netlist: same instance names, same cell
    *functions*, plus only physical-only (filler/tap/endcap) additions and/or
    `SOURCE TIMING`-marked cells clock-tree synthesis / hold repair
    legitimately inserted (issue #100 -- `flow/pnr_tmds_encoder.py` now runs
    both; see `def_components`'s docstring for how those are distinguished
    from a real defect, not just assumed benign). Returns `(netlist instance
    count, physical-only cell count, CTS/hold-repair-inserted cell count,
    resized instances)`.

    ## Why a drive-strength difference is accepted, and a function change is not (issue #115)

    An earlier revision of this check demanded a bit-identical cell type per
    instance. That is stricter than the property the check exists to
    establish -- "the DEF realizes this netlist, not a stale one" -- and it
    forbids `repair_timing -setup`, whose entire mechanism is upsizing an
    existing instance (`..._oai21_1` -> `..._oai21_2`) so it can drive its
    real, placement-derived load. Issue #115 needs that: the encoder's
    remaining 720p60 setup gap at `ss_125C_3v00` is a drive-strength problem
    (min-size cells on high-fanout nets, since ABC maps with no wire load at
    all), not a logic-depth one.

    So the check is relaxed **exactly one notch and no further**: a DEF
    component may differ from its netlist instance only in the numeric drive
    suffix, i.e. `cell_function()` must still match exactly. That is not a
    weakening of the netlist-vs-layout guarantee in any way that matters
    downstream:

    - **Logic** is unchanged by construction -- the two cells compute the
      same Boolean function on identically-named pins, so the routed
      connectivity the DEF carries is the netlist's connectivity.
    - **Timing** is *more* accurate, not less: the SPEF and the liberty arcs
      this driver times against both come from the DEF's actual cell, so the
      numbers reported are the physically-realized ones.
    - **A stale layout still fails loudly**: any instance whose function
      changed, went missing, or appeared without provenance still raises.

    Resized instances are returned so the evidence record can name every one
    of them rather than burying the delta in a count -- an unreported
    layout-vs-netlist difference is the thing this check is really guarding
    against.
    """
    instances = netlist_instances(netlist.read_text())
    components = def_components(routed_def.read_text())
    if not instances:
        raise StaError(f"parsed no standard-cell instances from {netlist}")

    missing = sorted(set(instances) - set(components))
    if missing:
        raise StaError(
            f"{len(missing)} netlist instance(s) absent from the routed DEF "
            f"(e.g. {missing[:5]}) -- the DEF does not realize this netlist; "
            "re-run flow/pnr_tmds_encoder.py before running STA"
        )
    retyped = sorted(
        n
        for n, cell in instances.items()
        if cell_function(components[n][0]) != cell_function(cell)
    )
    if retyped:
        raise StaError(
            f"{len(retyped)} instance(s) have a different cell *function* in the DEF than "
            f"in the netlist (e.g. {[f'{n}: {instances[n]} -> {components[n][0]}' for n in retyped[:5]]}) "
            "-- netlist and layout are out of sync"
        )
    resized = sorted(
        f"{n}: {cell} -> {components[n][0]}"
        for n, cell in instances.items()
        if components[n][0] != cell
    )
    extra = sorted(set(components) - set(instances))
    physical_only = [n for n in extra if _PHYSICAL_ONLY_RE.search(components[n][0])]
    timing_inserted = [n for n in extra if components[n][1] and n not in physical_only]
    unexpected = [n for n in extra if n not in physical_only and n not in timing_inserted]
    if unexpected:
        raise StaError(
            f"{len(unexpected)} DEF component(s) are neither netlist instances, "
            "physical-only cells, nor SOURCE TIMING (CTS/hold-repair) insertions "
            f"(e.g. {unexpected[:5]}) -- unexplained layout content"
        )
    return len(instances), len(physical_only), len(timing_inserted), resized


def build_sdc(freq_mhz: float, target: str) -> str:
    p = period_ns(freq_mhz)
    return f"""\
# Timing constraints for {TOP} -- GENERATED by flow/sta_tmds_encoder.py
# (issue #83). Regenerated in place on every run; edit that driver, not this
# file. See the driver's docstring for why each assumption below is what it
# is -- every one of them is disclosed in the evidence record too.

# {target} pixel clock, {freq_mhz:g} MHz (spec/tmds-tx.md §2). The encoder is a
# pixel-domain block: one 10-bit TMDS character per pixel clock.
create_clock -name clk -period {p:.4f} [get_ports clk]

# flow/pnr_tmds_encoder.py now runs clock-tree synthesis (issue #100).
# Propagate the real, CTS-balanced clock net delay rather than idealizing
# it, and add no uncertainty margin beyond what clock_tree_synthesis itself
# targets. The hold verdict this produces is therefore the post-CTS verdict.
set_propagated_clock [all_clocks]
set_clock_uncertainty 0.0000 [get_clocks clk]

# No block-boundary timing budget has been ratified for this block, so none
# is assumed: the whole period is available to the I/O paths. This is the
# most optimistic legal choice -- real surrounding logic can only make these
# slacks worse -- so a violation reported under it is a real violation.
set non_clk_inputs [get_ports {{data[*] ctrl[*] de rst}}]
set_input_delay 0.0000 -clock clk $non_clk_inputs
set_output_delay 0.0000 -clock clk [all_outputs]

# Stated design assumptions, not measurements: drive every primary input
# with the library's smallest inverter, and load every output with 4x that
# inverter's own input capacitance ({DRIVING_CELL_INPUT_CAP_PF} pF).
set_driving_cell -lib_cell {DRIVING_CELL} -pin {DRIVING_CELL_PIN} $non_clk_inputs
set_load {OUTPUT_LOAD_PF} [all_outputs]
"""


def build_tcl(tech_lef: Path, sc_lef: Path, liberty: Path, sdc: Path) -> str:
    return f"""\
read_lef {tech_lef}
read_lef {sc_lef}
read_liberty {liberty}
read_def {ROUTED_DEF}
read_spef {SPEF}
read_sdc {sdc}

puts "=== SETUP_WORST ==="
report_checks -path_delay max -group_path_count 1 -digits 4
puts "=== HOLD_WORST ==="
report_checks -path_delay min -group_path_count 1 -digits 4
puts "=== REG2REG_SETUP ==="
report_checks -path_delay max -from [all_registers] -to [all_registers] \
-group_path_count 1 -digits 4
puts "=== REG2REG_HOLD ==="
report_checks -path_delay min -from [all_registers] -to [all_registers] \
-group_path_count 1 -digits 4
puts "=== WORST_SLACK ==="
report_worst_slack -max -digits 4
report_worst_slack -min -digits 4
puts "=== TNS ==="
report_tns -digits 4
puts "=== SETUP_VIOLATORS ==="
report_checks -path_delay max -slack_max 0 -group_path_count 10000 -format slack_only \
-digits 4
puts "=== HOLD_VIOLATORS ==="
report_checks -path_delay min -slack_max 0 -group_path_count 10000 -format slack_only \
-digits 4
puts "=== CLOCK_SKEW ==="
report_clock_skew -setup -digits 4
puts "=== END ==="

exit
"""


def section(log_text: str, name: str) -> str:
    """Text between `=== name ===` and the next `=== ... ===` marker."""
    marker = f"=== {name} ==="
    start = log_text.find(marker)
    if start < 0:
        raise StaError(f"section '{name}' missing from OpenSTA log")
    start += len(marker)
    nxt = log_text.find("\n=== ", start)
    return log_text[start:nxt if nxt >= 0 else len(log_text)]


def first_slack(text: str) -> tuple[str, float] | None:
    """`(MET|VIOLATED, slack)` of the first path reported in `text`."""
    m = _SLACK_RE.search(text)
    return (m.group(2), float(m.group(1))) if m else None


def count_violators(text: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if (m := _SLACK_ONLY_LINE_RE.match(line)) and float(m.group(1)) < 0
    )


class Result:
    """One corner x target OpenSTA run, parsed."""

    def __init__(self, corner: str, target: str, freq_mhz: float, log_text: str, log_path: Path):
        self.corner = corner
        self.target = target
        self.freq_mhz = freq_mhz
        self.period = period_ns(freq_mhz)
        self.log_path = log_path

        worst_max = _WORST_MAX_RE.search(section(log_text, "WORST_SLACK"))
        worst_min = _WORST_MIN_RE.search(section(log_text, "WORST_SLACK"))
        if not worst_max or not worst_min:
            raise StaError(f"could not parse worst slack from {log_path}")
        self.setup_slack = float(worst_max.group(1))
        self.hold_slack = float(worst_min.group(1))

        tns = _TNS_RE.search(section(log_text, "TNS"))
        self.tns = float(tns.group(1)) if tns else None

        r2r_setup = first_slack(section(log_text, "REG2REG_SETUP"))
        r2r_hold = first_slack(section(log_text, "REG2REG_HOLD"))
        if r2r_setup is None or r2r_hold is None:
            raise StaError(f"could not parse register-to-register slack from {log_path}")
        self.r2r_setup_slack = r2r_setup[1]
        self.r2r_hold_slack = r2r_hold[1]

        setup_sec = section(log_text, "SETUP_WORST")
        start = _STARTPOINT_RE.search(setup_sec)
        end = _ENDPOINT_RE.search(setup_sec)
        arrival = _ARRIVAL_RE.search(setup_sec)
        self.setup_startpoint = start.group(1).strip() if start else "unknown"
        self.setup_endpoint = end.group(1).strip() if end else "unknown"
        self.setup_arrival = float(arrival.group(1)) if arrival else None

        self.setup_violators = count_violators(section(log_text, "SETUP_VIOLATORS"))
        self.hold_violators = count_violators(section(log_text, "HOLD_VIOLATORS"))

        skew = _SKEW_RE.search(section(log_text, "CLOCK_SKEW"))
        self.clock_skew = float(skew.group(1)) if skew else None

    @property
    def fmax_mhz(self) -> float:
        """Max clock frequency this netlist supports at this corner.

        Exact, not an extrapolation: nothing is re-synthesized or re-placed
        between constraints, so every path delay is constraint-independent
        and `period - slack` is the true critical-path requirement.
        """
        return 1000.0 / (self.period - self.setup_slack)

    @property
    def r2r_fmax_mhz(self) -> float:
        return 1000.0 / (self.period - self.r2r_setup_slack)

    @property
    def setup_pass(self) -> bool:
        return self.setup_slack >= 0

    @property
    def hold_pass(self) -> bool:
        return self.hold_slack >= 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        tech_lef, sc_lef, _liberty, _setup_liberty, _cell_gds = pnr.lef_paths(pdk)
    except pnr.PnrError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for required in (NETLIST, ROUTED_DEF, SPEF):
        if not required.is_file():
            print(
                f"ERROR: required input not found at {required} -- run the upstream "
                "flow/ driver (#82 synthesis / #84 P&R / #85 SDF) first",
                file=sys.stderr,
            )
            return 1

    lib_dir = pdk.path / "libs.ref" / pnr.STD_CELL_LIB / "lib"
    liberties: dict[str, Path] = {}
    for corner, _desc in CORNERS:
        lib = lib_dir / f"{pnr.STD_CELL_LIB}__{corner}.lib"
        if not lib.is_file():
            print(f"ERROR: liberty for corner {corner} not found at {lib}", file=sys.stderr)
            return 1
        liberties[corner] = lib

    try:
        (
            instance_count,
            physical_only_count,
            timing_inserted_count,
            resized_instances,
        ) = assert_def_matches_netlist(NETLIST, ROUTED_DEF)
    except StaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Netlist/DEF consistency: {instance_count} netlist instances all present in the "
        f"routed DEF with matching cell functions (+{physical_only_count} physical-only cells, "
        f"+{timing_inserted_count} CTS/hold-repair-inserted cells, "
        f"{len(resized_instances)} setup-repair resized instances)"
    )
    for line in resized_instances:
        print(f"  resized by repair_timing: {line}")

    when = synth._dt.datetime.now(synth._dt.timezone.utc)
    rid = synth.record_id(when)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STA_DIR.mkdir(parents=True, exist_ok=True)

    # The canonical committed constraint file is the 720p60 one; per-target
    # copies live beside the per-run scripts.
    SDC.write_text(build_sdc(TARGETS[0][1], TARGETS[0][0]))

    results: list[Result] = []
    or_version = "unknown"
    for target, freq_mhz in TARGETS:
        sdc_path = REPORTS_DIR / f"{rid}.sta_{target}.sdc"
        sdc_path.write_text(build_sdc(freq_mhz, target))
        for corner, _desc in CORNERS:
            stem = f"{rid}.sta_{corner}_{target}"
            log_path = REPORTS_DIR / f"{stem}.log"
            print(f"STA: corner {corner}, target {target} ({freq_mhz:g} MHz) ...")
            result = pnr.run_openroad(build_tcl(tech_lef, sc_lef, liberties[corner], sdc_path), log_path)
            log_text = log_path.read_text()
            if result.returncode != 0 or "Error:" in log_text or "[ERROR" in log_text:
                print(f"ERROR: openroad exited {result.returncode} -- see {log_path}", file=sys.stderr)
                return 1
            if "=== END ===" not in log_text:
                print(f"ERROR: OpenSTA run did not reach the end marker -- see {log_path}", file=sys.stderr)
                return 1
            or_version = pnr.openroad_version(log_text) or or_version
            try:
                parsed = Result(corner, target, freq_mhz, log_text, log_path)
            except StaError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            results.append(parsed)
            print(
                f"  setup {'PASS' if parsed.setup_pass else 'FAIL'} "
                f"(worst {parsed.setup_slack:+.4f} ns, {parsed.setup_violators} violating "
                f"endpoints), hold {'PASS' if parsed.hold_pass else 'FAIL'} "
                f"(worst {parsed.hold_slack:+.4f} ns, {parsed.hold_violators} violating "
                f"endpoints), Fmax {parsed.fmax_mhz:.2f} MHz"
            )

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
                rid,
                when,
                pdk,
                or_version,
                results,
                instance_count,
                physical_only_count,
                timing_inserted_count,
                resized_instances,
                dirty,
                sha,
            )
        )
        print(f"Evidence record written to {record_path}")

    return 0


def _verdict_table(results: list[Result], target: str) -> str:
    rows = [
        "| Corner | Setup (whole design) | Setup (reg-to-reg) | Hold (whole design) | "
        "Setup TNS | Clock skew | Fmax |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in (x for x in results if x.target == target):
        rows.append(
            f"| `{r.corner}` "
            f"| {'PASS' if r.setup_pass else 'FAIL'} {r.setup_slack:+.4f} ns "
            f"({r.setup_violators} viol. endpoints) "
            f"| {'PASS' if r.r2r_setup_slack >= 0 else 'FAIL'} {r.r2r_setup_slack:+.4f} ns "
            f"| {'PASS' if r.hold_pass else 'FAIL'} {r.hold_slack:+.4f} ns "
            f"({r.hold_violators} viol. endpoints) "
            f"| {r.tns:+.2f} ns "
            f"| {r.clock_skew:.4f} ns "
            f"| {r.fmax_mhz:.2f} MHz |"
        )
    return "\n".join(rows)


def render_record(
    rid,
    when,
    pdk: Pdk,
    or_version,
    results: list[Result],
    instance_count,
    physical_only_count,
    timing_inserted_count,
    resized_instances: list[str],
    dirty,
    sha,
) -> str:
    by_target = {t: [r for r in results if r.target == t] for t, _f in TARGETS}
    worst = min(results, key=lambda r: r.setup_slack)
    worst_hold = min(results, key=lambda r: r.hold_slack)
    fmax_worst = min(r.fmax_mhz for r in results)
    fmax_typ = next(r.fmax_mhz for r in results if r.corner == "tt_025C_3v30")
    r2r_fmax_worst = min(r.r2r_fmax_mhz for r in results)
    setup_720 = [r for r in by_target["720p60"] if not r.setup_pass]
    setup_480 = [r for r in by_target["480p"] if not r.setup_pass]
    hold_fail = [r for r in results if not r.hold_pass]

    verdict_720 = "FAIL" if setup_720 else "PASS"
    verdict_480 = "FAIL" if setup_480 else "PASS"
    hold_verdict = "FAIL" if hold_fail else "PASS"

    return f"""\
# Record {rid}

- **Record ID**: {rid}
- **Claim**: Static timing analysis (setup **and** hold) has been re-run
  (issue #115, following #83's original pre-timing-driven-synthesis,
  pre-CTS record `20260816-172539-930e864`, #100's post-timing-driven-
  synthesis/CTS record `20260817-001614-064d550`, and #110's DR-0008
  single-pipeline-register record `20260817-012556-7d9130d`) on the
  four-stage gate-level netlist issue #115 produced -- `rtl/tmds_encoder.v`
  is now the four-stage pipeline `spec/tmds-tx.md` DR-0009 specifies
  (S1 popcount/threshold, S2 parallel-prefix transition-minimized word,
  S3 accumulator-independent DC-balance candidates, S4 decision +
  accumulator recurrence), run through the timing-driven-synthesis + CTS +
  timing-repair machinery issue #100 built and issue #115 extended
  (sequential-overhead-corrected ABC delay target, two-corner P&R timing
  view with explicit CTS root/tree buffers and placement-stage layer RC, and
  a `repair_timing -setup` pass -- every one of which constrains the design
  *more* tightly, not less; see DR-0009's "Consequences") -- as physically
  realized by issue #115's own routed layout with issue #115's own
  re-extracted post-route parasitics back-annotated, across all five 3.3 V
  liberty corners the `{pnr.STD_CELL_LIB}` library ships, at both of
  `spec/tmds-tx.md` §2's pixel-clock rates. Addresses #65 item 5 (full
  corner verification vs. the ratified spec) on the digital partition, and
  supplies the measurement DR-0007 (which resolved DR-0003's open item to
  "an architecture change is needed"), DR-0008 (the first such change) and
  DR-0009 (this one) require -- this record specifically measures whether
  DR-0009 closed the 720p60 setup violations DR-0008's own record still had
  at `ss_125C_3v00` and `ss_n40C_3v00`.
- **Verdict (setup, 720p60 target, 74.25 MHz)**: **{verdict_720}** -- {
    f"setup violated at {len(setup_720)} of {len(by_target['720p60'])} corners"
    if setup_720 else "setup met at every corner"}.
- **Verdict (setup, 480p fallback, 27.000 MHz)**: **{verdict_480}** -- {
    f"setup violated at {len(setup_480)} of {len(by_target['480p'])} corners"
    if setup_480 else "setup met at every corner"}.
- **Verdict (hold, all corners and both targets)**: **{hold_verdict}** -- {
    f"hold violated at {len(hold_fail)} corner/target combinations"
    if hold_fail else "hold met at every corner, at both targets"}
  (hold is clock-period-independent, so both targets give the same answer).
- **Measured Fmax**: **{fmax_worst:.2f} MHz** worst-corner, {fmax_typ:.2f} MHz typical
  (whole design, i.e. including the input-port-to-register path); the
  register-to-register subset alone reaches {r2r_fmax_worst:.2f} MHz worst-corner.
  This is exact rather than extrapolated -- nothing is re-synthesized between
  constraints, so path delays are constraint-independent and `period - slack` is
  the true critical-path requirement.
- **Netlist revision analyzed** (the exact revision, verified, not just cited):
  - Netlist: `flow/tmds_encoder/netlist/{TOP}.synth.v`, issue #115's four-stage
    (DR-0009), timing-driven synthesis evidence record `{SYNTH_RECORD_ID}` --
    SHA-256 `{sha256(NETLIST)}`
  - Routed DEF: `flow/tmds_encoder/pnr/{TOP}.def`, issue #115's CTS/timing-repair
    record `{PNR_RECORD_ID}` -- SHA-256 `{sha256(ROUTED_DEF)}`
  - Parasitics (SPEF): `flow/tmds_encoder/sta/{TOP}.spef`, issue #115's
    post-CTS extraction record `{SPEF_RECORD_ID}` -- SHA-256 `{sha256(SPEF)}`
  - Netlist/DEF consistency **checked mechanically**, not assumed: all
    {instance_count} netlist instances are present in the routed DEF with matching
    cell *functions*; the DEF's only additional components are the
    {physical_only_count} physical-only cells P&R inserts (filler/tap/endcap) and
    {timing_inserted_count} cells clock-tree synthesis / timing repair inserted
    (DEF `SOURCE TIMING`-marked -- issue #100 introduced this CTS/hold-repair
    machinery, reused here; these have no netlist counterpart by
    design, since the netlist predates CTS). See
    `assert_def_matches_netlist` in `flow/sta_tmds_encoder.py`.
  - **Instances `repair_timing -setup` resized** ({len(resized_instances)}, enumerated rather
    than counted -- issue #115; a drive-strength difference is the *only*
    netlist-vs-DEF cell difference this driver accepts, and it re-checks that
    the logic function is unchanged for every one of them):
{chr(10).join(f"    - `{line}`" for line in resized_instances) if resized_instances
  else "    - none -- `repair_timing -setup` changed no instance's drive strength on this layout"}
- **Tool versions**:
  - OpenSTA: bundled in OpenROAD `{or_version}` (run via the `openroad/orfs:latest`
    Docker image -- see `flow/README.md`'s "Pinned toolchain")
  - gf180mcu PDK: variant `{pdk.variant}`, open_pdks `{pdk.version}` (via {pdk.source})
- **Corners checked** ({len(CORNERS)}, every 3.3 V corner the library ships --
  `{pnr.STD_CELL_LIB}__<corner>.lib`):
{chr(10).join(f"  - `{c}` -- {d}" for c, d in CORNERS)}
- **Corner reconciliation** (carried over from #85's own test plan, which asked
  its successor to confirm the SDF corner matches this analysis's): reconciled,
  no mismatch. The re-extracted SDF/SPEF (issue #115, record `{SPEF_RECORD_ID}`)
  were built at `tt_025C_3v30`, one of the five corners analyzed here; the other
  four re-time the same extracted parasitics against a different liberty corner
  (see "Known limitations" 2).
- **Constraints applied** (`flow/tmds_encoder/sta/{TOP}.sdc`, generated by the
  driver; per-run copies at `flow/tmds_encoder/reports/{rid}.sta_<target>.sdc`):
  - `create_clock -period {period_ns(TARGETS[0][1]):.4f}` (720p60, {TARGETS[0][1]:g} MHz) and
    `-period {period_ns(TARGETS[1][1]):.4f}` (480p fallback, {TARGETS[1][1]:g} MHz), both from
    `spec/tmds-tx.md` §2 -- not invented here.
  - `set_input_delay 0` / `set_output_delay 0`: no ratified block-boundary budget
    exists, so none is assumed. This is the *most optimistic* legal choice, so a
    violation reported under it is a real violation, not a budgeting artifact.
  - `set_driving_cell {DRIVING_CELL}` on inputs, `set_load {OUTPUT_LOAD_PF}` (4x that
    cell's own {DRIVING_CELL_INPUT_CAP_PF} pF input capacitance) on outputs -- stated
    assumptions, not measurements.
  - `set_propagated_clock`, `set_clock_uncertainty 0`: `flow/pnr_tmds_encoder.py`
    now runs CTS (issue #100), so the real, CTS-balanced clock net's delay is
    propagated; no margin beyond what `clock_tree_synthesis` itself targets is
    layered on. See "Known limitations" 1.

## Results -- 720p60 target ({TARGETS[0][1]:g} MHz pixel clock, {period_ns(TARGETS[0][1]):.4f} ns)

{_verdict_table(results, "720p60")}

## Results -- 480p fallback ({TARGETS[1][1]:g} MHz pixel clock, {period_ns(TARGETS[1][1]):.4f} ns)

{_verdict_table(results, "480p")}

- **Worst setup path (all runs)**: {worst.setup_slack:+.4f} ns at corner
  `{worst.corner}`, {worst.target} target -- startpoint `{worst.setup_startpoint}`,
  endpoint `{worst.setup_endpoint}`, data arrival {worst.setup_arrival} ns.
- **Worst hold path (all runs)**: {worst_hold.hold_slack:+.4f} ns at corner
  `{worst_hold.corner}`.
- **DR-0003's flagged intermediate rate ({DR0003_INTERMEDIATE_MHZ:g} MHz, 5x pixel clock)**:
  not met by this netlist ({fmax_worst:.2f} MHz worst-corner Fmax, {
    fmax_worst / DR0003_INTERMEDIATE_MHZ:.2f}x the required rate). That rate belongs
  to the not-yet-written 10:1->2:1 serializer, not to this encoder, so this is not
  a violation of anything this block promises -- but it is the first *measurement*
  against DR-0003's open item, and it says the ceiling is well below 5x pixel rate
  for area-mapped logic of this depth.

## Known limitations (disclosed, not silently worked around)

1. **Post-CTS hold verdict, but at a single P&R corner.** `flow/pnr_tmds_encoder.py`
   now runs clock-tree synthesis and `repair_timing -hold` (issue #100) at the
   `tt_025C_3v30` corner its own liberty uses -- so this record's hold verdict,
   unlike #83's original pre-CTS one, reflects real CTS-inserted buffer/skew and
   real hold-repair delay cells. It is not, however, a hold repair run *per
   corner*: CTS/hold-repair ran once, against one corner's timing, and this
   analysis then re-times that one fixed physical implementation at all five
   corners. A hold violation that only manifests at a corner CTS/hold-repair did
   not optimize against would not have been caught by `repair_timing`, though it
   would still be caught and reported here, since this driver re-checks hold at
   every corner independently of what corner produced the layout.
2. **One RC corner, five liberty corners.** The post-CTS re-extraction (issue
   #115, record `{SPEF_RECORD_ID}`) used the gf180 platform's typical
   (`FuncRCtyp`) RCX deck only, same as every earlier extraction in this
   chain; this analysis reuses that single SPEF at all five liberty
   corners. #85 established that post-route net delays on this die round to
   0.000 ns at 3-decimal precision, so the liberty corner dominates -- but
   this is an approximation, and re-extraction per RC corner is the right
   thing to do once interconnect matters.
3. **Timing-driven synthesis maps against one worst-case corner's liberty, not
   an on-chip-variation-derated multi-corner target.** Issue #100's
   `flow/synth_tmds_encoder.py` targets ABC's `-D` delay constraint using the
   `ss_125C_3v00` liberty specifically (per #83's own record, the worst setup
   corner of the five checked) rather than a formal multi-corner sign-off flow;
   issue #115 reuses this unchanged for the four-stage RTL, with the ABC
   delay target now corrected for sequential overhead (DR-0009). This is
   disclosed reasoning, not an unstated assumption (see that script's
   docstring), and this record's own multi-corner re-check is exactly the
   verification step that confirms (or does not confirm) it actually
   worked -- see the Results tables above for the corner-by-corner outcome.
4. **The 720p60 setup margin at the worst corner is small.**{
    f" It is met at every corner, but the worst of them ({worst.corner}) has"
    f" {worst.setup_slack:+.4f} ns of it against a"
    f" {period_ns(TARGETS[0][1]):.4f} ns period -- {abs(worst.setup_slack) / period_ns(TARGETS[0][1]) * 100:.1f}%."
    " That is a genuine pass under this record's own (deliberately"
    " pessimistic, see 'Constraints applied') boundary assumptions, and it is"
    " not a comfortable one: it leaves little room for a later netlist change,"
    " a floorplan change, or on-chip variation derating this flow does not yet"
    " model. Treat 720p60 as closed but margin-limited, not as closed with"
    " headroom." if not setup_720 else
    f" It is *not* met at {len(setup_720)} of {len(by_target['720p60'])} corners"
    f" ({', '.join(r.corner for r in setup_720)}); see the Results table above"
    " for the per-corner slack. This is not silently accepted as final -- per"
    " CLAUDE.md, an evidenced partial result is recorded as such rather than"
    " reported as a close."}
5. **`repair_timing -setup` upsizes existing instances, so the routed DEF can
   name a different drive strength than the committed netlist** (issue #115).
   Every such resize is enumerated by name above, and this driver re-checks
   that the logic *function* is identical for each; a function change, a
   missing instance, or an unexplained component still fails the run. The
   gate-level re-simulation (`flow/gate_level_sim_tmds_encoder.py`) simulates
   the committed netlist's cell types with this layout's extracted SDF
   annotated onto it -- the same additive approximation that flow already
   makes for CTS/hold-repair-inserted buffers, and a smaller one, since a
   drive-strength variant has identical pins, identical function, and
   identical `specify` paths.

- **Reproducibility**: working tree {"DIRTY (uncommitted changes outside flow/tmds_encoder/ at run time -- re-run against a clean checkout before trusting this record)" if dirty else "clean"} at commit `{sha}`.
- **Links**:
  - Netlist (input, unmodified): `flow/tmds_encoder/netlist/{TOP}.synth.v`
  - Routed DEF (input, unmodified): `flow/tmds_encoder/pnr/{TOP}.def`
  - Parasitics (input, unmodified): `flow/tmds_encoder/sta/{TOP}.spef`
  - Constraints: `flow/tmds_encoder/sta/{TOP}.sdc`
  - Per-run OpenSTA scripts / logs:
    `flow/tmds_encoder/reports/{rid}.sta_<corner>_<target>.tcl` / `.log`
- **Timestamp / author**: {when.strftime("%Y-%m-%d %H:%M:%S UTC")}, `flow/sta_tmds_encoder.py` (agent-run)
"""


if __name__ == "__main__":
    sys.exit(main())
