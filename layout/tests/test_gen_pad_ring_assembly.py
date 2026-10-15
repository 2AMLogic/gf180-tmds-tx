#!/usr/bin/env python3
"""Tests for layout/scripts/gen_pad_ring_assembly.py (issue #149).

Stdlib ``unittest``, no PDK, no ``klt``, no KLayout -- run by ``python3 -m
unittest discover -s layout/tests`` locally and by CI's PDK-free ``test``
job (same convention `test_pad_pitch_fit_study.py` established, issue #143
-- `gen_pad_ring_assembly.py` keeps its own `klayout.db` import optional for
exactly this reason).

**What is worth testing here, and what is not.** The drawn geometry itself
is checked by the strongest tool available: `klt drc --deck gf180mcu`
reports `status: clean` for both the assembly and its `_shorted` twin, and
`klt lvs` reports `status: match` / `status: mismatch` respectively
(`layout/lvs_reports/gf180_tmds_pad_ring_assembly*.lvs.{json,txt}`,
enforced by `check_lvs_signoff.py`). Re-asserting shapes here would
duplicate that weakly.

What DRC/LVS cannot catch is the *arithmetic that decides whether a clamp
structure is drawn at all* -- the row fold (`clamp_rows`) and the
slot-fit/hard-error guard (`_struct_width_um`, scope item 4 of issue #149:
"raise a hard error rather than overrunning the slot if a requested clamp
size cannot be folded to fit"). A silently-wrong fold would produce a tile
that is DRC-clean and *still* wrong -- two adjacent pad structures could
overlap, or a structure could overrun its 350 um slot, in a way no
per-shape DRC rule flags. These tests pin that arithmetic, ported from
(and cross-checked against) `pad_pitch_fit_study.py`'s own already-verified
version (issue #143).
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))

import gen_pad_ring_assembly as gen  # noqa: E402
import pad_pitch_fit_study as study  # noqa: E402

HBM_WINDOW_FINGERS = (111, 222, 334)

LAYOUT = REPO_ROOT / "layout"
CELL = "gf180_tmds_pad_ring_assembly"


def _d_cards(path: Path) -> dict[str, tuple[str, str, str, dict[str, str]]]:
    """name -> (anode, cathode, model, params) for each D card in a
    reference netlist."""
    cards = {}
    for line in path.read_text().splitlines():
        if not re.match(r"^D\S*\s", line):
            continue
        name, anode, cathode, model, *params = line.split()
        cards[name] = (anode, cathode, model, dict(p.split("=") for p in params))
    return cards


class DR0011ConstantsTest(unittest.TestCase):
    """DR-0011 is ratified. If these change, a decision record changed --
    or something silently relaxed a ratified number to make a fit pass,
    which CLAUDE.md forbids in as many words."""

    def test_pad_pitch_is_the_ratified_350um(self):
        self.assertEqual(gen.PAD_PITCH_UM, 350.0)

    def test_ring_depth_is_the_ratified_75um(self):
        self.assertEqual(gen.RING_DEPTH_UM, 75.0)

    def test_pad_side_and_opening_margin_match_gen_pad_v2(self):
        # gen_pad_v2.py's own numbers -- the geometry design/
        # esd-capacitance-budget.md's #87/#143 sections validated the
        # <=2 pF budget against. Landing it here (#149) means adopting
        # these exactly.
        self.assertEqual(gen.PAD_SIDE, 25.0)
        self.assertEqual(gen.PAD_OPENING_MARGIN, 2.5)
        self.assertGreater(gen.PAD_OPENING_MARGIN, 2.0)  # pad.enclosing.metal5.1 floor

    def test_pad_struct_oy_clears_the_dvdd_strap_band(self):
        # Issue #143's second required change: raised from 25.0 (which put
        # the 25um plate straight through DVDD_BAND) to 30.0.
        self.assertEqual(gen.PAD_STRUCT_OY_UM, 30.0)
        self.assertGreater(gen.PAD_STRUCT_OY_UM, gen.DVDD_BAND[1])


class ClampSizeTest(unittest.TestCase):
    def test_default_clamp_size_matches_gen_pad_v2s_own_as_drawn_array(self):
        # gen_pad_v2.py's own N_FINGERS -- this driver's actual clamp size,
        # not yet the final HBM-qualified one (see module docstring).
        self.assertEqual(gen.N_FINGERS, 20)


class ClampRowsTest(unittest.TestCase):
    """Ported from pad_pitch_fit_study.py's own ClampRowsTest (issue #143) --
    same arithmetic, same invariants, now pinned in this module too since
    this module's own `clamp_rows` is what `build()` actually calls."""

    def test_rejects_empty_clamp(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                gen.clamp_rows(bad)

    def test_small_clamp_is_a_single_row(self):
        self.assertEqual(gen.clamp_rows(20), [20])

    def test_every_row_is_within_the_cap(self):
        for n in (1, 20, 111, 120, 121, 222, 334, 1000):
            rows = gen.clamp_rows(n)
            self.assertTrue(all(r <= gen.MAX_FINGERS_PER_ROW for r in rows), rows)

    def test_fold_conserves_the_finger_count(self):
        """A fold that loses or duplicates fingers would silently mis-size
        the clamp -- the one error DRC cannot see."""
        for n in (1, 19, 20, 111, 120, 121, 222, 334, 1000):
            self.assertEqual(sum(gen.clamp_rows(n)), n)

    def test_fold_uses_the_fewest_rows_possible(self):
        for n in (1, 120, 121, 240, 241, 334):
            expected = -(-n // gen.MAX_FINGERS_PER_ROW)  # ceil division
            self.assertEqual(len(gen.clamp_rows(n)), expected, n)

    def test_agrees_with_pad_pitch_fit_studys_own_fold(self):
        """This module ports pad_pitch_fit_study.py's fold (issue #143's
        already-DRC-clean reference implementation) rather than re-deriving
        it -- so the two must agree at every point in the HBM-sizing window
        and at the as-drawn default."""
        for n in (gen.N_FINGERS,) + HBM_WINDOW_FINGERS:
            self.assertEqual(gen.clamp_rows(n), study.clamp_rows(n), n)


class StructWidthTest(unittest.TestCase):
    def test_as_drawn_clamp_matches_the_committed_65_4um_reading(self):
        # design/esd-capacitance-budget.md §10.2's own committed table.
        self.assertEqual(gen._struct_width_um(gen.N_FINGERS), 65.4)

    def test_agrees_with_pad_pitch_fit_studys_own_fit_report(self):
        for n in (gen.N_FINGERS,) + HBM_WINDOW_FINGERS:
            self.assertAlmostEqual(
                gen._struct_width_um(n), float(study.fit_report(n)["struct_width_um"])
            )

    def test_whole_hbm_window_still_fits_the_ratified_pitch(self):
        for n in HBM_WINDOW_FINGERS:
            self.assertLessEqual(gen._struct_width_um(n), gen.PAD_PITCH_UM, n)

    def test_default_bus_width_reproduces_gen_pad_v2s_own_row_pitch(self):
        self.assertAlmostEqual(gen._row_pitch(gen.DEFAULT_BUS_WIDTH_UM), 1.6)
        self.assertAlmostEqual(gen.DEFAULT_BUS_WIDTH_UM, 0.48)


class HardErrorGuardTest(unittest.TestCase):
    """Scope item 4: raise a hard error rather than silently overrunning the
    slot if a requested clamp size cannot be folded to fit -- DR-0011 is
    ratified, the fold widens (MAX_FINGERS_PER_ROW), never the pitch.

    `MAX_FINGERS_PER_ROW=120` already keeps every point up through the full
    HBM-sizing window inside the 350um pitch (see StructWidthTest above), so
    the guard cannot be exercised through `n_fingers` alone at the ratified
    fold cap -- it is exercised here by widening the per-row cap instead,
    which is exactly the "single row overruns the pitch" condition the
    guard exists to catch.
    """

    def setUp(self):
        self._orig_max = gen.MAX_FINGERS_PER_ROW

    def tearDown(self):
        gen.MAX_FINGERS_PER_ROW = self._orig_max

    def test_no_hard_error_within_the_hbm_window(self):
        for n in (gen.N_FINGERS,) + HBM_WINDOW_FINGERS:
            self.assertLessEqual(gen._struct_width_um(n), gen.PAD_PITCH_UM)

    def test_struct_width_exceeds_pitch_once_a_single_row_is_forced_too_wide(self):
        gen.MAX_FINGERS_PER_ROW = 1000
        width = gen._struct_width_um(500)
        self.assertGreater(width, gen.PAD_PITCH_UM)


class VddClampGeometryTest(unittest.TestCase):
    """Issue #210: the VDD-side `diode_pd2nw_06v0` leg. The drawn geometry is
    judged by `klt drc`/`klt lvs`/`klt erc`; what those cannot see is a
    constant edited to a value that merely stops mattering to them."""

    def test_nwell_stays_clear_of_the_vss_side_array_halos(self):
        # The VSS-side array's Nplus/Dualgate/diode_mk halos reach 0.4 um past
        # its top edge; the VDD array's Nwell starts NWELL_MARGIN_UM below
        # its own first row. The gap must leave real room between them.
        self.assertGreater(gen.VDD_CLAMP_GAP_UM - gen.NWELL_MARGIN_UM, 0.4 + 1.0)

    def test_nwell_tap_sits_left_of_the_array_inside_the_nwell(self):
        self.assertLess(gen.NWELL_TAP_X_UM, 0.0)
        self.assertGreater(gen.NWELL_MARGIN_UM, 0.12)  # nwell.enclosing.comp.1

    def test_vdd_clamp_array_stays_under_the_pad_plate_column(self):
        top = gen.PAD_STRUCT_OY_UM + gen.VDD_CLAMP_GAP_UM + 1.0 + gen.NWELL_MARGIN_UM
        self.assertLess(top, gen.PAD_STRUCT_OY_UM + gen.PAD_SIDE)

    def test_via_cuts_are_the_fixed_026um_square(self):
        # via*.width.1 is a fixed 0.26 x 0.26 um square at every level.
        self.assertAlmostEqual(gen.VIA_SIZE, 0.26)
        self.assertAlmostEqual(2 * gen.VIA_HALF, 0.26)


class VddReferenceAndSpecTest(unittest.TestCase):
    """The reference netlists and ERC specs carry VDD for real, and the VDD
    assertion was neither dropped nor weakened (the owner's ruling on #210)."""

    def test_reference_has_a_vdd_port_and_pd2nw_cards(self):
        for suffix in ("", "_shorted"):
            ref = LAYOUT / "lvs" / f"{CELL}{suffix}.ref.spice"
            subckt = next(
                line for line in ref.read_text().splitlines() if line.startswith(".SUBCKT")
            )
            self.assertIn(" VDD", subckt, ref.name)
            cards = _d_cards(ref)
            pd = {n: c for n, c in cards.items() if c[2] == "diode_pd2nw_06v0"}
            self.assertEqual(
                sorted((c[0], c[1]) for c in pd.values()),
                [("OUTN", "VDD"), ("OUTP", "VDD")],
                f"{ref.name}: anode = protected output, cathode = VDD",
            )

    def test_vdd_leg_matches_the_vss_leg_area_and_perimeter(self):
        cards = _d_cards(LAYOUT / "lvs" / f"{CELL}.ref.spice")
        params = {c[2]: c[3] for c in cards.values()}
        self.assertEqual(params["diode_pd2nw_06v0"], params["diode_nd2ps_06v0"])

    def test_supply_spec_keeps_vdd_and_ties_the_nwell_to_it(self):
        for name in ("", ".negctl-short", ".negctl-tie"):
            spec = json.loads((LAYOUT / f"erc-supply-spec.pad-ring{name}.json").read_text())
            self.assertIn({"name": "VDD", "kind": "supply"}, spec["nets"], name)
            ties = {t["name"]: t for t in spec["ties"]}
            self.assertEqual(ties["nwell_vdd_tap"]["net"], "VDD", name)
            self.assertEqual(ties["nwell_vdd_tap"]["well_layer"], "21/0", name)

    def test_vdd_negative_control_points_the_nwell_tie_at_a_signal_net(self):
        spec = json.loads(
            (LAYOUT / "erc-supply-spec.pad-ring.negctl-vdd-tie.json").read_text()
        )
        ties = {t["name"]: t for t in spec["ties"]}
        self.assertEqual(ties["nwell_vdd_tap"]["net"], "OUTP")
        self.assertEqual(ties["substrate_vss_tap"]["net"], "VSS")

    def test_committed_erc_reports(self):
        reports = LAYOUT / "erc_reports"
        pos = json.loads((reports / f"{CELL}.erc.json").read_text())
        self.assertEqual(pos["erc_finding_count"], 0)
        nets = {n["name"]: n for n in pos["nets"]}
        self.assertEqual(nets["VDD"]["matched_islands"], 1)
        self.assertEqual(nets["VDD"]["expected_islands"], 1)
        self.assertEqual(pos["erc_coverage"]["skipped"], [])
        self.assertIn('erc.missing_tie:["nwell_vdd_tap"]', pos["erc_coverage"]["checked"])
        neg = json.loads((reports / f"{CELL}.negctl_vdd_tie.erc.json").read_text())
        self.assertTrue(neg["erc_findings"])
        self.assertTrue(all(f["rule"] == "erc.missing_tie" for f in neg["erc_findings"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
