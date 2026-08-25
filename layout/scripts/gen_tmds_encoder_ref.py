#!/usr/bin/env python3
"""Derive the digital gate-level LVS reference netlist for `tmds_encoder`.

Mechanically translates a gate-level Verilog netlist into the hierarchical
SPICE form `klt lvs` compares against a `klt extract --abstract-cells`
layout-side extraction (issue #84; see docs/cli/extract.md's "Cell-level
(black-box + pins) abstraction" in a `klayout-tools` checkout for that
extraction mode's contract). This is *not* a schematic -- it is an existing
netlist restated as one `X<instance>` SPICE card per Verilog cell instance,
wired to the same net names.

**Which netlist, and why it matters (issue #142).** Pass `--from-pnr` with
`flow/tmds_encoder/netlist/tmds_encoder.pnr.v` -- the **post**-P&R netlist
that `flow/gen_pnr_netlist.py` reads out of the committed routed DEF. That
is the signoff path, and the one `layout/README.md` documents.

This script originally translated the **pre**-P&R synthesized netlist
(`tmds_encoder.synth.v`, issue #82) instead, framing LVS as "did
place-and-route preserve the synthesized netlist's connectivity". That
framing does not survive contact with a real P&R run: place-and-route
*legitimately* inserts cells the synthesized netlist has no counterpart for
-- fill, tap/endcap, CTS buffers, hold-repair delay cells and inverters,
setup-repair resized gates -- so the comparison reported 18 topology
mismatches that were not defects, and could not have reported anything else.
Grading the layout against the netlist it was actually built from is what
LVS is for; whether P&R preserved *synthesis* is a separate question, which
`flow/gate_level_sim_tmds_encoder.py`'s SDF-back-annotated re-simulation and
`flow/sta_tmds_encoder.py`'s `assert_def_matches_netlist` answer.

Both input formats are still accepted -- the synthesized netlist remains
translatable (without `--from-pnr`) for anyone who wants that comparison
explicitly -- but only the post-P&R form is expected to reach `status:
match` against a routed layout.

Two additions beyond a literal transliteration, both mechanical and
documented here rather than silently applied:

1. **Per-cell-type pin order** is read from `--subckt-headers-from`, a file
   containing one `.SUBCKT <celltype> <pins...>` header per distinct
   standard-cell type -- copied verbatim from a `klt extract
   --abstract-cells 'gf180mcu_fd_sc_mcu9t5v0__*'` run against the routed
   layout (this script's own `--abstract-cell-lef` companion run), *not*
   independently re-derived from the LEF. This guarantees the reference's
   `X<instance>` argument order matches the layout-side extraction's
   `.SUBCKT` declarations byte-for-byte, which is what makes the two
   netlists' shared cell-type names resolve to the same pin roles --
   `klt lvs` needs this because each abstracted cell type is declared
   independently (as an opaque empty-body black box) on both sides, matched
   by name, not by a shared physical definition.
2. **VDD/VSS power pins**, present on every standard-cell macro's LEF (and
   therefore in every abstracted `.SUBCKT` header) but absent from the
   synthesized netlist's per-instance port connections (synthesis is
   logic-only; power routing is a P&R-stage concern) are added to every
   `X<instance>` card, tied to two module-level nets named `VDD`/`VSS` --
   matching the physical block's own top-level power pins (P&R placed
   explicit `VDD`/`VSS` boundary pins; see this module's own PDN
   configuration). This reference declares VDD and VSS as two *separate*
   nets, as the design actually is, and as the layout-side extraction now
   also reports (see below -- this was not always true).

**A divergence this script originally worked around turned out to be a
merge-step bug, not a deck limitation, and no longer applies.** An earlier
version of `flow/pnr_tmds_encoder.py`'s DEF->GDS merge step had a DBU
mismatch (see that module's own docstring's "GDS streamout" section) that,
among other effects, corrupted net-boundary geometry and caused the
layout-side extraction to merge the `VDD`- and `VSS`-labelled nets into one
node (`VDD|VSS`). This script originally modeled that merged net directly
(a single `POWER_NET = "VDD|VSS"` constant) to match. Now that the merge
step is fixed, a fresh layout-side extraction reports `VDD` and `VSS` as
two distinct nets, matching what this reference always claimed in its own
prose (two separate nets) -- so the constant is now `POWER_PINS` mapped
1:1, not merged.

Two mechanical, zero-semantic-impact preprocessing deltas from the committed
`tmds_encoder.synth.v` are also carried over unchanged from the P&R input
copy (see `flow/pnr_tmds_encoder.py`'s docstring): `wire signed` -> `wire`
(a type-only annotation OpenROAD's simplified Verilog reader rejects), and
the single dead `assign cnt[0] = 1'h0;` (zero fanout, verified by this
script re-deriving the same fanout check `flow/pnr_tmds_encoder.py` runs)
dropped rather than translated to an unconnected reference net -- since
neither ever reaches P&R, neither should appear in the *reference* either;
representing physically-absent logic would be the actual netlist deviation.

Usage (signoff path):

    python3 flow/gen_pnr_netlist.py
    python3 layout/scripts/gen_tmds_encoder_ref.py \\
        --netlist flow/tmds_encoder/netlist/tmds_encoder.pnr.v --from-pnr \\
        --subckt-headers-from <klt-extract-output.spice> \\
        -o layout/lvs/tmds_encoder.ref.spice

and its negative control (add `--negative-control`, see break_one_net()):

    python3 layout/scripts/gen_tmds_encoder_ref.py \\
        --netlist flow/tmds_encoder/netlist/tmds_encoder.pnr.v --from-pnr \\
        --negative-control \\
        --subckt-headers-from <klt-extract-output.spice> \\
        -o layout/lvs/tmds_encoder_negctl.ref.spice
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_PORT_RE = re.compile(r"^\s*(input|output|inout)\s+(\[(\d+):(\d+)\])?\s*(\w+)\s*;", re.MULTILINE)
# One instance card, in either supported writer's layout (see `--from-pnr`):
#   Yosys      `  <celltype> <inst> (\n    .A(n),\n    .Z(m)\n  );`
#   OpenROAD   ` <celltype> <inst> (.A(n),\n    .Z(m));`  /  ` <celltype> <inst> ();`
# `\).*?\);` is non-greedy and `);` only ever terminates the card: a connection
# ends `),` or `)\n`, never `);`.
_INSTANCE_RE = re.compile(
    r"^\s*(gf180mcu_fd_sc_mcu9t5v0__\w+)\s+(\S+)\s*\((.*?)\);",
    re.MULTILINE | re.DOTALL,
)
_CONN_RE = re.compile(r"\.(\w+)\((.*?)\)")
_SUBCKT_HEADER_RE = re.compile(r"^\.SUBCKT (\S+) (.+)$", re.MULTILINE)

POWER_PINS = ("VDD", "VSS")  # each power pin ties to a module-level net of the same name


def parse_ports(text: str) -> list[str]:
    """Bit-blasted top-level port net names, in declaration order."""
    ports: list[str] = []
    for direction, _bus, msb, lsb, name in _PORT_RE.findall(text):
        if msb == "":
            ports.append(name)
        else:
            hi, lo = int(msb), int(lsb)
            step = -1 if hi >= lo else 1
            for i in range(hi, lo + step, step):
                ports.append(f"{name}[{i}]")
    return ports


def parse_instances(text: str) -> list[tuple[str, str, dict[str, str]]]:
    """[(cell_type, instance_name, {pin: net}), ...] in file order."""
    out = []
    for cell_type, inst_name, body in _INSTANCE_RE.findall(text):
        conns = dict(_CONN_RE.findall(body))
        out.append((cell_type, inst_name, conns))
    return out


def parse_subckt_headers(text: str) -> dict[str, list[str]]:
    """{cell_type: [pin, ...]} from klt extract's own `.SUBCKT` lines."""
    headers: dict[str, list[str]] = {}
    for name, pins in _SUBCKT_HEADER_RE.findall(text):
        if name.startswith("gf180mcu_fd_sc_mcu9t5v0__"):
            headers[name] = pins.split()
    return headers


def check_dead_net(text: str, net: str) -> bool:
    """True if `net` (e.g. 'cnt[0]') is never read by any instance connection
    or continuous assignment RHS -- the same "genuinely unused" check this
    script's docstring claims for the dropped `assign cnt[0] = 1'h0;` line."""
    # Every reference to the net other than its own declaration/assignment.
    refs = re.findall(re.escape(net) + r"\b", text)
    # 1 wire declaration + 1 assign LHS use are expected; anything more means
    # some instance reads it.
    return len(refs) <= 2


def render(top: str, ports: list[str], instances: list[tuple[str, str, dict[str, str]]],
           headers: dict[str, list[str]], allow_unconnected: bool = False) -> str:
    lines = []
    used_types = sorted({t for t, _, _ in instances})
    for t in used_types:
        if t not in headers:
            raise SystemExit(
                f"ERROR: no .SUBCKT header found for {t} in --subckt-headers-from "
                "-- re-run klt extract with --abstract-cells covering this cell type"
            )
        pins = headers[t]
        lines.append(f".SUBCKT {t} {' '.join(pins)}")
        lines.append(f".ENDS {t}")
        lines.append("")

    lines.append(f".SUBCKT {top} {' '.join(ports)} {' '.join(POWER_PINS)}")
    dangling = 0
    for cell_type, inst_name, conns in instances:
        pins = headers[cell_type]
        nets = []
        for pin in pins:
            if pin in POWER_PINS:
                nets.append(pin)
            elif pin in conns:
                nets.append(conns[pin])
            elif allow_unconnected:
                # A pin the writer omitted because nothing drives or reads it.
                # CTS's `clkload*` cells are the real case: `clock_tree_synthesis`
                # inserts them purely as capacitive balancing loads on leaf clock
                # nets, so their output pin is deliberately left open. SPICE has no
                # "unconnected" token, so each gets its own single-terminal net --
                # which is exactly what the layout-side extraction does too (it
                # names them `$<n>`). Matching floating net against floating net is
                # the honest representation; tying them to ground would invent
                # connectivity the layout does not have.
                dangling += 1
                nets.append(f"{inst_name}__{pin}__unconnected")
            else:
                raise SystemExit(
                    f"ERROR: instance {inst_name} ({cell_type}) has no connection for "
                    f"pin {pin} -- header/netlist pin-name mismatch"
                )
        lines.append(f"X{inst_name} {' '.join(nets)} {cell_type}")
    lines.append(f".ENDS {top}")
    lines.append("")
    if dangling:
        print(f"note: {dangling} deliberately-unconnected cell pin(s) given their own net")
    return "\n".join(lines)


def break_one_net(text: str) -> tuple[str, str]:
    """Merge two top-level input nets, producing the LVS negative control.

    Returns ``(broken_netlist_text, human_description)``.

    This is the *reference*-side counterpart of the `_shorted` GDS twin every
    other cell in this repo ships (`gen_pad_v2.py --shorted`): a deliberate,
    minimal, single-fault break whose only job is to prove that `klt lvs`
    still fails when the two netlists genuinely differ. Without it, the intact
    run's `status: match` is an unfalsified claim -- see
    `layout/scripts/check_lvs_signoff.py`'s docstring and issue #129 for the
    worked example of a negative control rotting into a silent pass.

    **Why the break is on the reference side here, and not on the layout
    side.** The layout half of this cell's comparison is a committed
    `klt extract --abstract-cells` netlist, and the currently-installed
    `klt` 0.3.0 mis-binds abstracted cell pins to nets on this design
    (klayout-tools#1366): re-extracting the same unchanged GDS yields 26
    instances with a ground pin bound to the power net and 100 instances
    with an output bound to one of their own inputs, none of which the
    committed 0.2.0 extraction contains. A `_shorted` GDS twin therefore
    cannot be extracted cleanly right now, and a control whose failure might
    be the tool's rather than the injected fault's is not a control. Breaking
    the reference instead keeps **both** sides of this comparison on
    artifacts that are known-good: the layout side stays the committed
    0.2.0 extraction, untouched. Restoring the layout-side twin is tracked
    separately, blocked on klayout-tools#1366.

    The break: rename every occurrence of the `ctrl[0]` net to `data[3]`,
    merging two logically-unrelated primary inputs into one. LVS must then
    report both a net-count difference and unmatched pins.
    """
    victim, absorber = "ctrl[0]", "data[3]"
    pattern = re.compile(re.escape(victim) + r"(?![\w\[])")
    broken, count = pattern.subn(absorber, text)
    if count < 2:
        raise SystemExit(
            f"ERROR: negative control expected to rewrite at least 2 "
            f"occurrences of {victim!r} (its top-level pin plus at least one "
            f"instance connection) but rewrote {count} -- the netlist no "
            f"longer looks the way this control assumes; pick another net"
        )
    return broken, (
        f"merged top-level input net {victim} into {absorber} "
        f"({count} occurrence(s) rewritten)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--netlist", required=True, type=Path)
    ap.add_argument("--subckt-headers-from", required=True, type=Path)
    ap.add_argument("--top", default="tmds_encoder")
    ap.add_argument(
        "--from-pnr",
        action="store_true",
        help="the --netlist is the post-P&R netlist written from the routed DEF "
        "(flow/tmds_encoder/netlist/tmds_encoder.pnr.v) rather than the pre-P&R "
        "synthesized netlist. Skips the synth-only `cnt[0]` dead-tie check, whose "
        "preprocessing has already been applied upstream of P&R.",
    )
    ap.add_argument(
        "--negative-control",
        action="store_true",
        help="emit the deliberately-broken reference (two top-level input nets "
        "merged) that `klt lvs` must report as a mismatch. See break_one_net().",
    )
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()

    text = args.netlist.read_text()

    if not args.from_pnr and not check_dead_net(text, "cnt[0]"):
        raise SystemExit(
            "ERROR: cnt[0] is no longer dead (read by some instance) -- "
            "the 'drop the dead tie' preprocessing this script documents no "
            "longer applies; investigate before trusting this reference"
        )

    ports = parse_ports(text)
    instances = parse_instances(text)
    headers = parse_subckt_headers(args.subckt_headers_from.read_text())

    out = render(args.top, ports, instances, headers, allow_unconnected=args.from_pnr)
    note = ""
    if args.negative_control:
        out, note = break_one_net(out)
        note = f" -- NEGATIVE CONTROL: {note}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out)
    print(
        f"OK: {len(instances)} instances, {len(ports)} top-level signal ports "
        f"-- wrote {args.output}{note}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
