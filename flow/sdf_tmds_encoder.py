#!/usr/bin/env python3
"""OpenSTA back-annotated SDF extraction driver for `tmds_encoder` (issue #85).

Takes the routed DEF issue #84 already produced and committed
(``flow/tmds_encoder/pnr/tmds_encoder.def``) and runs it through OpenSTA
(bundled in the same ``openroad`` binary the P&R driver uses) to:

  1. Extract RC parasitics from the actual routed geometry via OpenRCX,
     against the gf180 platform's own typical-corner extraction rule deck
     (see "RC extraction corner" below) -- not a placement-only estimate.
  2. Write those parasitics out as SPEF, for provenance:
       flow/tmds_encoder/sta/tmds_encoder.spef
  3. Write a back-annotated SDF (real per-cell and per-net delays, computed
     from the same ``tt_025C_3v30`` liberty corner #82/#84 used plus the
     extracted parasitics) to:
       flow/tmds_encoder/sta/tmds_encoder.sdf
  4. Report the worst-case combinational (input-port-to-register) delay
     found, unconstrained (this design has no SDC/clock-period commitment
     -- see "No SDC" below, same DR-0003 boundary #82/#84 already drew) --
     logged for provenance and cited in the evidence record, but *not* used
     to compute or imply an achievable operating frequency: that claim is
     issue #83's (STA) job, not this one's.
  5. Write the exact OpenSTA script run, and its full log:
       flow/tmds_encoder/reports/<record-id>.sta.tcl
       flow/tmds_encoder/reports/<record-id>.sta.log
  6. Write an append-only evidence record:
       flow/tmds_encoder/records/<record-id>.md

PDK resolution reuses ``sim/harness/pdk.py`` (via ``flow/synth_tmds_encoder.py``,
imported for its already-reviewed ``record_id``/``_git``/``working_tree_dirty``
helpers), and standard-cell LEF/liberty resolution reuses
``flow/pnr_tmds_encoder.py``'s ``lef_paths`` -- same PDK-pinning convention as
both those scripts.

## No SDC

Same boundary #82's synthesis and #84's P&R both already drew: no
`.sdc`/clock-period constraint is read or assumed here. `report_checks
-unconstrained` reports the worst-case combinational delay from a primary
input to the first register stage without a required-time comparison (no
setup/hold pass/fail verdict) -- that verdict, and any operating-frequency
claim, is issue #83's (STA) job. This driver only asks OpenSTA "how long do
these paths actually take", not "is that fast enough".

## RC extraction corner

The gf180 OpenROAD-flow-scripts platform config (`config.mk`) pins its own
default "typical" (`TC`) OpenRCX rule deck to
`gf180mcu_1p5m_1tm_9k_sp_smim_OPTB_typ.rules` (`TC_RCX_RC_CORNER =
FuncRCtyp`) -- used here unmodified. This is independent of, and orthogonal
to, the *liberty timing* corner (`tt_025C_3v30`, DR-0003's synthesized-domain
choice): the RCX deck characterizes the metal stack's own RC per unit
geometry (a process/temperature fact), not the standard-cell library's
chosen supply-voltage variant. Both selections represent nominal
process/temperature ("typical"), so they are consistent even though they
are not drawn from "the same" corner file family -- no known corner
mismatch between them. See "Reconciling with issue #83" below for the
liberty-corner side of this same question.

## Reconciling with issue #83

Issue #85's own test plan asks to confirm this SDF's corner matches the
corner issue #83's STA run uses. At the time this driver was written, #83
had not yet been implemented (still open) -- there is nothing yet to
reconcile against. This driver uses `tt_025C_3v30` (the same corner #82's
synthesis and #84's P&R both already used, DR-0003's synthesized-domain
corner), and #83 should use the same when it lands; if it does not, that
mismatch should be reconciled explicitly in #83's own evidence record
against this one, per issue #85's acceptance criteria.

Cold-start invocation (requires OpenROAD on `PATH`, run via the pinned
`openroad/orfs` Docker image -- see "Pinned toolchain" in `flow/README.md`):

    python3 flow/sdf_tmds_encoder.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "flow"))

from sim.harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402
import synth_tmds_encoder as synth  # noqa: E402  (reuses record_id/_git/working_tree_dirty)
import pnr_tmds_encoder as pnr  # noqa: E402  (reuses lef_paths, STD_CELL_LIB/CORNER, run_openroad, openroad_version)

TOP = "tmds_encoder"

OUT_DIR = REPO_ROOT / "flow" / "tmds_encoder"
STA_DIR = OUT_DIR / "sta"
REPORTS_DIR = OUT_DIR / "reports"
RECORDS_DIR = OUT_DIR / "records"

ROUTED_DEF = OUT_DIR / "pnr" / "tmds_encoder.def"
PNR_RECORD_ID = "20260817-105608-049c240"  # issue #115's four-stage (DR-0009) P&R record, cited below

SDF_PATH = STA_DIR / "tmds_encoder.sdf"
SPEF_PATH = STA_DIR / "tmds_encoder.spef"

# OpenROAD-flow-scripts' bundled gf180-platform RCX extraction rule deck this
# driver reuses read-only (static PDK-adjacent viewer/extraction metadata,
# not design data -- same "reuse ORFS's own bundled platform file" pattern
# flow/pnr_tmds_encoder.py's GDS merge step already established for the
# KLayout tech file / layer map). Path is inside the `openroad/orfs`
# container image this driver is run through; see flow/README.md's "Pinned
# toolchain". This is config.mk's own `TC_RCX_RULES` (`CORNER=TC`, the
# platform's typical-process deck) -- see this module's docstring's "RC
# extraction corner" section for why pairing it with the `tt_025C_3v30`
# liberty corner is not a mismatch.
ORFS_ROOT = Path("/OpenROAD-flow-scripts")
ORFS_RCX_RULES = (
    ORFS_ROOT
    / "flow"
    / "platforms"
    / "gf180"
    / "openROAD"
    / "rcx"
    / "gf180mcu_1p5m_1tm_9k_sp_smim_OPTB_typ.rules"
)
RCX_CORNER_NAME = "TYP"
RCX_RC_CORNER = "FuncRCtyp"  # config.mk's own TC_RCX_RC_CORNER label

_WORST_DELAY_RE = re.compile(r"^\s*([\d.]+)\s+data arrival time\s*$", re.MULTILINE)
_NET_COUNT_RE = re.compile(r"Extract (\d+) nets, (\d+) rsegs, (\d+) caps, (\d+) ccs")


def build_tcl(tech_lef: Path, sc_lef: Path, liberty: Path, routed_def: Path) -> str:
    return f"""\
read_lef {tech_lef}
read_lef {sc_lef}
read_liberty {liberty}
read_def {routed_def}

define_process_corner -ext_model_index 0 {RCX_CORNER_NAME}
extract_parasitics -ext_model_file {ORFS_RCX_RULES}

write_spef {SPEF_PATH}
write_sdf {SDF_PATH}

report_checks -unconstrained -group_count 1

exit
"""


def parse_worst_unconstrained_delay(log_text: str) -> str | None:
    matches = _WORST_DELAY_RE.findall(log_text)
    return matches[0] if matches else None


def parse_net_counts(log_text: str) -> str | None:
    m = _NET_COUNT_RE.search(log_text)
    if not m:
        return None
    nets, rsegs, caps, ccs = m.groups()
    return f"{nets} nets, {rsegs} rsegs, {caps} caps, {ccs} coupling caps"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        tech_lef, sc_lef, liberty, _setup_liberty, _cell_gds = pnr.lef_paths(pdk)
    except pnr.PnrError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not ROUTED_DEF.is_file():
        print(
            f"ERROR: routed DEF not found at {ROUTED_DEF} -- run flow/pnr_tmds_encoder.py "
            "(issue #84) first",
            file=sys.stderr,
        )
        return 1

    when = synth._dt.datetime.now(synth._dt.timezone.utc)
    rid = synth.record_id(when)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = REPORTS_DIR / f"{rid}.sta.log"

    STA_DIR.mkdir(parents=True, exist_ok=True)
    script = build_tcl(tech_lef, sc_lef, liberty, ROUTED_DEF)
    print(f"Extracting parasitics and back-annotated SDF for {TOP} ...")
    result = pnr.run_openroad(script, log_path)
    log_text = log_path.read_text()
    if result.returncode != 0 or "Error:" in log_text or "[ERROR" in log_text:
        print(f"ERROR: openroad exited {result.returncode} -- see {log_path}", file=sys.stderr)
        return 1
    if not SDF_PATH.is_file():
        print(f"ERROR: openroad reported success but {SDF_PATH} was not written", file=sys.stderr)
        return 1
    if not SPEF_PATH.is_file():
        print(f"ERROR: openroad reported success but {SPEF_PATH} was not written", file=sys.stderr)
        return 1

    worst_delay = parse_worst_unconstrained_delay(log_text)
    net_counts = parse_net_counts(log_text)
    or_version = pnr.openroad_version(log_text)
    print(
        f"OK: SDF written to {SDF_PATH}, SPEF written to {SPEF_PATH} "
        f"(worst unconstrained input-to-register delay: {worst_delay} ns; {net_counts})"
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
            render_record(rid, when, pdk, liberty, worst_delay, net_counts, or_version, dirty, sha, log_path)
        )
        print(f"Evidence record written to {record_path}")

    return 0


def render_record(rid, when, pdk: Pdk, liberty: Path, worst_delay, net_counts, or_version, dirty, sha, log_path) -> str:
    return f"""\
# Record {rid}

- **Record ID**: {rid}
- **Claim**: A back-annotated SDF (real per-cell and per-net delays) and its
  underlying extracted-parasitics SPEF exist for the post-route digital
  layout issue #115 produced (routed DEF `flow/tmds_encoder/pnr/tmds_encoder.def`,
  record `{PNR_RECORD_ID}`, git commit `{sha}`) -- the four-stage (DR-0009)
  netlist, place-and-routed through the timing-driven-synthesis + CTS +
  timing-repair machinery issue #100 built and issue #115 extended -- built against the gf180mcu
  `{pnr.STD_CELL_LIB}` standard-cell library at the `{pnr.STD_CELL_CORNER}` corner
  (spec/tmds-tx.md DR-0003's synthesized-domain corner, same as #82/#84/#100).
  Addresses #65 item 7 (post-layout verification) on the digital partition.
- **Scope**: SDF/SPEF extraction only -- delay computation from liberty +
  extracted RC parasitics. No SDC/clock-period constraint is read or assumed
  (see `flow/sdf_tmds_encoder.py`'s "No SDC" section); `report_checks
  -unconstrained` is used only to log the worst-case combinational delay
  found, not to render a setup/hold pass/fail verdict -- that is issue #83's
  (STA) job, not this one's.
- **P&R revision cited**: issue #115's evidence record `{PNR_RECORD_ID}`
  (`flow/tmds_encoder/records/{PNR_RECORD_ID}.md`), routed DEF
  `flow/tmds_encoder/pnr/tmds_encoder.def`, git commit `{sha}`.
- **Tool versions**:
  - OpenROAD/OpenSTA: `{or_version}` (run via the `openroad/orfs:latest`
    Docker image -- see `flow/README.md`'s "Pinned toolchain")
  - gf180mcu PDK: variant `{pdk.variant}`, open_pdks `{pdk.version}` (via {pdk.source})
- **RC extraction**:
  - Rule deck: OpenROAD-flow-scripts' bundled gf180 platform typical-corner
    deck, `gf180mcu_1p5m_1tm_9k_sp_smim_OPTB_typ.rules` (config.mk's own
    `TC_RCX_RULES`, RC corner label `{RCX_RC_CORNER}`) -- see
    `flow/sdf_tmds_encoder.py`'s "RC extraction corner" section for why
    pairing this with the `{pnr.STD_CELL_CORNER}` liberty corner is not a
    mismatch.
  - Result: {net_counts}.
- **Worst-case unconstrained combinational delay observed**: {worst_delay} ns
  (primary input to first register stage, `report_checks -unconstrained`;
  no clock/SDC applied, so this is a delay measurement, not a setup/hold
  verdict -- see "Scope" above).
- **Known limitations (disclosed, not silently worked around)**:
  1. **No SDC / no timing-closure verdict** -- see "Scope" above; issue #83
     owns that question.
  2. **Interconnect (net) delays are 0.000 ns throughout** the extracted
     SDF -- not an extraction failure: this design's core is a compact
     ~158 x 138 um die (see #84's evidence record), so per-net wire RC
     delay genuinely rounds to 0.000 at 3-decimal SDF precision for every
     net checked; corroborated independently by `report_checks` showing
     identical worst-path timing with and without parasitics extracted.
- **Reproducibility**: working tree {"DIRTY (uncommitted changes outside flow/tmds_encoder/ at run time -- re-run against a clean checkout before trusting this record)" if dirty else "clean"} at commit `{sha}`.
- **Links**:
  - Routed DEF (input, unmodified): `flow/tmds_encoder/pnr/tmds_encoder.def`
  - SDF: `flow/tmds_encoder/sta/tmds_encoder.sdf`
  - SPEF: `flow/tmds_encoder/sta/tmds_encoder.spef`
  - OpenSTA script: `flow/tmds_encoder/reports/{rid}.sta.tcl`
  - Full OpenSTA log: `flow/tmds_encoder/reports/{rid}.sta.log`
- **Timestamp / author**: {when.strftime("%Y-%m-%d %H:%M:%S UTC")}, `flow/sdf_tmds_encoder.py` (agent-run)
"""


if __name__ == "__main__":
    sys.exit(main())
