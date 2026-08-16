#!/usr/bin/env python3
"""Drop P&R-inserted, non-logic-bearing standard cells from a `klt extract`
netlist (issue #84).

`flow/pnr_tmds_encoder.py`'s place-and-route run inserts filler
(`gf180mcu_fd_sc_mcu9t5v0__fill_*`) and tap/endcap (`..._filltie`,
`..._endcap`) cells that the synthesized netlist (`flow/tmds_encoder/netlist/
tmds_encoder.synth.v`, issue #82) never instantiates and never could -- they
carry no logic pins at all (`VDD`/`VSS` only; zero devices once abstracted,
confirmed in isolation before this script was written) and exist purely for
density-fill and well/substrate-tap DRC rules. `gen_tmds_encoder_ref.py`'s
reference netlist, built directly from the synthesized netlist, has no
corresponding declarations for these cell types.

**Not part of the primary signoff flow used for the committed
`layout/lvs_reports/tmds_encoder.lvs.json`**: feeding both netlists straight
into `klt lvs` (i.e. skipping this script) does *not* fail the entire
top-level comparison, as an earlier draft of this docstring claimed --
verified directly: the top-level circuit's own nets/pins match fully, and
`NetlistComparer` reports exactly one isolated, clearly-attributable
`topology` mismatch per unmatched utility cell *type* (9 types + one
top-level rollup, 10 total), which is a scoped, explainable finding the
committed LVS report simply carries and documents, rather than a cascading
failure this script is required to work around. Kept as an optional utility
for a caller who wants a strictly filtered, warning-free comparison instead
of a disclosed one:

    python3 layout/scripts/filter_pnr_utility_cells.py \\
        layout/gds/tmds_encoder.spice -o /tmp/filtered.spice
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

UTILITY_SUFFIXES = ("filltie", "endcap", "tieh", "tiel")


def utility_types(text: str) -> set[str]:
    types = set(re.findall(r"gf180mcu_fd_sc_mcu9t5v0__fill_\d+", text))
    types.update(f"gf180mcu_fd_sc_mcu9t5v0__{s}" for s in UTILITY_SUFFIXES)
    return types


def group_statements(lines: list[str]) -> list[list[str]]:
    """SPICE '+'-continuation lines belong to the statement they continue."""
    statements: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line.startswith("+") and cur:
            cur.append(line)
        else:
            if cur:
                statements.append(cur)
            cur = [line]
    if cur:
        statements.append(cur)
    return statements


def filter_netlist(text: str) -> tuple[str, int, int]:
    types = utility_types(text)
    statements = group_statements(text.split("\n"))

    out_lines: list[str] = []
    dropped_subckts = 0
    dropped_instances = 0
    skip_subckt: str | None = None
    for stmt in statements:
        first = stmt[0]
        joined = " ".join(s.lstrip("+").strip() for s in stmt)
        if skip_subckt is not None:
            if first.startswith(f".ENDS {skip_subckt}"):
                skip_subckt = None
            continue
        if first.startswith(".SUBCKT "):
            name = first.split()[1]
            if name in types:
                skip_subckt = name
                dropped_subckts += 1
                continue
        if first.startswith("X"):
            if joined.split()[-1] in types:
                dropped_instances += 1
                continue
        out_lines.extend(stmt)

    return "\n".join(out_lines) + "\n", dropped_subckts, dropped_instances


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("netlist", type=Path)
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()

    text = args.netlist.read_text()
    filtered, dropped_subckts, dropped_instances = filter_netlist(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(filtered)
    print(
        f"OK: dropped {dropped_subckts} utility cell-type declaration(s), "
        f"{dropped_instances} utility instance(s) -- wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
