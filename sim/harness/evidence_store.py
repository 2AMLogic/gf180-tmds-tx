"""Stored-evidence writer: raw run output goes to the artifact store, git keeps
a manifest.

Raw per-corner ngspice logs are bulk run output, not source. A run stages them
in a git-ignored scratch directory, stores each one through
``klt artifact put`` (which hashes it, uploads it via the artifact broker and
emits a manifest entry), and only the manifest
(``manifests/artifacts/<bench>-<run-id>.manifest.json``) plus the summary
record are committed. The record lists name, size and sha256 per object so it
stays hand-checkable without the store.

The writer fails closed: no broker configured, a ``klt`` without ``artifact
put``, or an unreachable broker is an :class:`EvidenceStoreError`, and there is
no option to commit the bytes instead. :func:`preflight` runs before the
simulation so a misconfigured host does not burn a grid; a failure after the
grid leaves the staged bytes in place and writes no manifest or record.

Stdlib only. Layout and rules: ``manifests/artifacts/README.md``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .evidence_lint import _git

#: Environment variable naming the artifact broker (read by ``klt artifact``).
ENV_BROKER = "KLT_ARTIFACT_BROKER"

#: Repo-relative directory holding committed manifests.
MANIFEST_DIR = "manifests/artifacts"
MANIFEST_SUFFIX = ".manifest.json"

#: Name of the staged-bytes directory under ``sim/.work/`` (git-ignored).
STAGE_DIRNAME = ".stage"

#: ``sim/.work/.stage`` -- ``sim/.work/`` is git-ignored.
STAGE_ROOT = Path(__file__).resolve().parents[1] / ".work" / STAGE_DIRNAME

LOG_MEDIA_TYPE = "text/plain"


class EvidenceStoreError(RuntimeError):
    """The evidence cannot be stored; nothing was recorded."""


def manifest_rel_path(bench: str, run_id: str) -> str:
    """Repo-relative manifest path for one run."""
    return f"{MANIFEST_DIR}/{bench}-{run_id}{MANIFEST_SUFFIX}"


def stage_dir(bench: str, run_id: str) -> Path:
    """Git-ignored scratch directory the run's logs are written to."""
    return STAGE_ROOT / bench / run_id


def entry_name(bench: str, run_id: str, filename: str) -> str:
    """The manifest entry name a staged log is stored under."""
    return f"sim/{bench}/corners/{run_id}/{filename}"


def preflight(klt: str = "klt", env: dict | None = None) -> None:
    """Raise :class:`EvidenceStoreError` unless bytes can be stored at all."""
    env = os.environ if env is None else env
    if not env.get(ENV_BROKER):
        raise EvidenceStoreError(
            f"{ENV_BROKER} is not set; evidence bytes are stored through the "
            "artifact broker and there is no option to commit them instead"
        )
    if shutil.which(klt) is None:
        raise EvidenceStoreError(f"{klt!r} not found on PATH")
    try:
        probe = subprocess.run(
            [klt, "artifact", "put", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise EvidenceStoreError(f"cannot run {klt!r}: {exc}") from exc
    if probe.returncode != 0:
        raise EvidenceStoreError(
            f"{klt!r} does not provide `artifact put` (upgrade klayout-tools)"
        )


def require_ignored_stage(stage_root: Path, repo_root: Path) -> None:
    """Refuse a stage directory git would track: staged bytes must never be committable."""
    probe = stage_root / "probe"
    result = _git(repo_root, "check-ignore", "-q", str(probe))
    if result is None or result.returncode != 0:
        raise EvidenceStoreError(
            f"stage directory {stage_root} is not git-ignored; staged evidence "
            "bytes must live under an ignored path (sim/.work/)"
        )


def store_run(
    bench: str,
    run_id: str,
    stage_dir: Path,
    repo_root: Path,
    klt: str = "klt",
) -> dict:
    """Store every ``*.log`` in ``stage_dir``; write and return the manifest.

    Returns ``{"manifest": <repo-relative path>, "entries": [...]}``. The
    manifest is assembled beside the staged bytes and only moved into
    ``manifests/artifacts/`` once every object is stored, so a failure part
    way leaves no partial manifest behind. Refuses to overwrite a manifest.
    """
    logs = sorted(stage_dir.glob("*.log"))
    if not logs:
        raise EvidenceStoreError(f"no staged logs in {stage_dir}")
    for log in logs:
        if log.stat().st_size == 0:
            raise EvidenceStoreError(f"{log.name} is empty; the store holds non-empty objects")

    rel = manifest_rel_path(bench, run_id)
    final = repo_root / rel
    if final.exists():
        raise EvidenceStoreError(f"{rel} already exists; manifests are append-only")
    pending = stage_dir.parent / f"{bench}-{run_id}{MANIFEST_SUFFIX}.pending"
    pending.unlink(missing_ok=True)

    for log in logs:
        proc = subprocess.run(
            [
                klt, "artifact", "put",
                "--manifest", str(pending),
                "--name", entry_name(bench, run_id, log.name),
                "--media-type", LOG_MEDIA_TYPE,
                str(log),
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if proc.returncode != 0:
            raise EvidenceStoreError(
                f"`klt artifact put` failed for {log.name} (exit {proc.returncode}); "
                f"staged bytes kept in {stage_dir}: "
                + (proc.stderr.strip() or proc.stdout.strip() or "no output")
            )

    try:
        manifest = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceStoreError(f"`klt artifact put` left no readable manifest: {exc}") from exc
    entries = sorted(manifest.get("entries", []), key=lambda e: e.get("name", ""))
    if len(entries) != len(logs):
        raise EvidenceStoreError(
            f"manifest has {len(entries)} entries for {len(logs)} staged logs"
        )
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pending), str(final))
    return {"manifest": rel, "entries": entries}


def stored_evidence_lines(stored: dict) -> list[str]:
    """Markdown section listing name, size and sha256 per stored object."""
    lines = [
        "## Stored evidence",
        "",
        f"Raw per-corner logs are in the artifact store, not in git; manifest "
        f"`{stored['manifest']}` names each object. `klt artifact verify` "
        "re-checks size and sha256 against the store.",
        "",
        "| name | size (bytes) | sha256 |",
        "| --- | ---: | --- |",
    ]
    for entry in stored["entries"]:
        lines.append(f"| `{entry['name']}` | {entry['size']} | `{entry['sha256']}` |")
    lines.append("")
    return lines
