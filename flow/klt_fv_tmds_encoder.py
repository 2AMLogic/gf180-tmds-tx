#!/usr/bin/env python3
"""`klt functional-verification` envelopes for `tmds_encoder` (T1 items 5 and 7, digital).

Runs the existing cocotb bench (`verification/tmds_encoder/`) through the
`klt` verb twice and writes each response unmodified:

  - `flow/tmds_encoder/klt_fv_zero_delay.json` -- `rtl/tmds_encoder.v`,
    zero delay (item 5's functional leg).
  - `flow/tmds_encoder/klt_fv_sdf.json` -- the synthesized gate-level netlist
    with the post-route SDF back-annotated through `options.sdf` (item 7).
    The gf180mcu vendor cell models still need
    `flow/gate_level_sim_tmds_encoder.py`'s `ifnone` rewrite for Icarus, so
    its `build_filtered_library` is reused; `klt` strips the SDF
    `INTERCONNECT` entries itself, so the SDF is passed as committed.

The simulator clock period is `gate_level_sim_tmds_encoder.CLOCK_PERIOD_NS`
for the SDF run, exported to the bench as TMDS_SIM_CLOCK_PERIOD_NS.

    python3 flow/klt_fv_tmds_encoder.py [--klt PATH] [--only zero-delay|sdf]

The SDF leg currently aborts in `klt` (klayout-tools#3740) and writes no envelope.

Needs cocotb, Icarus Verilog >= 13 and the gf180mcuD PDK (find_pdk()).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "flow"))

import gate_level_sim_tmds_encoder as gl  # noqa: E402
from sim.harness.pdk import PdkNotFound, find_pdk  # noqa: E402

FLOW_DIR = REPO_ROOT / "flow" / "tmds_encoder"
BUILD_DIR = REPO_ROOT / "flow" / "build" / "klt"
TESTBENCH = {"module": "test_tmds_encoder", "search_path": str(REPO_ROOT / "verification" / "tmds_encoder")}


def zero_delay_request() -> dict:
    return {
        "schema": "klt.functional_verification.request/1",
        "sources": [str(REPO_ROOT / "rtl" / "tmds_encoder.v")],
        "hdl_toplevel": "tmds_encoder",
        "testbench": TESTBENCH,
        "engine": "icarus",
    }


def sdf_request() -> dict:
    pdk = find_pdk()
    netlist = gl.NETLIST_PATH
    filtered_lib = gl.build_filtered_library(pdk, netlist.read_text())
    return {
        "schema": "klt.functional_verification.request/1",
        "sources": [str(netlist), str(gl.primitives_path(pdk)), str(filtered_lib)],
        "hdl_toplevel": "tmds_encoder",
        "testbench": TESTBENCH,
        "engine": "icarus",
        "options": {"sdf": {"file": str(gl.SDF_PATH), "corner": "typ"}},
    }


def run(klt: str, name: str, request: dict, out_path: Path, env: dict) -> int:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    request_path = BUILD_DIR / f"fv_{name}.request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    proc = subprocess.run(
        [klt, "functional-verification", str(request_path), "--format", "json"],
        capture_output=True,
        text=True,
        env=env,
    )
    if not proc.stdout.strip():
        print(proc.stderr, file=sys.stderr)
        print(f"ERROR: klt functional-verification ({name}) exited {proc.returncode} with no envelope", file=sys.stderr)
        return 1
    out_path.write_text(proc.stdout)
    r = json.loads(proc.stdout)
    print(f"{name}: {r['status']} ({r['passed_count']}/{r['test_count']} passed) -> {out_path}")
    return 0 if r["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--klt", default="klt")
    parser.add_argument("--only", choices=["zero-delay", "sdf"])
    args = parser.parse_args()

    rc = 0
    if args.only in (None, "zero-delay"):
        rc |= run(args.klt, "zero_delay", zero_delay_request(), FLOW_DIR / "klt_fv_zero_delay.json", dict(os.environ))
    if args.only in (None, "sdf"):
        try:
            request = sdf_request()
        except PdkNotFound as exc:
            print(str(exc), file=sys.stderr)
            return 3
        env = dict(os.environ, TMDS_SIM_CLOCK_PERIOD_NS=str(gl.CLOCK_PERIOD_NS))
        rc |= run(args.klt, "sdf", request, FLOW_DIR / "klt_fv_sdf.json", env)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
