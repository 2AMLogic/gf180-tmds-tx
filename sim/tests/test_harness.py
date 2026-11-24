"""Harness unit tests -- no PDK, no ngspice required.

    python3 -m unittest discover -s sim/tests -v

Covers this repo's adaptation of the ported `2AMLogic/gf180-bandgap` harness
(issue #8): the bit-rate axis (`sim/harness/corners.py`), the paired
`rates_mbps`/`transient` manifest validation (`sim/harness/testbench.py`),
the extended corner-id grammar and the Operating point / Transient settings
cross-check (`sim/harness/evidence_lint.py`), and the rate-aware matrix
conformance check (`sim/harness/report.py`). Not a re-port of
gf180-bandgap's full ~2000-line self-test suite -- scoped to what this repo
actually adapted, plus a smoke check that the un-adapted DC/op-point path
still behaves identically to the source harness.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _dir in (SIM_DIR, TESTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from _harness_fixtures import (  # noqa: E402
    both_options_lines,
    fake_pdk,
    init_git_repo,
    load_testbench,
    make_point,
    options_testbench,
)
from harness import corners as corners_mod  # noqa: E402
from harness import evidence_lint as lint_mod  # noqa: E402
from harness import report as report_mod  # noqa: E402
from harness import runner as runner_mod  # noqa: E402
from harness import testbench as tb_mod  # noqa: E402


class CornerIdRateAxisTests(unittest.TestCase):
    def test_corner_id_without_rate_matches_unadapted_grammar(self):
        corner = corners_mod.CORNERS["tt"]
        point = corners_mod.PvtPoint(corner=corner, temp_c=27.0, vdd=3.3)
        self.assertEqual(point.corner_id, "tt_27c_3.30v")

    def test_corner_id_with_rate_appends_token(self):
        corner = corners_mod.CORNERS["tt"]
        point = corners_mod.PvtPoint(corner=corner, temp_c=27.0, vdd=3.3, rate_mbps=742.5)
        self.assertEqual(point.corner_id, "tt_27c_3.30v_742p5mbps")

    def test_corner_id_integer_rate_drops_trailing_zero(self):
        corner = corners_mod.CORNERS["tt"]
        point = corners_mod.PvtPoint(corner=corner, temp_c=-40.0, vdd=2.97, rate_mbps=270.0)
        self.assertEqual(point.corner_id, "tt_-40c_2.97v_270mbps")

    def test_build_grid_without_rates_matches_unadapted_point_count(self):
        corners = corners_mod.resolve_corners(["mos"])
        points = corners_mod.build_grid(corners, [27.0], [3.3])
        self.assertEqual(len(points), 5)
        self.assertTrue(all(p.rate_mbps is None for p in points))

    def test_build_grid_with_rates_cross_products(self):
        corners = corners_mod.resolve_corners(["mos"])
        points = corners_mod.build_grid(corners, [-40.0, 27.0, 125.0], [2.97, 3.3, 3.63], [742.5, 270.0])
        self.assertEqual(len(points), 5 * 3 * 3 * 2)
        rates = {p.rate_mbps for p in points}
        self.assertEqual(rates, {742.5, 270.0})

    def test_build_grid_rejects_empty_rates_list(self):
        corners = corners_mod.resolve_corners(["tt"])
        with self.assertRaises(ValueError):
            corners_mod.build_grid(corners, [27.0], [3.3], [])


class EvidenceLintCornerIdTests(unittest.TestCase):
    def test_parses_dc_corner_id(self):
        self.assertIsNone(lint_mod.parse_corner_id("tt_27c_3.30v"))
        self.assertIsNone(lint_mod.parse_corner_id("ss_-40c_2.97v"))
        self.assertIsNone(lint_mod.parse_corner_id("bjt_ff_125c_3.63v"))
        self.assertIsNone(lint_mod.parse_corner_id("res_typical_27c_nosupply"))

    def test_parses_rate_bearing_corner_id(self):
        self.assertIsNone(lint_mod.parse_corner_id("tt_27c_3.30v_742p5mbps"))
        self.assertIsNone(lint_mod.parse_corner_id("tt_27c_3.30v_270mbps"))
        self.assertIsNone(lint_mod.parse_corner_id("bjt_ff_-40c_2.97v_742p5mbps"))

    def test_rejects_malformed_rate_field(self):
        # "742p5" with no trailing "mbps" does not match _RATE_RE, so this
        # falls back to being parsed as a (malformed) <supply> field.
        reason = lint_mod.parse_corner_id("tt_27c_3.30v_742p5")
        self.assertIsNotNone(reason)

    def test_rejects_missing_temp_field(self):
        reason = lint_mod.parse_corner_id("tt_3.30v")
        self.assertIsNotNone(reason)

    def test_decode_rate_token_round_trip(self):
        self.assertEqual(lint_mod.decode_rate_token("742p5mbps"), 742.5)
        self.assertEqual(lint_mod.decode_rate_token("270mbps"), 270.0)


class _Field:
    """Minimal stand-in for evidence_lint.RecordField in these unit tests."""

    def __init__(self, value: str):
        self.value = value


class OperatingPointCheckTests(unittest.TestCase):
    def test_dc_record_skips_check_entirely(self):
        problems = lint_mod._check_operating_point("path", {}, rate_tokens=set())
        self.assertEqual(problems, [])

    def test_missing_both_fields_on_rate_bearing_record(self):
        problems = lint_mod._check_operating_point("path", {}, rate_tokens={"742p5mbps"})
        self.assertEqual(len(problems), 2)
        messages = " ".join(p.message for p in problems)
        self.assertIn("Operating point", messages)
        self.assertIn("Transient settings", messages)

    def test_operating_point_matches_logged_rate(self):
        fields = {
            "Operating point": _Field("742.5 Mbps/lane (target (720p60))"),
            "Transient settings": _Field("tstep=2e-12s tstop=2e-08s"),
        }
        problems = lint_mod._check_operating_point("path", fields, rate_tokens={"742p5mbps"})
        self.assertEqual(problems, [])

    def test_operating_point_mismatch_is_flagged(self):
        """A record covering only the 480p fallback cannot pass lint while
        its Operating point field claims the 720p60 target row -- this is
        the acceptance-criterion scenario from issue #8, exercised directly.
        """
        fields = {
            "Operating point": _Field("742.5 Mbps/lane (target (720p60))"),
            "Transient settings": _Field("tstep=2e-12s tstop=2e-08s"),
        }
        problems = lint_mod._check_operating_point("path", fields, rate_tokens={"270mbps"})
        self.assertEqual(len(problems), 1)
        self.assertIn("declares", problems[0].message)
        self.assertIn("270.0", problems[0].message)

    def test_operating_point_covering_both_rates_is_accepted(self):
        fields = {
            "Operating point": _Field(
                "270 Mbps/lane (fallback (480p)), 742.5 Mbps/lane (target (720p60))"
            ),
            "Transient settings": _Field("tstep=2e-12s tstop=2e-08s"),
        }
        problems = lint_mod._check_operating_point(
            "path", fields, rate_tokens={"270mbps", "742p5mbps"}
        )
        self.assertEqual(problems, [])

    def test_empty_transient_settings_field_is_flagged(self):
        fields = {
            "Operating point": _Field("270 Mbps/lane (fallback (480p))"),
            "Transient settings": _Field(""),
        }
        problems = lint_mod._check_operating_point("path", fields, rate_tokens={"270mbps"})
        self.assertEqual(len(problems), 1)
        self.assertIn("Transient settings", problems[0].message)


class TestbenchTransientValidationTests(unittest.TestCase):
    def test_rates_without_transient_is_rejected(self):
        with self.assertRaises(ValueError):
            load_testbench(
                self,
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                },
            )

    def test_transient_without_rates_is_rejected(self):
        with self.assertRaises(ValueError):
            load_testbench(
                self,
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "transient": {"tstep_s": 2e-12, "tstop_s": 20e-9},
                    "analyses": ["tran 2e-12 20e-9"],
                },
            )

    def test_transient_missing_required_key_is_rejected(self):
        with self.assertRaises(ValueError):
            load_testbench(
                self,
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                    "transient": {"tstop_s": 20e-9},
                    "analyses": ["tran 2e-12 20e-9"],
                },
            )

    def test_transient_with_no_tran_analysis_is_rejected(self):
        with self.assertRaises(ValueError):
            load_testbench(
                self,
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                    "transient": {"tstep_s": 2e-12, "tstop_s": 20e-9},
                    "analyses": ["op"],
                },
            )

    def test_transient_settings_disagreeing_with_tran_line_is_rejected(self):
        with self.assertRaises(ValueError):
            load_testbench(
                self,
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                    "transient": {"tstep_s": 2e-12, "tstop_s": 99e-9},
                    "analyses": ["tran 2e-12 20e-9"],
                },
            )

    def test_valid_transient_testbench_loads(self):
        tb = load_testbench(
            self,
            {
                "netlist": "frag.spice",
                "measure": {"x": "v(x)"},
                "rates_mbps": [742.5, 270.0],
                "transient": {
                    "tstep_s": 2e-12,
                    "tstop_s": 20e-9,
                    "reltol": 1e-6,
                },
                "analyses": ["tran 2e-12 20e-9"],
            },
        )
        self.assertEqual(tb.rates_mbps, (742.5, 270.0))
        self.assertEqual(tb.transient["reltol"], 1e-6)

    def test_dc_testbench_with_no_rate_axis_loads_unchanged(self):
        """A manifest with neither `rates_mbps` nor `transient` behaves
        exactly like the un-adapted gf180-bandgap harness."""
        tb = load_testbench(
            self,
            {
                "netlist": "frag.spice",
                "measure": {"x": "v(x)"},
            },
        )
        self.assertEqual(tb.rates_mbps, ())
        self.assertEqual(tb.transient, {})


class PerRateTransientWindowTests(unittest.TestCase):
    """Issue #405: a transient bench may map individual rates to their own
    ``.tran`` window (one ``tstop`` sized for the 270 Mbps fallback simulates
    dead time at 742.5 Mbps that Linux ngspice-47 aborts inside). The mapped
    line must reach the composed deck for that rate's points, leave every
    unmapped rate / DC point on the default ``analyses``, and stay
    cross-checked against ``transient`` exactly as the default line is.
    """

    DEFAULT_LINE = "tran 2e-12 20e-9"
    SHORT_LINE = "tran 2e-12 5e-9"

    def _tb(self, **extra) -> tb_mod.Testbench:
        manifest = {
            "netlist": "frag.spice",
            "measure": {"x": "v(x)"},
            "rates_mbps": [742.5, 270.0],
            "transient": {
                "tstep_s": 2e-12,
                "tstop_s": 20e-9,
                "tstop_s_by_rate": {"742.5": 5e-9},
            },
            "analyses": [self.DEFAULT_LINE],
            "analyses_by_rate": {"742.5": self.SHORT_LINE},
        }
        manifest.update(extra)
        return load_testbench(self, manifest)

    def _deck(self, tb, rate_mbps=None) -> list[str]:
        return runner_mod.compose_deck(
            tb, fake_pdk(), make_point(rate_mbps=rate_mbps)
        ).splitlines()

    def test_mapped_rate_runs_its_own_window_in_the_deck(self):
        deck = self._deck(self._tb(), rate_mbps=742.5)
        self.assertIn(f"  {self.SHORT_LINE}", deck)
        self.assertNotIn(f"  {self.DEFAULT_LINE}", deck)

    def test_unmapped_rate_runs_the_default_window(self):
        deck = self._deck(self._tb(), rate_mbps=270.0)
        self.assertIn(f"  {self.DEFAULT_LINE}", deck)
        self.assertNotIn(f"  {self.SHORT_LINE}", deck)

    def test_rateless_point_runs_the_default_window(self):
        deck = self._deck(self._tb(), rate_mbps=None)
        self.assertIn(f"  {self.DEFAULT_LINE}", deck)

    def test_real_eye_mask_manifest_windows(self):
        # The bench this scheme exists for: 742.5 Mbps gets the bit-count
        # derived 205e-9 window (Linux ngspice-47 aborts inside the dead
        # time of the old 560e-9 one), 270 Mbps keeps 560e-9 byte-identical
        # so its committed records stay reproducible (issue #405).
        tb = tb_mod.load(SIM_DIR / "cml-driver-eye-mask")
        self.assertEqual(
            tb.analyses_for_rate(742.5), ("tran 20e-12 205e-9 0 40e-12",)
        )
        self.assertEqual(
            tb.analyses_for_rate(270.0), ("tran 20e-12 560e-9 0 40e-12",)
        )
        self.assertEqual(tb.analyses, ("tran 20e-12 560e-9 0 40e-12",))

    def test_mapped_tstop_disagreeing_with_the_tran_line_is_rejected(self):
        with self.assertRaises(ValueError):
            self._tb(
                transient={"tstep_s": 2e-12, "tstop_s": 20e-9},
            )

    def test_orphan_rate_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._tb(
                analyses_by_rate={
                    "742.5": self.SHORT_LINE,
                    "148.5": self.SHORT_LINE,
                },
                transient={
                    "tstep_s": 2e-12,
                    "tstop_s": 20e-9,
                    "tstop_s_by_rate": {"742.5": 5e-9, "148.5": 5e-9},
                },
            )

    def test_analyses_by_rate_without_a_rate_axis_is_rejected(self):
        with self.assertRaises(ValueError):
            load_testbench(
                self,
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "analyses": [self.DEFAULT_LINE],
                    "analyses_by_rate": {"742.5": self.SHORT_LINE},
                },
            )

    def test_tstop_s_by_rate_entry_without_a_matching_line_is_rejected(self):
        # A per-rate tstop with no analyses_by_rate entry for that rate is a
        # manifest that declares a window nothing runs -- same drift class
        # the default cross-check exists to catch.
        with self.assertRaises(ValueError):
            self._tb(
                transient={
                    "tstep_s": 2e-12,
                    "tstop_s": 20e-9,
                    "tstop_s_by_rate": {"742.5": 5e-9, "270": 9e-9},
                },
            )

    def test_record_transient_settings_spell_out_per_rate_tstops(self):
        lines = report_mod._operating_point_lines(
            {
                "grid": {"rates_mbps": [742.5, 270.0]},
                "testbench": {
                    "transient": {
                        "tstep_s": 20e-12,
                        "tstop_s": 560e-9,
                        "tstop_s_by_rate": {"742.5": 205e-9, "270": 560e-9},
                    }
                },
            }
        )
        settings = [ln for ln in lines if ln.startswith("- **Transient settings**")][0]
        self.assertIn("tstop=5.600000e-07s", settings)
        self.assertIn("2.050000e-07s@742.5 Mbps", settings)
        self.assertIn("5.600000e-07s@270 Mbps", settings)


class MatrixConformanceRateAxisTests(unittest.TestCase):
    def _tb(self, rates_mbps=()):
        manifest = {"netlist": "frag.spice", "measure": {"x": "v(x)"}}
        if rates_mbps:
            manifest["rates_mbps"] = list(rates_mbps)
            manifest["transient"] = {"tstep_s": 2e-12, "tstop_s": 20e-9}
            manifest["analyses"] = ["tran 2e-12 20e-9"]
        return load_testbench(self, manifest)

    def test_full_dc_matrix_has_no_missing_axes(self):
        tb = self._tb()
        corners = corners_mod.resolve_corners(["mos"])
        points = corners_mod.build_grid(
            corners, list(corners_mod.DEFAULT_TEMPERATURES_C), corners_mod.supply_points()
        )
        conformance = report_mod.matrix_conformance(tb, points)
        self.assertTrue(conformance["full"], conformance["missing"])

    def test_rate_bearing_matrix_missing_a_rate_is_flagged(self):
        tb = self._tb(rates_mbps=(742.5, 270.0))
        corners = corners_mod.resolve_corners(["mos"])
        # Only the target rate was actually run -- 270 Mbps/lane is missing.
        points = corners_mod.build_grid(
            corners,
            list(corners_mod.DEFAULT_TEMPERATURES_C),
            corners_mod.supply_points(),
            [742.5],
        )
        conformance = report_mod.matrix_conformance(tb, points)
        self.assertFalse(conformance["full"])
        self.assertTrue(any("rate" in m for m in conformance["missing"]))

    def test_rate_bearing_matrix_with_both_rates_is_full(self):
        tb = self._tb(rates_mbps=(742.5, 270.0))
        corners = corners_mod.resolve_corners(["mos"])
        points = corners_mod.build_grid(
            corners,
            list(corners_mod.DEFAULT_TEMPERATURES_C),
            corners_mod.supply_points(),
            [742.5, 270.0],
        )
        conformance = report_mod.matrix_conformance(tb, points)
        self.assertTrue(conformance["full"], conformance["missing"])

    def test_loaded_fixture_files_stay_readable_until_cleanup(self):
        # Issue #394: the fixture helper must not return from inside a
        # TemporaryDirectory context manager -- the loaded Testbench's
        # netlist file and both content hashes must stay readable through
        # the assertions that use the fixture.
        tb = self._tb(rates_mbps=(742.5,))
        self.assertTrue(tb.netlist.exists())
        self.assertTrue(tb.netlist_sha256)
        self.assertTrue(tb.manifest_sha256)


class GitProvenanceTests(unittest.TestCase):
    """Smoke coverage for ``report.git_provenance``/``working_tree_dirty``.

    These wrap ``evidence_lint._git`` (issue #55's dedup target) and had no
    dedicated tests before that refactor; this locks in the pre-refactor
    behavior on a real git checkout plus the non-git-directory fallback.
    """

    def setUp(self):
        self.root, self.git = init_git_repo(self)
        (self.root / "README.md").write_text("seed\n")
        # Pre-track the evidence directory itself (empty via .gitkeep) so a
        # later *new file inside it* is reported by git as an individual
        # untracked path, not folded into a single "new directory" line --
        # matching how sim/README.md's evidence tree is actually populated
        # incrementally by successive runs.
        evidence_dir = self.root / "sim" / "output-voltage-tc" / "records"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / ".gitkeep").write_text("")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "seed")

    def test_git_provenance_reports_clean_tree_at_head(self):
        expected_commit = self.git("rev-parse", "HEAD").stdout.strip()
        prov = report_mod.git_provenance(self.root)
        self.assertEqual(prov["commit"], expected_commit)
        self.assertEqual(prov["short"], expected_commit[:7])
        self.assertFalse(prov["dirty"])
        self.assertNotEqual(prov["branch"], "unknown")

    def test_working_tree_dirty_true_for_a_tracked_edit(self):
        (self.root / "README.md").write_text("changed\n")
        self.assertTrue(report_mod.working_tree_dirty(self.root))

    def test_working_tree_dirty_false_when_only_evidence_paths_changed(self):
        evidence_dir = self.root / "sim" / "output-voltage-tc" / "records"
        (evidence_dir / "new-record.md").write_text("# new record\n")
        self.assertFalse(report_mod.working_tree_dirty(self.root))

    def test_working_tree_dirty_ignore_matches_leading_space_first_line(self):
        # Issue #100: an unstaged ` M` entry sorting first must keep its
        # leading space, or `line[3:]` is off by one and the ignore misses.
        out = self.root / "flow" / "out"
        out.mkdir(parents=True)
        (out / "a.v").write_text("v1\n")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "add flow output")
        (out / "a.v").write_text("v2\n")
        ignore = re.compile(r"^flow/out/")
        self.assertFalse(report_mod.working_tree_dirty(self.root, ignore=ignore))
        (self.root / "README.md").write_text("changed\n")
        self.assertTrue(report_mod.working_tree_dirty(self.root, ignore=ignore))

    def test_git_provenance_falls_back_to_unknown_outside_a_git_checkout(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        prov = report_mod.git_provenance(outside)
        self.assertEqual(prov["commit"], "unknown")
        self.assertEqual(prov["short"], "unknown")
        self.assertEqual(prov["branch"], "unknown")
        self.assertFalse(prov["dirty"])


class ComposeDeckSaveLineTests(unittest.TestCase):
    """Issue #154: ``compose_deck`` emits an explicit ``.save`` line naming
    only the vectors ``tb.measure``'s expressions actually reference,
    instead of relying on ngspice's default of saving every node -- see
    ``sim/harness/runner.py``'s own module docstring for why (the "memory
    required ... is more than memory available" allocation guard on a
    large post-layout-extracted DUT). No PDK, no ngspice: ``compose_deck``
    only renders text, it does not invoke ngspice or read the netlist
    fragment/PDK files it names.
    """

    def _tb(self, measure: dict) -> tb_mod.Testbench:
        return load_testbench(
            self, {"netlist": "frag.spice", "measure": measure, "analyses": ["op"]}
        )

    def test_measure_vector_refs_collects_let_expression_vectors(self):
        tb = self._tb({"swing": "vecmax(v(outp))-vecmin(v(outn))", "icc": "i(vsens)"})
        self.assertEqual(
            runner_mod._measure_vector_refs(tb), ["v(outp)", "v(outn)", "i(vsens)"]
        )

    def test_measure_vector_refs_collects_raw_meas_fragment_vectors(self):
        # A "TRIG ... TARG ..." raw meas fragment (rise/fall time), not a
        # `let` vector expression -- both forms must be scanned.
        tb = self._tb(
            {"trise": "TRIG v(vdiff) VAL=-0.4 RISE=1 TARG v(vdiff) VAL=0.4 RISE=1"}
        )
        self.assertEqual(runner_mod._measure_vector_refs(tb), ["v(vdiff)"])

    def test_measure_vector_refs_deduplicates_in_first_seen_order(self):
        tb = self._tb(
            {
                "a": "v(x)-v(y)",
                "b": "v(y)-v(x)",
                "c": "v(z)",
            }
        )
        self.assertEqual(runner_mod._measure_vector_refs(tb), ["v(x)", "v(y)", "v(z)"])

    def test_measure_vector_refs_is_case_insensitive_and_comma_tolerant(self):
        # A differential two-terminal probe V(a,b) must be captured whole,
        # not split into two single-terminal refs, and V()/I() in any case
        # must both be recognized.
        tb = self._tb({"vdiff": "V(a,b)", "icc": "I(Vsens)"})
        self.assertEqual(runner_mod._measure_vector_refs(tb), ["V(a,b)", "I(Vsens)"])

    def test_compose_deck_emits_save_line_naming_every_referenced_vector(self):
        tb = self._tb({"swing": "v(outp)-v(outn)"})
        deck = runner_mod.compose_deck(tb, fake_pdk(), make_point())
        self.assertIn("save v(outp) v(outn)", deck)

    def test_compose_deck_save_line_precedes_the_analysis_line(self):
        # ngspice's `save` must be issued before the `.tran`/`.op`/etc.
        # analysis it applies to, or nothing is actually restricted.
        tb = self._tb({"swing": "v(outp)-v(outn)"})
        deck = runner_mod.compose_deck(tb, fake_pdk(), make_point())
        lines = deck.splitlines()
        save_idx = next(i for i, line in enumerate(lines) if line.strip().startswith("save "))
        op_idx = next(i for i, line in enumerate(lines) if line.strip() == "op")
        self.assertLess(save_idx, op_idx)

    def test_compose_deck_save_line_does_not_change_which_measurements_are_printed(self):
        # The optimization must be invisible to every downstream `let`/`meas`
        # line -- same measure keys, same `print m_<name>` lines, regardless
        # of whether `.save` narrows what ngspice additionally stores.
        tb = self._tb(
            {
                "swing": "v(outp)-v(outn)",
                "trise": "TRIG v(vdiff) VAL=-0.4 RISE=1 TARG v(vdiff) VAL=0.4 RISE=1",
            }
        )
        deck = runner_mod.compose_deck(tb, fake_pdk(), make_point())
        self.assertIn("let m_swing = v(outp)-v(outn)", deck)
        self.assertIn(
            "meas tran m_trise TRIG v(vdiff) VAL=-0.4 RISE=1 TARG v(vdiff) VAL=0.4 RISE=1",
            deck,
        )
        self.assertIn("print m_swing", deck)
        # trise is a raw `meas` fragment -- it prints via `meas` itself, no
        # separate `print` line (see compose_deck's own comment).
        self.assertNotIn("print m_trise", deck)


class NoinitOptionTests(unittest.TestCase):
    """Issue #305: both netlist-assembly paths emit ``.options noinit`` so
    ngspice stops printing its operating-point node table into every log --
    76.8 MB of the 92.7 MB this repo's 1211 committed logs hold, a table
    nothing in the tree reads. ``runner.compose_deck`` (local) and
    ``batch.compose_body`` (batch) must agree, and a testbench must be able
    to keep the table.

    Text-only: ``compose_deck``/``compose_body`` render strings, they do not
    invoke ngspice or read the PDK/netlist files they name.
    """

    def test_both_backends_emit_noinit_by_default(self):
        deck_opts, body_opts = both_options_lines(self)
        self.assertIn(".options noinit", deck_opts)
        self.assertIn(".options noinit", body_opts)

    def test_both_backends_emit_the_same_options_block(self):
        # The anti-drift assertion: one helper feeds both paths, so a deck and
        # a batch body can never disagree about what they ask ngspice for.
        deck_opts, body_opts = both_options_lines(self, 
            rates_mbps=[742.5],
            transient={
                "tstep_s": 1e-11,
                "tstop_s": 6.1e-08,
                "tmax_s": 2e-11,
                "reltol": 1e-06,
                "abstol": 1e-09,
                "vntol": 1e-06,
            },
            analyses=["tran 10e-12 61e-9 0 20e-12"],
        )
        self.assertEqual(deck_opts, body_opts)

    def test_noinit_follows_the_declared_transient_tolerances(self):
        # The directive is appended after the tolerances, so the existing
        # reltol/abstol/vntol provenance lines are unchanged and still present.
        deck_opts, body_opts = both_options_lines(self, 
            rates_mbps=[742.5],
            transient={
                "tstep_s": 1e-11,
                "tstop_s": 6.1e-08,
                "tmax_s": 2e-11,
                "reltol": 1e-06,
                "abstol": 1e-09,
                "vntol": 1e-06,
            },
            analyses=["tran 10e-12 61e-9 0 20e-12"],
        )
        for opts in (deck_opts, body_opts):
            self.assertEqual(
                opts,
                [
                    ".options reltol=1e-06",
                    ".options abstol=1e-09",
                    ".options vntol=1e-06",
                    ".options noinit",
                ],
            )

    def test_a_manifest_options_entry_keeps_its_place_and_wording(self):
        deck_opts, body_opts = both_options_lines(self, options=["gmin=1e-13", "method=gear"])
        for opts in (deck_opts, body_opts):
            self.assertEqual(
                opts,
                [".options gmin=1e-13", ".options method=gear", ".options noinit"],
            )

    def test_noinit_zero_manifest_entry_keeps_the_op_point_table(self):
        # ngspice's `noinit` is a presence-only flag -- `.options noinit=0`
        # suppresses the table exactly as `.options noinit` does -- so the
        # opt-out has to be consumed by the harness, never passed through.
        deck_opts, body_opts = both_options_lines(self, options=["noinit=0"])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [])

    def test_noinit_zero_opt_out_is_whitespace_and_case_insensitive(self):
        deck_opts, body_opts = both_options_lines(self, options=[" NoInit = 0 "])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [])

    def test_noinit_zero_opt_out_leaves_other_declared_options_alone(self):
        deck_opts, body_opts = both_options_lines(self, options=["gmin=1e-13", "noinit=0"])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [".options gmin=1e-13"])

    def test_a_testbench_wording_noinit_itself_is_not_given_a_second_one(self):
        deck_opts, body_opts = both_options_lines(self, options=["noinit"])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [".options noinit"])

    def test_noinit_does_not_change_which_measurements_are_printed(self):
        # The suppression must be invisible to every `let`/`print`/`meas`
        # line -- the `m_*` lines are what `_MEASURE_RE` parses out of the log.
        tb = options_testbench(
            self,
            measure={
                "swing": "v(outp)-v(outn)",
                "trise": "TRIG v(vd) VAL=-0.4 RISE=1 TARG v(vd) VAL=0.4 RISE=1",
            },
        )
        deck = runner_mod.compose_deck(tb, fake_pdk(), make_point())
        self.assertIn("let m_swing = v(outp)-v(outn)", deck)
        self.assertIn("print m_swing", deck)
        self.assertIn(
            "meas tran m_trise TRIG v(vd) VAL=-0.4 RISE=1 TARG v(vd) VAL=0.4 RISE=1",
            deck,
        )

    def test_noinit_precedes_the_control_block(self):
        # `.options` is a deck-level directive: it must land before `.control`,
        # not inside it.
        tb = options_testbench(self)
        deck = runner_mod.compose_deck(tb, fake_pdk(), make_point())
        lines = deck.splitlines()
        noinit_idx = lines.index(".options noinit")
        self.assertLess(noinit_idx, lines.index(".control"))


class ProgressTraceFilterTests(unittest.TestCase):
    """Issue #317: the log write path drops ngspice's `` Reference value :
    <float>`` transient solver progress trace. It is not suppressible by any
    netlist directive, so the two write sites through which raw ngspice text
    reaches a log -- ``runner.run_point`` (local backend) and
    ``report.write_device_corner_log`` (device-level evidence plumbing) --
    both go through one shared ``runner.filter_progress_trace``. The batch
    backend is deliberately uncovered: its log is a klt CLI wrapper around
    klt's own JSON report, and raw ngspice text never reaches that write.

    Fixture text only, never a live run: the trace is non-deterministic
    run-to-run (the same deck printed 5 lines then 4 at different times,
    issue #317), so any assertion on a live run's line count would be flaky
    by construction.
    """

    TRACE_LINES = [
        " Reference value :  4.83720e+00\n",
        " Reference value :  2.15000e-03\n",
        " Reference value :  9.99851e+02\n",
        " Reference value :  1.00000e-09\n",
    ]

    # Every line class the filter must preserve byte for byte: the title,
    # the temp/solver lines, every `Warning:`/`Error:` line, every `m_*`
    # line (`let`/`print` form and `meas` form alike) and `No. of Data
    # Rows`. Modelled on a committed corner log.
    KEPT_LINES = [
        "\n",
        "Note: No compatibility mode selected!\n",
        "\n",
        "Circuit: * cml-driver-eye @ tt_27c_3.30v_742p5mbps"
        " -- generated by sim/harness, do not edit\n",
        "\n",
        "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n",
        "\n",
        "Using SPARSE 1.3 as Direct Linear Solver\n",
        "Warning: diode_nd2ps_06v0: IKR too small - model effect disabled!\n",
        "Error: unknown vector v(nonsense)\n",
        "m_trise  = 8.00000e-10 targ=6.10e-08 trig=6.02e-08\n",
        "m_swing_dc = 5.0449668753e-01\n",
        "No. of Data Rows : 1234\n",
        "Note: Simulation executed from .control section \n",
    ]

    def _fixture(self) -> tuple[str, str]:
        """A committed-log-shaped ngspice output, and the exact text that
        must survive it: the same kept lines, in the same order, with the
        trace lines gone and every other byte unchanged."""
        kept, trace = list(self.KEPT_LINES), list(self.TRACE_LINES)
        pieces = (
            kept[0:3]
            + trace[0:2]
            + kept[3:7]
            + [trace[2]]
            + kept[7:11]
            + [trace[3]]
            + kept[11:]
        )
        return "".join(pieces), "".join(kept)

    def test_trace_lines_are_dropped_and_the_rest_is_byte_identical(self):
        fixture, expected = self._fixture()
        self.assertEqual(runner_mod.filter_progress_trace(fixture), expected)

    def test_every_kept_line_survives_byte_for_byte(self):
        fixture, _ = self._fixture()
        filtered = runner_mod.filter_progress_trace(fixture)
        for line in self.KEPT_LINES:
            self.assertIn(line, filtered)

    def test_text_without_trace_lines_is_byte_identical(self):
        text = "".join(self.KEPT_LINES)
        self.assertEqual(runner_mod.filter_progress_trace(text), text)

    def test_a_line_merely_containing_the_phrase_survives(self):
        # Negative match: the anchor is the *whole line*, leading space
        # through end of line. A warning quoting the phrase, or the phrase
        # under any spacing/sign/number-shape variation, must come through
        # untouched -- this is what stops the filter widening silently.
        near_misses = [
            "Reference value :  1.00000e+00\n",  # no leading space
            " Reference value : 1.00000e+00\n",  # one space after the colon
            " Reference value :  1.00000e+00 \n",  # trailing space
            "Warning: last Reference value :  1.00000e+00 was negative\n",
            " Reference value :  -1.00000e+00\n",  # negative mantissa
            " Reference value :  1e+00\n",  # no fractional part
        ]
        text = "".join(near_misses)
        self.assertEqual(runner_mod.filter_progress_trace(text), text)

    def test_empty_text_passes_through(self):
        # A run whose ngspice output was empty wrote an empty log before
        # this filter existed too; the filter adds no new empty-log path
        # beyond the trace-only degenerate case documented on the helper.
        self.assertEqual(runner_mod.filter_progress_trace(""), "")

    def test_only_trace_lines_filters_to_empty(self):
        # Documented degenerate case: the evidence store's non-empty guard
        # rejects the result loudly at ingest, exactly as it rejects an
        # ngspice run that printed nothing at all.
        self.assertEqual(
            runner_mod.filter_progress_trace("".join(self.TRACE_LINES)), ""
        )

    def test_keep_true_returns_the_text_verbatim(self):
        fixture, _ = self._fixture()
        self.assertEqual(
            runner_mod.filter_progress_trace(fixture, keep=True), fixture
        )


class ProgressTraceOptionTests(unittest.TestCase):
    """Issue #317: the ``"reftrace=1"`` manifest ``options`` entry keeps the
    solver progress trace. It is consumed by ``_option_lines`` -- never
    emitted, since ngspice has no directive for it -- exactly the way
    ``"noinit=0"`` is consumed for the node table (issue #305), so both
    escape hatches share the one mechanism: a manifest ``options`` entry.
    """

    def test_reftrace_entry_is_consumed_not_emitted(self):
        deck_opts, body_opts = both_options_lines(self, options=["reftrace=1"])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [".options noinit"])

    def test_reftrace_entry_is_whitespace_and_case_insensitive(self):
        deck_opts, body_opts = both_options_lines(self, options=[" RefTrace = 1 "])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [".options noinit"])

    def test_reftrace_composes_with_the_noinit_zero_hatch(self):
        deck_opts, body_opts = both_options_lines(self, options=["noinit=0", "reftrace=1"])
        for opts in (deck_opts, body_opts):
            self.assertEqual(opts, [])

    def test_wants_progress_trace_follows_the_manifest(self):
        self.assertFalse(runner_mod._wants_progress_trace(options_testbench(self)))
        self.assertTrue(
            runner_mod._wants_progress_trace(
                options_testbench(self, options=["reftrace=1"])
            )
        )


class DeviceCornerLogTraceFilterTests(unittest.TestCase):
    """Issue #317: ``write_device_corner_log`` applies the same shared
    filter, so the Monte Carlo path (its one non-test caller,
    ``cml-driver-mismatch/run_mc.py``, which passes the raw ``s.log``) is
    covered before it can regress -- with ``keep_progress_trace=True``
    returning the log verbatim for a device-level debug run.

    Issue #345: the writer takes a *flat* destination directory -- a
    manifest-forward bench passes ``evidence_store.stage_dir(...)`` (whose
    record-id path component already encodes the run, and whose
    ``store_run`` globs the directory flat), so the writer must not add a
    ``<record-id>/`` level of its own.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.record_id = "20260101-000000-abc1234"
        self.header = f"* record-id : {self.record_id}\n"
        self.log = (
            "Circuit: * cml_driver_mismatch @ tt_27c_3.30v"
            " -- generated by sim/harness, do not edit\n"
            " Reference value :  4.83720e+00\n"
            "m_swing_dc = 5.0449668753e-01\n"
            "No. of Data Rows : 999\n"
        )

    def _write(self, **kwargs) -> str:
        path = report_mod.write_device_corner_log(
            self.tmp, "tt_27c_3.30v", self.header, self.log, **kwargs,
        )
        return path.read_text(encoding="utf-8")

    def test_device_corner_log_drops_the_trace_by_default(self):
        written = self._write()
        self.assertEqual(
            written,
            self.header
            + "Circuit: * cml_driver_mismatch @ tt_27c_3.30v"
            + " -- generated by sim/harness, do not edit\n"
            + "m_swing_dc = 5.0449668753e-01\n"
            + "No. of Data Rows : 999\n",
        )

    def test_device_corner_log_keeps_the_trace_when_asked(self):
        written = self._write(keep_progress_trace=True)
        self.assertEqual(written, self.header + self.log)

    def test_device_corner_log_writes_flat_no_record_subdir(self):
        # The stage dir's record-id component already encodes the run and
        # store_run globs flat, so a nested <record-id>/ level would hide
        # the staged logs from the store. The log lands at the top level.
        self._write()
        self.assertEqual(
            [p.name for p in self.tmp.iterdir()], ["tt_27c_3.30v.log"]
        )


class DeviceEvidenceAppendOnlyTests(unittest.TestCase):
    """Issue #95: ``write_device_netlist_snapshot`` must refuse a collision
    instead of silently overwriting via ``shutil.copyfile``.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.snapshot_dir = self.tmp / "netlist-snapshots"
        self.deck = self.tmp / "deck.spice"
        self.deck.write_text("* deck\n")

    def test_write_device_netlist_snapshot_refuses_a_collision(self):
        record = "20260101-000000-abc1234"
        report_mod.write_device_netlist_snapshot(self.snapshot_dir, record, self.deck)
        with self.assertRaises(report_mod.RecordExists):
            report_mod.write_device_netlist_snapshot(self.snapshot_dir, record, self.deck)


class LocalGridStartupTests(unittest.TestCase):
    """Issue #415: ``run_grid`` seeds the grid work directory's
    ``.spiceinit`` from ``pdk.GF180_NGSPICE_INIT`` before any ngspice child
    launches, so the local backend binds gf180mcu MOS model bins by width
    per finger on a host with no ``~/.spiceinit``. No PDK, no ngspice: the
    subprocess is a stub that records the startup file's contents at the
    moment ngspice would start, which is the only moment that matters --
    ngspice applies a working-directory ``.spiceinit`` before opening the
    deck, and a ``set`` inside the deck's ``.control`` block is too late
    for model binding.
    """

    _STARTUP_TEXT = "set wnflag=1\nset num_threads=1\n"

    def _tb(self) -> tb_mod.Testbench:
        return load_testbench(
            self,
            {"netlist": "frag.spice", "measure": {"swing": "v(a)"}, "analyses": ["op"]},
        )

    def _run_grid_with_stub_ngspice(self, workdir, *, points, jobs):
        startup_at_launch = []

        def fake_run(cmd, **kwargs):
            startup = Path(kwargs["cwd"]) / ".spiceinit"
            startup_at_launch.append(
                startup.read_text() if startup.is_file() else None
            )
            return subprocess.CompletedProcess(
                cmd, 0, stdout="m_swing = 6.9043645202e-01\n", stderr=""
            )

        with mock.patch.object(runner_mod.subprocess, "run", side_effect=fake_run):
            results = runner_mod.run_grid(
                self._tb(), fake_pdk(), points, Path(workdir), jobs=jobs
            )
        return results, startup_at_launch

    def test_ngspice_launches_with_the_pdk_startup_file_in_its_cwd(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        points = [make_point()]
        results, startup_at_launch = self._run_grid_with_stub_ngspice(
            tmp, points=points, jobs=1
        )
        self.assertEqual([r.status for r in results], ["ok"])
        self.assertEqual(startup_at_launch, [self._STARTUP_TEXT])

    def test_parallel_points_share_one_startup_file_and_leave_home_alone(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        points = [make_point(corner=name) for name in ("tt", "ss")]
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            results, startup_at_launch = self._run_grid_with_stub_ngspice(
                tmp, points=points, jobs=2
            )
        self.assertEqual([r.status for r in results], ["ok", "ok"])
        # Both parallel children saw the complete two-line startup in order,
        # never a truncated file -- run_grid writes it once, before the pool.
        self.assertEqual(startup_at_launch, [self._STARTUP_TEXT] * 2)
        # The host's home directory is never the lever: the startup file is
        # the grid work directory's, and nothing is written under $HOME.
        self.assertEqual(list(home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
