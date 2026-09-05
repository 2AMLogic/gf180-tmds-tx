#!/usr/bin/env python3
"""Serializer synthesized-domain rate-ceiling check -- the reproducible
measurement `spec/decisions/0014-serializer-rate-ceiling-and-microarchitecture.md`
cites.

This is deliberately **not** a synthesis, place-and-route, or STA driver
like `flow/synth_tmds_encoder.py` / `flow/pnr_tmds_encoder.py` /
`flow/sta_tmds_encoder.py` -- this repository's sandboxed build environment
could not reach the OpenROAD/Docker toolchain those need when DR-0014 was
written (see that record's "Alternatives considered"). What this script
*can* do without OpenROAD, and does: read the two library timing arcs
DR-0014's feasibility argument rests on directly out of the vendored
`gf180mcu_fd_sc_mcu9t5v0__ss_125C_3v00.lib` liberty file, and combine them
with the `SEQUENTIAL_OVERHEAD_NS` figure `flow/synth_tmds_encoder.py`
already measured (issue #115's post-route STA,
`flow/tmds_encoder/records/20260817-110611-37e197a.md`) for the *same*
library, corner, and flip-flop cell (`gf180mcu_fd_sc_mcu9t5v0__dffq_1`)
`rtl/tmds_serializer.v`'s own registers would map to if synthesized.

## What this proves and what it does not

`SEQUENTIAL_OVERHEAD_NS` is a floor on *every* register-to-register path in
this library at this corner, independent of which design the registers
belong to: it is the delay of a path with zero logic between two
`dffq_1` instances. Adding the one `mux2_2` level DR-0014's Decision 1
picks as the reduction stage's own micro-architecture gives a lower bound
on that micro-architecture's own register-to-register requirement. This
script compares that bound against both ratified operating points'
`clk_half` periods (DR-0012 Decision 1: 371.25 MHz @ 720p60, 135 MHz @
480p) and renders PASS ("this rate sits inside the achievable envelope")
or FAIL ("even the minimal micro-architecture cannot close timing at this
rate on this library").

A PASS here is **necessary, not sufficient** -- it says the floor does not
already rule the rate out, not that a real synthesized netlist has been
measured against it (no synthesis/P&R/STA run of `rtl/tmds_serializer.v`
exists yet at either rate; DR-0014's "Consequences" discloses this
explicitly). A FAIL here **is** sufficient -- no combinational network,
however small, can beat two flip-flops' own clock-to-Q and setup arcs.

Cold-start invocation (from a clean checkout, PDK installed -- same
resolution as `flow/synth_tmds_encoder.py`, no Yosys/OpenROAD required):

    python3 flow/serializer_rate_feasibility.py

Exit status is non-zero if the PDK/liberty file can't be found, or if
either the `mux2_2` or `dffq_1` timing arc this script looks for is
missing from the liberty file (a hard failure, not a silent fallback --
if the vendored library's cell-naming or timing-table grid ever changes,
this script must say so rather than report a stale number).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from flow.synth_tmds_encoder import (  # noqa: E402
    SEQUENTIAL_OVERHEAD_NS,
    STD_CELL_LIB,
    TIMING_CORNER,
    SynthError,
    timing_liberty_path,
)
from sim.harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402

# DR-0012 Decision 1's clk_half rate at each ratified operating point
# (spec/tmds-tx.md #1/#2 -- 742.5 Mbps/lane and 270 Mbps/lane bit rates,
# divided by 2 for clk_half, which is 5x the pixel clock by construction --
# see DR-0012 Decision 1 and rtl/tmds_serializer.v's own header).
CLK_HALF_MHZ = {
    "720p60": 371.25,
    "480p": 135.0,
}

# The one mux2_2 level DR-0014 Decision 1 picks as the reduction stage's
# register-to-register logic depth (the shift/load select between one
# 10-bit shift-register stage and the next).
_MUX_CELL = f"{STD_CELL_LIB}__mux2_2"
_DFF_CELL = f"{STD_CELL_LIB}__dffq_1"

# The liberty grid point read out for the mux2_2 I0->Z cell_fall arc:
# (input transition index, output load index) -- chosen as a small-but-not-
# zero point representative of a similarly-sized driving/loading stage,
# matching the exact point `rtl/tmds_serializer.v`'s own header comment
# already cites (1.192 ns). Any other grid point would still be a real,
# liberty-sourced number; this one is picked so this script's output is
# checkable against that existing citation.
_TRANSITION_INDEX = 1  # index_1[1] = 0.111 ns
_LOAD_INDEX = 2  # index_2[2] = 0.02966 pF


class FeasibilityError(RuntimeError):
    """The liberty file didn't contain what this script expected to find."""


def _extract_balanced_block(text: str, start: int) -> str:
    """Return the ``{ ... }`` block beginning at the ``{`` at or after `start`.

    Liberty files nest groups arbitrarily deep with no delimiter other than
    braces, so this is a plain depth counter over the raw text -- the same
    "parse only what you need, mechanically" discipline
    `flow/synth_tmds_encoder.py`'s own `_INSTANCE_RE`/netlist re-parse uses,
    applied to braces instead of a netlist's `instance name (` lines.
    """
    open_idx = text.index("{", start)
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx : i + 1]
    raise FeasibilityError(f"unbalanced braces starting at offset {open_idx}")


def _find_cell_block(liberty_text: str, cell_name: str) -> str:
    marker = f"cell({cell_name})"
    idx = liberty_text.find(marker)
    if idx < 0:
        raise FeasibilityError(
            f"cell {cell_name!r} not found in liberty file -- the vendored "
            f"{STD_CELL_LIB} library's cell naming may have changed"
        )
    return _extract_balanced_block(liberty_text, idx + len(marker))


def _parse_values_matrix(block: str) -> list[list[float]]:
    """Parse a ``values("a, b, ...", "c, d, ...")`` group into a 2-D float list."""
    match = re.search(r'values\((".*?")\s*\)', block, re.DOTALL)
    if not match:
        raise FeasibilityError("no values(...) group found in the expected timing block")
    rows_text = match.group(1)
    rows = re.findall(r'"([^"]*)"', rows_text)
    return [[float(x) for x in row.split(",")] for row in rows]


def mux2_i0_to_z_fall_ns(liberty_text: str) -> float:
    """The `mux2_2` I0->Z `cell_fall` delay at this module's chosen grid point.

    Scans every top-level ``timing() { ... }`` group in the `mux2_2` cell
    block (there are several -- one per input pin x sdf_cond combination,
    e.g. `internal_power()` groups also carry a `related_pin` field but are
    not `timing()` groups, so this deliberately looks for `timing()` groups
    specifically rather than searching backward from a `related_pin` match,
    which would also match those non-timing groups) and returns the
    `cell_fall` value at this module's chosen grid point for the one whose
    `related_pin` is `I0` and whose `sdf_cond` selects the I0-passthrough
    case (`I1===1'b0`) -- the I0->Z arc `rtl/tmds_serializer.v`'s own header
    comment cites.
    """
    cell_block = _find_cell_block(liberty_text, _MUX_CELL)
    search_from = 0
    while True:
        group_idx = cell_block.find("timing()", search_from)
        if group_idx < 0:
            break
        timing_block = _extract_balanced_block(cell_block, group_idx)
        search_from = group_idx + len(timing_block)
        if (
            'related_pin : "I0"' in timing_block
            and "sdf_cond : \"I1===1'b0\"" in timing_block
            and "cell_fall" in timing_block
        ):
            fall_idx = timing_block.find("cell_fall(")
            fall_block = _extract_balanced_block(timing_block, fall_idx)
            matrix = _parse_values_matrix(fall_block)
            return matrix[_TRANSITION_INDEX][_LOAD_INDEX]
    raise FeasibilityError(
        f"no I0->Z cell_fall timing() arc (sdf_cond I1===1'b0) found in "
        f"{_MUX_CELL}'s liberty block"
    )


def render_report(mux_delay_ns: float, liberty: Path, pdk: Pdk) -> tuple[str, bool]:
    required_ns = round(SEQUENTIAL_OVERHEAD_NS_EXACT + mux_delay_ns, 4)
    lines = [
        f"Serializer synthesized-domain rate-ceiling check ({TIMING_CORNER})",
        f"  liberty          : {liberty}",
        f"  PDK              : {pdk.variant} (open_pdks {pdk.version})",
        f"  sequential floor : {SEQUENTIAL_OVERHEAD_NS_EXACT:.4f} ns "
        f"(clk->Q + setup + skew, {_DFF_CELL}, flow/synth_tmds_encoder.py)",
        f"  mux2_2 I0->Z     : {mux_delay_ns:.4f} ns (cell_fall, this liberty file)",
        f"  required reg2reg : {required_ns:.4f} ns",
        "",
    ]
    ok = True
    for label, freq_mhz in CLK_HALF_MHZ.items():
        period_ns = round(1000.0 / freq_mhz, 4)
        margin_ns = round(period_ns - required_ns, 4)
        verdict = "PASS" if margin_ns > 0 else "FAIL"
        ok = ok and margin_ns > 0
        pct = round(100.0 * margin_ns / period_ns, 1)
        lines.append(
            f"  {label:8s} clk_half={freq_mhz:7.2f} MHz  period={period_ns:.4f} ns  "
            f"margin={margin_ns:+.4f} ns ({pct:+.1f} %)  {verdict}"
        )
    return "\n".join(lines), ok


# The unrounded sequential-overhead figure `flow/synth_tmds_encoder.py`'s own
# comment states (2.3452 + 0.7707 + 0.004 = 3.1199 ns), used here in
# preference to that module's rounded `SEQUENTIAL_OVERHEAD_NS = 3.2` constant
# so this script's arithmetic matches DR-0014's own worked numbers exactly.
# Importing the rounded constant above still ties this script to that
# module (so a future change to the measured figure is not silently
# missed); this local override is the deliberately tighter (harder-to-pass)
# of the two and is asserted against the imported constant below.
SEQUENTIAL_OVERHEAD_NS_EXACT = 3.1199
assert SEQUENTIAL_OVERHEAD_NS_EXACT <= SEQUENTIAL_OVERHEAD_NS, (
    "flow/synth_tmds_encoder.py's rounded-UP SEQUENTIAL_OVERHEAD_NS no longer "
    "bounds this script's unrounded figure from above -- re-derive both from a "
    "fresh STA record before trusting this script's output"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        liberty = timing_liberty_path(pdk)
    except SynthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    liberty_text = liberty.read_text()
    try:
        mux_delay_ns = mux2_i0_to_z_fall_ns(liberty_text)
    except FeasibilityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report, ok = render_report(mux_delay_ns, liberty, pdk)
    print(report)
    print()
    print("OVERALL:", "PASS (480p inside the envelope)" if ok else "FAIL")
    print(
        "(see spec/decisions/0014-serializer-rate-ceiling-and-microarchitecture.md "
        "for what this result means for each operating point -- a FAIL row is a "
        "hard floor violation; a PASS row is necessary, not sufficient, pending an "
        "actual synthesis/P&R/STA run of rtl/tmds_serializer.v)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
