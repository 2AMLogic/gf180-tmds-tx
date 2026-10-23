#!/usr/bin/env python3
"""Check the committed stored-evidence manifests under ``manifests/artifacts/``.

    python3 scripts/check_artifact_manifests.py [--root DIR]

Run as a step of ``.github/scripts/lint.sh`` (so ``npm run lint`` and the CI
``lint`` job both execute it). Stdlib only; reads tracked files, never the
broker (CI cannot reach it -- ``klt artifact verify`` is the out-of-band half).

For every tracked ``manifests/artifacts/*.manifest.json``:

- the manifest is ``{"schema_version": 1, "entries": [...]}`` and every entry
  carries exactly the ``klt artifact`` fields (sha256, size, kind, producer,
  uri, optional name / media_type) with the right shapes;
- every ``uri`` is a logical ``artifact:<key>`` whose last path segment is the
  entry's sha256 -- nothing that names a storage location;
- no stored object's bytes are also committed: no tracked file sits at an
  entry's ``name`` path, and no tracked file has an entry's sha256;
- the manifest text names no bucket or ARN (``s3://``, ``arn:aws:``).

The entry shape mirrors ``klayout_tools.artifact_store`` (manifest
``schema_version`` 1); it is restated here so CI needs no klt install.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST_RE = re.compile(r"^manifests/artifacts/[^/]+\.manifest\.json$")
SCHEMA_VERSION = 1
REQUIRED = ("sha256", "size", "kind", "producer", "uri")
OPTIONAL = ("name", "media_type")
KINDS = ("evidence", "transcript", "log", "pdk")
PRODUCER_FIELDS = ("tool", "version", "loom.repo", "commit")
URI_PREFIX = "artifact:"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STORAGE_LOCATION_RE = re.compile(r"s3://|arn:aws:")


def entry_problems(entry) -> list[str]:
    """Every way ``entry`` departs from the manifest entry shape."""
    if not isinstance(entry, dict):
        return ["entry is not an object"]
    problems = []
    missing = [f for f in REQUIRED if f not in entry]
    extra = sorted(set(entry) - set(REQUIRED) - set(OPTIONAL))
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    if extra:
        problems.append(f"unknown field(s) {', '.join(extra)}")
    sha256 = entry.get("sha256")
    if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
        problems.append("sha256 must be 64 lowercase hex digits")
    size = entry.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        problems.append("size must be a positive integer")
    if entry.get("kind") not in KINDS:
        problems.append(f"kind must be one of {', '.join(KINDS)}")
    producer = entry.get("producer")
    if not isinstance(producer, dict):
        problems.append("producer is not an object")
    else:
        if set(producer) != set(PRODUCER_FIELDS):
            problems.append(f"producer must carry exactly {', '.join(PRODUCER_FIELDS)}")
        for name in ("tool", "version", "loom.repo"):
            if not isinstance(producer.get(name), str) or not producer.get(name):
                problems.append(f"producer.{name} must be a non-empty string")
        if producer.get("commit") is not None and not isinstance(producer.get("commit"), str):
            problems.append("producer.commit must be a string or null")
    uri = entry.get("uri")
    if not isinstance(uri, str) or not uri.startswith(URI_PREFIX):
        problems.append(f"uri must be a logical {URI_PREFIX}<key> (got {uri!r})")
    elif uri[len(URI_PREFIX):].rsplit("/", 1)[-1] != sha256:
        problems.append("uri key does not end in the entry's sha256")
    for name in OPTIONAL:
        if name in entry and not isinstance(entry[name], str):
            problems.append(f"{name} must be a string")
    return problems


def tracked_files(root: Path) -> list[str]:
    done = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise SystemExit(f"error: git ls-files failed in {root}: {done.stderr.strip()}")
    return [p for p in done.stdout.split("\0") if p]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(root: Path) -> list[str]:
    """All problems, as ``<path>: <message>`` strings."""
    tracked = tracked_files(root)
    manifests = sorted(p for p in tracked if MANIFEST_RE.match(p))
    tracked_set = set(tracked)
    problems: list[str] = []
    # size -> tracked paths, so a candidate is hashed only when its size matches.
    by_size: dict[int, list[str]] = {}
    sized = False

    for rel in manifests:
        try:
            text = (root / rel).read_text(encoding="utf-8")
            manifest = json.loads(text)
        except (OSError, ValueError) as exc:
            problems.append(f"{rel}: unreadable manifest: {exc}")
            continue
        if STORAGE_LOCATION_RE.search(text):
            problems.append(f"{rel}: names a storage location (s3:// or arn:aws:)")
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != SCHEMA_VERSION
            or not isinstance(manifest.get("entries"), list)
            or not manifest["entries"]
        ):
            problems.append(
                f"{rel}: not {{schema_version: {SCHEMA_VERSION}, entries: [<one or more>]}}"
            )
            continue
        for index, entry in enumerate(manifest["entries"]):
            where = f"{rel}: entries[{index}]"
            bad = entry_problems(entry)
            problems += [f"{where}: {message}" for message in bad]
            if bad:
                continue
            name = entry.get("name")
            if name and name in tracked_set:
                problems.append(f"{where}: bytes are committed at {name} as well as stored")
            if not sized:
                for path in tracked:
                    if path in manifests:
                        continue
                    try:
                        by_size.setdefault((root / path).stat().st_size, []).append(path)
                    except OSError:
                        continue
                sized = True
            for path in by_size.get(entry["size"], []):
                if sha256_of(root / path) == entry["sha256"]:
                    problems.append(
                        f"{where}: stored object (sha256 {entry['sha256'][:12]}...) "
                        f"is also committed at {path}"
                    )
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=None, help="repo root (default: this checkout)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    count = sum(1 for p in tracked_files(root) if MANIFEST_RE.match(p))
    problems = check(root)
    print(f"{count} stored-evidence manifest(s) checked")
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
