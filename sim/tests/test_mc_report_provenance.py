"""run_mc.py reads sample index / seed / engine version from the report.

    python3 -m unittest sim.tests.test_mc_report_provenance -v

No PDK, ngspice or network: canned ``klt sim`` report dicts only.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness import batch  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "run_mc", SIM_DIR / "cml-driver-mismatch" / "run_mc.py"
)
run_mc = importlib.util.module_from_spec(_spec)
sys.modules["run_mc"] = run_mc
_spec.loader.exec_module(run_mc)


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
    def test_reads_report_versions(self):
        reports = [
            {"environment": {"engine_version": "47"}},
            {"environment": {"engine_version": "46"}},
            {"environment": {}},
        ]
        self.assertEqual(batch.engine_from_reports(reports), "ngspice-46, ngspice-47")

    def test_unreported(self):
        self.assertEqual(batch.engine_from_reports([{}]), "unreported (batch)")


if __name__ == "__main__":
    unittest.main()
