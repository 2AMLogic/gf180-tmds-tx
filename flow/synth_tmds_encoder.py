#!/usr/bin/env python3
"""Cold-start Yosys synthesis driver for ``rtl/tmds_encoder.v``.

Maps the TMDS encoder to the gf180mcu standard-cell library at the
supply corner ``spec/tmds-tx.md`` DR-0003 names -- ``gf180mcu_fd_sc_mcu9t5v0``,
``tt_025C_3v30`` (the 3.3 V nominal corner) -- and writes:

  - the gate-level netlist:  flow/tmds_encoder/netlist/tmds_encoder.synth.v
  - the exact Yosys script used, and its full log:
        flow/tmds_encoder/reports/<record-id>.synth.ys
        flow/tmds_encoder/reports/<record-id>.synth.log
  - an append-only evidence record: flow/tmds_encoder/records/<record-id>.md

Scope (per issue #82): synthesis only. No clock-period/SDC constraint is
applied, and no STA/timing-closure claim is made here -- DR-0003 flags the
synthesized-domain clock ceiling as unverified, and closing that question is
explicitly a separate, sequenced follow-on (issue #83), not this script's
job. See "no unmapped cells" below for what *is* checked mechanically.

PDK resolution reuses ``sim/harness/pdk.py`` (import, not a re-implementation
-- that module's own docstring says PDK discovery "has nothing to do with"
the domain adapting it, and this script's needs are a strict subset of what
it already resolves: a variant directory). The same env vars / sim/pdk.json
pin therefore apply here unchanged -- see sim/README.md's "PDK variant".

"No unmapped cells" is a *computed* claim, not an eyeballed one (same
discipline verification/README.md applies to "exhaustive"): after Yosys
writes the netlist, this script re-parses the written file itself and
asserts every cell instance is a `gf180mcu_fd_sc_mcu9t5v0__*` standard cell
-- independent of, and in addition to, the `select -assert-none t:$_*`
check the Yosys script itself runs before writing.

Cold-start invocation (from a clean checkout, PDK installed -- see
sim/README.md "PDK variant" / sim/harness/README.md "Prerequisites"):

    python3 flow/synth_tmds_encoder.py

Operational note for local/agent boxes running the ``yowasp-yosys`` pip
package (a WASM build of Yosys, not the apt/native binary CI installs):
its sandboxed filesystem access can silently fail to write output files
under ``/tmp`` even though reads from arbitrary absolute paths (e.g. the
PDK's liberty file) succeed -- confirmed by directly reproducing this with
plain writes under `/tmp` vs. under the repo tree while implementing this
script. This script therefore never writes anywhere but under the repo
tree (``flow/tmds_encoder/...``), which works with both the WASM build and
a native one.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sim.harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402

TOP = "tmds_encoder"
RTL_SOURCE = REPO_ROOT / "rtl" / "tmds_encoder.v"

OUT_DIR = REPO_ROOT / "flow" / "tmds_encoder"
NETLIST_PATH = OUT_DIR / "netlist" / "tmds_encoder.synth.v"
REPORTS_DIR = OUT_DIR / "reports"
RECORDS_DIR = OUT_DIR / "records"

# Standard-cell library + corner, per spec/tmds-tx.md DR-0003.
STD_CELL_LIB = "gf180mcu_fd_sc_mcu9t5v0"
STD_CELL_CORNER = "tt_025C_3v30"  # 3.3 V nominal corner
CELL_PREFIX = f"{STD_CELL_LIB}__"

_INSTANCE_RE = re.compile(r"^  (\S+) (\S+) \($", re.MULTILINE)


class SynthError(RuntimeError):
    """A synthesis run failed, or its output failed a sanity check."""


def liberty_path(pdk: Pdk) -> Path:
    path = pdk.path / "libs.ref" / STD_CELL_LIB / "lib" / f"{STD_CELL_LIB}__{STD_CELL_CORNER}.lib"
    if not path.is_file():
        raise SynthError(
            f"standard-cell liberty file not found at {path}\n"
            f"(expected the gf180mcu {STD_CELL_LIB} library's {STD_CELL_CORNER} corner, "
            "per spec/tmds-tx.md DR-0003 -- check the PDK install / variant)"
        )
    return path


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def record_id(when: _dt.datetime) -> str:
    """``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, matching sim/README.md's grammar."""
    sha = _git("rev-parse", "--short", "HEAD") or "nogit"
    return f"{when.strftime('%Y%m%d-%H%M%S')}-{sha}"


def working_tree_dirty() -> bool:
    status = _git("status", "--porcelain")
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        # This run's own output tree does not count -- it is exactly what a
        # run leaves behind (same reasoning as sim/harness/report.py's
        # working_tree_dirty, adapted to flow/'s output paths).
        if path and not path.startswith("flow/tmds_encoder/"):
            return True
    return False


def yosys_version() -> str:
    result = subprocess.run(["yosys", "-V"], capture_output=True, text=True, check=True)
    return (result.stdout or result.stderr).strip()


def build_yosys_script(liberty: Path) -> str:
    """Generic ASIC mapping recipe: proc/opt/fsm/memory/techmap, then
    dfflibmap+abc against the liberty file. No SDC / clock-period constraint
    is applied -- deliberately: see this module's docstring and DR-0003.
    """
    return f"""\
read_verilog {RTL_SOURCE}
hierarchy -check -top {TOP}
proc
opt
fsm
opt
memory
opt
techmap
opt
dfflibmap -liberty {liberty}
abc -liberty {liberty}
opt_clean -purge
clean
setundef -zero
stat -liberty {liberty}
select -assert-none t:$_*
check -noinit
write_verilog -noattr {NETLIST_PATH}
"""


def run_yosys(script: str, log_path: Path) -> subprocess.CompletedProcess:
    NETLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["yosys", "-p", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    log_path.write_text((result.stdout or "") + (result.stderr or ""))
    return result


def cell_counts(netlist_path: Path) -> dict[str, int]:
    """Parse the written netlist and count instances by cell type.

    Independent of, and a cross-check on, the Yosys-side
    `select -assert-none t:$_*` -- see this module's docstring.
    """
    text = netlist_path.read_text()
    counts: dict[str, int] = {}
    for cell_type, _instance_name in _INSTANCE_RE.findall(text):
        counts[cell_type] = counts.get(cell_type, 0) + 1
    return counts


def assert_fully_mapped(counts: dict[str, int]) -> None:
    unmapped = sorted(t for t in counts if not t.startswith(CELL_PREFIX))
    if unmapped:
        raise SynthError(
            "netlist contains non-standard-cell instances (unmapped): "
            + ", ".join(f"{t} x{counts[t]}" for t in unmapped)
        )
    if not counts:
        raise SynthError("netlist contains no cell instances at all -- synthesis produced nothing")


def render_record(
    *,
    rid: str,
    when: _dt.datetime,
    pdk: Pdk,
    liberty: Path,
    yosys_v: str,
    counts: dict[str, int],
    dirty: bool,
    log_path: Path,
    ys_path: Path,
) -> str:
    total_cells = sum(counts.values())
    seq_cells = sum(n for t, n in counts.items() if "dff" in t or "lat" in t)
    comb_cells = total_cells - seq_cells
    breakdown = "\n".join(f"  - `{t}`: {n}" for t, n in sorted(counts.items()))
    sha = _git("rev-parse", "HEAD") or "unknown"
    return f"""\
# Record {rid}

- **Record ID**: {rid}
- **Claim**: A gate-level netlist for `tmds_encoder` exists, synthesized against the
  gf180mcu standard-cell library and corner spec/tmds-tx.md DR-0003 names for the
  synthesized domain (`{STD_CELL_LIB}`, `{STD_CELL_CORNER}` -- the 3.3 V nominal
  corner). Closes #65 item 1 (design sources) on the digital partition.
- **Scope**: Synthesis only. No SDC / clock-period constraint was applied, and no
  timing-closure (STA) claim is made -- DR-0003 flags the synthesized-domain clock
  ceiling as unverified pending dedicated STA work (issue #83), which this record
  does not attempt to answer.
- **Tool versions**:
  - Yosys: `{yosys_v}`
  - gf180mcu PDK: variant `{pdk.variant}`, open_pdks `{pdk.version}` (via {pdk.source})
- **Standard-cell library**: `{liberty.relative_to(pdk.path)}` (`{STD_CELL_LIB}`,
  `{STD_CELL_CORNER}` corner)
- **Synthesis constraints**: none beyond technology mapping -- no `.sdc`, no clock
  period, no area/power target. Recipe: `proc; opt; fsm; opt; memory; opt; techmap;
  opt; dfflibmap -liberty <lib>; abc -liberty <lib>; opt_clean -purge; clean`. Exact
  script: `flow/tmds_encoder/reports/{rid}.synth.ys`.
- **Result**: PASS -- {total_cells} cell instances ({seq_cells} sequential, {comb_cells}
  combinational), 0 unmapped cells (every instance is a `{CELL_PREFIX}*` standard
  cell; checked both by the synthesis script's own
  `select -assert-none t:$_*` and by re-parsing the written netlist -- see
  `cell_counts`/`assert_fully_mapped` in `flow/synth_tmds_encoder.py`). Cell
  breakdown:
{breakdown}
- **Reproducibility**: working tree {"DIRTY (uncommitted changes outside flow/tmds_encoder/ at run time -- re-run against a clean checkout before trusting this record)" if dirty else "clean"} at commit `{sha}`.
- **Links**:
  - RTL source: `rtl/tmds_encoder.v`
  - Netlist: `flow/tmds_encoder/netlist/tmds_encoder.synth.v`
  - Yosys script: `flow/tmds_encoder/reports/{rid}.synth.ys`
  - Full log: `flow/tmds_encoder/reports/{rid}.synth.log`
- **Timestamp / author**: {when.strftime("%Y-%m-%d %H:%M:%S UTC")}, `flow/synth_tmds_encoder.py` (agent-run)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="run synthesis and write the netlist, but skip minting an evidence record",
    )
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        liberty = liberty_path(pdk)
    except SynthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    when = _dt.datetime.now(_dt.timezone.utc)
    rid = record_id(when)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ys_path = REPORTS_DIR / f"{rid}.synth.ys"
    log_path = REPORTS_DIR / f"{rid}.synth.log"

    script = build_yosys_script(liberty)
    ys_path.write_text(script)

    print(f"Synthesizing {TOP} against {liberty} ...")
    result = run_yosys(script, log_path)
    if result.returncode != 0:
        print(f"ERROR: yosys exited {result.returncode} -- see {log_path}", file=sys.stderr)
        return 1

    if not NETLIST_PATH.is_file():
        print(f"ERROR: yosys reported success but {NETLIST_PATH} was not written", file=sys.stderr)
        return 1

    try:
        counts = cell_counts(NETLIST_PATH)
        assert_fully_mapped(counts)
    except SynthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = sum(counts.values())
    print(f"OK: {total} cell instances, 0 unmapped -- netlist written to {NETLIST_PATH}")

    if not args.no_record:
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        record_path = RECORDS_DIR / f"{rid}.md"
        if record_path.exists():
            print(f"ERROR: record {record_path} already exists -- refusing to overwrite", file=sys.stderr)
            return 1
        record_path.write_text(
            render_record(
                rid=rid,
                when=when,
                pdk=pdk,
                liberty=liberty,
                yosys_v=yosys_version(),
                counts=counts,
                dirty=working_tree_dirty(),
                log_path=log_path,
                ys_path=ys_path,
            )
        )
        print(f"Evidence record written to {record_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
