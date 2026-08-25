#!/usr/bin/env python3
"""Tests for layout/scripts/gen_tmds_encoder_shorted.py (issue #146).

Stdlib ``unittest``, no PDK, no ``klt``, no KLayout -- run by ``python3 -m
unittest discover -s layout/tests`` locally and by CI's PDK-free ``test``
job. `gen_tmds_encoder_shorted.py` keeps its ``klayout.db`` import optional
precisely so this file can import it there (same pattern
`test_pad_pitch_fit_study.py` already established).

**What is worth testing here, and what is not.** Whether the drawn bridge
actually shorts the two nets under `klt extract` is checked by the
committed `layout/lvs_reports/tmds_encoder_shorted.lvs.{json,txt}` pair
(`status: mismatch`, >=1 error-severity finding) and
`check_lvs_signoff.py`'s enforcement of that invariant -- neither needs
re-checking here, and neither *can* be, without `klt`.

What belongs in a PDK-free unit test is the part issue #129/#146 both
warn about: the geometry-derivation logic that decides *where* to draw the
bridge, and the loud failures that fire when its assumptions about the
DEF no longer hold. A silently-wrong version of either would draw a bridge
that shorts nothing (or the wrong thing), producing a negative control that
*passes* -- worse than no control, since it looks like coverage without
being any. `parse_def_pins`/`compute_bridge` are pure stdlib, so both are
pinned directly here.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))

import gen_tmds_encoder_shorted as gen  # noqa: E402

REAL_DEF = REPO_ROOT / "flow" / "tmds_encoder" / "pnr" / "tmds_encoder.def"


def _pin_entry(name, net, direction, x0, y0, x1, y1, ox, oy, orient="N", layer="Metal4"):
    return dedent(
        f"""\
            - {name} + NET {net} + DIRECTION {direction} + USE SIGNAL
              + PORT
                + LAYER {layer} ( {x0} {y0} ) ( {x1} {y1} )
                + PLACED ( {ox} {oy} ) {orient} ;
        """
    )


def make_def(entries: str, count: int = 2) -> str:
    return f"PINS {count} ;\n{entries}END PINS ;\n"


class ParseDefPinsAgainstRealDefTest(unittest.TestCase):
    """Cross-check the parser against the actual committed DEF.

    If this ever fails, either the DEF changed (expected to be rare and
    reviewed) or the parser regressed -- both are worth a loud failure here
    rather than discovering it only when `compute_bridge` raises downstream.
    """

    def setUp(self):
        if not REAL_DEF.is_file():
            self.skipTest(f"real DEF not present at {REAL_DEF}")
        self.pins = gen.parse_def_pins(REAL_DEF.read_text())

    def test_parses_all_25_declared_pins(self):
        # The DEF's own `PINS 25 ;` header count -- a parser that silently
        # drops the last entry (a real bug this test caught during
        # development: a regex lookahead anchored on literal "END PINS"
        # text that the parser's own captured body does not contain) would
        # under-count here.
        self.assertEqual(len(self.pins), 25)

    def test_bridge_pins_present_with_expected_geometry(self):
        ctrl0 = self.pins["ctrl[0]"]
        data3 = self.pins["data[3]"]
        self.assertEqual(ctrl0.direction, "INPUT")
        self.assertEqual(data3.direction, "INPUT")
        self.assertEqual(ctrl0.layer, "Metal4")
        self.assertEqual(data3.layer, "Metal4")
        # DEF-DBU absolute boxes the issue's own known-good parameters cite
        # (DEF pin centres 208880 / 211120 DBU, 0.0005 um/DBU).
        self.assertEqual(ctrl0.bbox, (208600, 0, 209160, 1040))
        self.assertEqual(data3.bbox, (210840, 0, 211400, 1040))

    def test_compute_bridge_matches_known_good_rectangle(self):
        bbox, pin_a, pin_b = gen.compute_bridge(self.pins)
        self.assertEqual(bbox, (208600, 0, 211400, 1040))
        # 104.30-105.70 um x, 0.00-0.52 um y at 0.0005 um/DBU -- the issue's
        # cited known-good rectangle, reproduced here from first principles
        # (the DEF), not hard-coded into the generator itself.
        dbu = 0.0005
        bbox_um = tuple(round(v * dbu, 6) for v in bbox)
        self.assertEqual(bbox_um, (104.3, 0.0, 105.7, 0.52))


class ParseDefPinsSyntheticTest(unittest.TestCase):
    """Parser behavior on small, hand-built DEF fragments."""

    def test_two_pin_minimal_block(self):
        text = make_def(
            _pin_entry("a", "a", "INPUT", -280, -520, 280, 520, 1000, 520)
            + _pin_entry("b", "b", "OUTPUT", -280, -520, 280, 520, 2000, 520)
        )
        pins = gen.parse_def_pins(text)
        self.assertEqual(set(pins), {"a", "b"})
        self.assertEqual(pins["a"].bbox, (720, 0, 1280, 1040))
        self.assertEqual(pins["b"].direction, "OUTPUT")

    def test_missing_pins_block_fails_loudly(self):
        with self.assertRaises(gen.ShortGeometryError):
            gen.parse_def_pins("DESIGN foo ;\nEND DESIGN\n")

    def test_non_north_orientation_fails_loudly(self):
        text = make_def(
            _pin_entry("a", "a", "INPUT", -280, -520, 280, 520, 1000, 520, orient="S")
            + _pin_entry("b", "b", "INPUT", -280, -520, 280, 520, 2000, 520)
        )
        with self.assertRaises(gen.ShortGeometryError):
            gen.parse_def_pins(text)


class ComputeBridgeFailLoudTest(unittest.TestCase):
    """The #129 failure mode, applied to this generator: any of these
    silently returning a (wrong-but-plausible) bridge instead of raising
    would produce a negative control that shorts nothing, or shorts the
    wrong thing, and therefore passes when it should fail."""

    def _pins(self, **overrides):
        base = {
            "ctrl[0]": gen.DefPin("ctrl[0]", "ctrl[0]", "INPUT", "Metal4", (208600, 0, 209160, 1040)),
            "data[3]": gen.DefPin("data[3]", "data[3]", "INPUT", "Metal4", (210840, 0, 211400, 1040)),
        }
        base.update(overrides)
        return base

    def test_missing_pin_fails_loudly(self):
        with self.assertRaises(gen.ShortGeometryError):
            gen.compute_bridge({})

    def test_wrong_direction_fails_loudly(self):
        pins = self._pins(
            **{"ctrl[0]": gen.DefPin("ctrl[0]", "ctrl[0]", "OUTPUT", "Metal4", (208600, 0, 209160, 1040))}
        )
        with self.assertRaises(gen.ShortGeometryError):
            gen.compute_bridge(pins)

    def test_layer_mismatch_fails_loudly(self):
        pins = self._pins(
            **{"data[3]": gen.DefPin("data[3]", "data[3]", "INPUT", "Metal3", (210840, 0, 211400, 1040))}
        )
        with self.assertRaises(gen.ShortGeometryError):
            gen.compute_bridge(pins)

    def test_row_misalignment_fails_loudly(self):
        pins = self._pins(
            **{"data[3]": gen.DefPin("data[3]", "data[3]", "INPUT", "Metal4", (210840, 2000, 211400, 3040))}
        )
        with self.assertRaises(gen.ShortGeometryError):
            gen.compute_bridge(pins)

    def test_overlapping_pins_fail_loudly(self):
        pins = self._pins(
            **{"data[3]": gen.DefPin("data[3]", "data[3]", "INPUT", "Metal4", (209000, 0, 209500, 1040))}
        )
        with self.assertRaises(gen.ShortGeometryError):
            gen.compute_bridge(pins)

    def test_intruding_third_pin_fails_loudly(self):
        pins = self._pins(
            intruder=gen.DefPin("intruder", "intruder", "INPUT", "Metal4", (209500, 0, 210000, 1040))
        )
        with self.assertRaises(gen.ShortGeometryError):
            gen.compute_bridge(pins)

    def test_a_pin_outside_the_gap_does_not_block_the_bridge(self):
        # A same-row pin that is *not* between ctrl[0] and data[3] must not
        # trip the adjacency check -- only a genuine intruder should.
        pins = self._pins(
            elsewhere=gen.DefPin("elsewhere", "elsewhere", "INPUT", "Metal4", (0, 0, 500, 1040))
        )
        bbox, pin_a, pin_b = gen.compute_bridge(pins)
        self.assertEqual(bbox, (208600, 0, 211400, 1040))

    def test_build_without_klayout_raises_clean_error(self):
        original_db = gen.db
        gen.db = None
        try:
            with self.assertRaises(ModuleNotFoundError):
                gen.build(REAL_DEF, Path("/nonexistent.gds"))
        finally:
            gen.db = original_db


if __name__ == "__main__":
    unittest.main()
