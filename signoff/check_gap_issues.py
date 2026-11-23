#!/usr/bin/env python3
"""Read-only ``closes_with`` liveness check for the signoff spec maps (#383).

    python3 signoff/check_gap_issues.py [--spec signoff/analog-spec.json]
                                       [--repo OWNER/NAME]

A declared gap in the map must name the *open* issue that would close it
(the tier rule #372 quoted when the map landed). ``problems()`` in
``sim/tests/test_analog_spec.py`` checks the key exists; this command is
the reviewer-facing half: for every gap whose ``closes_with`` is a positive
integer, query the repository issue via ``gh api`` and require it to be an
open issue. An explicit ``null`` closer is skipped without any request --
it records that no open issue would close the row, with the rationale in
the gap text itself. Closed, missing, malformed and pull-request
references are reported with their row.

Read-only: queries GitHub, changes nothing, writes nothing. Exit codes --
    0  every tracked closer is an open issue (explicit-null gaps skipped)
    1  map problems found (closed / missing / malformed / PR references)
    2  the GitHub API could not be queried -- a distinct, retryable
       diagnostic (no ``gh``, no network, bad credentials); re-run later,
       this is not a verdict on the map

The unit suite (``sim/tests/test_gap_issue_check.py``) covers this module
offline with a fake fetcher; no test touches the network.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = REPO_ROOT / "signoff" / "analog-spec.json"

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_API_UNAVAILABLE = 2


class ApiUnavailable(Exception):
    """GitHub could not be queried. Retryable; says nothing about the map."""


def gh_fetch_issue(repo: str, ref: int, timeout: float = 30.0) -> dict:
    """One read-only ``gh api repos/<repo>/issues/<ref>`` lookup.

    Returns ``{"kind": "issue" | "pr" | "missing", "state": ...}`` or
    raises :class:`ApiUnavailable`.
    """
    argv = ["gh", "api", f"repos/{repo}/issues/{ref}"]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise ApiUnavailable(f"gh executable not found ({exc})") from exc
    except subprocess.TimeoutExpired as exc:
        raise ApiUnavailable(f"gh api timed out after {timeout}s") from exc
    if proc.returncode == 0:
        try:
            payload = json.loads(proc.stdout)
        except ValueError as exc:
            raise ApiUnavailable(f"gh api returned unparseable JSON: {exc}") from exc
        return {
            "kind": "pr" if "pull_request" in payload else "issue",
            "state": str(payload.get("state", "")),
        }
    stderr = (proc.stderr or "").strip()
    if proc.returncode == 1 and "Not Found" in stderr:
        return {"kind": "missing", "state": ""}
    raise ApiUnavailable(
        f"gh api exited {proc.returncode}: {stderr or '(no stderr)'}"
    )


def repo_from_origin() -> str:
    """OWNER/NAME parsed from the origin remote (works inside worktrees)."""
    try:
        url = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ApiUnavailable(f"cannot resolve origin remote: {exc}") from exc
    if url.returncode != 0:
        raise ApiUnavailable(
            "cannot resolve origin remote; pass --repo OWNER/NAME"
        )
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url.stdout.strip())
    if not match:
        raise ApiUnavailable(
            f"cannot parse OWNER/NAME from origin url {url.stdout.strip()!r}; "
            f"pass --repo OWNER/NAME"
        )
    return match.group(1)


def check(spec: dict, fetch) -> tuple[list[str], str | None]:
    """Validate every gap's ``closes_with`` against ``fetch(ref)``.

    Returns ``(findings, unavailable)``: ``findings`` are map problems;
    ``unavailable`` is the first API-unavailable diagnostic (the whole
    command is then retryable, not a verdict).
    """
    findings: list[str] = []
    unavailable: str | None = None
    for row in spec.get("rows", []):
        rid = str(row.get("id"))
        if "gap" not in row:
            if "closes_with" in row:
                findings.append(
                    f"row {rid}: closes_with on a row with no gap disposition"
                )
            continue
        if "closes_with" not in row:
            findings.append(
                f"row {rid}: a declared gap must carry closes_with "
                f"(the open issue that would close it, or null)"
            )
            continue
        ref = row["closes_with"]
        if ref is None:
            continue  # explicit null: no tracker to verify, no request made
        if isinstance(ref, bool) or not isinstance(ref, int) or ref <= 0:
            findings.append(
                f"row {rid}: closes_with must be a positive integer issue "
                f"number or null, got {ref!r}"
            )
            continue
        if unavailable is not None:
            continue  # API already known down; stop querying, stay retryable
        try:
            issue = fetch(ref)
        except ApiUnavailable as exc:
            unavailable = f"row {rid}: closes_with #{ref}: {exc}"
            continue
        if issue["kind"] == "missing":
            findings.append(
                f"row {rid}: closes_with #{ref} does not exist "
                f"(GitHub reports Not Found)"
            )
        elif issue["kind"] == "pr":
            findings.append(
                f"row {rid}: closes_with #{ref} is a pull request, not an issue"
            )
        elif issue["state"] != "open":
            state = issue["state"] or "unknown state"
            findings.append(
                f"row {rid}: closes_with #{ref} is {state} -- the gap reads "
                f"as tracked while nothing tracks it; re-point the gap or "
                f"record closes_with: null with the closing rationale"
            )
    return findings, unavailable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only closes_with liveness check (#383)."
    )
    parser.add_argument(
        "--spec",
        default=str(DEFAULT_SPEC),
        help="map to check (default: signoff/analog-spec.json)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="OWNER/NAME to query (default: parsed from the origin remote)",
    )
    args = parser.parse_args(argv)

    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read map {args.spec}: {exc}", file=sys.stderr)
        return EXIT_PROBLEMS
    try:
        repo = args.repo or repo_from_origin()
    except ApiUnavailable as exc:
        print(f"api unavailable: {exc}", file=sys.stderr)
        return EXIT_API_UNAVAILABLE

    findings, unavailable = check(spec, lambda ref: gh_fetch_issue(repo, ref))
    for problem in findings:
        print(problem)
    if unavailable is not None:
        print(f"api unavailable: {unavailable}", file=sys.stderr)
        print(
            "no verdict: GitHub could not be queried -- retry the command "
            "when the API is reachable",
            file=sys.stderr,
        )
        return EXIT_API_UNAVAILABLE
    if findings:
        print(f"{len(findings)} problem(s) -- the map is not signoff-consumable")
        return EXIT_PROBLEMS
    print("ok: every non-null closes_with names an open issue")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
