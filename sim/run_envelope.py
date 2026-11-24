#!/usr/bin/env python3
"""Write and verify the whole-grid ``klt sim`` envelopes T1 item 5 cites.

    python3 sim/run_envelope.py write <experiment> [--rate MBPS] [--record-id ID]
    klt sim sim/<experiment>/envelopes/<ID>.request.json --backend batch \
        --wait-for-capacity 600 --format json \
        --report-out sim/<experiment>/envelopes/<ID>.json -o sim/.work/envelopes/<ID>
    python3 sim/run_envelope.py verify <experiment> <ID>

``write`` derives a ``klt sim`` request (and its circuit body) from the
experiment's existing testbench definition -- the same DUT, fragment,
measures, limits and corner grid its Markdown records were taken against --
and commits them under ``sim/<experiment>/envelopes/<ID>.`` (``ID`` is a
fresh ``<record-id>``; nothing already written is ever overwritten). One
request covers the whole grid; a bench with per-rate transient windows
(``harness.klt_envelope.TRANSIENT_WINDOWS``) gets one request per rate,
each its own record. Every graded check is tagged with the DR-0013 row it
grades, read from ``signoff/analog-spec.json``, so ``klt signoff`` derives
the envelope's row coverage from the report itself.

The ``klt sim`` run itself is not driven from here: a multi-corner grid goes
to the batch fleet (``--wait-for-capacity`` per the host rule) and may
outlive any one shell, so the report is collected with ``--report-out``
straight into its committed path. ``verify`` then holds that report to the
bench's contract (``harness.klt_envelope.grid_problems``: ``klt sim``'s own
verdict, the full mandated grid exactly once, and the harness's grid-level
checks ``klt sim`` cannot grade) and prints the per-row worst case with its
binding corner. An envelope that fails ``verify`` is not cited.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = REPO_ROOT / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness import klt_envelope  # noqa: E402
from harness.batch import CAPACITY_WAIT_S  # noqa: E402
from harness.report import format_record_id, git_provenance  # noqa: E402
from harness.testbench import load as load_testbench  # noqa: E402

ENVELOPES_DIRNAME = "envelopes"
ANALOG_SPEC = REPO_ROOT / "signoff" / "analog-spec.json"
WORK_DIR = SIM_DIR / ".work" / ENVELOPES_DIRNAME
#: Problems ``verify`` lists before summarising the rest as a count.
MAX_PRINTED_PROBLEMS = 12


def spec_row_tags(tb) -> dict[str, str]:
    """Measurement name -> DR-0013 row id for this bench, from
    ``signoff/analog-spec.json``: every ``checks`` entry of every row's
    evidence names that row's graded checks in its testbench. A check the
    map grades for two different rows has no single ``spec_row`` and is
    refused."""
    doc = json.loads(ANALOG_SPEC.read_text())
    bench = f"sim/{tb.experiment}"
    tags: dict[str, str] = {}
    for row in doc["rows"]:
        for evidence in row.get("evidence") or []:
            if evidence.get("testbench") != bench:
                continue
            for check in evidence.get("checks") or []:
                other = tags.setdefault(check, row["id"])
                if other != row["id"]:
                    raise klt_envelope.EnvelopeError(
                        f"{ANALOG_SPEC.relative_to(REPO_ROOT)}: check {check!r} in {bench}"
                        f" is tagged with rows {other!r} and {row['id']!r}"
                    )
    return tags


def _envelopes_dir(tb) -> Path:
    return tb.experiment_dir / ENVELOPES_DIRNAME


def _mint_record_id(directory: Path) -> str:
    """A fresh ``<record-id>`` (sim/README.md's shape) with no envelope
    files under it yet; a same-second collision advances the timestamp."""
    short = git_provenance(REPO_ROOT)["short"]
    when = _dt.datetime.now(_dt.timezone.utc)
    while True:
        record_id = format_record_id(short, when)
        if not any(directory.glob(f"{record_id}.*")):
            return record_id
        when += _dt.timedelta(seconds=1)


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} already exists; envelopes are append-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def _write_one(tb, record_id: str, rate: float | None, slice_rate: bool) -> None:
    directory = _envelopes_dir(tb)
    body_name = f"{record_id}.body.spice"
    request_path = directory / f"{record_id}.request.json"
    body = klt_envelope.compose_body(tb, directory, rate, slice_rate=slice_rate)
    request = json.dumps(
        klt_envelope.build_request(
            tb, body_name, spec_rows=spec_row_tags(tb), rate=rate, slice_rate=slice_rate
        ),
        indent=2,
    ) + "\n"
    _write_new(directory / body_name, body)
    _write_new(request_path, request)
    report = directory / f"{record_id}.json"
    print(
        "run from the repo root:\n"
        f"  klt sim {request_path.relative_to(REPO_ROOT)} --backend batch"
        f" --wait-for-capacity {CAPACITY_WAIT_S} --format json \\\n"
        f"      --report-out {report.relative_to(REPO_ROOT)} -o {WORK_DIR.relative_to(REPO_ROOT)}/{record_id}\n"
        f"then: python3 sim/run_envelope.py verify {tb.experiment} {record_id}"
    )


def cmd_write(slug: str, record_id: str | None, rate: float | None) -> int:
    tb = load_testbench(SIM_DIR / slug)
    directory = _envelopes_dir(tb)
    if tb.experiment in klt_envelope.TRANSIENT_WINDOWS:
        rates = [rate] if rate is not None else list(tb.rates_mbps)
        if rate is not None and rate not in tb.rates_mbps:
            raise SystemExit(f"{slug}: {rate:g} Mbps is not one of its declared rates")
        if record_id is not None and len(rates) != 1:
            raise SystemExit("--record-id needs --rate: each rate slice is its own record")
        for r in rates:
            _write_one(tb, record_id or _mint_record_id(directory), r, slice_rate=True)
        return 0
    if rate is not None:
        raise SystemExit(f"{slug}: one request covers its whole grid; there is no --rate")
    _write_one(tb, record_id or _mint_record_id(directory), None, slice_rate=False)
    return 0


def _slice_of(tb, record_id: str) -> tuple[float | None, bool]:
    """``(rate, slice_rate)`` of the request that produced ``record_id``,
    read off its ``corners.params`` axis."""
    request = json.loads((_envelopes_dir(tb) / f"{record_id}.request.json").read_text())
    rates = set((request.get("corners") or {}).get("params", {}).get(klt_envelope.RATE_PARAM, []))
    if tb.experiment not in klt_envelope.TRANSIENT_WINDOWS:
        return None, False
    if len(rates) != 1:
        raise SystemExit(f"{record_id}: expected one rate in a per-rate request, found {sorted(rates)}")
    return rates.pop(), True


def _job_ids(report: dict) -> list[str]:
    remote = (report.get("environment") or {}).get("remote") or {}
    entries = remote.get("fleet") or [remote]
    return [str(e.get("job_id")) for e in entries if isinstance(e, dict) and e.get("job_id")]


def _print_rows(report: dict, tb) -> None:
    """Per measurement the envelope grades: limits, worst case and its
    binding corner, and the DR-0013 row it grades."""
    rollup = {m["name"]: m for m in report.get("measurements") or []}
    rows: dict[str, list[dict]] = {}
    for name, check in tb.checks.items():
        if klt_envelope.limits_of(check) is None:
            continue
        m = rollup.get(name) or {}
        rows.setdefault(str(m.get("spec_row") or "-"), []).append(m)
    print(f"{'row':>4}  {'measurement':16} {'limits':22} {'worst':>12}  {'margin':>10}  binding corner")
    for row in sorted(rows, key=lambda r: (r == "-", int(r) if r != "-" else 0)):
        for m in rows[row]:
            worst = m.get("worst_case") or {}
            margin = worst.get("margin")
            print(
                f"{row:>4}  {m.get('name'):16} {json.dumps(m.get('limits')):22}"
                f" {worst.get('value')!s:>12}  {margin if margin is None else f'{margin:.4g}':>10}"
                f"  {worst.get('corner_id')}"
            )


def cmd_verify(slug: str, record_id: str) -> int:
    tb = load_testbench(SIM_DIR / slug)
    path = _envelopes_dir(tb) / f"{record_id}.json"
    report = json.loads(path.read_text())
    environment = report.get("environment") or {}
    remote = environment.get("remote") or {}
    workers = [e.get("worker_environment") or {} for e in remote.get("fleet") or [remote]]
    stamps = sorted({(w.get("pdk") or {}).get("stamp_text") or "unreported" for w in workers})
    rate, slice_rate = _slice_of(tb, record_id)
    print(
        f"{path.relative_to(REPO_ROOT)}: status {report.get('status')},"
        f" {report.get('corner_count')} corners ({report.get('passed')} passed,"
        f" {report.get('failed')} failed, {report.get('errored')} errored),"
        f" fleet jobs {', '.join(_job_ids(report)) or 'none'},"
        f" ngspice-{environment.get('engine_version')} on the worker,"
        f" worker PDK {', '.join(stamps)}"
    )
    if slice_rate:
        print(f"rate slice {rate:g} Mbps/lane; analysis {klt_envelope.analysis_for(tb, rate)}")
    _print_rows(report, tb)
    problems = klt_envelope.grid_problems(report, tb, rate, slice_rate=slice_rate)
    for problem in problems[:MAX_PRINTED_PROBLEMS]:
        print(f"PROBLEM: {problem}")
    if len(problems) > MAX_PRINTED_PROBLEMS:
        print(f"PROBLEM: ... and {len(problems) - MAX_PRINTED_PROBLEMS} more")
    if problems:
        print(f"FAIL: {len(problems)} problem(s); do not cite this envelope")
        return 1
    print("PASS: whole-grid envelope passes klt sim and every harness check")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_envelope.py",
        description="Write and verify the whole-grid klt sim envelopes T1 item 5 cites.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write", help="write a fresh <ID>.body.spice + <ID>.request.json")
    write.add_argument("experiment", metavar="EXPERIMENT")
    write.add_argument("--record-id", default=None, help="use this record id instead of minting one")
    write.add_argument(
        "--rate", type=float, default=None,
        help="build only this rate's request (benches with per-rate transient windows)",
    )
    verify = sub.add_parser("verify", help="check a collected <ID>.json against its bench")
    verify.add_argument("experiment", metavar="EXPERIMENT")
    verify.add_argument("record_id", metavar="RECORD_ID")
    args = parser.parse_args(argv)
    try:
        if args.command == "write":
            return cmd_write(args.experiment, args.record_id, args.rate)
        return cmd_verify(args.experiment, args.record_id)
    except klt_envelope.EnvelopeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
