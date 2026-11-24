"""Whole-grid ``klt sim`` envelope request tests -- no PDK, no ngspice, no fleet.

    python3 -m unittest sim.tests.test_klt_envelope -v

Pins ``harness.klt_envelope`` and ``sim/run_envelope.py`` (issue #229): how a
bench manifest's ``measure``/``checks`` become ``klt sim`` measurements with
limits and ``spec_row`` tags, the corners axis, the per-rate transient
window, and what ``grid_problems`` accepts as a passing whole-grid report
(synthetic reports shaped like ``klt sim``'s). The last class turns the
committed evidence into a contract: every envelope ``signoff/manifest.json``
cites for item 5 (analog) must regenerate byte for byte from its bench and
must still pass ``grid_problems``, so a bench edit or a failing report
breaks the build until a fresh envelope is minted and cited.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
SIM_DIR = REPO / "sim"
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness import klt_envelope as klt  # noqa: E402
from harness.corners import CORNERS  # noqa: E402
from harness.testbench import load as load_tb  # noqa: E402

BENCHES = (
    "cml-driver-eye",
    "cml-driver-eye-mask",
    "cml-driver-eye-realmux",
    "tmds-final-mux-eye",
)


def _load_run_envelope():
    path = SIM_DIR / "run_envelope.py"
    spec = importlib.util.spec_from_file_location("run_envelope_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_envelope = _load_run_envelope()


def _value(name: str, point, tb) -> float:
    """A synthetic in-limit value for ``name`` at ``point``: the UI tracks
    the rate (so ``ui_ref``'s spread check holds), everything else sits at
    the midpoint of its limits (or safely inside a one-sided bound)."""
    if name == "ui_ref" and point.rate_mbps:
        return 1e-6 / point.rate_mbps
    limits = klt.limits_of(tb.checks.get(name) or {}) or {}
    low, high = limits.get("min"), limits.get("max")
    if low is not None and high is not None:
        return (low + high) / 2
    if low is not None:
        return low * 1.01
    if high is not None:
        return high * 0.99
    return 1.0


def _synthetic_report(tb, rate=None, *, slice_rate=False, status="pass", value_of=_value):
    """A report shaped like ``klt sim``'s for ``tb``'s grid (or rate slice),
    every measurement passing."""
    corners = []
    for point in klt.grid_points(tb, rate, slice_rate=slice_rate):
        params = {"vdd_val": point.vdd, "temp_c": point.temp_c}
        if point.rate_mbps is not None:
            params["rate_val"] = point.rate_mbps
        corners.append(
            {
                "corner_id": f"{point.corner.name}/{point.corner_id}",
                "process": point.corner.name,
                "temperature_c": point.temp_c,
                "params": params,
                "status": "pass",
                "runtime_s": 0.5,
                "measurements": [
                    {"name": name, "value": value_of(name, point, tb), "status": "pass"}
                    for name in tb.measure
                ],
            }
        )
    return {
        "schema_version": 2,
        "status": status,
        "corner_count": len(corners),
        "passed": len(corners),
        "failed": 0,
        "errored": 0,
        "corners": corners,
        "measurements": [
            {"name": name, "status": "pass", "limits": klt.limits_of(tb.checks.get(name) or {})}
            for name in tb.measure
        ],
    }


_TB_BY_NAME = {slug: load_tb(SIM_DIR / slug) for slug in BENCHES}


class TagAndLimitTests(unittest.TestCase):
    def test_limits_of_keeps_only_per_corner_bounds(self):
        self.assertEqual(klt.limits_of({"min": 0.4, "max": 0.6}), {"min": 0.4, "max": 0.6})
        self.assertEqual(klt.limits_of({"max": 0.15, "description": "x"}), {"max": 0.15})
        self.assertEqual(klt.limits_of({"min_spread_pct": 50.0}), None)
        self.assertEqual(klt.limits_of({}), None)

    def test_every_check_gets_its_limits_and_every_map_check_its_row(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        entries = klt.tag_measurements(klt.translate_measurements(tb), tb, run_envelope.spec_row_tags(tb))
        by_name = {e["name"]: e for e in entries}
        self.assertEqual(sorted(e["name"] for e in entries), sorted(tb.measure))
        for name, check in tb.checks.items():
            self.assertEqual(by_name[name].get("limits"), klt.limits_of(check), name)
        self.assertEqual(by_name["swing_c2"]["spec_row"], "1")
        self.assertEqual(by_name["vcm_c0"]["spec_row"], "2")
        self.assertEqual(by_name["dj_ui_cmis"]["spec_row"], "4")
        self.assertEqual(by_name["trise_ui_c2"]["spec_row"], "5")
        self.assertEqual(by_name["vds_tail_max"]["spec_row"], "8")
        self.assertEqual(by_name["itail_dc"]["spec_row"], "9")
        # ui_ref's only check is grid-level: reported, never graded, untagged
        self.assertNotIn("limits", by_name["ui_ref"])
        self.assertNotIn("spec_row", by_name["ui_ref"])
        for name in ("vpp_c0", "ro_leg", "swing_avcclo"):
            self.assertNotIn("limits", by_name[name])

    def test_spec_row_tags_are_per_bench(self):
        mask = run_envelope.spec_row_tags(_TB_BY_NAME["cml-driver-eye-mask"])
        self.assertEqual(mask, {"eyemask_margin_c0": "6", "eyemask_margin_c1": "6", "eyemask_margin_c2": "6"})
        mux = run_envelope.spec_row_tags(_TB_BY_NAME["tmds-final-mux-eye"])
        self.assertEqual(sorted(mux), ["vds_mt_max", "vds_mu_max", "vgs_mu_max"])
        self.assertEqual(set(mux.values()), {"8"})
        for slug, tags in ((s, run_envelope.spec_row_tags(t)) for s, t in _TB_BY_NAME.items()):
            unknown = sorted(set(tags) - set(t for t in _TB_BY_NAME[slug].measure))
            self.assertEqual(unknown, [], slug)

    def test_tag_on_unchecked_or_unknown_measurement_refused(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        entries = klt.translate_measurements(tb)
        with self.assertRaises(klt.EnvelopeError):
            klt.tag_measurements(entries, tb, {"vpp_c0": "1"})  # no limits: grades nothing
        with self.assertRaises(klt.EnvelopeError):
            klt.tag_measurements(entries, tb, {"no_such_measure": "1"})


class TranslationFormTests(unittest.TestCase):
    """The shared translator's three forms on a real bench (the pex
    generator's own tests pin the semantics on synthetic benches)."""

    def test_eye_bench_forms(self):
        entries = klt.translate_measurements(_TB_BY_NAME["cml-driver-eye"])
        cards = [e for e in entries if "spice" in e and " PARAM='" not in e["spice"]]
        params = [e for e in entries if "spice" in e and " PARAM='" in e["spice"]]
        exprs = [e for e in entries if "expr" in e]
        self.assertEqual(len(entries), len(_TB_BY_NAME["cml-driver-eye"].measure))
        self.assertEqual(len(cards), 17)
        self.assertEqual(len(params), 10)
        self.assertEqual(len(exprs), 25)
        self.assertEqual(entries[0], {"name": "ui_ref", "spice": ".meas tran ui_ref TRIG v(inref) VAL=0 FALL=1 TARG v(inref) VAL=0 RISE=1"})
        self.assertIn(".meas tran trise_ui_c0 PARAM='trise_c0/ui_ref'", [e["spice"] for e in params])
        self.assertTrue(all("m_" not in e["expr"] for e in exprs))

    def test_node_rewrites_are_opt_in(self):
        tb = SimpleNamespace(name="b", measure={"ui_ref": "TRIG v(in) VAL=0 FALL=1 TARG v(in) VAL=0 RISE=1", "m": "m_ui_ref*v(x.tail)"})
        self.assertEqual(klt.translate_measurements(tb)[1]["spice"], ".meas tran m PARAM='ui_ref*v(x.tail)'")
        self.assertEqual(
            klt.translate_measurements(tb, node_rewrites=(("x.tail", "x.y.tail"),))[1]["spice"],
            ".meas tran m PARAM='ui_ref*v(x.y.tail)'",
        )

    def test_mixed_dependency_refused(self):
        tb = SimpleNamespace(name="b", measure={"ui_ref": "TRIG v(in) VAL=0 FALL=1 TARG v(in) VAL=0 RISE=1", "h": "vecmin(v(o))", "bad": "m_ui_ref*m_h"})
        with self.assertRaises(klt.EnvelopeError) as ctx:
            klt.translate_measurements(tb)
        self.assertIn("bad", str(ctx.exception))


class RequestTests(unittest.TestCase):
    def test_eye_request_covers_the_whole_grid_in_one_request(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        request = klt.build_request(tb, "b.spice", spec_rows=run_envelope.spec_row_tags(tb))
        self.assertEqual(request["corners"]["process"], [{"name": c.name, "sections": list(c.sections)} for c in (CORNERS[n] for n in ("tt", "ff", "ss", "fs", "sf"))])
        self.assertEqual(request["corners"]["temperature_c"], [-40.0, 27.0, 125.0])
        # supply outer, rate inner: the harness's own grid order
        self.assertEqual(request["corners"]["params"], {"vdd_val": [2.97, 2.97, 3.3, 3.3, 3.63, 3.63], "rate_val": [742.5, 270.0, 742.5, 270.0, 742.5, 270.0]})
        self.assertEqual(request["corners"]["temperature_param"], "temp_c")
        self.assertEqual(request["analysis"], {"kind": "tran", "args": "10e-12 61e-9 0 20e-12"})
        self.assertEqual(request["models"], {"pdk": "gf180mcuD", "lib": klt.MODELS_LIB, "param_file": klt.MODELS_PARAM_FILE})
        self.assertEqual(request["options"], {"timeout_s": klt.TIMEOUT_S, "keep_artifacts": False, "ngspice_init": list(klt.NGSPICE_INIT)})
        self.assertEqual(request["batch"], {"capacity_wait_s": 600, "job_ceiling_check": "split"})
        self.assertEqual(request["netlist_source"], "schematic")
        self.assertEqual(len(klt.grid_points(tb)), 90)
        with self.assertRaises(klt.EnvelopeError):
            klt.build_request(tb, "b.spice", rate=742.5, slice_rate=True)

    def test_init_lines_are_complete_and_pin_single_thread(self):
        self.assertIn("set wnflag=1", klt.NGSPICE_INIT)
        self.assertIn("set num_threads=1", klt.NGSPICE_INIT)

    def test_mask_bench_is_per_rate_with_the_declared_window_override(self):
        tb = _TB_BY_NAME["cml-driver-eye-mask"]
        with self.assertRaises(klt.EnvelopeError):
            klt.build_request(tb, "b.spice")
        fast = klt.build_request(tb, "b.spice", rate=742.5, slice_rate=True)
        slow = klt.build_request(tb, "b.spice", rate=270.0, slice_rate=True)
        self.assertEqual(fast["analysis"], {"kind": "tran", "args": "20e-12 300e-9 0 40e-12"})
        self.assertEqual(slow["analysis"], {"kind": "tran", "args": "20e-12 560e-9 0 40e-12"})
        for request in (fast, slow):
            self.assertEqual(request["corners"]["params"]["vdd_val"], [2.97, 3.3, 3.63])
        self.assertEqual(len(set(fast["corners"]["params"]["rate_val"])), 1)
        self.assertEqual(len(klt.grid_points(tb, 742.5, slice_rate=True)), 45)
        with self.assertRaises(klt.EnvelopeError):
            klt.grid_points(tb, 600.0, slice_rate=True)
        # the window still covers every driven bit (150 UI) and stops
        # before the non-convergence event (300 UI)
        tstop_ui = float(fast["analysis"]["args"].split()[1]) * 742.5e6
        self.assertGreater(tstop_ui, 150)
        self.assertLess(tstop_ui, 300)

    def test_swept_parameter_names_may_not_collide_with_manifest_params(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        tb.params["rate_val"] = 742.5
        try:
            with self.assertRaises(klt.EnvelopeError):
                klt.corners_block(tb)
        finally:
            del tb.params["rate_val"]


class BodyTests(unittest.TestCase):
    def test_body_is_host_independent_and_resolves_its_includes(self):
        for slug in BENCHES:
            tb = _TB_BY_NAME[slug]
            directory = (SIM_DIR / slug / "envelopes").resolve()
            body = klt.compose_body(tb, directory, 742.5, slice_rate=True) if slug in klt.TRANSIENT_WINDOWS else klt.compose_body(tb, directory)
            self.assertNotIn("/home/", body, slug)
            self.assertNotIn(str(REPO), body, slug)
            self.assertNotIn(".lib", body, slug)
            self.assertNotIn(".control", body, slug)
            self.assertIn(f"sha256 {tb.dut_sha256}", body)
            self.assertIn(f"sha256 {tb.netlist_sha256}", body)
            self.assertIn(".options noinit", body)
            includes = [line.split('"')[1] for line in body.splitlines() if line.startswith(".include")]
            self.assertEqual(len(includes), 2, slug)
            for include in includes:
                self.assertTrue((directory / include).is_file(), (slug, include))
                self.assertFalse(include.startswith("/"), include)

    def test_slice_body_names_the_rate_and_the_window(self):
        body = klt.compose_body(_TB_BY_NAME["cml-driver-eye-mask"], (SIM_DIR / "cml-driver-eye-mask" / "envelopes").resolve(), 742.5, slice_rate=True)
        self.assertIn("45 corners at 742.5 Mbps/lane (one rate slice)", body)
        self.assertIn(".param rate_val=742.5", body)
        self.assertIn("TRANSIENT_WINDOWS override", body)
        slow = klt.compose_body(_TB_BY_NAME["cml-driver-eye-mask"], (SIM_DIR / "cml-driver-eye-mask" / "envelopes").resolve(), 270.0, slice_rate=True)
        self.assertIn(".param rate_val=270.0", slow)
        self.assertNotIn("TRANSIENT_WINDOWS override", slow)


class GridProblemTests(unittest.TestCase):
    def test_passing_report_has_no_problems(self):
        for slug in BENCHES:
            tb = _TB_BY_NAME[slug]
            if slug in klt.TRANSIENT_WINDOWS:
                reports = [(r, _synthetic_report(tb, r, slice_rate=True)) for r in tb.rates_mbps]
            else:
                reports = [(None, _synthetic_report(tb))]
            self.assertEqual(klt.grid_problems(reports, tb), [], slug)

    def test_non_passing_status_is_a_problem(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        report = _synthetic_report(tb, status="fail")
        report["corners"][3]["status"] = "fail"
        problems = klt.grid_problems([(None, report)], tb)
        self.assertTrue(any(p.startswith("klt sim status 'fail'") for p in problems))
        self.assertTrue(any("tt_-40c_3.30v_270mbps" in p for p in problems), problems)

    def test_missing_and_unexpected_points_are_problems(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        report = _synthetic_report(tb)
        gone = report["corners"].pop()
        problems = klt.grid_problems([(None, report)], tb)
        self.assertTrue(any(p == f"point {gone['corner_id'].split('/', 1)[1]}: 0 report entries, expected exactly 1" for p in problems), problems)
        report["corners"].append(dict(gone, corner_id="x/zz_27c_3.30v_742p5mbps", process="zz"))
        problems = klt.grid_problems([(None, report)], tb)
        self.assertTrue(any("does not map onto the bench grid" in p for p in problems), problems)

    def test_flat_rate_axis_fails_the_spread_check_klt_sim_cannot_grade(self):
        tb = _TB_BY_NAME["cml-driver-eye"]
        report = _synthetic_report(
            tb, value_of=lambda name, point, tb: 1e-6 / 742.5e6 if name == "ui_ref" else _value(name, point, tb)
        )
        problems = klt.grid_problems([(None, report)], tb)
        self.assertEqual(problems, ["check ui_ref min_spread_pct: observed 0.0 at grid (limit 50.0)"])

    def test_rate_slices_must_cover_each_declared_rate_once(self):
        tb = _TB_BY_NAME["cml-driver-eye-mask"]
        fast = (742.5, _synthetic_report(tb, 742.5, slice_rate=True))
        slow = (270.0, _synthetic_report(tb, 270.0, slice_rate=True))
        for reports, problem in (
            ([fast], "rate 270.0: 0 reports"),
            ([fast, slow, fast], "rate 742.5: 2 reports"),
            ([fast, (270.0, fast[1])], "unexpected point"),
        ):
            with self.subTest(problem=problem):
                self.assertTrue(any(problem in p for p in klt.grid_problems(reports, tb)))

    def test_flat_ui_across_passing_slices_fails(self):
        tb = _TB_BY_NAME["cml-driver-eye-mask"]

        def flat_ui(name, point, tb):
            return 1.3468e-9 if name == "ui_ref" else _value(name, point, tb)

        reports = [(r, _synthetic_report(tb, r, slice_rate=True, value_of=flat_ui)) for r in tb.rates_mbps]
        self.assertEqual(klt.grid_problems(reports, tb),
                         ["check ui_ref min_spread_pct: observed 0.0 at grid (limit 50.0)"])

    def test_harness_bounds_are_reapplied_to_reported_values(self):
        tb = _TB_BY_NAME["cml-driver-eye"]

        def near(name, point, tb):
            return 0.39 if name == "swing_c0" else _value(name, point, tb)

        report = _synthetic_report(tb, value_of=near)
        for corner in report["corners"]:
            for m in corner["measurements"]:
                if m["name"] == "swing_c0":
                    m["status"] = "pass"  # klt sim's own verdict is not what is under test
        problems = klt.grid_problems([(None, report)], tb)
        self.assertEqual(len(problems), 90)
        self.assertTrue(all(p.startswith("check swing_c0 min: observed 0.39") for p in problems))


class CitedEnvelopeTests(unittest.TestCase):
    """The committed contract: every item-5 (analog) citation in
    ``signoff/manifest.json`` regenerates byte for byte from its bench and
    passes ``grid_problems``."""

    def setUp(self):
        manifest = json.loads((REPO / "signoff" / "manifest.json").read_text())
        self.manifest = manifest
        self.citations = (manifest.get("evidence") or {}).get("5.analog")
        self.rows = (manifest.get("spec_rows") or {}).get("5.analog")
        if not isinstance(self.citations, list):
            self.fail("manifest cites no item-5 (analog) envelopes")
        if not isinstance(self.rows, list):
            self.fail("manifest declares no spec_rows.\"5.analog\" row set")

    def test_manifest_declares_item5_analog(self):
        self.assertTrue(self.citations)
        self.assertEqual(sorted((r["id"] for r in self.rows), key=int), [str(i) for i in range(1, 12)])

    def _cited(self):
        for citation in self.citations:
            path = citation["file"]
            parts = Path(path).parts
            self.assertEqual(parts[0], "sim", path)
            self.assertEqual(parts[2], "envelopes", path)
            yield parts[1], Path(path).stem, citation

    def test_cited_envelopes_regenerate_byte_for_byte(self):
        for slug, record_id, _citation in self._cited():
            tb = load_tb(SIM_DIR / slug)
            directory = SIM_DIR / slug / "envelopes"
            rate, slice_rate = run_envelope._slice_of(tb, record_id)
            committed_body = (directory / f"{record_id}.body.spice").read_text()
            self.assertEqual(
                klt.compose_body(tb, directory.resolve(), rate, slice_rate=slice_rate),
                committed_body,
                f"{slug}/{record_id}.body.spice is stale against its bench",
            )
            request = json.dumps(
                klt.build_request(tb, f"{record_id}.body.spice", spec_rows=run_envelope.spec_row_tags(tb), rate=rate, slice_rate=slice_rate),
                indent=2,
            ) + "\n"
            self.assertEqual(
                request,
                (directory / f"{record_id}.request.json").read_text(),
                f"{slug}/{record_id}.request.json is stale against its bench",
            )

    def test_cited_reports_cover_the_bench_and_pass_its_grid_checks(self):
        slugs = {slug for slug, _, _ in self._cited()} | set(klt.TRANSIENT_WINDOWS)
        for slug in sorted(slugs):
            tb = load_tb(SIM_DIR / slug)
            reports = []
            for record_id in run_envelope.cited_record_ids(self.manifest, slug):
                rate, _ = run_envelope._slice_of(tb, record_id)
                path = SIM_DIR / slug / "envelopes" / f"{record_id}.json"
                reports.append((rate, json.loads(path.read_text())))
            self.assertEqual(klt.grid_problems(reports, tb), [], slug)

    def test_cited_envelopes_pin_their_body(self):
        import hashlib

        for slug, record_id, citation in self._cited():
            report = json.loads((SIM_DIR / slug / "envelopes" / f"{record_id}.json").read_text())
            self.assertEqual(report["netlist"], {"path": f"sim/{slug}/envelopes/{record_id}.body.spice", "scope": "repo"})
            body_hash = "sha256:" + hashlib.sha256((SIM_DIR / slug / "envelopes" / f"{record_id}.body.spice").read_bytes()).hexdigest()
            self.assertEqual(report["provenance"]["input"]["content_hash"], body_hash, f"{slug}/{record_id}")
            self.assertEqual(citation["content_hash"], body_hash, f"{slug}/{record_id}: manifest pin")

    def test_citation_rows_match_the_envelopes_tags(self):
        for slug, record_id, citation in self._cited():
            report = json.loads((SIM_DIR / slug / "envelopes" / f"{record_id}.json").read_text())
            tagged = sorted({m["spec_row"] for m in report["measurements"] if m.get("spec_row") and m.get("limits")})
            self.assertEqual(sorted(citation["rows"]), tagged, f"{slug}/{record_id}")


if __name__ == "__main__":
    unittest.main()
