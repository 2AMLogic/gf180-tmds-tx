#!/usr/bin/env python3
"""Unit tests for the stored-evidence writer and the manifest-backed lint form.

No PDK, ngspice, klt or broker required: a fake ``klt`` stands in for
``klt artifact put`` and appends manifest entries the way the real one does.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import hashlib
import json
import os
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

from harness import evidence_lint, evidence_store, report  # noqa: E402
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
