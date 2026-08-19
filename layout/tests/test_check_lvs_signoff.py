#!/usr/bin/env python3
"""Tests for layout/scripts/check_lvs_signoff.py (issue #129).

Stdlib ``unittest``, no PDK and no ``klt`` -- run by ``python3 -m unittest
discover -s layout/tests`` locally and by CI's PDK-free ``test`` job.

The load-bearing test is ``test_regressed_negative_control_fails``: it runs
the checker against ``fixtures/klayout_tools_1196/``, a **real, captured**
``klt lvs`` report pair produced by the drifted extraction deck that issue
#129 reports (see that directory's README for the exact klayout-tools commit
and deck ``content_hash``). That report says ``status: match`` on a cell whose
drawn geometry still shorts PAD to VSS. If the checker ever passes that
fixture, the guard has stopped guarding.
"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))

import check_lvs_signoff  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REGRESSED = FIXTURES / "klayout_tools_1196"
COMMITTED_REPORTS = REPO_ROOT / "layout" / "lvs_reports"


def run_checker(reports_dir: Path) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = check_lvs_signoff.main(["--reports-dir", str(reports_dir)])
    return code, buffer.getvalue()


class CommittedReportsTest(unittest.TestCase):
    """The reports actually committed under layout/lvs_reports/ must pass."""

    def test_committed_reports_pass(self):
        code, output = run_checker(COMMITTED_REPORTS)
        self.assertEqual(code, 0, output)
        self.assertIn("PASS", output)

    def test_every_shorted_report_is_a_failing_negative_control(self):
        controls = sorted(COMMITTED_REPORTS.glob("*_shorted.lvs.json"))
        self.assertTrue(controls, "no _shorted negative-control reports found")
        for path in controls:
            with self.subTest(report=path.name):
                report = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "mismatch")
                self.assertGreaterEqual(check_lvs_signoff._error_count(report), 1)

    def test_pad_v2_pair_is_the_issue_129_verdict(self):
        """The specific cell issue #129 is about, pinned both ways."""
        intact = json.loads(
            (COMMITTED_REPORTS / "gf180_tmds_pad_v2.lvs.json").read_text(
                encoding="utf-8"
            )
        )
        shorted = json.loads(
            (COMMITTED_REPORTS / "gf180_tmds_pad_v2_shorted.lvs.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(intact["status"], "match")
        self.assertEqual(shorted["status"], "mismatch")
        # The intact cell's two nets are the real drawn PAD/VSS pair, with no
        # deck-synthesized `vsubs` among them -- the DR-0011
        # `device.body_unverified` claim layout/README.md makes for this cell.
        nets = {
            entry.get("layout")
            for entry in intact.get("net_correspondence", [])
            if isinstance(entry, dict)
        }
        self.assertNotIn("vsubs", nets)


class RegressedFixtureTest(unittest.TestCase):
    """The captured klayout-tools#1196 regression must be rejected."""

    def test_fixture_is_the_regression(self):
        report = json.loads(
            (REGRESSED / "gf180_tmds_pad_v2_shorted.lvs.json").read_text(
                encoding="utf-8"
            )
        )
        # Sanity-check the fixture really is the defeated control, so this
        # test cannot quietly degrade into asserting nothing.
        self.assertTrue(report["top"].endswith("_shorted"))
        self.assertEqual(report["status"], "match")

    def test_regressed_negative_control_fails(self):
        code, output = run_checker(REGRESSED)
        self.assertEqual(code, 1, output)
        self.assertIn("DEFEATED", output)


class SyntheticCaseTest(unittest.TestCase):
    """Cases with no captured artifact, built by mutating a real report."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for suffix in (".json", ".txt"):
            shutil.copy(
                COMMITTED_REPORTS / f"gf180_tmds_pad_v2_shorted.lvs{suffix}",
                self.tmp / f"gf180_tmds_pad_v2_shorted.lvs{suffix}",
            )

    def _report_path(self) -> Path:
        return self.tmp / "gf180_tmds_pad_v2_shorted.lvs.json"

    def test_warning_only_mismatch_is_not_a_negative_control(self):
        """`mismatch` reached without a single error-severity finding."""
        path = self._report_path()
        report = json.loads(path.read_text(encoding="utf-8"))
        report["error_count"] = 0
        for finding in report["mismatches"]:
            finding["severity"] = "warning"
        path.write_text(json.dumps(report), encoding="utf-8")
        code, output = run_checker(self.tmp)
        self.assertEqual(code, 1, output)
        self.assertIn("0 error-severity findings", output)

    def test_txt_json_disagreement_fails(self):
        """The klayout-tools#1185 hazard: two runs, two different verdicts."""
        txt = self.tmp / "gf180_tmds_pad_v2_shorted.lvs.txt"
        txt.write_text(
            txt.read_text(encoding="utf-8").replace(
                "status: mismatch", "status: match", 1
            ),
            encoding="utf-8",
        )
        code, output = run_checker(self.tmp)
        self.assertEqual(code, 1, output)
        self.assertIn("contradicts", output)

    def test_missing_txt_fails(self):
        (self.tmp / "gf180_tmds_pad_v2_shorted.lvs.txt").unlink()
        code, output = run_checker(self.tmp)
        self.assertEqual(code, 1, output)
        self.assertIn("missing text report", output)

    def test_undocumented_intact_mismatch_fails(self):
        for suffix in (".json", ".txt"):
            shutil.copy(
                COMMITTED_REPORTS / f"gf180_tmds_pad_v2.lvs{suffix}",
                self.tmp / f"gf180_tmds_pad_v2.lvs{suffix}",
            )
        path = self.tmp / "gf180_tmds_pad_v2.lvs.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["status"] = "mismatch"
        path.write_text(json.dumps(report), encoding="utf-8")
        code, output = run_checker(self.tmp)
        self.assertEqual(code, 1, output)
        self.assertIn("DOCUMENTED_MISMATCHES", output)

    def test_documented_intact_mismatch_passes(self):
        """tmds_encoder's accepted mismatch is allowlisted, not ignored."""
        self.assertIn("tmds_encoder", check_lvs_signoff.DOCUMENTED_MISMATCHES)
        for suffix in (".json", ".txt"):
            shutil.copy(
                COMMITTED_REPORTS / f"tmds_encoder.lvs{suffix}",
                self.tmp / f"tmds_encoder.lvs{suffix}",
            )
        code, output = run_checker(self.tmp)
        self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main()
