"""``klt yield`` campaign driver tests -- no PDK, no ngspice, no fleet.

    python3 -m unittest sim.tests.test_run_yield -v

Pins ``sim/cml-driver-mismatch/run_yield.py`` (issue #229): the campaign's
seeds (the nominal draw numbered exactly as ``run_mc.py`` numbers its
samples, the control drawn from an independent offset), the requests'
shape, and what ``report_problems`` accepts as a report that would grade
``met`` for T1 item 6 (synthetic reports shaped like ``klt yield``'s). The
last class turns the committed evidence into a contract: every ``klt
yield`` report ``signoff/manifest.json`` cites for item 6 (analog) must
still pass ``report_problems``, must pin the samples document the manifest
hashes, and that document's two source campaigns must be the committed
Monte Carlo reports.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIM_DIR = REPO / "sim"
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness.corners import CORNER_SETS, CORNERS  # noqa: E402

YIELD_DIR = SIM_DIR / "cml-driver-mismatch" / "yield"


def _load_run_yield():
    path = SIM_DIR / "cml-driver-mismatch" / "run_yield.py"
    spec = importlib.util.spec_from_file_location("run_yield_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_yield = _load_run_yield()


class _Pdk:
    variant = "gf180mcuD"
    path = Path("/pdk/gf180mcuD")
    model_lib = "/pdk/gf180mcuD/libs.tech/ngspice/sm141064.ngspice"


def _yield_report(**overrides) -> dict:
    """A ``klt yield`` report for three measurements that would grade met."""
    names = [m["name"] for m in run_yield.MEASUREMENTS]
    measurements = []
    for name in names:
        measurement = {
            "name": name,
            "n": 200,
            "errored": 0,
            "inconclusive": 0,
            "limits": {"min": 0.0, "max": 1.0},
            "distribution": {"mean": 0.5, "stddev": 0.001, "min": 0.49, "max": 0.51},
            "sample_size": {"verdict": "sufficient", "required_n": 183},
            "negative_control": {"verdict": "detected"},
        }
        measurement.update(overrides.get(name, {}))
        measurements.append(measurement)
    return {"status": "reported", "measurements": measurements}


class RunMcParityTests(unittest.TestCase):
    """The campaign re-expresses ``run_mc.py``'s deck; its constants must
    not drift from the record-producing driver's."""

    def test_deck_constants_match_run_mc(self):
        path = SIM_DIR / "cml-driver-mismatch" / "run_mc.py"
        spec = importlib.util.spec_from_file_location("run_mc_for_run_yield", path)
        run_mc = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = run_mc
        spec.loader.exec_module(run_mc)
        self.assertEqual(run_yield.TEMP_C, run_mc.TEMP_C)
        self.assertEqual(run_yield.VDD_V, run_mc.VDD_V)
        self.assertEqual((run_yield.PAR_PAIR, run_yield.PAR_TAIL, run_yield.PAR_MIRROR), (run_mc.PAR_PAIR_NOMINAL, run_mc.PAR_TAIL_NOMINAL, run_mc.PAR_MIRROR_NOMINAL))
        self.assertEqual(run_yield.NEG_CTRL_PAR_TAIL, run_mc.NEG_CTRL_PAR_TAIL)
        self.assertEqual(run_yield.NGSPICE_INIT, run_mc.NGSPICE_INIT)
        self.assertEqual(run_yield.PROCESS_CORNERS, [CORNERS[name] for name in CORNER_SETS["mos"]])
        self.assertEqual(run_yield.MEASUREMENTS[0]["expr"], run_mc.MEASUREMENTS[0]["expr"])
        self.assertEqual(run_yield.MEASUREMENTS[1]["expr"], run_mc.MEASUREMENTS[1]["expr"])
        # run_mc.py numbers corner k's first sample base_seed + k*1000 + 1
        # (its default base seed is 20260814, the seed its records cite)
        self.assertEqual(run_yield._seed(2, False), 20260814 + 2 * 1000 + 1)


class SeedTests(unittest.TestCase):
    def test_nominal_seeds_are_run_mc_sample_numbers(self):
        # run_mc.py: sample i (1..N) of corner k runs base + k*1000 + i
        self.assertEqual(run_yield.BASE_SEED, 20260814)
        self.assertEqual([run_yield._seed(k, control=False) for k in range(5)], [20260815, 20261815, 20262815, 20263815, 20264815])

    def test_control_seeds_are_independent_of_the_nominal_draw(self):
        for k in range(5):
            nominal = range(run_yield._seed(k, False), run_yield._seed(k, False) + 10_000)
            control = range(run_yield._seed(k, True), run_yield._seed(k, True) + 10_000)
            self.assertFalse(set(nominal) & set(control))
        self.assertEqual(run_yield._seed(0, True), 20260814 + run_yield.CONTROL_SEED_OFFSET + 1)


class CampaignFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = (YIELD_DIR / "20990101-000000-abcdef0").resolve()
        self.files = run_yield.campaign_files(self.directory, 200, _Pdk())

    def test_file_set(self):
        self.assertEqual(
            sorted(self.files),
            sorted(
                ["mc.body.spice", "negctl.body.spice", "nominal.body.spice", "nominal.request.json"]
                + [f"{kind}_{c}.request.json" for kind in ("mc", "negctl") for c in ("tt", "ff", "ss", "fs", "sf")]
            ),
        )

    def test_requests(self):
        mc = json.loads(self.files["mc_ss.request.json"])
        self.assertEqual(mc["netlist"], "mc.body.spice")
        self.assertEqual(mc["analysis"], {"kind": "op", "args": ""})
        self.assertEqual([p["name"] for p in mc["corners"]["process"]], ["ss"])
        self.assertEqual(mc["corners"]["temperature_c"], [27.0])
        self.assertEqual(
            mc["monte_carlo"],
            {"n": 200, "seed": 20262815, "vary": "mismatch", "seed_mode": "sequential", "seed_scope": "point"},
        )
        self.assertEqual(
            mc["measurements"],
            [
                {"name": "swing_dc", "expr": "v(outn)-v(outp)", "spec_row": "1", "limits": {"min": 0.4, "max": 0.6}},
                {"name": "vcm_dc", "expr": "(v(outn)+v(outp))/2", "spec_row": "2", "limits": {"min": 2.8, "max": 3.3}},
                {"name": "itail_dc", "expr": "i(vsens)", "spec_row": "9", "limits": {"min": 8e-3, "max": 12e-3}},
            ],
        )
        self.assertEqual(mc["models"], {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice", "param_file": "libs.tech/ngspice/design.ngspice"})
        self.assertEqual(mc["options"], {"timeout_s": run_yield.TIMEOUT_S, "keep_artifacts": False, "ngspice_init": list(run_yield.NGSPICE_INIT)})
        self.assertEqual(mc["batch"], {"capacity_wait_s": 600, "job_ceiling_check": "split"})
        self.assertEqual(mc["netlist_source"], "schematic")
        # one job: n samples at the per-unit timeout stay inside the 3600 s ceiling
        self.assertLess(run_yield.TIMEOUT_S * 200 + 120, 3600)

        control = json.loads(self.files["negctl_ss.request.json"])
        self.assertEqual(control["monte_carlo"]["seed"], 20262815 + run_yield.CONTROL_SEED_OFFSET)
        self.assertEqual(control["netlist"], "negctl.body.spice")

        nominal = json.loads(self.files["nominal.request.json"])
        self.assertNotIn("monte_carlo", nominal)
        self.assertEqual(len(nominal["corners"]["process"]), 5)
        self.assertEqual(nominal["netlist"], "nominal.body.spice")

    def test_bodies_differ_only_where_the_campaign_says_so(self):
        mc, control, nominal = (self.files[f"{n}.body.spice"] for n in ("mc", "negctl", "nominal"))

        def sans(body, *prefixes):
            return [line for line in body.splitlines() if not line.startswith(prefixes)]

        self.assertIn(f".param par_tail_val={run_yield.PAR_TAIL}\n", mc)
        self.assertIn(f".param par_tail_val={run_yield.NEG_CTRL_PAR_TAIL}\n", control)
        self.assertIn(".param sw_stat_mismatch=1\n", mc)
        self.assertIn(".param sw_stat_mismatch=0\n", nominal)
        self.assertEqual(
            sans(mc, ".param par_tail_val", "* sw_stat_mismatch"),
            sans(control, ".param par_tail_val", "* sw_stat_mismatch"),
        )
        self.assertEqual(
            sans(mc, ".param sw_stat_mismatch", "* sw_stat_mismatch"),
            sans(nominal, ".param sw_stat_mismatch", "* sw_stat_mismatch"),
        )
        for body in (mc, control, nominal):
            self.assertNotIn("/home/", body)
            self.assertNotIn(str(REPO), body)
            includes = [line.split('"')[1] for line in body.splitlines() if line.startswith(".include")]
            self.assertEqual(len(includes), 2)
            for include in includes:
                self.assertTrue(Path(os.path.normpath(self.directory / include)).is_file(), include)
                self.assertFalse(include.startswith("/"), include)


class ReportProblemTests(unittest.TestCase):
    def test_a_sized_detected_in_limit_report_has_no_problems(self):
        self.assertEqual(run_yield.report_problems(_yield_report(), 200), [])

    def test_undersized_sample_is_a_problem(self):
        report = _yield_report(vcm_dc={"sample_size": {"verdict": "insufficient", "required_n": 400}})
        self.assertEqual(run_yield.report_problems(report, 200), ["vcm_dc: sample_size.verdict 'insufficient'"])

    def test_undetected_control_is_a_problem(self):
        report = _yield_report(itail_dc={"negative_control": {"verdict": "not_detected"}})
        self.assertEqual(run_yield.report_problems(report, 200), ["itail_dc: negative_control.verdict 'not_detected'"])

    def test_missing_control_is_a_problem(self):
        report = _yield_report(swing_dc={"negative_control": None})
        self.assertEqual(run_yield.report_problems(report, 200), ["swing_dc: negative_control.verdict None"])

    def test_errored_or_short_draw_is_a_problem(self):
        report = _yield_report(vcm_dc={"errored": 3, "inconclusive": 1, "n": 196})
        self.assertEqual(
            run_yield.report_problems(report, 200),
            ["vcm_dc: 196 usable samples, expected 200", "vcm_dc: 3 errored, 1 inconclusive draws"],
        )

    def test_observed_span_outside_the_row_limits_is_a_problem(self):
        report = _yield_report(
            swing_dc={"distribution": {"min": -0.39, "max": 1.61, "mean": 0.5, "stddev": 0.01}}
        )
        self.assertEqual(
            run_yield.report_problems(report, 200),
            ["swing_dc: min -0.39 below limit 0.0", "swing_dc: max 1.61 above limit 1.0"],
        )

    def test_failing_status_is_a_problem(self):
        report = _yield_report()
        report["status"] = "fail"
        self.assertEqual(run_yield.report_problems(report, 200), ["klt yield status 'fail'"])


class CitedYieldReportTests(unittest.TestCase):
    """The committed contract for every item-6 (analog) citation."""

    def setUp(self):
        manifest = json.loads((REPO / "signoff" / "manifest.json").read_text())
        self.citations = (manifest.get("evidence") or {}).get("6.analog")
        self.rows = (manifest.get("spec_rows") or {}).get("6.analog")
        if not isinstance(self.citations, list):
            self.fail("manifest cites no item-6 (analog) klt yield reports")
        if not isinstance(self.rows, list):
            self.fail('manifest declares no spec_rows."6.analog" row set')

    def _cited(self):
        for citation in self.citations:
            path = Path(citation["file"])
            self.assertEqual(path.parts[0], "sim", citation["file"])
            yield citation, REPO / path

    def test_one_report_per_process_corner(self):
        self.assertEqual(
            sorted(Path(c["file"]).name for c, _ in self._cited()),
            sorted(f"yield_{c}.json" for c in ("tt", "ff", "ss", "fs", "sf")),
        )
        for citation, _path in self._cited():
            self.assertEqual(citation["rows"], [r["id"] for r in self.rows])

    def test_cited_reports_would_grade_and_pin_their_samples(self):
        for citation, path in self._cited():
            report = json.loads(path.read_text())
            request = path.parent / path.name.replace("yield_", "mc_").replace(".json", ".request.json")
            n = json.loads(request.read_text())["monte_carlo"]["n"]
            self.assertEqual(run_yield.report_problems(report, n), [], citation["file"])
            self.assertEqual(report["status"], "reported", citation["file"])
            samples = REPO / report["samples"]
            self.assertTrue(samples.is_file(), report["samples"])
            self.assertEqual(
                citation["content_hash"], "sha256:" + hashlib.sha256(samples.read_bytes()).hexdigest(), citation["file"]
            )

    def test_samples_come_from_the_committed_campaigns(self):
        for citation, path in self._cited():
            report = json.loads(path.read_text())
            derived = json.loads((REPO / report["samples"]).read_text())
            for role in ("nominal", "negative_control"):
                source = REPO / derived["derivation"][role]["path"]
                self.assertTrue(source.is_file(), derived["derivation"][role]["path"])
                self.assertEqual(
                    derived["derivation"][role]["content_hash"],
                    "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
                )
            for measurement in derived["measurements"]:
                self.assertEqual(measurement["negative_control"]["description"], run_yield.CONTROL_DESCRIPTION)

    def test_cited_campaign_regenerates_byte_for_byte(self):
        for citation, path in self._cited():
            directory = path.parent
            request = json.loads((directory / path.name.replace("yield_", "mc_").replace(".json", ".request.json")).read_text())
            files = run_yield.campaign_files(directory.resolve(), request["monte_carlo"]["n"], _Pdk())
            committed = sorted(p.name for p in directory.iterdir() if p.name.endswith((".request.json", ".body.spice")))
            self.assertEqual(sorted(files), committed, str(directory))
            for name, text in files.items():
                self.assertEqual((directory / name).read_text(), text, f"{directory.name}/{name} is stale")

    def test_monte_carlo_reports_ran_the_committed_bodies(self):
        for citation, path in self._cited():
            directory = path.parent
            for stem, body in (("mc", "mc"), ("negctl", "negctl"), ("nominal", "nominal")):
                report_path = directory / (f"{stem}.json" if stem == "nominal" else f"{stem}_{path.name.split('_', 1)[1]}")
                report = json.loads(report_path.read_text())
                self.assertEqual(report["netlist"], {"path": str((directory / f"{body}.body.spice").relative_to(REPO)), "scope": "repo"}, str(report_path))
                self.assertEqual(
                    report["provenance"]["input"]["content_hash"],
                    "sha256:" + hashlib.sha256((directory / f"{body}.body.spice").read_bytes()).hexdigest(),
                    str(report_path),
                )
                self.assertEqual(report["environment"]["engine_host"], "worker", str(report_path))
                for measurement in report["measurements"]:
                    self.assertIn(measurement["name"], [m["name"] for m in run_yield.MEASUREMENTS])


if __name__ == "__main__":
    unittest.main()
