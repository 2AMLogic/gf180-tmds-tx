#!/usr/bin/env python3
"""Unit tests for scripts/check_attest_files.py. Offline; temp directories only."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_attest_files as checker  # noqa: E402


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class CheckAttestFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "signoff/envelopes").mkdir(parents=True)
        (self.root / "README.md").write_bytes(b"hello\n")

    def envelope(self, checks, name="item10.json"):
        doc = {"attestation": {"checks": checks}}
        (self.root / "signoff/envelopes" / name).write_text(json.dumps(doc))

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = checker.main(["--root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def pin(self, content_hash=None, path="README.md"):
        return {"check": "present", "path": path, "content_hash": content_hash or sha(b"hello\n")}

    def test_match_passes(self):
        self.envelope([self.pin()])
        self.assertEqual(self.run_main()[0], 0)

    def test_mismatch_names_path_and_escalates_without_regen_command(self):
        self.envelope([self.pin()])
        (self.root / "README.md").write_bytes(b"edited\n")
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("README.md", err)
        self.assertIn("escalate", err)
        self.assertNotIn("klt signoff", err)

    def test_missing_file_is_reported_not_a_traceback(self):
        self.envelope([self.pin(path="LICENSE")])
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("LICENSE is missing", err)

    def test_command_only_entries_are_ignored(self):
        self.envelope([{"check": "command", "name": "lint", "argv": ["false"], "passed": True}])
        self.assertEqual(self.run_main()[0], 0)

    def test_signoff_record_and_manifest_are_never_read(self):
        self.envelope([self.pin()])
        (self.root / "signoff/signoff.json").write_text("{not json")
        (self.root / "signoff/manifest.json").write_text("{not json")
        self.assertEqual(self.run_main()[0], 0)

    def test_unreadable_envelope_is_reported(self):
        (self.root / "signoff/envelopes/bad.json").write_text("{nope")
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("bad.json", err)

    def test_live_tree_matches(self):
        # Guards the committed state: envelopes agree with the files they pin.
        live = Path(__file__).resolve().parents[2]
        self.assertEqual(checker.main(["--root", str(live)]), 0)


if __name__ == "__main__":
    unittest.main()
