#!/usr/bin/env python3
"""Drop P&R-inserted, non-logic-bearing standard cells from a netlist
(issue #84; Verilog form added for issue #190).

`flow/pnr_tmds_encoder.py`'s place-and-route run inserts filler
(`gf180mcu_fd_sc_mcu9t5v0__fill_*`) and tap/endcap (`..._filltie`,
`..._endcap`) cells that the synthesized netlist (`flow/tmds_encoder/netlist/
tmds_encoder.synth.v`, issue #82) never instantiates and never could -- they
carry no logic pins at all (`VDD`/`VSS` only; zero devices once abstracted,
confirmed in isolation before this script was written) and exist purely for
density-fill and well/substrate-tap DRC rules. `gen_tmds_encoder_ref.py`'s
reference netlist, built directly from the synthesized netlist, has no
corresponding declarations for these cell types.

Two input forms, selected by `--form`:

**SPICE** (the original, issue #84): drops the utility types' `.SUBCKT`
declaration blocks and every `X<...>` instance calling them, from a
`klt extract` netlist.

**Verilog** (issue #190): drops the utility types' instance statements from
a post-P&R gate-level Verilog netlist. OpenROAD's `write_verilog`, as run by
`flow/gen_pnr_netlist.py` against the routed DEF, *does* emit these
instances -- each as a single line with an empty connection list, e.g.
`gf180mcu_fd_sc_mcu9t5v0__fill_4 FILLER_0_10 ();` -- even though the cells
carry no signal pins (klt's own `write_verilog` equivalent skips them
altogether, `docs/cli/lvs.md` "`topology.power_only_pruned`"). `klt lvs
reference.form: "gate-level-verilog"` cannot compare such a design cleanly
today: it prunes the *layout*-side power-only circuits (issue #1622) but
has no symmetric handling when the reference itself instantiates them
(filed upstream generically; see `layout/README.md`'s gate-level LVS
subsection for the citation), so each reference-side filler instance
surfaces as a `topology` / "circuit could not be matched to a counterpart"
error (970 of them + one per type on this design). Reading the committed
`tmds_encoder.pnr.v` through this filter first removes exactly those
power-only instances -- **and nothing else**: mode "verilog" verifies that
every dropped line is a utility-master instantiation with an *empty*
connection list, and aborts (exit 1) on any utility-master line that is not,
because a fill/tap cell that carries a real connection is signal-bearing
content that must not silently vanish. On the committed
`tmds_encoder.pnr.v`: 970 dropped (72 `endcap`, 19 `filltie`, 879 `fill_*`),
zero aborts.

**SPICE form not part of the primary signoff flow used for the committed
`layout/lvs_reports/tmds_encoder.lvs.json`**: feeding both netlists straight
into `klt lvs` (i.e. skipping this script) does *not* fail the entire
top-level comparison, as an earlier draft of this docstring claimed --
verified directly: the top-level circuit's own nets/pins match fully, and
`NetlistComparer` reports exactly one isolated, clearly-attributable
`topology` mismatch per unmatched utility cell *type* (9 types + one
top-level rollup, 10 total), which is a scoped, explainable finding the
committed LVS report simply carries and documents, rather than a cascading
failure this script is required to work around. Kept as an optional SPICE
utility for a caller who wants a strictly filtered, warning-free comparison
instead of a disclosed one:

    python3 layout/scripts/filter_pnr_utility_cells.py \\
        layout/gds/tmds_encoder.spice -o /tmp/filtered.spice

The Verilog form IS part of a committed flow -- the gate-level-verilog LVS
read's recipe (`layout/README.md`'s "gate-level-verilog LVS read" section,
issue #190):

    python3 layout/scripts/filter_pnr_utility_cells.py --form verilog \\
        flow/tmds_encoder/netlist/tmds_encoder.pnr.v \\
        -o layout/lvs/tmds_encoder.pnr_signal_only.v
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


class UtilityInstanceHasConnectionsError(Exception):
    """A utility-master Verilog line carries content beyond an empty
    instantiation -- signal-bearing content this filter must not drop."""

    def __init__(self, lineno: int, line: str) -> None:
        super().__init__(
            f"line {lineno}: utility-cell instantiation is not the expected "
            f"single-line empty form and will NOT be dropped -- a fill/tap "
            f"instance that carries a connection is real content:\n{line}"
        )
        self.lineno = lineno
        self.line = line


def filter_verilog_netlist(text: str) -> tuple[str, int, int]:
    """Drop utility-cell **instances** from a post-P&R gate-level Verilog
    netlist. Verilog has no in-file master declarations to drop (the cell
    types live in the standard-cell library), so every dropped statement is
    an instantiation line; anything a utility master instantiates with real
    connections raises :class:`UtilityInstanceHasConnectionsError` and nothing
    is written.

    Only lines whose first token is a utility master are examined at all --
    everything else passes through verbatim, multi-line logic instantiations
    included; this filter never re-groups or reformats passing content.
    """
    types = utility_types(text)
    master = re.compile(r"^\s*(\S+)\s+(\S+)\s*\((.*)\)\s*;\s*$")

    out_lines: list[str] = []
    dropped_subckts = 0
    dropped_instances = 0
    for lineno, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        first = stripped.split(" ")[0] if stripped else ""
        if first not in types:
            out_lines.append(line)
            continue
        m = master.match(line)
        if m is None or m.group(3).strip():
            raise UtilityInstanceHasConnectionsError(lineno, line)
        dropped_instances += 1

    return "\n".join(out_lines) + "\n", dropped_subckts, dropped_instances


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("netlist", type=Path)
    ap.add_argument("-o", "--output", required=True, type=Path)
    ap.add_argument(
        "--form",
        choices=("spice", "verilog"),
        default="spice",
        help="input netlist form: 'spice' (the klt extract netlist, the original "
        "issue #84 mode) or 'verilog' (a post-P&R gate-level netlist; drops only "
        "empty-connection utility instances and aborts on any that carry content)",
    )
    args = ap.parse_args()

    text = args.netlist.read_text()
    if args.form == "verilog":
        try:
            filtered, dropped_subckts, dropped_instances = filter_verilog_netlist(text)
        except UtilityInstanceHasConnectionsError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
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
