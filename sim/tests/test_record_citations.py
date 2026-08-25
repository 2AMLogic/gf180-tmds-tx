#!/usr/bin/env python3
"""Unit tests for the characterization-report coverage checker. No PDK required.

    python3 -m unittest discover -s sim/tests -v

Covers `sim/check_record_citations.py` (issue #142), the lint step that fails
the build when `measurements/characterization.md` -- this block's single
aggregated T1 characterization report -- does not cite a tracked evidence
record.

The load-bearing test here is `test_catches_the_real_142_omission`: it
reconstructs the exact stale prose the report actually carried for eleven
days (a Monte Carlo record that had landed, described by the report as not
existing) and asserts the checker rejects it. A guard that cannot fail on
the defect that motivated it is not a guard.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

import check_record_citations as crc  # noqa: E402

#: The record issue #142 found missing from the rollup.
MISMATCH_RECORD = "sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md"
EYE_RECORD = "sim/cml-driver-eye/records/20260810-041436-a2c358b.md"

#: Verbatim from `measurements/characterization.md` §3 item 3 as it stood at
#: `88e758f` -- the text that denied the record above existed. Reproduced here
#: (rather than read out of git history) so the test does not depend on the
#: checkout depth CI happens to use.
STALE_ITEM_3 = """
3. **Monte Carlo evidence.** No record in `sim/` today carries a
   **Statistical convention** field with a seed, sample count, and a
   deterministic negative control -- every record in §1 is a corner-matrix
   claim (`Statistical convention: N/A`), not a distribution claim. This is
   tracked separately by **issue #23**, the sibling Monte Carlo issue in
   this same Epic #17 phase, and has not landed as of this document.
"""


def _init_repo(root: Path, records: list[str], report_body: str) -> None:
    """A throwaway git repo with `records` committed and a report."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)

    for record in records:
        path = root / record
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Record for {record}\n", encoding="utf-8")

    report = root / crc.REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(report_body, encoding="utf-8")

    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True)


@contextlib.contextmanager
def _repo(records: list[str], report_body: str):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _init_repo(root, records, report_body)
        yield root


class CitationParsingTests(unittest.TestCase):
    def test_recognises_every_citation_form_the_report_uses(self) -> None:
        text = (
            f"a markdown link [`{EYE_RECORD}`](../{EYE_RECORD}) and\n"
            f"an inline code span `{MISMATCH_RECORD}` and\n"
            f"bare prose {MISMATCH_RECORD} on its own.\n"
        )
        self.assertEqual(crc.cited_records(text), {EYE_RECORD, MISMATCH_RECORD})

    def test_link_punctuation_is_not_swallowed_into_the_path(self) -> None:
        cited = crc.cited_records(f"see [the record](../{EYE_RECORD}).")
        self.assertEqual(cited, {EYE_RECORD})

    def test_a_glob_in_prose_is_not_a_citation(self) -> None:
        """`sim/*/records/*.md` names the shape, not a file."""
        self.assertEqual(crc.cited_records("every `sim/*/records/*.md` is"), set())

    def test_a_deeper_path_is_not_a_record_citation(self) -> None:
        cited = crc.cited_records("sim/cml-driver-eye/corners/x/records/y.md")
        self.assertEqual(cited, set())


class CoverageCheckTests(unittest.TestCase):
    def test_passes_when_every_record_is_cited(self) -> None:
        body = f"cites [one](../{EYE_RECORD}) and [two](../{MISMATCH_RECORD}).\n"
        with _repo([EYE_RECORD, MISMATCH_RECORD], body) as root:
            records, uncited, dangling = crc.check(root)
            self.assertEqual(len(records), 2)
            self.assertEqual(uncited, [])
            self.assertEqual(dangling, [])

    def test_catches_the_real_142_omission(self) -> None:
        """The regression this checker exists for.

        A report that cites the eye record, omits the Monte Carlo record,
        and asserts in prose that no such record exists -- exactly the state
        `measurements/characterization.md` was in at `88e758f`.
        """
        body = f"§1 cites [the eye record](../{EYE_RECORD}).\n{STALE_ITEM_3}"
        with _repo([EYE_RECORD, MISMATCH_RECORD], body) as root:
            _, uncited, _ = crc.check(root)
            self.assertEqual(uncited, [MISMATCH_RECORD])

    def test_untracked_record_does_not_gate_the_build(self) -> None:
        """A record minted by a dirty-tree run is not yet evidence."""
        body = f"cites [one](../{EYE_RECORD}).\n"
        with _repo([EYE_RECORD], body) as root:
            scratch = root / MISMATCH_RECORD
            scratch.parent.mkdir(parents=True, exist_ok=True)
            scratch.write_text("# uncommitted scratch record\n", encoding="utf-8")
            records, uncited, _ = crc.check(root)
            self.assertEqual(records, [EYE_RECORD])
            self.assertEqual(uncited, [])

    def test_flags_a_citation_that_resolves_to_nothing(self) -> None:
        """A typo'd link renders fine; only a reader who clicks finds out."""
        typo = "sim/cml-driver-eye/records/20260810-041436-typo000.md"
        body = f"cites [one](../{EYE_RECORD}) and [a typo](../{typo}).\n"
        with _repo([EYE_RECORD], body) as root:
            _, uncited, dangling = crc.check(root)
            self.assertEqual(uncited, [])
            self.assertEqual(dangling, [typo])

    def test_missing_report_is_an_error_not_a_silent_pass(self) -> None:
        with _repo([EYE_RECORD], "placeholder\n") as root:
            (root / crc.REPORT).unlink()
            with self.assertRaises(FileNotFoundError):
                crc.check(root)


class ExitCodeTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = crc.main(argv)
        return code, buffer.getvalue()

    def test_this_repo_currently_passes(self) -> None:
        """The live invariant, against the real tree."""
        code, out = self._run([])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_list_names_every_tracked_record(self) -> None:
        code, out = self._run(["--list"])
        self.assertEqual(code, 0, out)
        for record in crc.tracked_records(REPO_ROOT):
            self.assertIn(record, out)


if __name__ == "__main__":
    unittest.main()
