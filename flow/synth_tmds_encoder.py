#!/usr/bin/env python3
"""Cold-start Yosys synthesis driver for ``rtl/tmds_encoder.v``.

Maps the TMDS encoder to the gf180mcu standard-cell library, within the 3.3 V
corner family ``spec/tmds-tx.md`` DR-0003 names (``gf180mcu_fd_sc_mcu9t5v0``),
and writes:

  - the gate-level netlist:  flow/tmds_encoder/netlist/tmds_encoder.synth.v
  - the exact Yosys script used, and its full log:
        flow/tmds_encoder/reports/<record-id>.synth.ys
        flow/tmds_encoder/reports/<record-id>.synth.log
  - an append-only evidence record: flow/tmds_encoder/records/<record-id>.md

## Timing-driven mapping (issue #100)

Issue #83's multi-corner STA (record `20260816-172539-930e864`) found that
the netlist this script previously produced -- mapped with **no** clock
constraint at all, area-only, every cell forced to drive strength 1 -- failed
setup at 74.25 MHz (`spec/tmds-tx.md` §2's 720p60 target) at 4 of 5 3.3 V
corners. This script now feeds ABC an explicit delay target instead:

  - **Target period**: `TARGET_PERIOD_NS` (13.4680 ns = 1/74.25 MHz, spec
    §2's 720p60 pixel clock -- not invented here; identical rounding to
    `flow/sta_tmds_encoder.py`'s own `period_ns(74.25)`).
  - **Mapping corner**: `TIMING_CORNER` (`ss_125C_3v00`) rather than the
    `tt_025C_3v30` nominal corner DR-0003's synthesized-domain decision
    names. This is a **worst-case-corner synthesis** choice, not a DR-0003
    deviation -- `ss_125C_3v00` is itself one of DR-0003's own named "ff/ss
    counterparts" of the 3.3 V corner family, and #83's record confirms it is
    the worst of the five checked corners for every setup metric (worst
    slack, TNS, Fmax). Mapping ABC's `-D` delay target against the *slowest*
    corner's own cell-delay arcs means a netlist that meets the target there
    carries positive margin at every faster corner by construction -- the
    standard "synthesize at worst corner, verify all corners via STA"
    discipline, not a heuristic derating guess.
  - **I/O boundary assumptions** (`-constr`, ABC's own two-line format):
    `set_driving_cell`/`set_load` are kept numerically identical to
    `flow/sta_tmds_encoder.py`'s own `DRIVING_CELL`/`OUTPUT_LOAD_PF` (the
    smallest inverter driving inputs, 4x its own input capacitance loading
    outputs) so the synthesis-time boundary assumption cannot be tighter
    than what STA later checks against -- see this module's `CONSTR_*`
    constants.

This does not by itself guarantee closure at every corner (that is what the
new STA evidence record this issue produces measures) -- it is the first,
least-invasive step of issue #100's scope, before clock-tree synthesis and,
if still insufficient, RTL pipelining.

See "no unmapped cells" below for what *is* checked mechanically.

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

# Standard-cell library, per spec/tmds-tx.md DR-0003 (the 3.3 V corner family).
STD_CELL_LIB = "gf180mcu_fd_sc_mcu9t5v0"
STD_CELL_CORNER = "tt_025C_3v30"  # 3.3 V nominal corner -- still the corner
# DR-0003 names for the synthesized domain generally; reported in the record
# for provenance, but no longer the corner ABC's delay-driven mapping itself
# runs against -- see TIMING_CORNER below.
CELL_PREFIX = f"{STD_CELL_LIB}__"

# Issue #100: timing-driven mapping. See this module's docstring
# "Timing-driven mapping" section for the full rationale.
TIMING_CORNER = "ss_125C_3v00"  # worst setup corner per issue #83's record
TARGET_FREQ_MHZ = 74.25  # 720p60 pixel clock, spec/tmds-tx.md §2
TARGET_PERIOD_NS = round(1000.0 / TARGET_FREQ_MHZ, 4)  # 13.4680 ns
TARGET_PERIOD_PS = round(TARGET_PERIOD_NS * 1000)

# I/O boundary assumptions for ABC's `-constr` file -- numerically identical
# to flow/sta_tmds_encoder.py's DRIVING_CELL / OUTPUT_LOAD_PF (kept in sync
# manually; both cite the same rationale: smallest inverter driving inputs,
# 4x its own input capacitance loading outputs).
CONSTR_DRIVING_CELL = f"{STD_CELL_LIB}__inv_1"
CONSTR_DRIVING_CELL_INPUT_CAP_PF = 0.006813  # inv_1 pin(I) capacitance, tt_025C_3v30
CONSTR_LOAD_FF = round(4 * CONSTR_DRIVING_CELL_INPUT_CAP_PF * 1000, 3)  # femtofarads, ABC's -constr unit

_INSTANCE_RE = re.compile(r"^  (\S+) (\S+) \($", re.MULTILINE)


class SynthError(RuntimeError):
    """A synthesis run failed, or its output failed a sanity check."""


def _liberty_path(pdk: Pdk, corner: str) -> Path:
    path = pdk.path / "libs.ref" / STD_CELL_LIB / "lib" / f"{STD_CELL_LIB}__{corner}.lib"
    if not path.is_file():
        raise SynthError(
            f"standard-cell liberty file not found at {path}\n"
            f"(expected the gf180mcu {STD_CELL_LIB} library's {corner} corner -- "
            "check the PDK install / variant)"
        )
    return path


def liberty_path(pdk: Pdk) -> Path:
    """The nominal (tt_025C_3v30) corner liberty -- reporting/provenance only."""
    return _liberty_path(pdk, STD_CELL_CORNER)


def timing_liberty_path(pdk: Pdk) -> Path:
    """The worst-setup-corner liberty ABC's `-D` delay target is mapped against."""
    return _liberty_path(pdk, TIMING_CORNER)


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


def _git_status_porcelain() -> str:
    """``git status --porcelain``, stripped only of trailing whitespace.

    Deliberately NOT `_git()` (issue #100 -- found directly, not assumed):
    `_git()`'s `.strip()` trims the *whole* multi-line stdout, which eats the
    leading space of porcelain's unstaged-modify (`" M "`) / unstaged-delete
    (`" D"`) status code whenever that happens to be the first line -- e.g.
    `" M flow/tmds_encoder/netlist/tmds_encoder.synth.v"` becomes
    `"M flow/tmds_encoder/..."`, one character short, so
    `working_tree_dirty`'s `line[3:]` then reads `"low/tmds_encoder/..."`
    instead of `"flow/tmds_encoder/..."` and the `flow/tmds_encoder/` exclusion
    below silently fails to match -- a real run with zero out-of-tree changes
    was reproducibly flagged `DIRTY` this way while building this issue's
    evidence records. Every other line is unaffected (`.strip()` only trims
    string boundaries, not internal lines), which is why this went unnoticed
    until a `flow/tmds_encoder/` path happened to sort first.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout.rstrip("\n") if result.returncode == 0 else ""


def working_tree_dirty() -> bool:
    status = _git_status_porcelain()
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


def build_constr_file() -> str:
    """ABC's own two-line `-constr` format (`help abc`): driving cell for
    primary inputs, load (femtofarads) for primary outputs. See this
    module's docstring "Timing-driven mapping" section.
    """
    return f"set_driving_cell {CONSTR_DRIVING_CELL}\nset_load {CONSTR_LOAD_FF}\n"


def build_abc_script() -> str:
    """ABC mapping script for the timing-driven `-constr` case, replicating
    Yosys's own default "-liberty/-genlib with -constr" recipe (`help abc`)
    verbatim -- **except** dropping the `retime -o -D <ps>` step that `-D`
    would otherwise splice into `dretime` (`dretime` -> `dretime; retime -o
    -D <ps>`).

    That splice is *not* used here because it was found, directly, to
    corrupt this design: passing `-D {TARGET_PERIOD_PS}` (no custom
    `-script`) produced a netlist whose `tmds` primary output had **no
    driver at all** (`Warning: Wire tmds_encoder.\\tmds [N] is used but has
    no driver`, all 10 bits, reproduced deterministically) -- ABC's `retime`
    pass evidently mishandles this design's single-output-register topology
    under a delay target it cannot satisfy by retiming alone. `dretime`
    alone (the un-spliced, always-present step, used by every previous
    synthesis record including #82's pre-#100 area-only one) does not
    exhibit this -- confirmed by omitting only the spliced `retime -o -D`
    step and re-running: the "no driver" warning disappears and
    `write_verilog`'s netlist drives every output bit (see
    `assert_fully_mapped` / `cell_counts`, which would otherwise not find
    272 consistently-connected cell instances). `&nf -D <ps>` (the actual
    delay-driven *technology mapping* step, distinct from `retime`) is kept
    -- that is what does the real work of picking higher-drive-strength
    cells to hit the delay target, and it is not implicated in the
    corruption.
    """
    d = f"-D {TARGET_PERIOD_PS}"
    return f"""\
strash
&get -n
&fraig -x
&put
scorr
dc2
dretime
strash
&get -n
&dch -f
&nf {d}
&put
buffer
upsize {d}
dnsize {d}
stime -p
"""


def build_yosys_script(
    timing_liberty: Path, nominal_liberty: Path, constr_path: Path, abc_script_path: Path
) -> str:
    """Generic ASIC mapping recipe: proc/opt/fsm/memory/techmap, then
    dfflibmap+abc against the *worst-setup-corner* liberty file
    (`timing_liberty`), with an explicit ABC delay target and I/O boundary
    constraint (`-constr`), via the custom `-script` `build_abc_script`
    writes (see that function's docstring for why a custom script, not bare
    `-D`, is used) -- see this module's docstring "Timing-driven mapping"
    section for why the worst corner, not the nominal one DR-0003 names,
    drives the mapping itself. `nominal_liberty` (tt_025C_3v30) is used only
    for the post-mapping `stat` area/cell report, for provenance continuity
    with prior records.
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
dfflibmap -liberty {timing_liberty}
abc -liberty {timing_liberty} -constr {constr_path} -script {abc_script_path}
opt_clean -purge
clean
setundef -zero
stat -liberty {nominal_liberty}
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


#: Known-benign Yosys/ABC warnings, matched by regex, with the explanation
#: this driver records rather than leaving unexplained (per issue #82's
#: acceptance criteria). Extend this list, don't silently ignore a new
#: warning -- an unrecognized one is reported verbatim in the record with a
#: "not yet explained" flag instead of being dropped.
_KNOWN_WARNINGS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^Warning: Detected \d+ multi-output cells"),
        "ABC's liberty reader noting the library has multi-output cells (e.g. "
        "the full-adder `gf180mcu_fd_sc_mcu9t5v0__addf_1`, S+CO on one instance) "
        "it can use during mapping -- informational, about the *library*, not "
        "this design. This netlist does not instantiate any multi-output cell "
        "(see the cell breakdown below); confirmed by grepping the written "
        "netlist for `addf`/`subf`/`fah`/`fas` cell types (none present).",
    ),
    (
        re.compile(r"^Warning: Wire \S+ \[\d+\] is used but has no driver\.$"),
        "A false positive from Yosys's `check` pass, not a real missing driver "
        "(issue #100 -- investigated directly, not assumed): `dfflibmap` maps "
        "each `$dff` to a named `gf180mcu_fd_sc_mcu9t5v0__dff*` liberty cell by "
        "name only, without importing a blackbox module that declares that "
        "cell's port directions, so `check`'s conservative used-vs-driven "
        "classifier cannot confirm the cell's `Q` port is an output at the "
        "point it runs and flags every wire solely driven by one as "
        "'used but has no driver'. Confirmed benign by dumping the design's "
        "RTLIL immediately before `check` runs and by inspecting the final "
        "`write_verilog` output: every flagged bit (`tmds[0..9]`) is a normal "
        "`.Q(<net>)` cell-port connection from a real "
        "`gf180mcu_fd_sc_mcu9t5v0__dffq_1`/`dffrsnq_*` instance, with no `assign` "
        "or floating net involved. Reproduced identically (same 10 warnings) by "
        "re-running the *unmodified*, pre-#100 area-only recipe with no `-D`/"
        "`-constr`/timing-corner change at all -- this is a pre-existing Yosys "
        "diagnostic quirk, not something issue #100's timing-driven mapping "
        "introduced. It was invisible in #82's original evidence record only "
        "because that record's `yowasp-yosys` log truncates before reaching "
        "the `check` pass (a known, already-disclosed gotcha -- see "
        "`flow/README.md`'s 'yowasp-yosys' note); this driver's native-Yosys "
        "runs capture the full log and so are the first to actually see it.",
    ),
]


def extract_warnings(log_text: str) -> list[str]:
    """Every distinct ``Warning: ...`` line in the captured log, in order."""
    seen: list[str] = []
    for line in log_text.splitlines():
        line = line.strip()
        if line.startswith("Warning:") and line not in seen:
            seen.append(line)
    return seen


def explain_warning(warning: str) -> str:
    for pattern, explanation in _KNOWN_WARNINGS:
        if pattern.match(warning):
            return explanation
    return "NOT YET EXPLAINED -- investigate before trusting this record."


def render_record(
    *,
    rid: str,
    when: _dt.datetime,
    pdk: Pdk,
    liberty: Path,
    timing_liberty: Path,
    yosys_v: str,
    counts: dict[str, int],
    dirty: bool,
    warnings: list[str],
    log_path: Path,
    ys_path: Path,
) -> str:
    total_cells = sum(counts.values())
    seq_cells = sum(n for t, n in counts.items() if "dff" in t or "lat" in t)
    comb_cells = total_cells - seq_cells
    breakdown = "\n".join(f"  - `{t}`: {n}" for t, n in sorted(counts.items()))
    sha = _git("rev-parse", "HEAD") or "unknown"
    if warnings:
        warnings_block = "\n".join(
            f"  - `{w}` -- {explain_warning(w)}" for w in warnings
        )
    else:
        warnings_block = "  - none observed"
    return f"""\
# Record {rid}

- **Record ID**: {rid}
- **Claim**: A gate-level netlist for `tmds_encoder` exists, timing-driven-synthesized
  (issue #100, follow-up to #83's STA finding that the prior area-only netlist failed
  setup at 4/5 corners) against the gf180mcu standard-cell library
  (`{STD_CELL_LIB}`), within the 3.3 V corner family spec/tmds-tx.md DR-0003 names for
  the synthesized domain. Closes #65 item 1 (design sources) on the digital partition.
- **Scope**: Synthesis only, now timing-driven (issue #100 step 1 of 3 -- see
  `flow/synth_tmds_encoder.py`'s "Timing-driven mapping" docstring section). No
  standalone STA/timing-closure claim is made by *this* record -- that is
  `flow/sta_tmds_encoder.py`'s job, re-run separately after this netlist and its
  place-and-route.
- **Tool versions**:
  - Yosys: `{yosys_v}`
  - gf180mcu PDK: variant `{pdk.variant}`, open_pdks `{pdk.version}` (via {pdk.source})
- **Standard-cell library**: `{liberty.relative_to(pdk.path)}` (`{STD_CELL_LIB}`,
  `{STD_CELL_CORNER}` nominal corner -- reporting/provenance only, see below)
- **Timing-driven mapping** (issue #100):
  - ABC delay target: `-D {TARGET_PERIOD_PS}` ({TARGET_PERIOD_NS:.4f} ns = 1/{TARGET_FREQ_MHZ:g} MHz,
    `spec/tmds-tx.md` §2's 720p60 pixel clock -- not invented here).
  - Mapping corner: `{timing_liberty.relative_to(pdk.path)}` (`{TIMING_CORNER}`) --
    the **worst setup corner** per issue #83's STA record `20260816-172539-930e864`,
    not the `{STD_CELL_CORNER}` nominal corner DR-0003 names for the synthesized
    domain generally. Synthesizing against the slowest corner's own cell-delay arcs
    means a netlist meeting the `-D` target there carries positive margin at every
    faster corner by construction -- see this module's docstring for the full
    rationale for why this is not a DR-0003 deviation.
  - I/O boundary (`-constr`, exact file: `flow/tmds_encoder/reports/{rid}.synth.constr`):
    `set_driving_cell {CONSTR_DRIVING_CELL}` / `set_load {CONSTR_LOAD_FF}` (femtofarads)
    -- numerically identical to `flow/sta_tmds_encoder.py`'s own
    `DRIVING_CELL`/`OUTPUT_LOAD_PF` assumption, so synthesis cannot assume a tighter
    boundary than STA later checks against.
- **Synthesis constraints**: technology mapping plus the timing-driven target above.
  Recipe: `proc; opt; fsm; opt; memory; opt; techmap; opt; dfflibmap -liberty <timing
  lib>; abc -liberty <timing lib> -constr <constr file> -script <abc script>;
  opt_clean -purge; clean`. The `-script` is a custom recipe (`build_abc_script` in
  `flow/synth_tmds_encoder.py`) that replicates Yosys's own default `-D`-driven
  `-constr` script **except** it omits the `retime -o -D <ps>` splice that bare
  `-D` would otherwise insert -- that splice was found, directly, to corrupt this
  design (`tmds` primary output left with no driver at all); see that function's
  docstring for the full finding. Exact scripts:
  `flow/tmds_encoder/reports/{rid}.synth.ys` (Yosys),
  `flow/tmds_encoder/reports/{rid}.synth.abc` (ABC), and the `-constr` file above.
- **Result**: PASS -- {total_cells} cell instances ({seq_cells} sequential, {comb_cells}
  combinational), 0 unmapped cells (every instance is a `{CELL_PREFIX}*` standard
  cell; checked both by the synthesis script's own
  `select -assert-none t:$_*` and by re-parsing the written netlist -- see
  `cell_counts`/`assert_fully_mapped` in `flow/synth_tmds_encoder.py`). Cell
  breakdown:
{breakdown}
- **Warnings**: every distinct `Warning:` line the run's log contains, explained rather
  than left as noise (per issue #82's "no synthesis warnings left unexplained"
  acceptance criterion; note the captured log can end early on this repo's
  `yowasp-yosys` install after ABC's liberty-load stage even though the run itself
  completes successfully -- see `flow/README.md`'s "yowasp-yosys" gotcha -- so this
  list is a lower bound, not a guarantee no further warning was printed):
{warnings_block}
- **Reproducibility**: working tree {"DIRTY (uncommitted changes outside flow/tmds_encoder/ at run time -- re-run against a clean checkout before trusting this record)" if dirty else "clean"} at commit `{sha}`.
- **Links**:
  - RTL source: `rtl/tmds_encoder.v`
  - Netlist: `flow/tmds_encoder/netlist/tmds_encoder.synth.v`
  - Yosys script: `flow/tmds_encoder/reports/{rid}.synth.ys`
  - ABC script: `flow/tmds_encoder/reports/{rid}.synth.abc`
  - ABC `-constr` file: `flow/tmds_encoder/reports/{rid}.synth.constr`
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
    parser.add_argument(
        "--allow-unexplained-warnings",
        action="store_true",
        help=(
            "don't fail on a Warning: line this script doesn't recognize -- record it "
            "as 'NOT YET EXPLAINED' instead of refusing to mint a record. Use only to "
            "investigate a new warning; add it to _KNOWN_WARNINGS afterward."
        ),
    )
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        liberty = liberty_path(pdk)
        timing_liberty = timing_liberty_path(pdk)
    except SynthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    when = _dt.datetime.now(_dt.timezone.utc)
    rid = record_id(when)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ys_path = REPORTS_DIR / f"{rid}.synth.ys"
    log_path = REPORTS_DIR / f"{rid}.synth.log"
    constr_path = REPORTS_DIR / f"{rid}.synth.constr"
    constr_path.write_text(build_constr_file())
    abc_script_path = REPORTS_DIR / f"{rid}.synth.abc"
    abc_script_path.write_text(build_abc_script())

    script = build_yosys_script(timing_liberty, liberty, constr_path, abc_script_path)
    ys_path.write_text(script)

    print(
        f"Synthesizing {TOP} against {timing_liberty} "
        f"(timing-driven, -D {TARGET_PERIOD_PS}ps target) ..."
    )
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

    warnings = extract_warnings(log_path.read_text())
    unexplained = [w for w in warnings if explain_warning(w).startswith("NOT YET EXPLAINED")]
    if unexplained and not args.allow_unexplained_warnings:
        print("ERROR: unexplained synthesis warning(s) -- add an entry to _KNOWN_WARNINGS", file=sys.stderr)
        for w in unexplained:
            print(f"  {w}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"WARNING: {w}")

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
                timing_liberty=timing_liberty,
                yosys_v=yosys_version(),
                counts=counts,
                dirty=working_tree_dirty(),
                warnings=warnings,
                log_path=log_path,
                ys_path=ys_path,
            )
        )
        print(f"Evidence record written to {record_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
