#!/usr/bin/env python3
"""Tests for layout/scripts/pad_pitch_fit_study.py (issue #143).

Stdlib ``unittest``, no PDK, no ``klt``, no KLayout -- run by ``python3 -m
unittest discover -s layout/tests`` locally and by CI's PDK-free ``test``
job. The study module keeps its ``klayout.db`` import optional precisely so
this file can import it there.

**What is worth testing here, and what is not.** The drawn geometry is
already checked by the strongest tool available: `klt drc --deck gf180mcu`
reports `status: clean`, 0 violations, on every committed tile
(`layout/drc_reports/pad_pitch_fit_*.drc.json`), and `klt components`
confirms ring continuity. Re-asserting shapes here would duplicate that
weakly.

What DRC cannot catch is the *arithmetic that decides whether a clamp is
drawn at all* -- the row fold. That fold is this study's load-bearing
conclusion (`layout/README.md`: "a single row of 334 fingers is 881.8 um,
2.5x DR-0011's ratified 350 um pitch"), and a silently-wrong fold would
produce a tile that is DRC-clean and *still* wrong, because two adjacent
pad structures would overlap in a way no per-shape rule flags. These tests
pin that arithmetic, and pin the ratified DR-0011 constants it is checked
against, so neither can drift unnoticed.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))

import pad_pitch_fit_study as study  # noqa: E402

# design/esd-capacitance-budget.md Sec.2b's HBM-sizing window, expressed in
# this study's own units: each finger is FINGER_L (2.0 um) of clamp width.
HBM_WINDOW_FINGERS = (111, 222, 334)


class DR0011ConstantsTest(unittest.TestCase):
    """DR-0011 is ratified. If these change, a decision record changed --
    or something silently relaxed a ratified number to make a fit pass,
    which CLAUDE.md forbids in as many words."""

    def test_pad_pitch_is_the_ratified_350um(self):
        self.assertEqual(study.PAD_PITCH_UM, 350.0)

    def test_ring_depth_is_the_ratified_75um(self):
        self.assertEqual(study.RING_DEPTH_UM, 75.0)

    def test_pad_side_and_opening_margin_match_gf180_tmds_pad_v2(self):
        # gen_pad_v2.py's own numbers -- the geometry Sec.9 validated the
        # <=2 pF budget against. Adopting it means adopting these exactly.
        self.assertEqual(study.PAD_SIDE, 25.0)
        self.assertEqual(study.PAD_OPENING_MARGIN, 2.5)
        # pad.enclosing.metal5.1's floor is 2.0 um; the margin must clear it.
        self.assertGreater(study.PAD_OPENING_MARGIN, 2.0)


class ClampRowsTest(unittest.TestCase):
    def test_rejects_empty_clamp(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                study.clamp_rows(bad)

    def test_small_clamp_is_a_single_row(self):
        self.assertEqual(study.clamp_rows(20), [20])

    def test_every_row_is_within_the_cap(self):
        for n in (1, 20, 111, 120, 121, 222, 334, 1000):
            rows = study.clamp_rows(n)
            self.assertTrue(all(r <= study.MAX_FINGERS_PER_ROW for r in rows), rows)

    def test_fold_conserves_the_finger_count(self):
        """A fold that loses or duplicates fingers would silently mis-size the
        clamp -- the one error DRC cannot see."""
        for n in (1, 19, 20, 111, 120, 121, 222, 334, 1000):
            self.assertEqual(sum(study.clamp_rows(n)), n)

    def test_fold_uses_the_fewest_rows_possible(self):
        for n in (1, 120, 121, 240, 241, 334):
            expected = -(-n // study.MAX_FINGERS_PER_ROW)  # ceil division
            self.assertEqual(len(study.clamp_rows(n)), expected, n)


class FitReportTest(unittest.TestCase):
    def test_as_drawn_clamp_fits_with_room_to_spare(self):
        r = study.fit_report(20)
        self.assertEqual(r["rows"], [20])
        self.assertTrue(r["fits_pitch"])
        self.assertTrue(r["fits_ring_depth"])
        self.assertEqual(r["struct_width_um"], 65.4)

    def test_whole_hbm_window_fits_the_ratified_pitch_when_folded(self):
        """The study's headline conclusion: every point in
        design/esd-capacitance-budget.md Sec.2b's HBM-sizing window fits
        DR-0011's 350 um pitch and 75 um depth once folded."""
        for n in HBM_WINDOW_FINGERS:
            r = study.fit_report(n)
            self.assertTrue(r["fits_pitch"], f"{n} fingers overruns the pitch: {r}")
            self.assertTrue(r["fits_ring_depth"], f"{n} fingers overruns the depth: {r}")
            self.assertLessEqual(float(r["struct_width_um"]), study.PAD_PITCH_UM)

    def test_top_of_the_window_does_not_fit_unfolded(self):
        """The other half of the conclusion, and the reason the fold exists:
        at 667+ um of clamp width a single row is ~2.5x the ratified pitch.
        If this ever starts passing, the fold has become unnecessary and the
        README's claim needs re-deriving, not quietly leaving in place."""
        r = study.fit_report(334)
        self.assertFalse(r["unfolded_fits_pitch"])
        self.assertGreater(float(r["unfolded_width_um"]), 2 * study.PAD_PITCH_UM)
        self.assertEqual(r["row_count"], 3)

    def test_222um_point_still_fits_unfolded(self):
        # The bottom of the HBM window is a single row; the fold only bites
        # further up. Pinned so the boundary is explicit, not incidental.
        r = study.fit_report(111)
        self.assertTrue(r["unfolded_fits_pitch"])
        self.assertEqual(r["row_count"], 1)

    def test_pad_plate_clears_the_dvdd_strap_at_every_window_point(self):
        """The second required change #143 found: the 25 um-tall Metal5 plate
        has to sit above the DVDD strap band. metal5.space.1's floor is
        0.28 um; every point must clear it, with real margin."""
        for n in (20,) + HBM_WINDOW_FINGERS:
            r = study.fit_report(n)
            self.assertGreaterEqual(float(r["dvdd_strap_clearance_um"]), 1.0, f"{n} fingers: {r}")
            plate_y0, plate_y1 = r["pad_plate_y_um"]
            self.assertGreater(plate_y0, study.DVDD_BAND[1])
            self.assertLessEqual(plate_y1, study.RING_DEPTH_UM)

    def test_wider_gather_bus_costs_ring_depth_but_still_fits(self):
        narrow = study.fit_report(334)
        wide = study.fit_report(334, bus_width=4.0)
        self.assertEqual(wide["bus_width_um"], 4.0)
        # A wider bus forces a taller row pitch, pushing the plate up.
        self.assertGreater(wide["pad_plate_y_um"][0], narrow["pad_plate_y_um"][0])
        self.assertTrue(wide["fits_ring_depth"])
        self.assertTrue(wide["fits_pitch"])
        # ...but it does not change the x budget, which is row-span-driven.
        self.assertEqual(wide["struct_width_um"], narrow["struct_width_um"])

    def test_default_bus_width_reproduces_gf180_tmds_pad_v2s_row_pitch(self):
        # gen_pad_v2.py's finger pitch and this study's default row pitch both
        # come out of the same 0.6 um margin over the finger's own dimension.
        self.assertAlmostEqual(study._row_pitch(study.DEFAULT_BUS_WIDTH_UM), 1.6)
        self.assertAlmostEqual(study.DEFAULT_BUS_WIDTH_UM, 0.48)

    def test_clamp_width_is_reported_in_um_not_fingers(self):
        for n in HBM_WINDOW_FINGERS:
            self.assertAlmostEqual(float(study.fit_report(n)["clamp_width_um"]), n * study.FINGER_L)


class CommittedReportsTest(unittest.TestCase):
    """The committed `*.fit.json` artifacts are what `layout/README.md` and
    `design/esd-capacitance-budget.md` Sec.10 quote. Re-derive them here so a
    hand-edited number in either document cannot outlive the arithmetic."""

    REPORTS = REPO_ROOT / "layout" / "drc_reports"

    def test_committed_fit_reports_still_re_derive(self):
        import json

        found = sorted(self.REPORTS.glob("pad_pitch_fit_*.fit.json"))
        self.assertTrue(found, "no committed pad_pitch_fit_*.fit.json reports")
        for path in found:
            with open(path, encoding="utf-8") as fh:
                committed = json.load(fh)
            fresh = study.fit_report(committed["clamp_fingers"], committed["bus_width_um"])
            for key, value in fresh.items():
                self.assertEqual(committed[key], value, f"{path.name}: {key}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
