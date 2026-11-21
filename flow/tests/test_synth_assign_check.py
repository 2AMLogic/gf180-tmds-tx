#!/usr/bin/env python3
"""Tests for flow/synth_assign_check.py and its P&R consumer (issue #384).

Stdlib ``unittest``, no PDK, no ``klt``, no ``openroad`` -- run by
``python3 -m unittest discover -s flow/tests`` locally and by CI's PDK-free
``test`` job. Imports ``pnr_tmds_encoder`` only for
``preprocess_netlist_for_openroad`` (pure text in/text out); ``main()`` and
every OpenROAD-touching helper are never called.

The load-bearing regression is ``test_live_assign_reader_is_rejected``:
issue #384 reports a netlist whose cell input reads the assign-driven bit
``cnt[0]`` sailing through preprocessing. The companion entry point
(``layout/scripts/gen_tmds_encoder_ref.py`` synth mode) is covered by
``layout/tests/test_gen_tmds_encoder_ref.py`` -- both must reject the same
input, from the same shared validator.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "flow"))

import pnr_tmds_encoder as pnr  # noqa: E402
import synth_assign_check  # noqa: E402

SYNTH_NETLIST = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / "tmds_encoder.synth.v"

#: One standard-cell instance card, whose first pin connection is rewritten
#: to read an assign-driven bit -- the exact shape of input issue #384
#: reports.
_FIRST_CONN_RE = re.compile(
    r"^(\s*gf180mcu_fd_sc_mcu9t5v0__\w+ \S+ \(\n\s*\.\w+\()\S+(\),)",
    re.MULTILINE,
)


def read_an_assign_bit(text: str, bit: str) -> str:
    """Rewrite the first cell connection in `text` to read `bit`."""
    mutated, n = _FIRST_CONN_RE.subn(r"\g<1>" + bit + r"\g<2>", text, count=1)
    assert n == 1, "no standard-cell instance connection found to rewrite"
    return mutated


class SharedValidatorTest(unittest.TestCase):
    """validate_dead_tie_assigns on the committed netlist and mutants."""

    def test_committed_synth_netlist_passes(self):
        synth_assign_check.validate_dead_tie_assigns(SYNTH_NETLIST.read_text())

    def test_live_assign_target_bit_is_rejected(self):
        text = read_an_assign_bit(SYNTH_NETLIST.read_text(), "cnt[0]")
        self.assertEqual(synth_assign_check.live_assign_targets(text), ["cnt[0]"])
        with self.assertRaises(synth_assign_check.SynthAssignError) as ctx:
            synth_assign_check.validate_dead_tie_assigns(text)
        self.assertIn("cnt[0]", str(ctx.exception))

    def test_live_range_assign_target_bit_is_rejected(self):
        # word_keep_s3[9:8] is a *range* assign: its LHS never spells the
        # individual bits out, so occurrence-counting (the approach the old
        # private checker in gen_tmds_encoder_ref.py took) cannot see this.
        text = read_an_assign_bit(SYNTH_NETLIST.read_text(), "word_keep_s3[8]")
        self.assertEqual(synth_assign_check.live_assign_targets(text), ["word_keep_s3[8]"])
        with self.assertRaises(synth_assign_check.SynthAssignError):
            synth_assign_check.validate_dead_tie_assigns(text)

    def test_unrecognized_assign_form_is_rejected(self):
        text = SYNTH_NETLIST.read_text() + "  assign whole_net = other_net;\n"
        with self.assertRaises(synth_assign_check.SynthAssignError) as ctx:
            synth_assign_check.validate_dead_tie_assigns(text)
        self.assertIn("bit-select", str(ctx.exception))


class PnrEntryPointTest(unittest.TestCase):
    """preprocess_netlist_for_openroad -- the P&R consumer of the check."""

    def test_committed_synth_netlist_preprocesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "tmds_encoder.pnr_input.v"
            pnr.preprocess_netlist_for_openroad(SYNTH_NETLIST, dst)
            out = dst.read_text()
            self.assertNotRegex(out, r"^  assign ", "assign lines must be stripped")
            self.assertNotIn("wire signed", out)

    def test_live_assign_reader_is_rejected(self):
        src_text = read_an_assign_bit(SYNTH_NETLIST.read_text(), "cnt[0]")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mutated.synth.v"
            src.write_text(src_text)
            with self.assertRaises(pnr.PnrError) as ctx:
                pnr.preprocess_netlist_for_openroad(src, Path(tmp) / "out.v")
            self.assertIn("cnt[0]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
