#!/usr/bin/env python3
"""Tests for layout/scripts/gen_pad_v2.py substrate-tap placement (issue #422).

DRM DF.14_MV needs every finger within 15 um of a substrate tap, so the tap
pitch must never exceed ``TAP_MAX_PITCH_UM`` for any finger count -- DRC only
sees the one ``N_FINGERS`` that is committed. Needs ``klayout`` (the module
imports it); skipped where it is absent.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "layout" / "scripts"))

try:
    import gen_pad_v2 as g
    from pad_ring_cells import _row_span, clamp_rows
except ImportError:  # no klayout in the PDK-free environment
    g = None


@unittest.skipIf(g is None, "klayout not installed")
class TapPitchTest(unittest.TestCase):
    def test_pitch_bounded_for_all_finger_counts(self):
        for n in range(2, 131):
            span = _row_span(max(clamp_rows(n)))
            taps = g.tap_count(span)
            pitch = (span - g.TAP_WIDTH_UM) / (taps - 1)
            self.assertLessEqual(pitch, g.TAP_MAX_PITCH_UM, f"{n} fingers")

    def test_committed_cell_keeps_three_taps(self):
        span = _row_span(max(clamp_rows(g.N_FINGERS)))
        self.assertEqual(g.tap_count(span), 3)


if __name__ == "__main__":
    unittest.main()
