#!/usr/bin/env python3
"""Toolchain-free tripwire: committed attestation envelopes vs the files they pin.

    python3 scripts/check_attest_files.py [--root DIR]

Every ``signoff/envelopes/*.json`` that carries an ``attestation.checks`` list
pins, for each *path* entry, the raw-byte ``sha256`` of a tracked file (item 10
pins ``README.md``, ``spec/tmds-tx.md``, ``LICENSE`` and
``.github/workflows/ci.yml``). Editing a pinned file drifts the envelope, and the
slow ``signoff`` job then reports it by list index, not by path. This check runs
in the fast CI ``lint`` job and names the file instead.

It is a *report*, never a refresh: re-attesting an envelope is a sign-off action
(klayout-tools ``docs/cli/signoff.md``, "Item 10"), so the message says to
escalate -- it prints no regeneration command, and there is no ``--fix`` mode.

Only entries with a ``path`` are compared; ``command`` entries need cocotb /
iverilog and are the ``signoff`` job's business. It reads the envelopes and the
pinned files only (never ``signoff/signoff.json`` or ``signoff/manifest.json``),
and needs no ``klt``, network or git.

Deliberately NOT a step of ``.github/scripts/lint.sh``: that script is itself one
of item 10's attested ``command`` checks, so during a re-attest this check would
compare the new file against the *old* envelope, fail, and be recorded as a
failed check -- making the envelope unregenerable. It runs as its own CI step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ENVELOPE_GLOB = "signoff/envelopes/*.json"
ESCALATION = (
    "escalate to the repo owner -- re-attesting an envelope is a sign-off action; "
    "do not regenerate it to clear this check (signoff/README.md, 'CI: the record cannot rot')"
)


def sha256_of(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def envelope_problems(envelope: Path, root: Path) -> list[str]:
    """Every pinned path entry of ``envelope`` that departs from the file on disk."""
    rel = envelope.relative_to(root).as_posix()
    try:
        doc = json.loads(envelope.read_text())
    except (OSError, ValueError) as exc:
        return [f"{rel}: unreadable envelope ({exc})"]
    checks = (doc.get("attestation") or {}).get("checks") if isinstance(doc, dict) else None
    if not isinstance(checks, list):
        return []  # not an attestation envelope
    problems = []
    for entry in checks:
        if not isinstance(entry, dict) or entry.get("path") is None:
            continue
        path, pinned = entry["path"], entry.get("content_hash")
        target = root / path
        if not target.is_file():
            problems.append(f"{rel}: pinned file {path} is missing")
        elif pinned != sha256_of(target):
            problems.append(f"{rel}: pinned file {path} has changed since it was attested")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args(argv).root.resolve()
    problems: list[str] = []
    for envelope in sorted(root.glob(ENVELOPE_GLOB)):
        problems += envelope_problems(envelope, root)
    if problems:
        print("attestation drift:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"{ESCALATION}", file=sys.stderr)
        return 1
    print("attestation envelopes match the files they pin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
