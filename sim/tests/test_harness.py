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

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod  # noqa: E402
from harness import evidence_lint as lint_mod  # noqa: E402
from harness import report as report_mod  # noqa: E402
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

    def test_corner_id_rate_mbps(self):
        self.assertEqual(lint_mod.corner_id_rate_mbps("tt_27c_3.30v_742p5mbps"), 742.5)
        self.assertIsNone(lint_mod.corner_id_rate_mbps("tt_27c_3.30v"))


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
    def _write_manifest(self, tmp: Path, manifest: dict, netlist_body: str = "* fragment\n") -> Path:
        directory = tmp / "my-experiment" / "testbench"
        directory.mkdir(parents=True)
        (directory / "frag.spice").write_text(netlist_body)
        (directory / tb_mod.MANIFEST_NAME).write_text(json.dumps(manifest))
        return directory

    def test_rates_without_transient_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                },
            )
            with self.assertRaises(ValueError):
                tb_mod.load(directory)

    def test_transient_without_rates_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "transient": {"tstep_s": 2e-12, "tstop_s": 20e-9},
                    "analyses": ["tran 2e-12 20e-9"],
                },
            )
            with self.assertRaises(ValueError):
                tb_mod.load(directory)

    def test_transient_missing_required_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                    "transient": {"tstop_s": 20e-9},
                    "analyses": ["tran 2e-12 20e-9"],
                },
            )
            with self.assertRaises(ValueError):
                tb_mod.load(directory)

    def test_transient_with_no_tran_analysis_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                    "transient": {"tstep_s": 2e-12, "tstop_s": 20e-9},
                    "analyses": ["op"],
                },
            )
            with self.assertRaises(ValueError):
                tb_mod.load(directory)

    def test_transient_settings_disagreeing_with_tran_line_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                    "rates_mbps": [742.5],
                    "transient": {"tstep_s": 2e-12, "tstop_s": 99e-9},
                    "analyses": ["tran 2e-12 20e-9"],
                },
            )
            with self.assertRaises(ValueError):
                tb_mod.load(directory)

    def test_valid_transient_testbench_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
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
            tb = tb_mod.load(directory)
            self.assertEqual(tb.rates_mbps, (742.5, 270.0))
            self.assertEqual(tb.transient["reltol"], 1e-6)

    def test_dc_testbench_with_no_rate_axis_loads_unchanged(self):
        """A manifest with neither `rates_mbps` nor `transient` behaves
        exactly like the un-adapted gf180-bandgap harness."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._write_manifest(
                Path(tmp),
                {
                    "netlist": "frag.spice",
                    "measure": {"x": "v(x)"},
                },
            )
            tb = tb_mod.load(directory)
            self.assertEqual(tb.rates_mbps, ())
            self.assertEqual(tb.transient, {})


class MatrixConformanceRateAxisTests(unittest.TestCase):
    def _tb(self, rates_mbps=()):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "exp" / "testbench"
            directory.mkdir(parents=True)
            (directory / "frag.spice").write_text("* fragment\n")
            manifest = {"netlist": "frag.spice", "measure": {"x": "v(x)"}}
            if rates_mbps:
                manifest["rates_mbps"] = list(rates_mbps)
                manifest["transient"] = {"tstep_s": 2e-12, "tstop_s": 20e-9}
                manifest["analyses"] = ["tran 2e-12 20e-9"]
            (directory / tb_mod.MANIFEST_NAME).write_text(json.dumps(manifest))
            return tb_mod.load(directory)

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


if __name__ == "__main__":
    unittest.main()
