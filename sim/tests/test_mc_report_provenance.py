"""run_mc.py reads sample index / seed / engine version from the report.

    python3 -m unittest sim.tests.test_mc_report_provenance -v

No PDK, ngspice or network: canned ``klt sim`` report dicts only.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _dir in (SIM_DIR, TESTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from _harness_fixtures import load_run_mc  # noqa: E402
from harness import batch  # noqa: E402
from harness.corners import CORNERS, PvtPoint  # noqa: E402
from harness.runner import PointResult  # noqa: E402

run_mc = load_run_mc("run_mc")


def _entry(cid, mc=None):
    e = {
        "corner_id": cid,
        "status": "ok",
        "runtime_s": 1.0,
        "measurements": [
            {"name": "swing_dc", "value": 0.4},
            {"name": "vcm_dc", "value": 1.2},
        ],
    }
    if mc is not None:
        e["monte_carlo"] = mc
    return e


def _samples(entries, **kw):
    corner = run_mc.CORNERS["tt"]
    return run_mc._samples_from_report(
        {"corners": entries}, [corner], lambda i: f"mc{i + 1:03d}",
        run_mc.PAR_TAIL_NOMINAL, 1, lambda c, i: 1000 + i, need_index=True, **kw,
    )


class SampleIdentityTests(unittest.TestCase):
    def test_reported_index_and_seed_win(self):
        got = _samples([_entry("tt/novdd/27C/mc9", {"sample_index": 2, "seed": 777})])
        self.assertEqual(got[0].label, "mc003")
        self.assertEqual(got[0].seed, 777)

    def test_fallback_when_block_absent(self):
        got = _samples([_entry("tt/novdd/27C/mc4")])
        self.assertEqual(got[0].label, "mc005")
        self.assertEqual(got[0].seed, 1004)

    def test_no_index_anywhere_is_batch_error(self):
        with self.assertRaises(batch.BatchError):
            _samples([_entry("tt/novdd/27C")])

    def test_index_from_block_without_mcn_suffix(self):
        got = _samples([_entry("tt/novdd/27C", {"sample_index": 0, "seed": 5})])
        self.assertEqual((got[0].label, got[0].seed), ("mc001", 5))


class EngineVersionTests(unittest.TestCase):
    """Both entry points share one rendering rule (issue #381)."""

    MIXED = ("ngspice-48", "47", "46", "47", "")

    @staticmethod
    def _results(versions):
        return [
            PointResult(
                point=PvtPoint(corner=CORNERS["tt"], temp_c=27.0, vdd=3.3),
                status="ok",
                engine_version=v,
            )
            for v in versions
        ]

    def test_reads_report_versions(self):
        reports = [
            {"environment": {"engine_version": "47"}},
            {"environment": {"engine_version": "46"}},
            {"environment": {}},
        ]
        self.assertEqual(batch.engine_from_reports(reports), "ngspice-46, ngspice-47")

    def test_unreported(self):
        self.assertEqual(batch.engine_from_reports([{}]), "unreported (batch)")

    def test_mixed_versions_render_identically(self):
        expected = "ngspice-46, ngspice-47, ngspice-48"
        reports = [{"environment": {"engine_version": v}} for v in self.MIXED]
        self.assertEqual(batch.engine_from_reports(reports), expected)
        self.assertEqual(batch.engine_summary(self._results(self.MIXED)), expected)

    def test_unreported_through_both_entry_points(self):
        self.assertEqual(
            batch.engine_summary(self._results(("", ""))), "unreported (batch)"
        )
        self.assertEqual(
            batch.engine_from_reports([{}, {"environment": None}, {"environment": {}}]),
            "unreported (batch)",
        )

    def test_absent_null_and_empty_environment_are_unreported(self):
        for report in ({}, {"environment": None}, {"environment": {}}):
            with self.subTest(report=report):
                self.assertEqual(batch.engine_from_reports([report]), "unreported (batch)")


if __name__ == "__main__":
    unittest.main()
