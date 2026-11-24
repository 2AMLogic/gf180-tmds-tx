"""``run_mc`` report -> ``Sample`` mapping tests (issue #359).

    python3 -m unittest sim.tests.test_run_mc_report_mapping -v

Report dicts are fed straight into ``run_mc._samples_from_report`` and
``run_mc.run_all`` (with ``_run`` stubbed to return a report). The fixtures
under ``sim/tests/fixtures/`` are entries captured from real ``klt sim``
reports (see their ``_provenance`` key). No PDK, ngspice or network.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TESTS_DIR = Path(__file__).resolve().parent
for _dir in (SIM_DIR, TESTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from _harness_fixtures import load_run_mc  # noqa: E402
from harness import batch  # noqa: E402
from harness import evidence_lint  # noqa: E402
from harness.corners import CORNER_SETS, CORNERS  # noqa: E402

run_mc = load_run_mc("cml_driver_mismatch_run_mc_mapping")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _map(report, corners, *, mc: bool):
    if mc:
        return run_mc._samples_from_report(
            report, corners, lambda i: f"mc{i + 1:03d}", run_mc.PAR_TAIL_NOMINAL, 1,
            lambda c, i: 20260815 + i,
        )
    return run_mc._samples_from_report(
        report, corners, lambda i: "nominal", run_mc.PAR_TAIL_NOMINAL, 0, lambda c, i: None
    )


class McReportTests(unittest.TestCase):
    def setUp(self):
        self.report = _fixture("klt_report_mc_tt.json")
        self.samples = _map(self.report, [CORNERS["tt"]], mc=True)

    def test_n_entries_give_n_samples_in_order(self):
        self.assertEqual(len(self.samples), len(self.report["corners"]))
        self.assertEqual([s.label for s in self.samples], ["mc001", "mc002", "mc003"])

    def test_ids_match_the_evidence_lint_grammar(self):
        for s in self.samples:
            self.assertIsNone(evidence_lint.parse_corner_id(s.corner_id), s.corner_id)
        self.assertEqual(self.samples[0].corner_id, "tt_mc001_27c_3.30v")

    def test_seeds_are_the_ones_the_report_states(self):
        stated = [e["monte_carlo"]["seed"] for e in self.report["corners"]]
        self.assertEqual([s.seed for s in self.samples], stated)

    def test_values_and_status_come_from_the_measurements(self):
        first = self.samples[0]
        self.assertEqual(first.status, "ok")
        self.assertEqual(first.swing_dc, 0.4697662)
        self.assertEqual(first.vcm_dc, 3.065116)

    def test_index_extraction_uses_the_trailing_mc_number(self):
        report = copy.deepcopy(self.report)
        report["corners"][0]["corner_id"] = "tt/novdd/27C/mc11"
        # the entry's monte_carlo.sample_index is authoritative (#358) ...
        self.assertEqual(_map(report, [CORNERS["tt"]], mc=True)[0].label, "mc001")
        # ... and the trailing mcN is the fallback when the report states none
        del report["corners"][0]["monte_carlo"]["sample_index"]
        self.assertEqual(_map(report, [CORNERS["tt"]], mc=True)[0].label, "mc012")


class NominalReportTests(unittest.TestCase):
    def setUp(self):
        self.report = _fixture("klt_report_nominal.json")
        self.corners = [CORNERS[n] for n in ("tt", "ss", "ff")]
        self.samples = _map(self.report, self.corners, mc=False)

    def test_one_nominal_sample_per_corner_without_seed(self):
        self.assertEqual([s.corner.name for s in self.samples], ["tt", "ss", "ff"])
        for s in self.samples:
            self.assertEqual(s.label, "nominal")
            self.assertIsNone(s.seed)
            self.assertEqual(s.status, "ok")
            self.assertIsNone(evidence_lint.parse_corner_id(s.corner_id), s.corner_id)
        self.assertEqual(self.samples[1].corner_id, "ss_nominal_27c_3.30v")


class ErrorEntryTests(unittest.TestCase):
    def setUp(self):
        self.report = _fixture("klt_report_mc_tt.json")

    def _graded(self, mutate):
        report = copy.deepcopy(self.report)
        mutate(report["corners"][1])
        samples = _map(report, [CORNERS["tt"]], mc=True)
        self.assertEqual(len(samples), len(self.report["corners"]))  # still counted in N
        return samples

    def test_status_error_is_an_error_sample(self):
        samples = self._graded(lambda e: e.update(status="error"))
        self.assertEqual([s.status for s in samples], ["ok", "error", "ok"])

    def test_status_inconclusive_is_an_error_sample(self):
        samples = self._graded(lambda e: e.update(status="inconclusive"))
        self.assertEqual(samples[1].status, "error")

    def test_missing_vcm_dc_is_an_error_sample(self):
        samples = self._graded(
            lambda e: e.update(measurements=[m for m in e["measurements"] if m["name"] != "vcm_dc"])
        )
        self.assertEqual(samples[1].status, "error")
        self.assertIsNone(samples[1].vcm_dc)

    def test_missing_swing_dc_is_an_error_sample(self):
        samples = self._graded(lambda e: e.update(measurements=[]))
        self.assertEqual(samples[1].status, "error")
        self.assertIsNone(samples[1].swing_dc)


class RunAllGuardTests(unittest.TestCase):
    """``run_all`` with ``_run`` stubbed to return canned reports."""

    N = 3
    BASE_SEED = 20260814  # first tt sample seed = base + 1 = the fixture's 20260815

    def setUp(self):
        self.mc = _fixture("klt_report_mc_tt.json")
        nominal = _fixture("klt_report_nominal.json")
        # The fixture holds tt/ss/ff; fs/sf units are the tt entry re-keyed.
        for name in ("fs", "sf"):
            entry = copy.deepcopy(nominal["corners"][0])
            entry["corner_id"] = f"{name}/novdd/27C"
            entry["process"] = name
            nominal["corners"].append(entry)
        self.nominal = nominal
        self.neg = {"corners": [copy.deepcopy(self.mc["corners"][0])]}
        self.neg["corners"][0]["corner_id"] = "tt/novdd/27C"
        self._orig = run_mc._run
        self.addCleanup(setattr, run_mc, "_run", self._orig)

    def _stub(self, *, mc=None, nominal=None, neg=None):
        reports = {
            "nominal": nominal or self.nominal,
            "mcneg": neg or self.neg,
        }

        self.run_seeds = {}

        def fake_run(pdk, workdir, name, corners, **kw):
            self.run_seeds[name] = kw.get("seed")
            if name.startswith("mc_"):
                report = copy.deepcopy(mc or self.mc)  # tt entries re-keyed to this corner
                for entry in report["corners"]:
                    entry["corner_id"] = entry["corner_id"].replace("tt/", f"{corners[0].name}/", 1)
                return report, ""
            return reports[name], ""

        run_mc._run = fake_run

    def _run_all(self):
        return run_mc.run_all(None, Path("."), self.N, self.BASE_SEED)

    def test_complete_reports_map_every_unit(self):
        self._stub()
        samples, _jobs, _engine, _staging = self._run_all()
        n_corners = len(CORNER_SETS["mos"])
        self.assertEqual(len(samples), n_corners * self.N + n_corners + 1)
        self.assertEqual([s.status for s in samples].count("ok"), len(samples))

    def test_run_all_supplies_ids_and_seeds(self):
        """Pin the ids `run_all` supplies and the per-corner seed block it requests.

        Sample seeds come from the report (#358), so the k*1000 block is
        observable only as the ``seed`` kwarg `run_all` passes to `_run`.
        """
        self._stub()
        samples, _jobs, _engine, _staging = self._run_all()
        # Spelled out, not read from CORNER_SETS: the record's "k: 0=tt, 1=ff, ..."
        # prose is the contract, so a reorder of the tuple must fail here.
        names = ("tt", "ff", "ss", "fs", "sf")
        self.assertEqual(
            {n: self.run_seeds[f"mc_{n}"] for n in names},
            {n: self.BASE_SEED + k * 1000 + 1 for k, n in enumerate(names)},
        )
        self.assertEqual(self.run_seeds["mcneg"], self.BASE_SEED)
        # Nominal is a deterministic point: no seed requested, none recorded.
        self.assertIsNone(self.run_seeds["nominal"])
        nominal = [s for s in samples if s.label == "nominal"]
        self.assertEqual(len(nominal), len(names))
        self.assertTrue(all(s.seed is None for s in nominal))
        expected = {f"{n}_mc{i:03d}_27c_3.30v" for n in names for i in range(1, self.N + 1)}
        expected |= {f"{n}_nominal_27c_3.30v" for n in names}
        expected.add("tt_mcneg_27c_3.30v")
        self.assertEqual({s.corner_id for s in samples}, expected)
        self.assertEqual(len(samples), len(expected))  # no duplicate ids collapsed

    def test_short_mc_report_raises(self):
        short = copy.deepcopy(self.mc)
        short["corners"].pop()
        self._stub(mc=short)
        with self.assertRaisesRegex(batch.BatchError, r"report has 2 units, expected 3"):
            self._run_all()

    def test_short_nominal_report_raises(self):
        short = copy.deepcopy(self.nominal)
        short["corners"].pop()
        self._stub(nominal=short)
        with self.assertRaisesRegex(batch.BatchError, r"nominal: report has 4 units, expected 5"):
            self._run_all()

    def test_short_negative_control_report_raises(self):
        self._stub(neg={"corners": []})
        with self.assertRaisesRegex(
            batch.BatchError, r"negative control: report has 0 units, expected 1"
        ):
            self._run_all()


if __name__ == "__main__":
    unittest.main()
