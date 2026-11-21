#!/usr/bin/env python3
"""Shared dead-tie assignment validation for ``tmds_encoder.synth.v`` (issue #384).

The synthesized netlist Yosys writes carries a handful of top-level
continuous assignments (``  assign cnt[0] = 1'h0;`` and friends). Two
consumers drop them -- OpenROAD's simplified Verilog reader rejects
continuous assignments it cannot fold, and the LVS reference generator
translates cell instances only -- so both must first prove that dropping
each assignment loses no driver:

- ``flow/pnr_tmds_encoder.py`` runs the validator before stripping the
  assignments for its OpenROAD input copy
  (``preprocess_netlist_for_openroad``);
- ``layout/scripts/gen_tmds_encoder_ref.py`` runs it before translating a
  synthesized netlist without ``--from-pnr`` (the post-P&R input has
  already been through the P&R preprocessing, so ``--from-pnr`` skips it).

Both checks lived privately in ``pnr_tmds_encoder.py`` until issue #384,
whose reported defect was the reference generator re-implementing them
badly: a word-boundary regex that cannot see an instance connection (there
is no word boundary between ``]`` and ``)``) and a single-bit scope let a
netlist whose cell read an assign-driven bit translate "successfully",
writing the connection while silently omitting its driver. Both consumers
now run the same text-only validator from here, so the two can no longer
disagree about what "dead" means.

Stdlib only (``re``), no PDK and no ``klt`` -- imported by CI's PDK-free
``test`` job through ``flow/tests/test_synth_assign_check.py`` and
``layout/tests/test_gen_tmds_encoder_ref.py``.
"""

from __future__ import annotations

import re

#: A top-level continuous assignment in the written netlist, e.g.
#: `  assign cnt[0] = 1'h0;` or `  assign word_keep_s3[9:8] = { 1'h0, qm8_s3 };`.
ASSIGN_RE = re.compile(
    r"^  assign (?P<net>\w+)\[(?P<msb>\d+)(?::(?P<lsb>\d+))?\] = (?P<rhs>[^;]+);\n",
    re.MULTILINE,
)


class SynthAssignError(ValueError):
    """A top-level continuous assignment violates the dead-tie contract.

    Either it is not the recognized bit-select form, or one of the bits it
    drives is actually read somewhere else in the same netlist -- dropping
    it would lose its driver.
    """


def validate_dead_tie_assigns(text: str) -> None:
    """Raise :class:`SynthAssignError` unless every top-level continuous
    assignment in a synthesized netlist is (1) the recognized bit-select
    form and (2) dead -- no bit it drives is read by anything else in the
    same text.

    Run this before dropping assignments (the P&R input copy) or
    translating around them (the synth-mode LVS reference). A violation
    means dropping the assignment would change the netlist's connectivity,
    which is a real structural delta to investigate, not a mechanical
    preprocessing step either consumer is allowed to apply silently.
    """
    all_assigns = re.findall(r"^  assign .*$", text, re.MULTILINE)
    recognized = len(ASSIGN_RE.findall(text))
    if len(all_assigns) != recognized:
        raise SynthAssignError(
            f"netlist has {len(all_assigns)} top-level continuous assignment(s) but only "
            f"{recognized} match the bit-select dead-tie form -- an unrecognized "
            "assignment cannot be dropped; investigate the netlist before using it"
        )

    live = live_assign_targets(text)
    if live:
        raise SynthAssignError(
            "netlist contains top-level continuous assignment(s) whose target bits "
            f"are actually read: {', '.join(live)} -- dropping the assignment would "
            "lose its driver; investigate the netlist before using it"
        )


def strip_dead_tie_assigns(text: str) -> str:
    """Remove every recognized top-level continuous assignment.

    Only valid on text :func:`validate_dead_tie_assigns` has accepted (the
    validator guarantees the recognized form covers every ``assign`` line,
    so this drops exactly the dead ties and nothing else).
    """
    return ASSIGN_RE.sub("", text)


def assign_target_bits(text: str) -> list[str]:
    """Every ``<net>[<bit>]`` a top-level continuous assignment drives."""
    targets: list[str] = []
    for m in ASSIGN_RE.finditer(text):
        msb = int(m.group("msb"))
        lsb = int(m.group("lsb")) if m.group("lsb") is not None else msb
        lo, hi = min(msb, lsb), max(msb, lsb)
        targets.extend(f"{m.group('net')}[{bit}]" for bit in range(lo, hi + 1))
    return targets


def live_assign_targets(text: str) -> list[str]:
    """Assign-driven bits that something *other than* the assign itself reads.

    Measured by deleting every top-level continuous assignment first and then
    searching what remains -- which is exactly the netlist the consumers
    would see once the dead ties are dropped -- rather than by counting
    occurrences and guessing how many of them belong to the assign's own
    left-hand side (a range assign such as `foo[9:8] = ...` never spells its
    individual bits out, so occurrence-counting undercounts it).
    """
    without_assigns = ASSIGN_RE.sub("", text)
    return [
        target
        for target in assign_target_bits(text)
        if dead_net_fanout_count(without_assigns, target) > 0
    ]


def dead_net_fanout_count(text: str, net: str) -> int:
    """Occurrences of the exact bit-select `net` in `text`."""
    return len(re.findall(re.escape(net), text))
