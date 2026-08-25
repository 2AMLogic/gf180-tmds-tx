#!/usr/bin/env python3
"""LVS signoff-verdict checker for gf180-tmds-tx (issue #129).

    python3 layout/scripts/check_lvs_signoff.py
    python3 layout/scripts/check_lvs_signoff.py --list

Stdlib only, no PDK, no ``klt``, no virtualenv -- so it runs in the same
PDK-free CI job as the rest of ``.github/scripts/lint.sh`` (step 6/6).

Why this exists
---------------
Every drawn cell under ``layout/`` is signed off with a **pair** of ``klt
lvs`` runs: the intact cell, which must report ``status: match``, and a
deliberately-broken ``_shorted`` twin, which must report ``status:
mismatch``. The second run is the negative control -- the only evidence that
the first run's ``match`` means anything at all. Its committed report is the
proof that ``klt lvs`` can still tell a genuine short from an intact cell.

Issue #129 is what happens when that proof rots silently. A drift in the
installed ``klt``'s gf180mcu extraction deck (klayout-tools#1196, root-caused
below in ``layout/README.md``) rebound ``gf180_tmds_pad_v2``'s ESD-diode
anode from the cell's real drawn ``VSS`` tap onto the deck's synthesized
``vsubs`` global. The substituted net happened to size-match the reference
netlist's own separate ``VSS``, so the ``_shorted`` control flipped from the
intended ``mismatch`` to ``match`` -- a negative control that no longer
detects the short it was drawn to detect, reported by the tool as a clean
pass. Nothing in this repo noticed: the reports are committed artifacts, and
a committed artifact that says ``match`` looks like good news.

So the invariant is enforced here rather than merely documented: **a
``_shorted`` report that does not fail LVS fails the build.** A future deck
drift that defeats a negative control now has to argue with CI instead of
slipping through as a green ``match``.

What is checked, per ``layout/lvs_reports/<cell>.lvs.json``
-----------------------------------------------------------
1. The committed ``.json``/``.txt`` pair exists and **agrees** on ``status``
   and on the mismatch count. ``klt lvs`` emits one format per invocation, so
   the pair is necessarily two separate runs; ``layout/README.md``'s
   ``gf180_tmds_pad_ring_assembly`` section documents a real upstream
   flakiness (klayout-tools#1185) under which those two runs can land on
   *different* verdicts, leaving a self-contradicting committed pair. That
   agreement check is written down there as a manual step -- this makes it
   mechanical.
2. A negative control (top cell ending in ``_shorted``) reports ``status:
   mismatch`` **and** carries at least one ``severity: error`` finding. The
   error-severity half matters: ``klt lvs`` also emits ``severity: warning``
   topology notes on a perfectly clean cell, so "mismatch" alone could in
   principle be reached without any real, disqualifying finding.
3. Every other (intact) cell reports ``status: match``, unless it is listed
   in ``DOCUMENTED_MISMATCHES`` below -- an explicit, rationale-carrying
   allowlist, so an accepted mismatch is a deliberate, reviewed entry in this
   file rather than an unexplained red report nobody re-reads.

What is deliberately NOT checked
--------------------------------
Whether a committed report still *reproduces* against the currently-installed
``klt``. That needs ``klt`` (hence KLayout, hence a non-PDK-free job) and is
``klt lvs --check``'s job -- see ``layout/README.md``'s "Re-verifying a
committed LVS report" for the command and for the one negative-control
limitation ``--check --rerun`` currently has.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "layout" / "lvs_reports"

# Intact (non-``_shorted``) cells whose committed report is a ``mismatch``
# on purpose, each with the reason and where it is argued in full. Adding an
# entry here is a review decision: it silences rule 3 for exactly one report.
DOCUMENTED_MISMATCHES: dict[str, str] = {
    # `tmds_encoder` lived here until issue #142. Its mismatch was the 18
    # P&R-inserted standard-cell types (fill/tie/endcap/CTS/hold- and
    # setup-repair) that the *pre*-P&R reference netlist had no counterpart
    # for. The reference is now derived from the post-P&R netlist instead
    # (`layout/scripts/gen_tmds_encoder_ref.py --from-pnr`), the report is a
    # real `match`, and the entry is deliberately not replaced by a weaker
    # one -- an allowlist entry that outlives the mismatch it excused is how
    # the next genuine regression gets waved through.
}

# Suffixes marking a report as a deliberately-broken twin rather than an
# intact cell. `_shorted` is the layout-side convention (an extra metal
# bridge in the GDS: `gen_pad_v2.py --shorted`). `_negctl` marks a
# reference-side break, used where a layout-side twin cannot currently be
# extracted cleanly -- see `layout/README.md`'s `tmds_encoder` section and
# `gen_tmds_encoder_ref.py`'s `break_one_net()` for when that applies and why
# it is still a valid control.
NEGATIVE_CONTROL_SUFFIXES = ("_shorted", "_negctl")

# Header lines `klt lvs --format text` writes, e.g. "status: mismatch" and
# "mismatches: 7".
_TXT_FIELD = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.+?)\s*$")


def _error_count(report: dict) -> int:
    """Number of error-severity findings in a ``klt lvs`` JSON report.

    ``error_count`` is a newer top-level field; reports committed before it
    existed carry the same information per-finding, so fall back to counting
    ``mismatches[].severity`` rather than treating an older report as having
    zero errors (which would silently pass rule 2).
    """
    if isinstance(report.get("error_count"), int):
        return report["error_count"]
    return sum(
        1
        for finding in report.get("mismatches", [])
        if isinstance(finding, dict) and finding.get("severity") == "error"
    )


def _parse_txt_header(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        if line.startswith(" ") or not line.strip():
            continue
        match = _TXT_FIELD.match(line)
        if match:
            fields.setdefault(match.group("key"), match.group("value"))
    return fields


def _is_negative_control(report: dict, stem: str) -> bool:
    """True for a deliberately-broken twin.

    Classified from the report's own recorded layout ``top`` cell **or** the
    file stem -- either one carrying a `NEGATIVE_CONTROL_SUFFIXES` marker is
    enough. Both are consulted rather than only the authoritative ``top``,
    because a *reference*-side control (``_negctl``) leaves the layout ``top``
    at the intact cell's name by construction: the whole point is that the
    layout half is unchanged. Keying on ``top`` alone would misfile such a
    report as an intact cell reporting ``mismatch`` and fail the build for
    the control doing exactly its job.

    Erring toward classifying-as-control is the safe direction here only
    because rule 2 then *demands* the report fail; a misclassified intact
    cell that actually matches would be caught by rule 2's `expected
    'mismatch'` branch rather than slipping through.
    """
    top = report.get("top")
    names = [stem]
    if isinstance(top, str) and top:
        names.append(top)
    return any(n.endswith(s) for n in names for s in NEGATIVE_CONTROL_SUFFIXES)


def check_report(path: Path) -> tuple[list[str], dict]:
    """Check one ``<cell>.lvs.json`` (plus its ``.txt`` twin).

    Returns ``(failures, summary)``.
    """
    failures: list[str] = []
    stem = path.name[: -len(".lvs.json")]

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path}: unreadable JSON report: {exc}"], {}

    status = report.get("status")
    count = report.get("mismatch_count")
    errors = _error_count(report)
    negative_control = _is_negative_control(report, stem)
    summary = {
        "cell": stem,
        "status": status,
        "mismatches": count,
        "errors": errors,
        "kind": "negative control" if negative_control else "intact cell",
    }

    if status not in ("match", "mismatch"):
        failures.append(f"{path}: status is {status!r}, expected 'match' or 'mismatch'")
        return failures, summary

    # 1. the committed .txt must agree with the committed .json.
    txt_path = path.with_name(f"{stem}.lvs.txt")
    if not txt_path.is_file():
        failures.append(f"{txt_path}: missing text report for {path.name}")
    else:
        fields = _parse_txt_header(txt_path.read_text(encoding="utf-8"))
        txt_status = fields.get("status")
        if txt_status != status:
            failures.append(
                f"{txt_path}: status {txt_status!r} contradicts {path.name}'s "
                f"{status!r} -- the .txt and .json come from two separate "
                f"`klt lvs` runs that disagreed; re-run both and commit an "
                f"agreeing pair (layout/README.md, klayout-tools#1185)"
            )
        txt_count = fields.get("mismatches")
        if txt_count is not None and str(count) != txt_count:
            failures.append(
                f"{txt_path}: mismatches {txt_count} contradicts {path.name}'s "
                f"{count}"
            )

    # 2. a negative control must actually fail, on a real (error) finding.
    if negative_control:
        if status != "mismatch":
            failures.append(
                f"{path}: negative control reports {status!r}, expected "
                f"'mismatch'. A `_shorted` cell that passes LVS is a DEFEATED "
                f"negative control -- the intact cell's own `match` proves "
                f"nothing until this one fails again. Do not relax this "
                f"check; root-cause the extraction/reference divergence "
                f"(issue #129 is the worked example)."
            )
        elif errors < 1:
            failures.append(
                f"{path}: negative control reports 'mismatch' but carries 0 "
                f"error-severity findings ({count} warning-only) -- the short "
                f"it was drawn to expose is not what is failing LVS"
            )
    # 3. an intact cell must match, unless the mismatch is documented.
    elif status != "match":
        reason = DOCUMENTED_MISMATCHES.get(stem)
        if reason is None:
            failures.append(
                f"{path}: intact cell reports {status!r}, expected 'match'. "
                f"If this mismatch is understood and accepted, add {stem!r} to "
                f"DOCUMENTED_MISMATCHES in {Path(__file__).name} with the "
                f"rationale, and argue it in layout/README.md."
            )
        else:
            summary["kind"] = "intact cell (documented mismatch)"

    return failures, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check every committed klt lvs report under layout/lvs_reports/: "
            "negative controls (_shorted) must fail LVS, intact cells must "
            "pass, and each .json/.txt pair must agree."
        )
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the per-report verdict table as well as checking it",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORT_DIR,
        help=(
            "directory of klt lvs reports to check "
            f"(default: {REPORT_DIR.relative_to(REPO_ROOT)}). Used by "
            "layout/tests/ to run the checker against captured fixtures."
        ),
    )
    args = parser.parse_args(argv)

    reports = sorted(args.reports_dir.glob("*.lvs.json"))
    if not reports:
        print(f"FAIL: no klt lvs reports found under {args.reports_dir}")
        return 1

    failures: list[str] = []
    summaries: list[dict] = []
    for path in reports:
        report_failures, summary = check_report(path)
        failures.extend(report_failures)
        if summary:
            summaries.append(summary)

    if args.list:
        width = max(len(s["cell"]) for s in summaries)
        for summary in summaries:
            print(
                f"{summary['cell']:<{width}}  {summary['status']:<8} "
                f"{summary['mismatches']:>3} finding(s), "
                f"{summary['errors']:>3} error(s)  [{summary['kind']}]"
            )
        print()

    controls = sum(1 for s in summaries if s["kind"] == "negative control")
    if failures:
        for failure in failures:
            print(f"  {failure}")
        print(
            f"FAIL: {len(failures)} problem(s) across {len(reports)} LVS "
            f"report(s) ({controls} negative control(s))"
        )
        return 1

    print(
        f"PASS: {len(reports)} LVS report(s) consistent "
        f"({controls} negative control(s) still failing as designed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
