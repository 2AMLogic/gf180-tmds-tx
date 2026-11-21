#!/usr/bin/env python3
"""Tests for layout/scripts/gen_tmds_encoder_ref.py (issue #384).

Stdlib ``unittest``, no PDK, no ``klt``, no KLayout -- run by
``python3 -m unittest discover -s layout/tests`` locally and by CI's
PDK-free ``test`` job.

The load-bearing regression is ``test_live_assign_reader_is_rejected``:
issue #384 reports that a temporary copy of the committed synth netlist
with one cell input changed to read ``cnt[0]`` (driven only by the dead
``assign cnt[0] = 1'h0;`` tie) exited 0 and wrote 342 instances -- the
connection included, its driver silently omitted -- because the private
``check_dead_net`` guard's word-boundary regex cannot match a bit-select
followed by ``)`` and it checked one bit only. Since issue #384 synth mode
runs the same shared validator as the P&R preprocessing
(``flow/synth_assign_check.py``), so both entry points reject the same
input (the flow-side half is ``flow/tests/test_synth_assign_check.py``).

The byte-for-byte ``--from-pnr`` regenerations pin the *signoff* path
against this refactor: both committed references must regenerate exactly,
proving the shared-check change did not disturb the routed-netlist
translation. The header source is the committed reference itself -- its
``.SUBCKT`` lines are what the original run embedded verbatim, and the
pnr netlist's cell types are a superset of the synth netlist's (asserted
by ``test_committed_synth_netlist_translates`` passing render's
header-coverage check), so it stands in for the ``klt extract`` output
that is not committed. That makes these determinism checks, not live
extraction evidence; the live signoff runs remain the committed
``layout/lvs_reports/`` pair that ``check_lvs_signoff.py`` grades.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "flow"))

import gen_tmds_encoder_ref as gen  # noqa: E402
import synth_assign_check  # noqa: E402

SYNTH_NETLIST = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / "tmds_encoder.synth.v"
PNR_NETLIST = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / "tmds_encoder.pnr.v"
COMMITTED_REF = REPO_ROOT / "layout" / "lvs" / "tmds_encoder.ref.spice"
COMMITTED_NEGCTL = REPO_ROOT / "layout" / "lvs" / "tmds_encoder_negctl.ref.spice"

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


def run_gen(argv: list[str]) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        gen.main(argv)
    return buffer.getvalue()


class SynthModeTest(unittest.TestCase):
    """Synth mode (no --from-pnr): shared validation, then translation."""

    def test_committed_synth_netlist_translates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ref.spice"
            output = run_gen(
                ["--netlist", str(SYNTH_NETLIST), "--subckt-headers-from", str(COMMITTED_REF),
                 "-o", str(out)]
            )
            self.assertIn("342 instances", output)

    def test_live_assign_reader_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mutated.synth.v"
            src.write_text(read_an_assign_bit(SYNTH_NETLIST.read_text(), "cnt[0]"))
            with self.assertRaises(SystemExit) as ctx:
                run_gen(
                    ["--netlist", str(src), "--subckt-headers-from", str(COMMITTED_REF),
                     "-o", str(Path(tmp) / "ref.spice")]
                )
            self.assertIn("cnt[0]", str(ctx.exception))

    def test_live_range_assign_reader_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mutated.synth.v"
            src.write_text(read_an_assign_bit(SYNTH_NETLIST.read_text(), "word_keep_s3[8]"))
            with self.assertRaises(SystemExit) as ctx:
                run_gen(
                    ["--netlist", str(src), "--subckt-headers-from", str(COMMITTED_REF),
                     "-o", str(Path(tmp) / "ref.spice")]
                )
            self.assertIn("word_keep_s3[8]", str(ctx.exception))

    def test_from_pnr_skips_the_synth_assign_check(self):
        """Validation is scoped to synth mode (issue #384): the signoff path
        reads the routed netlist, whose assigns were settled upstream."""
        text = PNR_NETLIST.read_text() + "  assign data[3] = 1'h0;\n"
        self.assertEqual(  # would be live (data[3] is read throughout) ...
            synth_assign_check.live_assign_targets(text), ["data[3]"]
        )
        with tempfile.TemporaryDirectory() as tmp:  # ... yet from-pnr accepts it
            src = Path(tmp) / "mutated.pnr.v"
            src.write_text(text)
            out = Path(tmp) / "ref.spice"
            output = run_gen(
                ["--netlist", str(src), "--from-pnr", "--subckt-headers-from", str(COMMITTED_REF),
                 "-o", str(out)]
            )
            self.assertIn("OK:", output)


class FromPnrRegenerationTest(unittest.TestCase):
    """The issue #384 verification, kept as a regression: both routed
    references regenerate byte-for-byte from the committed pnr netlist."""

    def test_intact_reference_regenerates_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ref.spice"
            run_gen(
                ["--netlist", str(PNR_NETLIST), "--from-pnr",
                 "--subckt-headers-from", str(COMMITTED_REF), "-o", str(out)]
            )
            self.assertEqual(out.read_text(), COMMITTED_REF.read_text())

    def test_negative_control_regenerates_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "negctl.spice"
            run_gen(
                ["--netlist", str(PNR_NETLIST), "--from-pnr", "--negative-control",
                 "--subckt-headers-from", str(COMMITTED_REF), "-o", str(out)]
            )
            self.assertEqual(out.read_text(), COMMITTED_NEGCTL.read_text())


if __name__ == "__main__":
    unittest.main()
