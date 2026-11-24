#!/usr/bin/env python3
"""``klt yield`` evidence for T1 item 6 (analog) -- issue #229.

    python3 sim/cml-driver-mismatch/run_yield.py write [--record-id ID] [--n 200]
    klt sim sim/cml-driver-mismatch/yield/<ID>/<request>.request.json --backend batch \\
        --wait-for-capacity 600 --format json \\
        --report-out sim/cml-driver-mismatch/yield/<ID>/<request>.json -o sim/.work/yield/<ID>/<request>
    python3 sim/cml-driver-mismatch/run_yield.py derive <ID> [--klt <klt>]

``klt signoff`` grades "statistical claims carry Monte Carlo evidence" (item
6) only from ``klt yield`` JSON reports, and refuses a report whose
``sample_size.verdict`` is ``insufficient`` or whose declared negative
control did not show the seeded degradation. This driver turns the
``sim/cml-driver-mismatch`` campaign (``run_mc.py``'s DUT, fragment, switch
and seeds -- unchanged) into that evidence:

- **Per process corner, never pooled.** Each corner gets its own Monte
  Carlo request, its own negative-control request and therefore its own
  ``klt yield`` report: the five corners are the deterministic axis item 5
  already grades, and item 6's claim is made *combined with* them, not
  instead (DR-0013's matrix is the process axis this campaign adds sample
  count against, at nominal temperature and supply as ``run_mc.py`` runs).
- **Sized.** ``n`` defaults to 200 per corner. With zero observed failures
  the 95 % Clopper-Pearson interval reaches the default +/-1 % half-width
  only at n >= 183, so 200 clears ``sample_size.verdict`` with margin.
- **A negative control that is itself a campaign.** ``klt yield-samples``
  derives the control from a second ``klt sim`` Monte Carlo report, never
  from a hand-edited one, so the control here is N samples of the same
  seeded defect ``run_mc.py`` uses -- ``par_tail_val=1e-4``, an artificially
  tiny Pelgrom area term on the tail mirror through gf180mcu's own
  unmodified mismatch mechanism -- drawn from a seed independent of the
  nominal campaign's.
- **Against the rows' own limits.** ``swing_dc`` (DR-0013 row 1, 400-600
  mV), ``vcm_dc`` (row 2, 2.8-3.3 V) and ``itail_dc`` (row 9, 8-12 mA --
  the quantity the dominant tail-mirror mismatch sets directly) carry their
  limits in the request, and ``klt yield`` reports Cpk / sigma-to-spec
  against them. No ``target_yield`` is declared because the ratified spec
  states none; the report's ``status`` is therefore ``reported``, which is
  the honest verdict for a campaign nothing could fail.

``write`` derives the bodies and requests and commits them under
``sim/cml-driver-mismatch/yield/<ID>/``; the ``klt sim`` runs go to the
batch fleet (``--wait-for-capacity`` per the host rule) and land in their
committed paths with ``--report-out``. ``derive`` then runs ``klt
yield-samples`` and ``klt yield`` per corner with the pinned grading build
(``klayout-tools[yield]==<pin>``, the extra ``klt yield`` needs), writes
``samples_<corner>.json`` / ``yield_<corner>.json`` beside the reports, and
refuses any report that would not grade: an insufficient sample, an
undetected control, an errored draw or a measurement outside its limits.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness import batch  # noqa: E402
from harness.corners import CORNER_SETS, CORNERS  # noqa: E402
from harness.klt_envelope import MODELS_PARAM_FILE  # noqa: E402
from harness.pdk import find_pdk  # noqa: E402
from harness.report import format_record_id, git_provenance  # noqa: E402

YIELD_DIRNAME = "yield"
WORK_DIR = SIM_DIR / ".work" / YIELD_DIRNAME
PROCESS_CORNERS = [CORNERS[name] for name in CORNER_SETS["mos"]]

#: Samples per corner, nominal and control alike. 183 is the zero-failure
#: 95 % Clopper-Pearson requirement for a +/-1 % half-width; 200 clears it.
DEFAULT_N = 200
BASE_SEED = 20260814
#: The control's seeds sit a fixed offset from the nominal campaign's so the
#: two draws are independent (klt yield.md, "Negative control").
CONTROL_SEED_OFFSET = 500_000
NEG_CTRL_PAR_TAIL = 1e-4
TEMP_C = 27.0
VDD_V = 3.30
PAR_PAIR, PAR_TAIL, PAR_MIRROR = 64, 200, 10

#: gf180mcu's vendor deck is HSPICE-style; run_mc.py requests the same
#: compatibility mode, so this campaign's decks differ from its by content
#: only where this driver says so.
NGSPICE_INIT = ("set ngbehavior=hsa",)
#: An ``.op`` unit takes well under a second; 15 s keeps a 200-sample request
#: inside the fleet's whole-job ceiling as one job (200 x 15 s + 120 s).
TIMEOUT_S = 15

MEASUREMENTS = [
    {"name": "swing_dc", "expr": "v(outn)-v(outp)", "spec_row": "1",
     "limits": {"min": 0.4, "max": 0.6}},
    {"name": "vcm_dc", "expr": "(v(outn)+v(outp))/2", "spec_row": "2",
     "limits": {"min": 2.8, "max": 3.3}},
    {"name": "itail_dc", "expr": "((v(avcc)-v(outp))+(v(avcc)-v(outn)))/50", "spec_row": "9",
     "limits": {"min": 8e-3, "max": 12e-3}},
]
CONTROL_DESCRIPTION = (
    "par_tail_val=1e-4 (nominal 200): an artificially tiny Pelgrom area term on the"
    " tail-mirror device, through gf180mcu's own unmodified nfet_03v3_dss mismatch"
    " mechanism; seed independent of the nominal campaign"
)


def _mint_record_id(directory: Path) -> str:
    short = git_provenance(REPO_ROOT)["short"]
    when = _dt.datetime.now(_dt.timezone.utc)
    while True:
        record_id = format_record_id(short, when)
        if not (directory / record_id).exists():
            return record_id
        when += _dt.timedelta(seconds=1)


def _seed(index: int, control: bool) -> int:
    """First sample's seed of corner ``index``: ``base + k*1000 + 1`` as
    ``run_mc.py`` numbers its samples (``seed_mode: sequential`` then gives
    sample i the seed ``base + k*1000 + i``), offset for the control."""
    return BASE_SEED + (CONTROL_SEED_OFFSET if control else 0) + index * 1000 + 1


def compose_body(*, sw_stat_mismatch: int, par_tail: float, dut_rel: str, fragment_rel: str) -> str:
    """One circuit body: the mismatch switch and Pelgrom-area parameters, then
    the mismatch DUT and the static-steering fragment. The model sections,
    the PDK design include (``models.param_file``), ``.temp``, ``.options
    seed`` and the ``.op`` analysis are request fields ``klt sim`` writes."""
    return "\n".join(
        [
            "* cml-driver-mismatch -- klt yield campaign body (T1 item 6, run_yield.py)",
            f"* sw_stat_mismatch={sw_stat_mismatch} par_tail_val={par_tail!r}"
            f" par_pair_val={PAR_PAIR!r} par_mirror_val={PAR_MIRROR!r}",
            f".param vdd_val={VDD_V!r}",
            f".param par_pair_val={PAR_PAIR!r}",
            f".param par_tail_val={par_tail!r}",
            f".param par_mirror_val={PAR_MIRROR!r}",
            f".param sw_stat_mismatch={sw_stat_mismatch}",
            f'.include "{dut_rel}"',
            f'.include "{fragment_rel}"',
            "",
        ]
    )


def _request(pdk, body_name: str, corners, *, n, seed, sw_stat_mismatch) -> dict:
    request = batch.build_mc_request(
        pdk, corners, body_name, measurements=MEASUREMENTS, temp_c=TEMP_C,
        n=n, seed=seed, backend="batch", ngspice_init=NGSPICE_INIT, timeout_s=TIMEOUT_S,
    )
    request["models"]["param_file"] = MODELS_PARAM_FILE
    request["options"]["keep_artifacts"] = False
    request["batch"]["job_ceiling_check"] = "split"
    request["netlist_source"] = "schematic"
    return request


def campaign_files(directory: Path, n: int, pdk) -> dict[str, str]:
    """Every file of the campaign under ``directory``: the three bodies
    (nominal, control, mismatch-off reference) and one request per
    process corner for the nominal and the control campaign, plus the
    five-corner mismatch-off reference request."""
    root = SIM_DIR / "cml-driver-mismatch"
    dut_rel = os.path.relpath(root / "testbench" / "cml_driver_dut_mismatch.spice", directory).replace(os.sep, "/")
    fragment_rel = os.path.relpath(root / "testbench" / "cml_driver_mismatch.spice", directory).replace(os.sep, "/")
    bodies = {
        "mc": compose_body(sw_stat_mismatch=1, par_tail=PAR_TAIL, dut_rel=dut_rel, fragment_rel=fragment_rel),
        "negctl": compose_body(sw_stat_mismatch=1, par_tail=NEG_CTRL_PAR_TAIL, dut_rel=dut_rel, fragment_rel=fragment_rel),
        "nominal": compose_body(sw_stat_mismatch=0, par_tail=PAR_TAIL, dut_rel=dut_rel, fragment_rel=fragment_rel),
    }
    requests = [
        (f"mc_{corner.name}", "mc", [corner], n, _seed(k, control=False), 1)
        for k, corner in enumerate(PROCESS_CORNERS)
    ] + [
        (f"negctl_{corner.name}", "negctl", [corner], n, _seed(k, control=True), 1)
        for k, corner in enumerate(PROCESS_CORNERS)
    ] + [("nominal", "nominal", PROCESS_CORNERS, None, None, 0)]
    files = {f"{name}.body.spice": body for name, body in bodies.items()}
    for name, body, corners, samples, seed, switch in requests:
        files[f"{name}.request.json"] = json.dumps(
            _request(pdk, f"{body}.body.spice", corners, n=samples, seed=seed, sw_stat_mismatch=switch),
            indent=2,
        ) + "\n"
    return files


def cmd_write(record_id: str | None, n: int) -> int:
    root = SIM_DIR / "cml-driver-mismatch" / YIELD_DIRNAME
    record_id = record_id or _mint_record_id(root)
    directory = root / record_id
    rel = os.path.relpath(directory, REPO_ROOT)
    files = campaign_files(directory, n, find_pdk())
    if directory.exists():
        raise SystemExit(f"{rel} already exists; yield campaigns are append-only")
    directory.mkdir(parents=True)
    for name, text in files.items():
        (directory / name).write_text(text)
        print(f"wrote {rel}/{name}")
    print("run each from the repo root, then `derive`:")
    for name in files:
        if not name.endswith(".request.json"):
            continue
        stem = name[: -len(".request.json")]
        print(
            f"  klt sim {rel}/{name} --backend batch --wait-for-capacity"
            f" {batch.CAPACITY_WAIT_S} --format json --report-out {rel}/{stem}.json"
            f" -o {os.path.relpath(WORK_DIR / record_id / stem, REPO_ROOT)}"
        )
    print(f"  python3 sim/cml-driver-mismatch/run_yield.py derive {record_id}")
    return 0


def _run(klt: str, argv: list[str]) -> str:
    """``klt``'s stdout for ``argv``, verbatim: the committed documents are
    the tool's own bytes, never a re-serialization of them."""
    proc = subprocess.run([klt, *argv], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 3, 4) or not proc.stdout.strip():
        raise SystemExit(f"{' '.join(argv)}: exit {proc.returncode}\n{proc.stderr.strip()[-2000:]}")
    return proc.stdout


def report_problems(yield_report: dict, n: int) -> list[str]:
    """Why ``yield_report`` would not grade ``met`` for item 6 -- empty when
    it would: exactly one result per requested measurement with the declared
    limits, every measurement sized ``sufficient``, its negative control
    ``detected``, no errored or inconclusive draw, and its observed span
    inside the row's limits."""
    problems: list[str] = []
    if yield_report.get("status") not in ("pass", "reported"):
        problems.append(f"klt yield status {yield_report.get('status')!r}")
    measurements = yield_report.get("measurements") or []
    expected = {m["name"]: m["limits"] for m in MEASUREMENTS}
    counts = Counter(m.get("name") for m in measurements)
    for name in expected:
        if counts[name] != 1:
            problems.append(f"{name}: {counts[name]} results, expected exactly 1")
    for m in measurements:
        name = m.get("name")
        if name not in expected:
            problems.append(f"unexpected measurement {name!r}")
            continue
        limits = expected[name]
        if m.get("limits") != limits:
            problems.append(f"{name}: reported limits {m.get('limits')!r}, expected {limits!r}")
        sample_size = m.get("sample_size") or {}
        if sample_size.get("verdict") != "sufficient":
            problems.append(f"{name}: sample_size.verdict {sample_size.get('verdict')!r}")
        if m.get("n") != n:
            problems.append(f"{name}: {m.get('n')} usable samples, expected {n}")
        if (m.get("errored") or 0) or (m.get("inconclusive") or 0):
            problems.append(
                f"{name}: {m.get('errored')} errored, {m.get('inconclusive')} inconclusive draws"
            )
        control = m.get("negative_control") or {}
        if control.get("verdict") != "detected":
            problems.append(f"{name}: negative_control.verdict {control.get('verdict')!r}")
        dist = m.get("distribution") or {}
        low, high = limits.get("min"), limits.get("max")
        if low is not None and (dist.get("min") is None or dist["min"] < low):
            problems.append(f"{name}: min {dist.get('min')!r} below limit {low!r}")
        if high is not None and (dist.get("max") is None or dist["max"] > high):
            problems.append(f"{name}: max {dist.get('max')!r} above limit {high!r}")
    return problems


def cmd_derive(record_id: str, klt: str, n: int) -> int:
    directory = SIM_DIR / "cml-driver-mismatch" / YIELD_DIRNAME / record_id
    rel = os.path.relpath(directory, REPO_ROOT)
    failed = 0
    for corner in PROCESS_CORNERS:
        samples = f"{rel}/samples_{corner.name}.json"
        derived = _run(
            klt,
            [
                "yield-samples", f"{rel}/mc_{corner.name}.json",
                "--negative-control", f"{rel}/negctl_{corner.name}.json",
                "--description", CONTROL_DESCRIPTION, "--format", "json",
            ],
        )
        (REPO_ROOT / samples).write_text(derived)
        text = _run(klt, ["yield", samples, "--format", "json"])
        (REPO_ROOT / rel / f"yield_{corner.name}.json").write_text(text)
        yield_report = json.loads(text)
        problems = report_problems(yield_report, n)
        print(
            f"{rel}/yield_{corner.name}.json: klt yield status {yield_report.get('status')},"
            f" {len(problems)} problem(s)"
        )
        for m in yield_report.get("measurements") or []:
            cap = m.get("capability") or {}
            control = m.get("negative_control") or {}
            dist = m.get("distribution") or {}
            print(
                f"  {m['name']:9s} n={m.get('n')} mean={dist.get('mean')!r} sigma={dist.get('stddev')!r}"
                f" cpk={cap.get('cpk')!r} sigma_to_spec={cap.get('sigma_to_spec')!r}"
                f" control={control.get('verdict')!r}"
                f" (control yield {((control.get('yield') or {}).get('empirical') or {}).get('estimate')!r})"
                f" sample_size={(m.get('sample_size') or {}).get('verdict')!r}"
                f" required_n={(m.get('sample_size') or {}).get('required_n')!r}"
            )
        for problem in problems:
            print(f"  PROBLEM: {problem}")
        failed += bool(problems)
    if failed:
        print(f"FAIL: {failed} report(s) would not grade; do not cite them")
        return 1
    print("PASS: every corner's klt yield report is sized, self-checked and inside its limits")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_yield.py",
        description="Write and derive the klt yield evidence T1 item 6 (analog) cites.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write", help="write the campaign's bodies and requests")
    write.add_argument("--record-id", default=None)
    write.add_argument("--n", type=int, default=DEFAULT_N, help="samples per corner (default 200)")
    derive = sub.add_parser("derive", help="klt yield-samples + klt yield per corner")
    derive.add_argument("record_id")
    derive.add_argument("--n", type=int, default=DEFAULT_N)
    derive.add_argument("--klt", default="klt", help="klt binary with the `yield` extra")
    args = parser.parse_args(argv)
    if args.command == "write":
        return cmd_write(args.record_id, args.n)
    return cmd_derive(args.record_id, args.klt, args.n)


if __name__ == "__main__":
    raise SystemExit(main())
