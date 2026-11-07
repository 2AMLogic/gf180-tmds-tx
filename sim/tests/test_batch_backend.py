"""Batch backend tests -- a stubbed ``klt`` returns canned reports.

    python3 -m unittest sim.tests.test_batch_backend -v

No PDK, ngspice, AWS or network is used. The stub is a tiny Python script
standing in for ``klt``; it reads the request ``klt sim`` is given and answers
with a canned ``klt sim`` JSON envelope (or a failure) per point.
"""

from __future__ import annotations

import contextlib
import io
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness import batch as batch_mod  # noqa: E402
from harness import cli as cli_mod  # noqa: E402
from harness import corners as corners_mod  # noqa: E402
from harness import report as report_mod  # noqa: E402
from harness import testbench as tb_mod  # noqa: E402
from harness.pdk import Pdk  # noqa: E402

STUB = '''#!{python}
import json, sys
argv = sys.argv[1:]
assert argv[0] == "sim" and "--backend" in argv and argv[argv.index("--backend") + 1] == "batch"
assert "--wait-for-capacity" in argv and argv[argv.index("--wait-for-capacity") + 1] == "600"
req_path = argv[1]
cid = req_path.rsplit("/", 1)[-1][: -len(".request.json")]
mode = json.load(open({modes!r})).get(cid, "ok")
if mode == "nojson":
    sys.stderr.write("batch_no_capacity: fleet is full\\n"); sys.exit(4)
names = [m["name"] for m in json.load(open(req_path))["measurements"]]
def corner(status="pass", drop=()):
    return {{"corner_id": cid, "status": status, "runtime_s": 1.5, "diagnostics": [],
            "measurements": [{{"name": n, "value": 1.0e-13, "status": "pass"}} for n in names if n not in drop]}}
corners = [corner()]
if mode == "missing": corners = []
if mode == "duplicate": corners = [corner(), corner()]
if mode == "failed": corners = [corner("error", drop=names[:1])]
env = {{"engine_version": "46", "remote": {{"job_id": "job-" + cid}}}}
print(json.dumps({{"status": "pass", "corners": corners, "environment": env}}))
'''


def _point(corner="tt", temp=27.0, vdd=3.3):
    return corners_mod.PvtPoint(corner=corners_mod.CORNERS[corner], temp_c=temp, vdd=vdd)


class _Pdk:
    variant = "gf180mcuD"
    version = "test"
    path = Path("/pdk/gf180mcuD")
    model_lib = "/pdk/gf180mcuD/libs.tech/ngspice/sm141064.ngspice"
    design_include = "/pdk/gf180mcuD/libs.tech/ngspice/design.ngspice"


class BatchBackendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.tb = tb_mod.load(SIM_DIR / "esd-clamp-cv")
        self.points = [_point(temp=t) for t in (-40.0, 27.0, 125.0)]
        self.modes = self.tmp / "modes.json"
        self.set_modes({})
        self.klt = self.tmp / "klt-stub"
        self.klt.write_text(STUB.format(python=sys.executable, modes=str(self.modes)))
        self.klt.chmod(self.klt.stat().st_mode | stat.S_IEXEC)

    def set_modes(self, modes):
        self.modes.write_text(json.dumps(modes))

    def grid(self, points=None):
        return batch_mod.run_grid(
            self.tb, _Pdk(), points or self.points, self.tmp / "work",
            jobs=2, klt=str(self.klt), log_dir=self.tmp / "logs",
        )

    def status(self, results):
        record = report_mod.build_record(
            tb=self.tb, pdk=mock.MagicMock(provenance=lambda: {}), points=self.points,
            results=results, ngspice=batch_mod.engine_summary(results), repo_root=self.tmp,
            record_id="r", started_utc="t", wall_seconds=1.0, git={"commit": "x"}, backend="batch",
        )
        return record

    def test_request_is_well_formed(self):
        request = batch_mod.build_request(self.tb, _Pdk(), self.points[1], "b.spice")
        self.assertEqual(request["backend"], "batch")
        self.assertEqual(request["models"], {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"})
        self.assertEqual(request["corners"]["temperature_c"], [27.0])
        self.assertEqual(request["analysis"], {"kind": "ac", "args": "lin 1 100meg 100meg"})
        self.assertEqual([m["name"] for m in request["measurements"]], list(self.tb.measure))
        self.assertEqual(request["batch"]["capacity_wait_s"], 600)
        body = batch_mod.compose_body(self.tb, _Pdk(), self.points[1])
        self.assertIn(".param vdd_val=3.3", body)
        self.assertNotIn(".control", body)
        self.assertNotIn(".end\n", body)

    def test_full_grid_ok_and_record_marks_batch(self):
        results = self.grid()
        self.assertEqual([r.status for r in results], ["ok"] * 3)
        self.assertEqual(results[0].job_id, "job-tt_-40c_3.30v")
        record = self.status(results)
        self.assertEqual(record["status"], "pass")
        self.assertEqual(record["environment"]["backend"], "batch")
        self.assertEqual(record["environment"]["ngspice"], "ngspice-46")
        self.assertEqual(len(record["environment"]["batch_job_ids"]), 3)
        self.assertEqual(record["points"][0]["batch_job_id"], "job-tt_-40c_3.30v")

    def test_missing_point_is_not_pass(self):
        self.set_modes({"tt_27c_3.30v": "missing"})
        results = self.grid()
        self.assertEqual(results[1].status, "error")
        self.assertIn("missing point", results[1].message)
        self.assertEqual(self.status(results)["status"], "error")

    def test_duplicate_point_is_not_pass(self):
        self.set_modes({"tt_27c_3.30v": "duplicate"})
        results = self.grid()
        self.assertEqual(results[1].status, "error")
        self.assertEqual(self.status(results)["status"], "error")

    def test_failed_point_is_not_pass(self):
        self.set_modes({"tt_125c_3.30v": "failed"})
        results = self.grid()
        self.assertNotEqual(results[2].status, "ok")
        self.assertTrue(results[2].missing)
        self.assertEqual(self.status(results)["status"], "error")

    def test_submit_failure_is_loud_and_never_local(self):
        self.set_modes({"tt_27c_3.30v": "nojson"})
        with mock.patch("subprocess.run", wraps=__import__("subprocess").run) as run:
            results = self.grid()
        self.assertEqual(results[1].status, "error")
        self.assertIn("batch_no_capacity", results[1].message)
        for call in run.call_args_list:
            self.assertNotIn("ngspice", str(call.args[0][0]))

    def test_missing_klt_is_an_error_not_a_local_run(self):
        results = batch_mod.run_grid(
            self.tb, _Pdk(), self.points[:1], self.tmp / "w", klt=str(self.tmp / "nope")
        )
        self.assertEqual(results[0].status, "error")
        self.assertIn("no local fallback", results[0].message)

    def test_assemble_rejects_missing_duplicate_unexpected(self):
        ok = [batch_mod._failed(p, "error", "x") for p in self.points]
        batch_mod.assemble(self.points, ok)
        with self.assertRaisesRegex(batch_mod.BatchError, "missing point"):
            batch_mod.assemble(self.points, ok[:2])
        with self.assertRaisesRegex(batch_mod.BatchError, "duplicate point"):
            batch_mod.assemble(self.points, ok + ok[:1])
        with self.assertRaisesRegex(batch_mod.BatchError, "unexpected point"):
            batch_mod.assemble(self.points[:2], ok)

    def test_dry_run_prints_every_request_and_submits_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("subprocess.run") as run, mock.patch.object(
            cli_mod, "find_pdk", return_value=_Pdk()
        ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_mod.main(["esd-clamp-cv", "--backend", "batch", "--dry-run"])
        self.assertEqual(code, 0)
        run.assert_not_called()
        text = out.getvalue()
        n = len(corners_mod.build_grid(
            corners_mod.resolve_corners(list(self.tb.corners)),
            list(self.tb.temperatures_c),
            corners_mod.supply_points(self.tb.nominal_supply_v, self.tb.supply_tolerance),
            None,
        ))
        self.assertEqual(text.count("# point "), n)
        self.assertIn("nothing submitted", err.getvalue())

    def test_dry_run_requires_batch_backend(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotEqual(cli_mod.main(["esd-clamp-cv", "--dry-run"]), 0)

    def test_local_default_unchanged(self):
        args = cli_mod.build_parser().parse_args(["esd-clamp-cv"])
        self.assertEqual(args.backend, "local")
        point = _point()
        from harness.runner import PointResult
        d = PointResult(point=point, status="ok").as_dict()
        self.assertNotIn("backend", d)
        self.assertNotIn("batch_job_id", d)


if __name__ == "__main__":
    unittest.main()
