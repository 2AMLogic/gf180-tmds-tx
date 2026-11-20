#!/usr/bin/env python3
"""Monte Carlo local-mismatch sweep of the CML driver's DR-0002 swing/
common-mode (issue #23, part of epic #17's T1 evidence ladder).

    python3 sim/cml-driver-mismatch/run_mc.py                 # run, mint a record
    python3 sim/cml-driver-mismatch/run_mc.py --no-write       # debug, record nothing
    python3 sim/cml-driver-mismatch/run_mc.py --n-samples 50

How it runs: a Monte Carlo mismatch claim needs N independent, randomly-seeded
samples *per* process corner plus a deterministic negative control that must
fail -- an axis the harness's PVT grid has none of. It is expressed as `klt sim`
requests with `monte_carlo` (`sim/harness/batch.py`'s `build_mc_request` /
`submit_request`, the same boundary every PVT bench uses; the dispatch-worker
rules forbid a hand-launched `ngspice -b` grid): one `monte_carlo` request per
process corner and one deterministic mismatch=0 multi-corner request go to the
batch fleet; the negative control is a single-unit request run locally. The
`par_pair`/`par_tail`/`par_mirror` values and the `sw_stat_mismatch` switch live
in the generated circuit body; the per-sample seed is `klt sim`'s `seed_mode:
sequential` (see `render_record`). PDK discovery (`sim/harness/pdk.py`), the
five process corners (`sim/harness/corners.py`) and the device-level evidence
plumbing in `sim/harness/report.py` are reused. The raw per-sample results
(each `klt sim` report corner entry) are manifest-forward: staged by
`write_device_corner_log` into `evidence_store.stage_dir(...)` (git-ignored),
stored with `evidence_store.store_run` (`klt artifact put`), and only the
resulting manifest plus the summary record are committed.

## What is measured, and why a DC operating point

DR-0002's swing/common-mode claim is a *static* one: cml_driver_eye.spice's
own comment records vcm = avcc - I_tail*R/2 -- set by the driver's tail
current against the termination resistor once the differential pair is
fully steered, not by transient switching behaviour. This experiment
statically steers one lane of the driver (mirroring
sim/cml-driver-eye/testbench/cml_driver_eye.spice's own "_z" copy) and
measures swing_dc = v(outn)-v(outp), vcm_dc = (v(outn)+v(outp))/2 -- a cheap
`.op` analysis, which is what makes an N-sample statistical claim tractable
at all (a per-sample transient eye run, as cml-driver-eye performs
deterministically, would multiply this experiment's run count by the
transient solver's cost for no benefit to a claim that is fundamentally
about a settled DC level).

## Where the mismatch comes from

gf180mcu ships local (intra-die) device mismatch as part of its own model
library (sm141064.ngspice): the `nfet_03v3_dss` subcircuit wraps the
ordinary `nfet_03v3` BSIM4 instance with gf180mcu's own Pelgrom-law
delvto/mulu0 injection, gated by the `sw_stat_mismatch` switch
(design.ngspice default: 0 -- off, matching every other experiment in this
repo, which never touches it). `cml_driver_dut_mismatch.spice` -- a
minimal, documented fork of sim/cml-driver-eye/testbench/cml_driver_dut.spice
that swaps all four transistors from `nfet_03v3` to `nfet_03v3_dss` and
nothing else -- is this experiment's own DUT copy; see that file's header
for the exact substitution and the par_pair/par_tail/par_mirror parameters
this script drives.

## The negative control

gf180mcu's own realistic mismatch coefficients, at this driver's device
sizes, are small (a fraction of a mV of delvto -- see the record). A
Monte Carlo check that only ever sees realistic mismatch never actually
exercises its own FAIL path, which is exactly the "prove the check isn't
vacuous" requirement: `nfet_03v3_dss`'s `par` argument scales only the
Pelgrom AREA term (not the transistor's real electrical w/l/nf/m -- see
cml_driver_dut_mismatch.spice's header), so passing an artificially tiny
`par_tail_val` to the SAME unmodified mismatch machinery injects an
artificially large, deterministic (fixed seed), reproducible mismatch on
the tail mirror. `main()` asserts this point actually violates the DR-0002
window before writing any record; if it does not (e.g. gf180mcu's model
library changes underfoot), it aborts loudly instead of writing a record
that would silently claim a validated check that this run did not validate.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness import batch, evidence_store  # noqa: E402
from harness.corners import CORNER_SETS, CORNERS, Corner  # noqa: E402
from harness.pdk import Pdk, PdkNotFound, find_pdk  # noqa: E402
from harness.report import (  # noqa: E402
    device_write_record,
    environment,
    git_provenance,
    allocate_record_id,
    write_device_corner_log,
    write_device_netlist_snapshot,
)

EXPERIMENT_DIR = SIM_DIR / "cml-driver-mismatch"
TESTBENCH_DIR = EXPERIMENT_DIR / "testbench"
DUT_PATH = TESTBENCH_DIR / "cml_driver_dut_mismatch.spice"
FRAGMENT_PATH = TESTBENCH_DIR / "cml_driver_mismatch.spice"
SNAPSHOT_DIR = EXPERIMENT_DIR / "netlist-snapshots"
RECORDS_DIR = EXPERIMENT_DIR / "records"

CLAIM = (
    "spec/tmds-tx.md#dr-0002 -- single-ended swing 400-600 mV and common "
    "mode 2.8-3.3 V into 50 ohm/leg with a ~10 mA tail -- under gf180mcu "
    "local (intra-die) device mismatch, combined with the process-corner "
    "matrix sim/cml-driver-eye already validates deterministically."
)

TEMP_C = 27.0
VDD_V = 3.30

# Nominal Pelgrom-area scale for each device (nf*m -- see
# cml_driver_dut_mismatch.spice's header for why this is the standard
# multi-finger/multi-copy mismatch-averaging convention, and why it is
# decoupled from the transistor's real electrical width/current).
PAR_PAIR_NOMINAL = 64
PAR_TAIL_NOMINAL = 200
PAR_MIRROR_NOMINAL = 10

# Negative control: an artificially tiny par_tail_val on the SAME unmodified
# nfet_03v3_dss mismatch machinery (~1/2,000,000th of the nominal Pelgrom
# area term on the tail-mirror device), at a fixed seed empirically verified
# (see the record) to push swing_dc/vcm_dc outside DR-0002's window.
NEG_CTRL_PAR_TAIL = 1e-4

DR0002_SWING_MIN, DR0002_SWING_MAX = 0.4, 0.6
DR0002_VCM_MIN, DR0002_VCM_MAX = 2.8, 3.3


@dataclass
class Sample:
    corner_id: str
    corner: Corner
    label: str  # "nominal" | "mc<NNN>" | "mcneg"
    seed: int | None  # None: deterministic point (no `.options seed`)
    sw_stat_mismatch: int
    par_pair: float
    par_tail: float
    par_mirror: float
    status: str = "pending"
    swing_dc: float | None = None
    vcm_dc: float | None = None
    seconds: float = 0.0
    log: str = ""


#: gf180mcu's vendor deck is HSPICE-style; the pre-migration record ran with
#: ngspice's `hs a` compatibility mode from the host's ~/.spiceinit. Request it
#: explicitly so the run does not depend on any host's init file.
NGSPICE_INIT = ("set ngbehavior=hsa",)

#: The two DC measures, as `klt sim` request measurements over the `.op` result.
MEASUREMENTS = [
    {"name": "swing_dc", "expr": "v(outn)-v(outp)"},
    {"name": "vcm_dc", "expr": "(v(outn)+v(outp))/2"},
]


def write_body(
    pdk: Pdk, path: Path, *, sw_stat_mismatch: int, par_pair: float, par_tail: float, par_mirror: float
) -> None:
    """Circuit body for one request: parameters, the PDK design include, the
    mismatch switch, then the DUT and testbench fragment. The model `.lib`
    sections, `.temp`, `.options seed` and the `.op` analysis are request
    fields `klt sim` writes itself."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "* cml-driver-mismatch -- GENERATED by sim/cml-driver-mismatch/run_mc.py, do not edit",
                f".param vdd_val={VDD_V!r}",
                f".param par_pair_val={par_pair!r}",
                f".param par_tail_val={par_tail!r}",
                f".param par_mirror_val={par_mirror!r}",
                f'.include "{pdk.design_include}"',
                f".param sw_stat_mismatch={sw_stat_mismatch}",
                f'.include "{DUT_PATH}"',
                f'.include "{FRAGMENT_PATH}"',
                "",
            ]
        )
    )


def _run(pdk, workdir, name, corners, *, sw_stat_mismatch, par_tail, n, seed, backend,
         stage_model_inputs=False):
    """Write body + request ``name`` and submit it; return (report, transcript).

    ``stage_model_inputs`` reaches only the batch requests (see
    ``batch.build_mc_request``); the local negative control keeps running on
    this host's own models."""
    body = f"{name}.body.spice"
    write_body(
        pdk, workdir / body, sw_stat_mismatch=sw_stat_mismatch,
        par_pair=PAR_PAIR_NOMINAL, par_tail=par_tail, par_mirror=PAR_MIRROR_NOMINAL,
    )
    request = batch.build_mc_request(
        pdk, corners, body, measurements=MEASUREMENTS, temp_c=TEMP_C,
        n=n, seed=seed, backend=backend, ngspice_init=NGSPICE_INIT,
        stage_model_inputs=stage_model_inputs,
    )
    request_path = workdir / f"{name}.request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    return batch.submit_request(request_path, workdir / f"{name}.out", backend=backend)


def _sample_identity(entry, raw_cid, *, need_index):
    """``(sample_index, reported_seed)`` for one report corner entry.

    The report's ``monte_carlo`` block is authoritative; the trailing ``mcN`` of
    the corner id is the fallback for an entry without it. ``reported_seed`` is
    ``None`` when the report does not state one (the caller then derives it).
    A Monte Carlo entry with no recoverable index is a ``BatchError``."""
    mc = entry.get("monte_carlo")
    mc = mc if isinstance(mc, dict) else {}
    index = mc.get("sample_index")
    if isinstance(index, bool) or not isinstance(index, int):
        m = re.search(r"mc(\d+)$", raw_cid)
        index = int(m.group(1)) if m else None
    seed = mc.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        seed = None
    if need_index and index is None:
        raise batch.BatchError(
            f"corner {raw_cid!r}: Monte Carlo entry has neither monte_carlo.sample_index "
            "nor a trailing mcN in its corner id"
        )
    return index, seed


def _samples_from_report(report, corners, label_of, par_tail, sw, seed_of, *, need_index=False):
    """Map a `klt sim` report's corner entries to Samples; a unit with no
    values stays status ``error`` (never dropped from N). Sample index and
    seed come from the entry's ``monte_carlo`` block; ``seed_of`` is only the
    fallback when the report states no seed."""
    by_name = {c.name: c for c in corners}
    out = []
    for entry in report.get("corners") or []:
        raw_cid = str(entry.get("corner_id", ""))
        corner = by_name[raw_cid.split("/")[0].split("_")[0]]  # mos corner names carry no underscore
        index, reported_seed = _sample_identity(entry, raw_cid, need_index=need_index)
        label = label_of(index)
        # Ratified corner-id grammar (sim/README.md): <process>_<temp>c_<supply>;
        # the sample label rides in the process field (`tt_mc001`), as before.
        cid = f"{corner.name}_{label}_{TEMP_C:g}c_{VDD_V:.2f}v"
        values = batch.corner_values(entry)
        ok = (
            entry.get("status") not in ("error", "inconclusive")
            and "swing_dc" in values and "vcm_dc" in values
        )
        out.append(
            Sample(
                corner_id=cid, corner=corner, label=label,
                seed=reported_seed if reported_seed is not None else seed_of(corner, index),
                sw_stat_mismatch=sw,
                par_pair=PAR_PAIR_NOMINAL, par_tail=par_tail, par_mirror=PAR_MIRROR_NOMINAL,
                status="ok" if ok else "error",
                swing_dc=values.get("swing_dc"), vcm_dc=values.get("vcm_dc"),
                seconds=float(entry.get("runtime_s") or 0.0),
                log=json.dumps(entry, indent=2, sort_keys=True) + "\n",
            )
        )
    return out


def run_all(pdk: Pdk, workdir: Path, n_samples: int, base_seed: int,
            stage_model_inputs: bool = False):
    """Submit the sweep: one Monte Carlo request per process corner (fleet),
    one deterministic mismatch=0 request over all corners (fleet), and the
    single-unit negative control (the one run host rules allow locally).
    ``stage_model_inputs`` opts the fleet requests into
    ``options.stage_model_inputs`` (this client's own model closure); the
    local negative control is unchanged either way.

    Returns ``(samples, job_ids, ngspice)`` where ``ngspice`` is the engine
    version(s) the reports state (not this host's probe). Raises ``batch.BatchError`` on a failed
    submit -- there is no local fallback."""
    corners = [CORNERS[name] for name in CORNER_SETS["mos"]]
    samples: list[Sample] = []
    jobs: list[str] = []
    reports: list[dict] = []

    def job_of(report):
        remote = (report.get("environment") or {}).get("remote") or {}
        return str(remote.get("job_id") or "")

    for k, corner in enumerate(corners):
        # seed_mode "sequential": sample j (0-based) runs `.options seed=` seed+j,
        # so this corner's sample i (1..N) keeps the pre-migration
        # base_seed + k*1000 + i seed.
        first = base_seed + k * 1000 + 1
        report, _transcript = _run(
            pdk, workdir, f"mc_{corner.name}", [corner], sw_stat_mismatch=1,
            par_tail=PAR_TAIL_NOMINAL, n=n_samples, seed=first, backend="batch",
            stage_model_inputs=stage_model_inputs,
        )
        jobs.append(job_of(report))
        reports.append(report)
        got = _samples_from_report(
            report, [corner], lambda i: f"mc{i + 1:03d}", PAR_TAIL_NOMINAL, 1,
            lambda c, i: first + i, need_index=True,
        )
        if len(got) != n_samples:
            raise batch.BatchError(
                f"{corner.name}: report has {len(got)} units, expected {n_samples}"
            )
        samples += got

    report, _transcript = _run(
        pdk, workdir, "nominal", corners, sw_stat_mismatch=0,
        par_tail=PAR_TAIL_NOMINAL, n=None, seed=None, backend="batch",
        stage_model_inputs=stage_model_inputs,
    )
    jobs.append(job_of(report))
    reports.append(report)
    nominal = _samples_from_report(
        report, corners, lambda i: "nominal", PAR_TAIL_NOMINAL, 0, lambda c, i: None
    )
    if len(nominal) != len(corners):
        raise batch.BatchError(f"nominal: report has {len(nominal)} units, expected {len(corners)}")
    samples += nominal

    # Deterministic negative control -- tt corner only, tiny par_tail_val on
    # the SAME unmodified mismatch machinery. See the module docstring. One
    # unit at the base seed: a single local run, not a grid.
    tt = CORNERS["tt"]
    report, _transcript = _run(
        pdk, workdir, "mcneg", [tt], sw_stat_mismatch=1,
        par_tail=NEG_CTRL_PAR_TAIL, n=1, seed=base_seed, backend="local",
    )
    neg = _samples_from_report(
        report, [tt], lambda i: "mcneg", NEG_CTRL_PAR_TAIL, 1, lambda c, i: base_seed,
        need_index=True,
    )
    if len(neg) != 1:
        raise batch.BatchError(f"negative control: report has {len(neg)} units, expected 1")
    samples += neg
    reports.append(report)
    return samples, [j for j in jobs if j], batch.engine_from_reports(reports)


def _within(value: float, lo: float, hi: float) -> bool:
    return lo <= value <= hi


@dataclass
class CornerStats:
    corner_name: str
    n: int
    swing_mean: float
    swing_sigma: float
    swing_min: float
    swing_max: float
    vcm_mean: float
    vcm_sigma: float
    vcm_min: float
    vcm_max: float
    swing_pass: bool
    vcm_pass: bool
    nominal_swing: float
    nominal_vcm: float


def summarize_corner(corner_name: str, mc_samples: list[Sample], nominal: Sample) -> CornerStats:
    swings = [s.swing_dc for s in mc_samples if s.status == "ok"]
    vcms = [s.vcm_dc for s in mc_samples if s.status == "ok"]
    swing_pass = _within(min(swings), *_bounds_swing()) and _within(max(swings), *_bounds_swing())
    vcm_pass = _within(min(vcms), *_bounds_vcm()) and _within(max(vcms), *_bounds_vcm())
    return CornerStats(
        corner_name=corner_name,
        n=len(swings),
        swing_mean=statistics.mean(swings),
        swing_sigma=statistics.pstdev(swings),
        swing_min=min(swings),
        swing_max=max(swings),
        vcm_mean=statistics.mean(vcms),
        vcm_sigma=statistics.pstdev(vcms),
        vcm_min=min(vcms),
        vcm_max=max(vcms),
        swing_pass=swing_pass,
        vcm_pass=vcm_pass,
        nominal_swing=nominal.swing_dc,
        nominal_vcm=nominal.vcm_dc,
    )


def _bounds_swing() -> tuple[float, float]:
    return DR0002_SWING_MIN, DR0002_SWING_MAX


def _bounds_vcm() -> tuple[float, float]:
    return DR0002_VCM_MIN, DR0002_VCM_MAX


def _fmt(v: float) -> str:
    return f"{v:.6f}"


def render_record(
    record_id: str,
    job_ids: list[str],
    n_samples: int,
    base_seed: int,
    stats: list[CornerStats],
    neg_ctrl: Sample,
    pdk: Pdk,
    ngspice_v: str,
    git: dict,
    wall_seconds: float,
    dut_sha256: str,
    fragment_sha256: str,
    stored: dict,
) -> str:
    overall_pass = all(cs.swing_pass and cs.vcm_pass for cs in stats)
    neg_ctrl_swing_fail = not _within(neg_ctrl.swing_dc, *_bounds_swing())
    neg_ctrl_vcm_fail = not _within(neg_ctrl.vcm_dc, *_bounds_vcm())
    neg_ctrl_fail = neg_ctrl_swing_fail or neg_ctrl_vcm_fail
    assert neg_ctrl_fail, (
        "negative control did not fail the DR-0002 window -- refusing to "
        "render a record around a vacuous check"
    )

    lines: list[str] = []
    lines.append(f"# Record {record_id}")
    lines.append("")
    lines.append(f"- **Record ID**: {record_id}")
    lines.append(f"- **Claim**: {CLAIM}")
    lines.append(
        "- **Netlist provenance**: schematic -- DUT "
        f"`sim/cml-driver-mismatch/testbench/cml_driver_dut_mismatch.spice` "
        f"(sha256 `{dut_sha256}`), driven by "
        f"`sim/cml-driver-mismatch/testbench/cml_driver_mismatch.spice` "
        f"(sha256 `{fragment_sha256}`)"
    )
    lines.append("- **Corner matrix run**:")
    lines.append("  - Process: " + ", ".join(cs.corner_name for cs in stats) + " (the mos corner set)")
    lines.append(f"  - Temperature: {TEMP_C:g} °C (nominal only -- see subset justification below)")
    lines.append(f"  - Supply: {VDD_V:.2f} V (nominal only -- see subset justification below)")
    lines.append(
        f"  - {len(stats)} process corners × {n_samples} Monte Carlo samples each "
        f"= {len(stats) * n_samples} statistical points, plus {len(stats)} deterministic "
        "mismatch=0 reference points (one per corner) and 1 deterministic negative "
        f"control = {len(stats) * n_samples + len(stats) + 1} `klt sim` units total, all completed. "
        f"Fleet job ids: {', '.join(job_ids) or '(none reported)'} (negative control ran as "
        "one local single-unit run)."
    )
    lines.append(
        "  - **Subset of the mandated PVT matrix**: this record holds temperature and "
        "supply at nominal and sweeps the full process-corner set (tt/ff/ss/fs/sf) "
        "× N Monte Carlo samples instead. Justification: sim/cml-driver-eye's "
        "existing record already carries this driver's deterministic swing/common-mode "
        "claim across the full −40/27/125 °C × ±10 % supply × process-corner "
        "matrix (90 points, both rates); running that same T×V grid again here, "
        f"multiplied by N={n_samples} Monte Carlo samples per point, is a "
        f"{9}× cost multiplier this record does not need to pay to add "
        "statistical (mismatch) evidence on top of that existing deterministic PVT "
        "coverage -- process corner is the axis this record adds sample count "
        "against; temperature/supply sensitivity is already evidenced. See "
        "sim/cml-driver-eye/records/ for the full-PVT deterministic sweep this "
        "record's mismatch=0 reference rows are comparable to (not numerically "
        "identical -- this DUT variant's nfet_03v3_dss wrapper adds small, real "
        "routing-resistance parasitics the un-wrapped nfet_03v3 model omits; see "
        "cml_driver_dut_mismatch.spice's header)."
    )
    lines.append("- **Statistical convention**:")
    lines.append(
        f"  - Monte Carlo local (intra-die) device mismatch: N={n_samples} independent "
        "samples per process corner, gf180mcu's own Pelgrom-law mismatch injection "
        "(`nfet_03v3_dss`, `sw_stat_mismatch=1`) on all four transistors of the "
        "statically-steered CML driver DUT (see the module docstring in run_mc.py for "
        "why input-pair and tail-mirror mismatch both matter here, and why the "
        "tail-mirror pair dominates)."
    )
    lines.append(
        f"  - Seed: `klt sim` `monte_carlo` per process corner, `seed` = base_seed + k*1000 + 1 "
        f"(base seed {base_seed}; k: 0=tt, 1=ff, 2=ss, 3=fs, 4=sf), `seed_mode: sequential` "
        "(sample j, 0-based, runs `.options seed=` seed+j, so sample i (1..N) has "
        "`.options seed=` base_seed + k*1000 + i -- the same per-sample integer seeds as the "
        "20260815 record), `seed_scope: point`, `vary: mismatch`. The sweep moved from a "
        "hand-rolled local ngspice pool to `klt sim` on the batch fleet, so statistics are "
        "**not** guaranteed bit-identical to the 20260815 record even at equal seeds (the "
        "request's deck composition and the fleet's ngspice build differ); compare "
        "distributions, not individual samples. The mismatch=0 reference per corner is one "
        "deterministic multi-corner request (no sampling; seed-independent by construction: "
        "sw_stat_mismatch=0 zeroes delvto/mulu0)."
    )
    lines.append(
        "  - Reported per corner at 1-sigma (population stdev across the N samples), "
        "but the PASS/FAIL grade below uses the observed min/max across all N samples, "
        "not a sigma projection, so a heavy-tailed sample is not hidden by a Gaussian "
        "assumption."
    )
    lines.append(
        "  - **Deterministic negative control** (corner-id `tt_mcneg_27c_3.30v`): same "
        f"mismatch machinery, same base seed ({base_seed}), but `par_tail_val="
        f"{NEG_CTRL_PAR_TAIL:g}` in place of the nominal {PAR_TAIL_NOMINAL:g} on the "
        "tail-mirror device -- `nfet_03v3_dss`'s `par` argument scales only the "
        "Pelgrom-law area term the mismatch sigma is drawn against, not the "
        "transistor's real electrical w/l/nf/m (see cml_driver_dut_mismatch.spice's "
        "header), so this injects an artificially large, deterministic, "
        "seed-reproducible mismatch using the SAME unmodified vendor mismatch "
        "mechanism the N-sample sweep uses, rather than a hand-rolled fault "
        f"injection. Measured: swing_dc={_fmt(neg_ctrl.swing_dc)} V "
        f"(window {DR0002_SWING_MIN:.1f}-{DR0002_SWING_MAX:.1f} V, "
        f"{'FAILS' if neg_ctrl_swing_fail else 'passes'}), "
        f"vcm_dc={_fmt(neg_ctrl.vcm_dc)} V "
        f"(window {DR0002_VCM_MIN:.1f}-{DR0002_VCM_MAX:.1f} V, "
        f"{'FAILS' if neg_ctrl_vcm_fail else 'passes'}) -- confirms the pass/fail "
        "check below actually fires and is not vacuous. Excluded from the N-sample "
        "statistics and from the overall pass/fail roll-up (it is not a claim about "
        "the real design)."
    )
    lines.append("- **Result**:")
    lines.append("")
    lines.append(
        "  | corner | N | swing mean (V) | swing σ (V) | swing min (V) | swing max (V) | "
        "swing pass | vcm mean (V) | vcm σ (V) | vcm min (V) | vcm max (V) | vcm pass | "
        "mismatch=0 ref swing (V) | mismatch=0 ref vcm (V) |"
    )
    lines.append("  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for cs in stats:
        lines.append(
            f"  | `{cs.corner_name}` | {cs.n} | {_fmt(cs.swing_mean)} | {_fmt(cs.swing_sigma)} | "
            f"{_fmt(cs.swing_min)} | {_fmt(cs.swing_max)} | {'PASS' if cs.swing_pass else 'FAIL'} | "
            f"{_fmt(cs.vcm_mean)} | {_fmt(cs.vcm_sigma)} | {_fmt(cs.vcm_min)} | {_fmt(cs.vcm_max)} | "
            f"{'PASS' if cs.vcm_pass else 'FAIL'} | {_fmt(cs.nominal_swing)} | {_fmt(cs.nominal_vcm)} |"
        )
    lines.append("")
    lines.append(
        f"  - Negative control (`tt_mcneg_27c_3.30v`, excluded above): swing_dc="
        f"{_fmt(neg_ctrl.swing_dc)} V, vcm_dc={_fmt(neg_ctrl.vcm_dc)} V -- "
        f"{'FAIL (expected -- proves the check fires)' if neg_ctrl_fail else 'unexpectedly passed'}."
    )
    lines.append(f"  - **Overall (real-design samples only): {'PASS' if overall_pass else 'FAIL'}**")
    lines.append("- **Links**:")
    lines.append(
        "  - Testbench: `sim/cml-driver-mismatch/testbench/cml_driver_mismatch.spice`"
    )
    lines.append(
        "  - DUT netlist: `sim/cml-driver-mismatch/testbench/cml_driver_dut_mismatch.spice`"
    )
    lines.append(f"  - Netlist snapshot: `sim/cml-driver-mismatch/netlist-snapshots/{record_id}.spice`")
    lines.append(f"  - Stored evidence manifest: `{stored['manifest']}`")
    lines.append(
        f"- **Timestamp / author**: {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}, "
        f"{environment(pdk, ngspice_v, REPO_ROOT, git)['user']}"
    )
    lines.append("- **Supersedes**: (none)")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append("Everything needed to re-run this record:")
    lines.append("")
    env = environment(pdk, ngspice_v, REPO_ROOT, git)
    lines.append(
        f"- PDK: {env['pdk']['variant']} @ open_pdks `{env['pdk']['open_pdks_version']}` "
        f"({env['pdk']['path']}, via {env['pdk']['discovered_via']})"
    )
    lines.append(f"- ngspice: {env['ngspice']}")
    lines.append(f"- Harness: sim/cml-driver-mismatch/run_mc.py (`klt sim` monte_carlo requests via sim/harness/batch.py), python {env['python']}")
    dirty_note = " (dirty)" if env["git"]["dirty"] else " (clean)"
    lines.append(f"- git: `{env['git']['commit']}` on `{env['git']['branch']}`{dirty_note}")
    lines.append(f"- DUT netlist sha256: `{dut_sha256}`")
    lines.append(f"- Testbench fragment sha256: `{fragment_sha256}`")
    lines.append(f"- Wall time: {wall_seconds:.2f} s")
    lines.append("")
    lines += evidence_store.stored_evidence_lines(stored)
    lines.append("---")
    lines.append("")
    lines.append(
        "Written by `sim/cml-driver-mismatch/run_mc.py`. Append-only: never edit or "
        "delete this file -- a re-run or correction mints a new record-id and points "
        "back here via **Supersedes** (see `sim/README.md`)."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-samples", type=int, default=30, help="Monte Carlo samples per process corner (default: 30)")
    parser.add_argument("--base-seed", type=int, default=20260814, help="deterministic base seed (default: 20260814)")
    parser.add_argument("--no-write", action="store_true", help="run everything but write nothing to records/")
    parser.add_argument(
        "--stage-models", action="store_true",
        help="set options.stage_model_inputs on the fleet requests so the batch "
        "workers run this client's own model closure instead of the fleet "
        "image's PDK (the local negative control is unaffected)",
    )
    args = parser.parse_args(argv)

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3
    git = git_provenance(REPO_ROOT)

    # Raw logs are stored through the artifact broker, never committed. Fail
    # before simulating if that is impossible (no option commits bytes), so a
    # misconfigured host aborts in seconds instead of after the whole sweep.
    if not args.no_write:
        try:
            evidence_store.preflight()
            evidence_store.require_ignored_stage(evidence_store.STAGE_ROOT, REPO_ROOT)
        except evidence_store.EvidenceStoreError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        record_id = allocate_record_id(REPO_ROOT, RECORDS_DIR, git=git)
        log_dir = evidence_store.stage_dir(EXPERIMENT_DIR.name, record_id)
    else:
        record_id = None
        log_dir = None

    workdir = SIM_DIR / ".work" / "cml-driver-mismatch" / "debug"
    started = time.monotonic()
    try:
        results, job_ids, ngspice_v = run_all(
            pdk, workdir, args.n_samples, args.base_seed,
            stage_model_inputs=args.stage_models,
        )
    except batch.BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    wall_seconds = time.monotonic() - started

    errors = [s for s in results if s.status != "ok"]
    if errors:
        for s in errors:
            print(f"ERROR: {s.corner_id} did not produce measurements", file=sys.stderr)
            print(s.log[-2000:], file=sys.stderr)
        return 2

    by_corner: dict[str, list[Sample]] = {}
    nominal_by_corner: dict[str, Sample] = {}
    neg_ctrl: Sample | None = None
    for s in results:
        if s.label == "mcneg":
            neg_ctrl = s
        elif s.label == "nominal":
            nominal_by_corner[s.corner.name] = s
        else:
            by_corner.setdefault(s.corner.name, []).append(s)
    assert neg_ctrl is not None

    stats = [
        summarize_corner(name, by_corner[name], nominal_by_corner[name])
        for name in CORNER_SETS["mos"]
    ]

    if args.no_write:
        for cs in stats:
            print(
                f"{cs.corner_name}: swing {cs.swing_min:.4f}-{cs.swing_max:.4f} V "
                f"({'PASS' if cs.swing_pass else 'FAIL'}), "
                f"vcm {cs.vcm_min:.4f}-{cs.vcm_max:.4f} V "
                f"({'PASS' if cs.vcm_pass else 'FAIL'})"
            )
        print(
            f"negative control: swing={neg_ctrl.swing_dc:.4f} V, vcm={neg_ctrl.vcm_dc:.4f} V"
        )
        return 0

    dut_sha256 = hashlib.sha256(DUT_PATH.read_bytes()).hexdigest()
    fragment_sha256 = hashlib.sha256(FRAGMENT_PATH.read_bytes()).hexdigest()

    for s in results:
        header = (
            "* ====================================================================\n"
            f"* record-id : {record_id}\n"
            f"* testbench : cml_driver_mismatch.spice\n"
            f"* corner    : {s.corner.name} ({s.label})\n"
            f"* temp      : {TEMP_C:g} C\n"
            f"* supply    : {VDD_V:.2f} V\n"
            f"* seed      : {s.seed if s.seed is not None else 'n/a (deterministic)'}\n"
            f"* sw_stat_mismatch : {s.sw_stat_mismatch}\n"
            f"* par_pair/par_tail/par_mirror : {s.par_pair!r}/{s.par_tail!r}/{s.par_mirror!r}\n"
            f"* pdk       : {pdk.variant} ({pdk.path})\n"
            f"* klt sim   : {job_ids}\n"
            f"* run (UTC) : {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            "* ====================================================================\n"
        )
        write_device_corner_log(log_dir, s.corner_id, header, s.log)

    try:
        stored = evidence_store.store_run(
            EXPERIMENT_DIR.name, record_id, log_dir, REPO_ROOT
        )
    except evidence_store.EvidenceStoreError as exc:
        print(f"error: evidence not recorded: {exc}", file=sys.stderr)
        return 3

    write_device_netlist_snapshot(SNAPSHOT_DIR, record_id, FRAGMENT_PATH)

    body = render_record(
        record_id=record_id,
        job_ids=job_ids,
        n_samples=args.n_samples,
        base_seed=args.base_seed,
        stats=stats,
        neg_ctrl=neg_ctrl,
        pdk=pdk,
        ngspice_v=ngspice_v,
        git=git,
        wall_seconds=wall_seconds,
        dut_sha256=dut_sha256,
        fragment_sha256=fragment_sha256,
        stored=stored,
    )
    device_write_record(RECORDS_DIR, record_id, body)

    overall_pass = all(cs.swing_pass and cs.vcm_pass for cs in stats)
    print(f"Record {record_id} written. Overall (real-design samples): {'PASS' if overall_pass else 'FAIL'}")
    print(f"Evidence stored: {stored['manifest']} (bytes via klt artifact; not committed)")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
