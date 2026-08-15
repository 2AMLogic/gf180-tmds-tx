#!/usr/bin/env python3
"""Compare two evidence records of the same experiment, corner by corner.

    python3 sim/compare_records.py <experiment> <baseline-id> <candidate-id>
    python3 sim/compare_records.py cml-driver-eye 20260810-041436-a2c358b \
        20260815-063054-997527e --measurements swing_c0,vcm_c0,dj_ui_c2

`sim/README.md` requires a post-layout (`Netlist provenance: extracted`)
re-run to report its delta against the schematic-level record it re-runs --
that is what the **Supersedes** field is for. Doing that by eye across a
90-point grid and ~46 measurements is exactly the kind of transcription a
reader cannot check, so the comparison is computed here instead: this reads
the per-corner result tables out of two records in the same experiment
directory and reports, per measurement, the worst absolute and relative
delta and the corner it occurs at.

Records are append-only evidence -- this script only ever *reads* them, and
writes its table to stdout for a human-authored analysis document
(`measurements/characterization.md`) to cite. It intentionally has no
pass/fail opinion: it reports deltas, and a person explains them.

stdlib only (`sim/harness/README.md`: python3 >= 3.9, no venv, no packages).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = REPO_ROOT / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness.evidence_lint import RECORD_ID_RE as _RECORD_ID_RE  # noqa: E402
from harness.report import _fmt  # noqa: E402


class RecordError(RuntimeError):
    pass


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_results(path: Path) -> tuple[list[str], dict[str, dict[str, float]], dict[str, str]]:
    """Return (measurement names, {corner-id: {name: value}}, {corner-id: verdict}).

    The per-corner table is the one whose header row starts with
    ``corner-id`` (``sim/harness/report.py``'s ``render_record``); every
    other table in the record is ignored.
    """
    names: list[str] = []
    values: dict[str, dict[str, float]] = {}
    verdicts: dict[str, str] = {}
    in_table = False

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            # A markdown table is contiguous: the first non-row line ends it.
            # Without this the record's *other* tables (the spread summary
            # that follows the per-corner one) would be parsed as corners.
            in_table = False
            continue
        cells = _cells(stripped)
        if not cells:
            continue
        if cells[0] == "corner-id":
            names = [c for c in cells[1:] if c != "pass/fail"]
            in_table = True
            continue
        if not in_table or set(cells[0]) <= {"-", ":"}:
            continue
        corner = cells[0].strip("`")
        row = cells[1:]
        if len(row) < len(names):
            continue
        point: dict[str, float] = {}
        for name, cell in zip(names, row):
            try:
                point[name] = float(cell)
            except ValueError:
                point[name] = float("nan")
        values[corner] = point
        if len(row) > len(names):
            verdicts[corner] = row[len(names)]

    if not names or not values:
        raise RecordError(f"{path}: no per-corner result table found")
    return names, values, verdicts


def record_path(experiment: str, record_id: str) -> Path:
    if not _RECORD_ID_RE.match(record_id):
        raise RecordError(f"{record_id!r} is not a <YYYYMMDD>-<HHMMSS>-<sha> record id")
    path = SIM_DIR / experiment / "records" / f"{record_id}.md"
    if not path.exists():
        raise RecordError(f"no such record: {path}")
    return path


def provenance(path: Path) -> str:
    match = re.search(r"^- \*\*Netlist provenance\*\*: (.+)$", path.read_text(), re.M)
    if not match:
        return "(unstated)"
    return match.group(1).split("—")[0].strip()


def compare(
    baseline: Path, candidate: Path, wanted: list[str] | None = None
) -> tuple[list[dict], list[str], list[str]]:
    names_a, values_a, verdicts_a = parse_results(baseline)
    names_b, values_b, verdicts_b = parse_results(candidate)

    common_corners = sorted(set(values_a) & set(values_b))
    if not common_corners:
        raise RecordError("the two records share no corner-id")

    names = [n for n in names_a if n in set(names_b)]
    if wanted:
        missing = [n for n in wanted if n not in names]
        if missing:
            raise RecordError(f"measurement(s) not in both records: {missing}")
        names = [n for n in names if n in wanted]

    rows: list[dict] = []
    for name in names:
        worst_abs = None
        for corner in common_corners:
            a = values_a[corner].get(name, float("nan"))
            b = values_b[corner].get(name, float("nan"))
            if a != a or b != b:
                continue
            delta = b - a
            if worst_abs is None or abs(delta) > abs(worst_abs["delta"]):
                worst_abs = {
                    "corner": corner,
                    "a": a,
                    "b": b,
                    "delta": delta,
                    "rel": (delta / a * 100.0) if a else float("nan"),
                }
        if worst_abs is None:
            continue
        worst_rel = None
        for corner in common_corners:
            a = values_a[corner].get(name, float("nan"))
            b = values_b[corner].get(name, float("nan"))
            if a != a or b != b or not a:
                continue
            rel = (b - a) / a * 100.0
            if worst_rel is None or abs(rel) > abs(worst_rel["rel"]):
                worst_rel = {"corner": corner, "rel": rel}
        rows.append({"measurement": name, "abs": worst_abs, "rel": worst_rel})

    only_a = sorted(set(values_a) - set(values_b))
    only_b = sorted(set(values_b) - set(values_a))

    verdict_diffs = [
        f"{corner}: {verdicts_a.get(corner, '?')} -> {verdicts_b.get(corner, '?')}"
        for corner in common_corners
        if verdicts_a.get(corner) != verdicts_b.get(corner)
    ]
    return rows, only_a + only_b, verdict_diffs


def render(
    rows: list[dict],
    experiment: str,
    baseline_id: str,
    candidate_id: str,
    baseline: Path,
    candidate: Path,
    unmatched: list[str],
    verdict_diffs: list[str],
) -> str:
    out = [
        f"# {experiment}: {baseline_id} -> {candidate_id}",
        "",
        f"- baseline  `{baseline_id}` — netlist provenance: {provenance(baseline)}",
        f"- candidate `{candidate_id}` — netlist provenance: {provenance(candidate)}",
        "",
        "Worst per-corner delta (candidate − baseline) over the corners both",
        "records share.",
        "",
        "| measurement | baseline @ worst | candidate @ worst | Δ | Δ % | at corner | worst Δ % |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        worst = row["abs"]
        rel = row["rel"]
        out.append(
            f"| `{row['measurement']}` | {_fmt(worst['a'])} | {_fmt(worst['b'])} | "
            f"{_fmt(worst['delta'])} | {_fmt(worst['rel'])} | `{worst['corner']}` | "
            f"{_fmt(rel['rel'])} @ `{rel['corner']}` |"
        )
    if unmatched:
        out += ["", "Corners present in only one record: " + ", ".join(unmatched)]
    out += [
        "",
        "Per-corner verdict changes: "
        + (", ".join(verdict_diffs) if verdict_diffs else "none"),
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("experiment", help="experiment slug under sim/")
    parser.add_argument("baseline", help="baseline <record-id>")
    parser.add_argument("candidate", help="candidate <record-id>")
    parser.add_argument(
        "--measurements",
        default="",
        help="comma-separated subset of measurements (default: all shared)",
    )
    args = parser.parse_args(argv)

    wanted = [m.strip() for m in args.measurements.split(",") if m.strip()]
    try:
        baseline = record_path(args.experiment, args.baseline)
        candidate = record_path(args.experiment, args.candidate)
        rows, unmatched, verdict_diffs = compare(baseline, candidate, wanted or None)
    except RecordError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        render(
            rows,
            args.experiment,
            args.baseline,
            args.candidate,
            baseline,
            candidate,
            unmatched,
            verdict_diffs,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
