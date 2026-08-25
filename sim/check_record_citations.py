#!/usr/bin/env python3
"""Characterization-report coverage checker for gf180-tmds-tx (issue #142).

    python3 sim/check_record_citations.py
    python3 sim/check_record_citations.py --list

Stdlib only, no PDK, no ngspice, no virtualenv -- so it runs in the same
PDK-free CI job as the rest of ``.github/scripts/lint.sh`` (step 7/7).

Why this exists
---------------
``measurements/characterization.md`` opens by describing itself as *"the
single aggregated, current summary of what this block's recorded evidence
actually substantiates"* -- *"one artifact, citing every evidence record
against the specific spec row it verifies"*. That is the T1 evidence
ladder's "characterization report" item, and the whole value of the artifact
is that a reader can trust it to be complete: a spec row absent from it is
supposed to mean *no evidence exists*, not *nobody updated the rollup*.

Issue #142 is what happens when that promise is kept by convention alone.
``sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md`` -- the Monte
Carlo device-mismatch record, T1 checklist item 6, landed 2026-08-15 by
issue #23 -- was never added to the rollup. Worse, the rollup's own
"what is not yet covered" section went on asserting, for ten days and
across five subsequent revisions of the file, that *"no record in sim/ today
carries a Statistical convention field with a seed, sample count, and a
deterministic negative control"* and that issue #23 *"has not landed as of
this document"*. Both statements were false the day they were written. The
report did not merely omit the evidence; it affirmatively denied it existed,
and every subsequent revision read past it.

Nothing could have caught that, because "the rollup cites every record" was
a sentence in a document rather than a check. So it is enforced here
instead: **a tracked evidence record that the characterization report does
not cite fails the build.**

This is the same move the neighbouring lint steps already make -- step 4
(generated DUT freshness), step 5 (evidence-record schema + append-only) and
step 6 (LVS negative-control verdicts) each exist because a documented rule
drifted silently at least once.

What is checked
---------------
1. **Coverage.** Every tracked ``sim/<slug>/records/<record-id>.md`` appears
   somewhere in ``measurements/characterization.md``. Tracked-only, matching
   ``collect()`` in ``.github/scripts/lint.sh``, so an untracked scratch
   record never gates the build.
2. **No dangling citations.** Every ``sim/<slug>/records/<record-id>.md``
   path the report cites resolves to a file that actually exists. A record
   is append-only (``sim/README.md``) so it should never vanish, but a typo
   in a hand-written citation is silent otherwise -- the link renders, and
   only a reader who clicks it finds out.

What is deliberately NOT checked
--------------------------------
- **Whether the citation is in the right place, or says the right thing.**
  This is a presence check. It cannot tell a record cited against the spec
  row it substantiates from one name-dropped in a footnote, and it makes no
  attempt to. Judging whether the rollup characterizes a record *correctly*
  is a reviewer's job; noticing that the rollup forgot a record entirely is
  not, and that is the half automated here.
- **`flow/` and `verification/` records.** The digital partition's evidence
  trail uses its own conventions (``flow/README.md``,
  ``verification/README.md``) and is indexed by §2 of the report in prose
  rather than by per-record path. Extending this check to cover it would
  need that convention pinned down first; asserting a path format that
  ``flow/`` does not promise would be a false invariant.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The aggregated rollup this check enforces the completeness of.
REPORT = Path("measurements/characterization.md")

# Records live at sim/<slug>/records/<record-id>.md (sim/README.md).
RECORD_GLOB = "sim/*/records/*.md"

# The same shape, as it appears inside the report: as a Markdown link target
# (``../sim/...``), inside inline code, or in running prose. The character
# class stops at whitespace and at the delimiters those three forms use, so a
# link's trailing ``)`` or a code span's backtick is not swallowed into the
# path. ``*`` is excluded so that prose naming the *glob* -- ``sim/*/records/
# *.md``, which this file's own docstring and the report both do -- is not
# mistaken for a citation of a literal file named ``*.md``.
CITATION_RE = re.compile(r"sim/[^/\s`'\"()\[\]*]+/records/[^/\s`'\"()\[\]*]+\.md")


def tracked_records(repo_root: Path) -> list[str]:
    """Tracked evidence-record paths, repo-relative, sorted.

    Tracked-only, exactly like ``collect()`` in ``.github/scripts/lint.sh``:
    an experiment run in a dirty tree mints a record on disk, and that
    record should not gate the build until it is deliberately committed.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", RECORD_GLOB],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(p for p in result.stdout.split("\0") if p)


def cited_records(report_text: str) -> set[str]:
    """Every ``sim/<slug>/records/<id>.md`` path the report mentions.

    Matched as a plain substring rather than by parsing Markdown links: the
    report cites records as links (``../sim/...``), as inline code, and in
    running prose, and a citation is a citation in all three forms.
    """
    return set(CITATION_RE.findall(report_text))


def check(repo_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (records, uncited, dangling)."""
    report_path = repo_root / REPORT
    if not report_path.is_file():
        raise FileNotFoundError(f"{REPORT} not found under {repo_root}")
    report_text = report_path.read_text(encoding="utf-8")

    records = tracked_records(repo_root)
    cited = cited_records(report_text)

    uncited = [r for r in records if r not in cited]
    dangling = sorted(c for c in cited if not (repo_root / c).is_file())
    return records, uncited, dangling


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that measurements/characterization.md cites every tracked "
            "sim/*/records/*.md evidence record."
        )
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print every record and whether the report cites it",
    )
    args = parser.parse_args(argv)

    records, uncited, dangling = check(REPO_ROOT)

    if not records:
        print("no tracked evidence records under sim/*/records/")
        return 0

    if args.list:
        width = max(len(r) for r in records)
        for record in records:
            verdict = "MISSING" if record in uncited else "cited"
            print(f"{record:<{width}}  {verdict}")
        print()

    if uncited or dangling:
        for record in uncited:
            print(f"  not cited by {REPORT}: {record}")
        for path in dangling:
            print(f"  {REPORT} cites a record that does not exist: {path}")
        print(
            f"FAIL: {len(uncited)} uncited record(s), {len(dangling)} dangling "
            f"citation(s) across {len(records)} tracked record(s)"
        )
        print(
            f"  {REPORT} is this block's single aggregated characterization "
            "report; add the record above to it (or, if the record is not "
            "evidence for any spec row, say so there explicitly)."
        )
        return 1

    print(
        f"PASS: {REPORT} cites all {len(records)} tracked evidence record(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
