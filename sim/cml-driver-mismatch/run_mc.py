#!/usr/bin/env python3
"""Monte Carlo local-mismatch sweep of the CML driver's DR-0002 swing/
common-mode (issue #23, part of epic #17's T1 evidence ladder).

    python3 sim/cml-driver-mismatch/run_mc.py                 # run, mint a record
    python3 sim/cml-driver-mismatch/run_mc.py --no-write       # debug, record nothing
    python3 sim/cml-driver-mismatch/run_mc.py --n-samples 50

Why this is a bespoke script rather than a `sim/harness/runner.py` PVT-grid
run (`python3 sim/run_corners.py <slug>`): the shared harness sweeps a
process x temperature x supply (x rate) grid -- one ngspice invocation per
*deterministic* point. A Monte Carlo mismatch claim needs a different axis
entirely: N independent, randomly-seeded samples *per* process corner, plus
a deterministic negative control that must fail. `sim/harness/report.py`'s
"Device-level evidence plumbing" section (`device_log_header`,
`write_device_corner_log`, `write_device_netlist_snapshot`,
`device_write_record`) exists for exactly this shape of experiment -- reused
here unmodified -- while PDK discovery (`sim/harness/pdk.py`) and the five
process corners' `.lib` section bundles (`sim/harness/corners.py`) are
reused unmodified too. Nothing in `sim/harness/` is edited by this issue.

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
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
sys.path.insert(0, str(SIM_DIR))

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
from harness.runner import NGSPICE, ngspice_version  # noqa: E402

EXPERIMENT_DIR = SIM_DIR / "cml-driver-mismatch"
TESTBENCH_DIR = EXPERIMENT_DIR / "testbench"
DUT_PATH = TESTBENCH_DIR / "cml_driver_dut_mismatch.spice"
FRAGMENT_PATH = TESTBENCH_DIR / "cml_driver_mismatch.spice"
SNAPSHOT_DIR = EXPERIMENT_DIR / "netlist-snapshots"
CORNERS_DIR = EXPERIMENT_DIR / "corners"
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

_MEAS_RE = re.compile(r"^\s*m_(\w+)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)")


def parse_measurements(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in text.splitlines():
        match = _MEAS_RE.match(line)
        if match:
            try:
                found[match.group(1)] = float(match.group(2))
            except ValueError:  # pragma: no cover - regex already constrains this
                continue
    return found


@dataclass
class Sample:
    corner_id: str
    corner: Corner
    label: str  # "nominal" | "mc<NNN>" | "mcneg"
    seed: int
    sw_stat_mismatch: int
    par_pair: float
    par_tail: float
    par_mirror: float
    status: str = "pending"
    swing_dc: float | None = None
    vcm_dc: float | None = None
    seconds: float = 0.0
    log: str = ""
    deck: str = ""


def compose_deck(pdk: Pdk, s: Sample) -> str:
    lines = [
        f"* cml-driver-mismatch @ {s.corner_id} -- GENERATED by "
        "sim/cml-driver-mismatch/run_mc.py, do not edit",
        f"* corner={s.corner.name} ({s.corner.description})  temp={TEMP_C:g} C  "
        f"vdd={VDD_V:.2f} V  pdk={pdk.variant}@{pdk.version}",
        f"* sw_stat_mismatch={s.sw_stat_mismatch}  seed={s.seed}  "
        f"par_pair={s.par_pair!r} par_tail={s.par_tail!r} par_mirror={s.par_mirror!r}",
        "",
        "* ---- static bias / steering parameters -------------------------------",
        f".param vdd_val={VDD_V!r}",
        f".param par_pair_val={s.par_pair!r}",
        f".param par_tail_val={s.par_tail!r}",
        f".param par_mirror_val={s.par_mirror!r}",
        "",
        "* ---- gf180mcu models --------------------------------------------------",
        f'.include "{pdk.design_include}"',
        f".param sw_stat_mismatch={s.sw_stat_mismatch}",
    ]
    for section in s.corner.sections:
        lines.append(f'.lib "{pdk.model_lib}" {section}')
    lines += [
        "",
        f".temp {TEMP_C!r}",
        f".option seed={s.seed}",
        "",
        "* ---- device under test -------------------------------------------------",
        f'.include "{DUT_PATH}"',
        "",
        "* ---- testbench -----------------------------------------------------------",
        f'.include "{FRAGMENT_PATH}"',
        "",
        "* ---- measurement -----------------------------------------------------",
        ".control",
        "set numdgt=10",
        "set noaskquit",
        "  op",
        "  let m_swing_dc = v(outn) - v(outp)",
        "  let m_vcm_dc = (v(outn)+v(outp))/2",
        "  print m_swing_dc",
        "  print m_vcm_dc",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def run_sample(pdk: Pdk, s: Sample, workdir: Path, timeout_s: int = 120) -> Sample:
    workdir.mkdir(parents=True, exist_ok=True)
    deck_path = workdir / f"{s.corner_id}.spice"
    deck_text = compose_deck(pdk, s)
    deck_path.write_text(deck_text)
    started = time.monotonic()
    proc = subprocess.run(
        [NGSPICE, "-b", str(deck_path)],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        cwd=workdir,
        check=False,
    )
    s.seconds = time.monotonic() - started
    s.log = proc.stdout + "\n" + proc.stderr
    s.deck = deck_text
    measured = parse_measurements(s.log)
    if proc.returncode != 0 or "swing_dc" not in measured or "vcm_dc" not in measured:
        s.status = "error"
        return s
    s.status = "ok"
    s.swing_dc = measured["swing_dc"]
    s.vcm_dc = measured["vcm_dc"]
    return s


def build_samples(n_samples: int, base_seed: int) -> list[Sample]:
    corners = [CORNERS[name] for name in CORNER_SETS["mos"]]
    samples: list[Sample] = []
    for idx, corner in enumerate(corners):
        samples.append(
            Sample(
                corner_id=f"{corner.name}_nominal_{TEMP_C:g}c_{VDD_V:.2f}v",
                corner=corner,
                label="nominal",
                seed=base_seed + idx * 1000,
                sw_stat_mismatch=0,
                par_pair=PAR_PAIR_NOMINAL,
                par_tail=PAR_TAIL_NOMINAL,
                par_mirror=PAR_MIRROR_NOMINAL,
            )
        )
        for i in range(1, n_samples + 1):
            samples.append(
                Sample(
                    corner_id=f"{corner.name}_mc{i:03d}_{TEMP_C:g}c_{VDD_V:.2f}v",
                    corner=corner,
                    label=f"mc{i:03d}",
                    seed=base_seed + idx * 1000 + i,
                    sw_stat_mismatch=1,
                    par_pair=PAR_PAIR_NOMINAL,
                    par_tail=PAR_TAIL_NOMINAL,
                    par_mirror=PAR_MIRROR_NOMINAL,
                )
            )
    # Deterministic negative control -- tt corner only, tiny par_tail_val on
    # the SAME unmodified mismatch machinery. See the module docstring.
    tt = CORNERS["tt"]
    samples.append(
        Sample(
            corner_id=f"tt_mcneg_{TEMP_C:g}c_{VDD_V:.2f}v",
            corner=tt,
            label="mcneg",
            seed=base_seed,
            sw_stat_mismatch=1,
            par_pair=PAR_PAIR_NOMINAL,
            par_tail=NEG_CTRL_PAR_TAIL,
            par_mirror=PAR_MIRROR_NOMINAL,
        )
    )
    return samples


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
        f"control = {len(stats) * n_samples + len(stats) + 1} ngspice invocations total, "
        "all completed."
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
        f"  - Seed: base seed {base_seed}; sample `i` (1..N) at process-corner index `k` "
        f"(0=tt, 1=ff, 2=ss, 3=fs, 4=sf) uses `.option seed=` = "
        "base_seed + k*1000 + i -- deterministic and independently reproducible per "
        "sample. The mismatch=0 reference point per corner uses seed = base_seed + "
        "k*1000 (its result is seed-independent by construction: sw_stat_mismatch=0 "
        "zeroes delvto/mulu0 regardless of the agauss draw)."
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
    lines.append(f"  - Raw logs: `sim/cml-driver-mismatch/corners/{record_id}/`")
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
    lines.append(f"- Harness: sim/cml-driver-mismatch/run_mc.py (bespoke, not sim/harness/runner.py), python {env['python']}")
    dirty_note = " (dirty)" if env["git"]["dirty"] else " (clean)"
    lines.append(f"- git: `{env['git']['commit']}` on `{env['git']['branch']}`{dirty_note}")
    lines.append(f"- DUT netlist sha256: `{dut_sha256}`")
    lines.append(f"- Testbench fragment sha256: `{fragment_sha256}`")
    lines.append(f"- Wall time: {wall_seconds:.2f} s")
    lines.append("")
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
    parser.add_argument("-j", "--jobs", type=int, default=4, help="parallel ngspice invocations (default: 4)")
    args = parser.parse_args(argv)

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3
    ngspice_v = ngspice_version()

    git = git_provenance(REPO_ROOT)
    samples = build_samples(args.n_samples, args.base_seed)

    workdir = SIM_DIR / ".work" / "cml-driver-mismatch" / "debug"
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(lambda s: run_sample(pdk, s, workdir), samples))
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

    record_id = allocate_record_id(REPO_ROOT, RECORDS_DIR, git=git)

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
            f"* seed      : {s.seed}\n"
            f"* sw_stat_mismatch : {s.sw_stat_mismatch}\n"
            f"* par_pair/par_tail/par_mirror : {s.par_pair!r}/{s.par_tail!r}/{s.par_mirror!r}\n"
            f"* pdk       : {pdk.variant} ({pdk.path})\n"
            f"* ngspice   : {ngspice_v}\n"
            f"* run (UTC) : {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            "* ====================================================================\n"
        )
        write_device_corner_log(CORNERS_DIR, record_id, s.corner_id, header, s.log)

    write_device_netlist_snapshot(SNAPSHOT_DIR, record_id, FRAGMENT_PATH)

    body = render_record(
        record_id=record_id,
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
    )
    device_write_record(RECORDS_DIR, record_id, body)

    overall_pass = all(cs.swing_pass and cs.vcm_pass for cs in stats)
    print(f"Record {record_id} written. Overall (real-design samples): {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
