#!/usr/bin/env python3
"""Unit tests for the stored-evidence writer and the manifest-backed lint form.

No PDK, ngspice, klt or broker required: a fake ``klt`` stands in for
``klt artifact put`` and appends manifest entries the way the real one does.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import evidence_lint, evidence_store, pdk as pdk_mod, report  # noqa: E402
from test_evidence_lint import RECORD_ID, valid_record, write_experiment  # noqa: E402

FAKE_KLT = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    import hashlib, json, os, sys
    args = sys.argv[1:]
    assert args[:2] == ["artifact", "put"], args
    if "--help" in args:
        sys.exit(int(os.environ.get("FAKE_KLT_HELP_RC", "0")))
    if os.environ.get("FAKE_KLT_FAIL_ON") and os.environ["FAKE_KLT_FAIL_ON"] in args[-1]:
        print("broker unreachable", file=sys.stderr)
        sys.exit(1)
    manifest = args[args.index("--manifest") + 1]
    name = args[args.index("--name") + 1]
    data = open(args[-1], "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    doc = {"schema_version": 1, "entries": []}
    if os.path.exists(manifest):
        doc = json.load(open(manifest))
    doc["entries"].append({
        "sha256": sha, "size": len(data), "kind": "evidence",
        "producer": {"tool": "klt", "version": "0", "loom.repo": "o/r", "commit": None},
        "uri": "artifact:evidence/o__r/" + sha, "name": name, "media_type": "text/plain",
    })
    json.dump(doc, open(manifest, "w"))
    '''
)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text("sim/.work/\n")
        self.klt = self.root / "fake-klt"
        self.klt.write_text(FAKE_KLT)
        self.klt.chmod(self.klt.stat().st_mode | stat.S_IEXEC)
        self.stage = self.root / "sim" / ".work" / ".stage" / "bench" / RECORD_ID
        self.stage.mkdir(parents=True)
        (self.stage / "tt_27c_3.30v.log").write_text("log one\n")
        (self.stage / "ss_-40c_2.97v.log").write_text("log two\n")
        self.env_backup = dict(os.environ)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.clear()
        os.environ.update(self.env_backup)

    def store(self):
        return evidence_store.store_run(
            "bench", RECORD_ID, self.stage, self.root, klt=str(self.klt)
        )


class StoreRunTests(StoreCase):
    def test_stores_each_log_and_writes_manifest(self):
        stored = self.store()
        self.assertEqual(
            stored["manifest"], f"manifests/artifacts/bench-{RECORD_ID}.manifest.json"
        )
        manifest = json.loads((self.root / stored["manifest"]).read_text())
        names = [e["name"] for e in manifest["entries"]]
        self.assertEqual(
            names,
            [
                f"sim/bench/corners/{RECORD_ID}/ss_-40c_2.97v.log",
                f"sim/bench/corners/{RECORD_ID}/tt_27c_3.30v.log",
            ],
        )
        self.assertTrue(all(e["uri"].startswith("artifact:") for e in manifest["entries"]))
        self.assertEqual(
            manifest["entries"][1]["sha256"], hashlib.sha256(b"log one\n").hexdigest()
        )

    def test_broker_failure_keeps_staged_bytes_and_writes_nothing(self):
        os.environ["FAKE_KLT_FAIL_ON"] = "tt_27c"
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "broker unreachable"):
            self.store()
        self.assertFalse((self.root / "manifests").exists())
        self.assertEqual(len(list(self.stage.glob("*.log"))), 2)

    def test_empty_file_is_refused_before_any_upload(self):
        (self.stage / "ff_125c_3.63v.log").write_text("")
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "empty"):
            self.store()
        self.assertFalse((self.root / "manifests").exists())

    def test_existing_manifest_is_never_overwritten(self):
        self.store()
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "append-only"):
            self.store()

    def test_stage_inside_tracked_tree_is_refused(self):
        evidence_store.require_ignored_stage(self.root / "sim" / ".work" / ".stage", self.root)
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "not git-ignored"):
            evidence_store.require_ignored_stage(self.root / "sim" / "bench", self.root)


class PreflightTests(StoreCase):
    def test_unset_broker_fails_closed(self):
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "KLT_ARTIFACT_BROKER"):
            evidence_store.preflight(str(self.klt), env={})

    def test_missing_klt_fails_closed(self):
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "not found"):
            evidence_store.preflight("no-such-klt", env={evidence_store.ENV_BROKER: "http://x"})

    def test_klt_without_artifact_put_fails_closed(self):
        os.environ["FAKE_KLT_HELP_RC"] = "2"
        with self.assertRaisesRegex(evidence_store.EvidenceStoreError, "artifact put"):
            evidence_store.preflight(str(self.klt), env={evidence_store.ENV_BROKER: "http://x"})

    def test_configured_host_passes(self):
        evidence_store.preflight(str(self.klt), env={evidence_store.ENV_BROKER: "http://x"})


class ManifestBackedLintTests(StoreCase):
    """A record citing a manifest lints without committed logs."""

    def lint(self, text=None, logs=()):
        write_experiment(self.root, slug="bench", text=text, logs=logs)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        paths, _ = evidence_lint.list_evidence_paths(self.root)
        experiments = evidence_lint.collect_experiments(
            [p for p in paths if p.startswith("sim/bench/")]
        )
        return evidence_lint.check_experiments(self.root, experiments)

    def record_citing(self, rel: str, **overrides) -> str:
        return valid_record(Links=f"Stored evidence manifest: `{rel}`", **overrides)

    def test_manifest_backed_record_passes_without_logs(self):
        rel = self.store()["manifest"]
        self.assertEqual(self.lint(self.record_citing(rel)), [])

    def test_bad_corner_id_in_manifest_names_is_rejected(self):
        rel = self.store()["manifest"]
        path = self.root / rel
        doc = json.loads(path.read_text())
        doc["entries"][0]["name"] = f"sim/bench/corners/{RECORD_ID}/bogus.log"
        path.write_text(json.dumps(doc))
        problems = [str(p) for p in self.lint(self.record_citing(rel))]
        self.assertTrue(any("bogus" in p for p in problems), problems)

    def test_operating_point_cross_check_runs_over_manifest_names(self):
        (self.stage / "tt_27c_3.30v.log").unlink()
        (self.stage / "ss_-40c_2.97v.log").unlink()
        (self.stage / "tt_27c_3.30v_742p5mbps.log").write_text("eye\n")
        rel = self.store()["manifest"]
        text = self.record_citing(
            rel, **{"Operating point": "270 Mbps/lane", "Transient settings": "tstep 1p"}
        )
        problems = [str(p) for p in self.lint(text)]
        self.assertTrue(any("Operating point" in p and "742.5" in p for p in problems), problems)

    def test_committed_logs_alongside_manifest_are_rejected(self):
        rel = self.store()["manifest"]
        problems = [
            str(p) for p in self.lint(self.record_citing(rel), logs=("tt_27c_3.30v.log",))
        ]
        self.assertTrue(any("must not be committed" in p for p in problems), problems)

    def test_wrong_manifest_name_or_missing_manifest_is_rejected(self):
        problems = [str(p) for p in self.lint(self.record_citing("manifests/artifacts/nope.manifest.json"))]
        self.assertTrue(any("must cite" in p for p in problems), problems)
        self.assertTrue(any("unreadable" in p for p in problems), problems)

    def test_legacy_record_without_logs_still_fails(self):
        problems = [str(p) for p in self.lint(None)]
        self.assertTrue(any("no raw per-corner logs" in p for p in problems), problems)


def _load_run_mc():
    """Import ``sim/cml-driver-mismatch/run_mc.py`` as a module object.

    Loading it runs only imports and constant definitions -- no PDK
    discovery, ngspice probe or sweep -- so the evidence path is exercised
    with the fake ``klt`` and a stubbed ``run_all``, never a real
    simulation and never the real evidence tree.
    """
    path = SIM_DIR / "cml-driver-mismatch" / "run_mc.py"
    name = "cml_driver_mismatch_run_mc"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass processing resolves annotations via sys.modules
    spec.loader.exec_module(module)
    return module


class RunMcEvidencePathTests(StoreCase):
    """Issue #345: ``run_mc.py``'s raw logs are manifest-forward like every
    harness bench. The sweep is stubbed out -- only the evidence path is
    under test: staged flat into ``evidence_store.stage_dir`` through the
    shared #317-filtered writer, stored with ``store_run`` before anything
    is committed, cited from the record's **Links** field, nothing written
    under ``--no-write``, preflight aborting before the sweep, and a broker
    failure leaving no record, no manifest and no snapshot."""

    BENCH = "cml-driver-mismatch"
    FAKE_LOG = (
        "Circuit: * cml_driver_mismatch @ tt_27c_3.30v"
        " -- generated by sim/harness, do not edit\n"
        " Reference value :  4.83720e+00\n"
        "m_swing_dc = 5.0449668753e-01\n"
        "No. of Data Rows : 999\n"
    )

    def setUp(self):
        super().setUp()
        # git_provenance() needs a HEAD to mint a conforming record id.
        subprocess.run(
            ["git", "-c", "user.email=fleet@example.invalid",
             "-c", "user.name=fleet", "commit", "--allow-empty", "-m", "init"],
            cwd=self.root, check=True, capture_output=True,
        )
        self.run_mc = _load_run_mc()
        # Re-point the bench at the throwaway repo root: repo root, records,
        # snapshots and stage root all live in the fake tree, so the real
        # evidence tree is never touched and nothing real is committed.
        self._swap(
            self.run_mc,
            REPO_ROOT=self.root,
            SIM_DIR=self.root / "sim",
            RECORDS_DIR=self.root / "sim" / self.BENCH / "records",
            SNAPSHOT_DIR=self.root / "sim" / self.BENCH / "netlist-snapshots",
        )
        self._swap(evidence_store, STAGE_ROOT=self.root / "sim" / ".work" / ".stage")
        self._swap(
            self.run_mc,
            find_pdk=lambda: pdk_mod.Pdk(
                path=self.root / "fake-pdk", variant="gf180mcuD", source="test fixture"
            ),
            ngspice_version=lambda: "ngspice-47-test",
        )
        self.sweep_calls = 0
        self._swap(self.run_mc, run_all=self._fake_run_all)
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        klt = bin_dir / "klt"
        shutil.copy(self.klt, klt)  # run_mc resolves plain `klt` on PATH
        klt.chmod(klt.stat().st_mode | stat.S_IEXEC)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
        os.environ[evidence_store.ENV_BROKER] = "http://broker.invalid"

    # -- stubs and helpers -------------------------------------------

    def _swap(self, obj, **attrs):
        saved = {name: getattr(obj, name) for name in attrs}
        self.addCleanup(lambda: [setattr(obj, k, v) for k, v in saved.items()])
        for name, value in attrs.items():
            setattr(obj, name, value)

    def _fake_run_all(self, pdk, workdir, n_samples, base_seed):
        """Stand-in for ``run_mc.run_all`` (the `klt sim` submit): the same
        Sample set it returns -- N Monte Carlo samples per process corner, one
        nominal per corner, one negative control -- with canned values."""
        self.sweep_calls += 1
        rc = self.run_mc
        tt = rc.CORNERS["tt"]

        def sample(corner, label, sw, par_tail, swing, vcm):
            return rc.Sample(
                corner_id=f"{corner.name}_{label}_{rc.TEMP_C:g}c_{rc.VDD_V:.2f}v",
                corner=corner, label=label, seed=base_seed, sw_stat_mismatch=sw,
                par_pair=rc.PAR_PAIR_NOMINAL, par_tail=par_tail,
                par_mirror=rc.PAR_MIRROR_NOMINAL, status="ok",
                swing_dc=swing, vcm_dc=vcm, log=self.FAKE_LOG,
            )

        samples = []
        for name in rc.CORNER_SETS["mos"]:
            corner = rc.CORNERS[name]
            samples += [
                sample(corner, f"mc{i:03d}", 1, rc.PAR_TAIL_NOMINAL, 0.5, 3.0)
                for i in range(1, n_samples + 1)
            ]
            samples.append(sample(corner, "nominal", 0, rc.PAR_TAIL_NOMINAL, 0.5, 3.0))
        # outside DR-0002: the negative control must fail
        samples.append(sample(tt, "mcneg", 1, rc.NEG_CTRL_PAR_TAIL, 0.1, 2.0))
        return samples, ["job-test-1"]

    def _record_id(self) -> str:
        records = sorted((self.root / "sim" / self.BENCH / "records").glob("*.md"))
        self.assertEqual(len(records), 1, records)
        return records[0].stem

    def _stage(self, record_id: str) -> Path:
        return evidence_store.stage_dir(self.BENCH, record_id)

    def _lint_bench(self) -> list:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        paths, _ = evidence_lint.list_evidence_paths(self.root)
        experiments = evidence_lint.collect_experiments(
            [p for p in paths if p.startswith(f"sim/{self.BENCH}/")]
        )
        return evidence_lint.check_experiments(self.root, experiments)

    def _assert_nothing_written(self):
        self.assertFalse((self.root / "manifests").exists())
        for kind in ("records", "corners", "netlist-snapshots"):
            self.assertFalse(
                (self.root / "sim" / self.BENCH / kind).exists(), kind
            )
        # Nothing staged for this bench either (StoreCase's own fixture
        # stage for a different bench pre-exists by design).
        self.assertFalse(
            (self.root / "sim" / ".work" / ".stage" / self.BENCH).exists()
        )

    # -- the evidence path --------------------------------------------

    def test_run_stages_flat_stores_and_cites_the_manifest(self):
        rc = self.run_mc.main(["--n-samples", "2"])
        self.assertEqual(rc, 0)
        record_id = self._record_id()
        rel = f"manifests/artifacts/{self.BENCH}-{record_id}.manifest.json"

        # Nothing under the bench's tracked corners/ tree; staged logs are
        # flat in the git-ignored stage dir.
        self.assertFalse((self.root / "sim" / self.BENCH / "corners").exists())
        stage = self._stage(record_id)
        logs = sorted(stage.glob("*.log"))
        self.assertEqual(len(logs), 16, [p.name for p in logs])
        self.assertTrue(all(p.parent == stage for p in logs))

        # The shared #317 filter applied at the shared write site: header
        # kept, progress trace dropped, measurement lines byte-identical.
        written = (stage / "tt_mc001_27c_3.30v.log").read_text(encoding="utf-8")
        self.assertIn(f"* record-id : {record_id}\n", written)
        self.assertNotIn(" Reference value : ", written)
        self.assertIn("m_swing_dc = 5.0449668753e-01\n", written)

        # The manifest lists every log under the store's entry grammar.
        manifest = json.loads((self.root / rel).read_text())
        names = [e["name"] for e in manifest["entries"]]
        self.assertIn(f"sim/{self.BENCH}/corners/{record_id}/tt_mc001_27c_3.30v.log", names)

        # The record cites the manifest in Links and lints clean with no
        # committed corner files.
        text = (self.root / "sim" / self.BENCH / "records" / f"{record_id}.md").read_text(
            encoding="utf-8"
        )
        fields, _ = evidence_lint.parse_fields(text)
        self.assertEqual(evidence_lint._cited_manifest(fields), rel)
        self.assertIn("## Stored evidence", text)
        self.assertEqual(self._lint_bench(), [])

    def test_no_write_runs_the_sweep_and_writes_nothing(self):
        rc = self.run_mc.main(["--n-samples", "2", "--no-write"])
        self.assertEqual(rc, 0)
        self.assertGreater(self.sweep_calls, 0)
        self._assert_nothing_written()

    def test_unset_broker_aborts_before_the_sweep(self):
        del os.environ[evidence_store.ENV_BROKER]
        rc = self.run_mc.main(["--n-samples", "2"])
        self.assertEqual(rc, 3)
        self.assertEqual(self.sweep_calls, 0)
        self._assert_nothing_written()

    def test_broker_failure_leaves_no_record_manifest_or_snapshot(self):
        os.environ["FAKE_KLT_FAIL_ON"] = "tt_mc001"
        rc = self.run_mc.main(["--n-samples", "2"])
        self.assertEqual(rc, 3)
        self.assertGreater(self.sweep_calls, 0)  # the sweep ran; the store failed
        self.assertFalse((self.root / "manifests").exists())
        for kind in ("records", "corners", "netlist-snapshots"):
            self.assertFalse(
                (self.root / "sim" / self.BENCH / kind).exists(), kind
            )
        # Staged bytes survive for diagnosis; nothing was committed.
        bench_stage = self.root / "sim" / ".work" / ".stage" / self.BENCH
        record_ids = [p.name for p in bench_stage.iterdir() if p.is_dir()]
        self.assertEqual(len(record_ids), 1, record_ids)
        stage = self._stage(record_ids[0])
        self.assertEqual(len(list(stage.glob("*.log"))), 16)


class AppendOnlyManifestTests(StoreCase):
    def test_manifest_edit_is_flagged(self):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        rel = self.store()["manifest"]
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.root, check=True, env=env)
        self.assertEqual(evidence_lint.check_append_only(self.root, "HEAD"), ([], None))
        (self.root / rel).write_text("{}")
        problems, skip = evidence_lint.check_append_only(self.root, "HEAD")
        self.assertIsNone(skip)
        self.assertEqual([p.path for p in problems], [rel])


class RenderTests(unittest.TestCase):
    def test_stored_evidence_lines_list_name_size_sha(self):
        lines = evidence_store.stored_evidence_lines(
            {"manifest": "manifests/artifacts/b-r.manifest.json",
             "entries": [{"name": "sim/b/corners/r/x.log", "size": 7, "sha256": "ab" * 32}]}
        )
        text = "\n".join(lines)
        self.assertIn("| `sim/b/corners/r/x.log` | 7 | `" + "ab" * 32 + "` |", text)


if __name__ == "__main__":
    unittest.main()
