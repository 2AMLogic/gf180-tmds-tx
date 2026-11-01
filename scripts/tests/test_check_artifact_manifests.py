#!/usr/bin/env python3
"""Unit tests for scripts/check_artifact_manifests.py. Offline; temp git repos."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_artifact_manifests as checker  # noqa: E402

PAYLOAD = b"* ngspice log\n"
SHA = hashlib.sha256(PAYLOAD).hexdigest()
NAME = "sim/bench/corners/20260101-000000-abcdef0/tt_27c_3.30v.log"


def entry(**overrides) -> dict:
    value = {
        "sha256": SHA,
        "size": len(PAYLOAD),
        "kind": "evidence",
        "producer": {"tool": "klt", "version": "0.7.1", "loom.repo": "o/r", "commit": None},
        "uri": f"artifact:evidence/o__r/{SHA}",
        "name": NAME,
    }
    value.update(overrides)
    return value


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def commit(self, files: dict) -> list:
        for rel, data in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        return checker.check(self.root)

    def manifest(self, *entries, **top) -> str:
        body = {"schema_version": 1, "entries": list(entries)}
        body.update(top)
        return json.dumps(body)

    def test_valid_manifest_passes(self):
        self.assertEqual(
            self.commit({"manifests/artifacts/bench-run.manifest.json": self.manifest(entry())}),
            [],
        )

    def test_bad_schema_is_rejected(self):
        problems = self.commit(
            {
                "manifests/artifacts/a.manifest.json": self.manifest(entry(), schema_version=2),
                "manifests/artifacts/b.manifest.json": self.manifest(entry(size=0, kind="x")),
                "manifests/artifacts/c.manifest.json": self.manifest({"sha256": SHA}),
            }
        )
        text = "\n".join(problems)
        self.assertIn("a.manifest.json: not {schema_version", text)
        self.assertIn("b.manifest.json: entries[0]: size must be a positive integer", text)
        self.assertIn("kind must be one of", text)
        self.assertIn("c.manifest.json: entries[0]: missing", text)

    def test_non_artifact_uri_is_rejected(self):
        for uri in (f"https://example.test/{SHA}", f"s3://bucket/{SHA}"):
            with self.subTest(uri=uri):
                problems = self.commit(
                    {"manifests/artifacts/x.manifest.json": self.manifest(entry(uri=uri))}
                )
                self.assertTrue(any("logical artifact:" in p for p in problems), problems)

    def test_storage_location_text_is_rejected(self):
        problems = self.commit(
            {
                "manifests/artifacts/x.manifest.json": self.manifest(
                    entry(media_type="arn:aws:s3:::bucket")
                )
            }
        )
        self.assertTrue(any("storage location" in p for p in problems), problems)

    def test_uri_key_must_end_in_sha(self):
        problems = self.commit(
            {
                "manifests/artifacts/x.manifest.json": self.manifest(
                    entry(uri="artifact:evidence/o__r/" + "0" * 64)
                )
            }
        )
        self.assertTrue(any("does not end in" in p for p in problems), problems)

    def test_bytes_committed_at_entry_name_are_rejected(self):
        problems = self.commit(
            {
                "manifests/artifacts/x.manifest.json": self.manifest(entry()),
                NAME: b"different bytes",
            }
        )
        self.assertTrue(any("committed at" in p for p in problems), problems)

    def test_bytes_committed_anywhere_by_sha_are_rejected(self):
        problems = self.commit(
            {
                "manifests/artifacts/x.manifest.json": self.manifest(entry()),
                "elsewhere/copy.log": PAYLOAD,
            }
        )
        self.assertTrue(any("also committed at elsewhere/copy.log" in p for p in problems), problems)

    def test_no_manifests_is_clean(self):
        self.assertEqual(self.commit({"README.md": "x"}), [])


if __name__ == "__main__":
    unittest.main()
