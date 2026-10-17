#!/usr/bin/env python3
"""Standalone `klt sta` envelope for `tmds_encoder` (T1 item 5, digital).

Builds a `klt sta` request over the routed DEF and post-route SPEF the
existing flow already committed (`flow/pnr_tmds_encoder.py`,
`flow/sdf_tmds_encoder.py`) and writes the verb's own response to
`flow/tmds_encoder/klt_sta.json`. That response is the only thing
`klt signoff` grades -- `flow/sta_tmds_encoder.py`'s Markdown records are not
`klt` envelopes -- so nothing here is hand-built: the file is `klt sta`'s
stdout, byte for byte.

One request characterizes the one fixed DEF at all five 3.3 V corners
(`pdk.corners`): an analysis, not a simulation grid. Clock target is the
720p60 pixel clock, 13.4680 ns (spec/tmds-tx.md section 2), with the same
zero input/output delay `flow/sta_tmds_encoder.py` applies.

One path normalisation is applied, and only that: `klt sta` echoes `def_path`
and `spef_path` as absolute paths of the producing checkout, which do not exist
on another machine -- there the grader's re-hash of the DEF
(`input_verified`) would silently become `null` and CI's byte-compare of
`signoff/signoff.json` would fail. Those two fields are rewritten to
repo-relative paths (the grader resolves them against the working directory,
the repo root). Every verdict and hash field is `klt`'s own output, untouched.

Not reproduced by `klt sta`'s request schema (disclosed in
`signoff/README.md`): `set_propagated_clock`, `set_driving_cell` on inputs and
`set_load` on outputs from `flow/tmds_encoder/sta/tmds_encoder.sdc`.

    klt must resolve gf180mcuD (set PDK_ROOT or pass --pdk-root) and be the
    graded build pinned in signoff/README.md; openroad must be on PATH.

    python3 flow/klt_sta_tmds_encoder.py [--klt PATH] [--pdk-root DIR]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FLOW_DIR = REPO_ROOT / "flow" / "tmds_encoder"
BUILD_DIR = REPO_ROOT / "flow" / "build" / "klt"
OUT_PATH = FLOW_DIR / "klt_sta.json"

CELL_LIBRARY = "gf180mcu_fd_sc_mcu9t5v0"
CORNERS = ["tt_025C_3v30", "ss_125C_3v00", "ss_n40C_3v00", "ff_125C_3v60", "ff_n40C_3v60"]
CLOCK_PERIOD_NS = 13.4680  # 720p60, 74.25 MHz


def build_request() -> dict:
    return {
        "schema": "klt.sta.request/1",
        "def": str(FLOW_DIR / "pnr" / "tmds_encoder.def"),
        "hdl_toplevel": "tmds_encoder",
        "pdk": {"cell_library": CELL_LIBRARY, "corners": CORNERS},
        "constraints": {
            "clock_port": "clk",
            "clock_period_ns": CLOCK_PERIOD_NS,
            "input_delay_ns": 0,
            "output_delay_ns": 0,
        },
        "spef": str(FLOW_DIR / "sta" / "tmds_encoder.spef"),
        "geometry_source": "routed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--klt", default="klt")
    parser.add_argument("--pdk", default="gf180mcuD")
    parser.add_argument("--pdk-root")
    args = parser.parse_args()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    request_path = BUILD_DIR / "sta.request.json"
    request_path.write_text(json.dumps(build_request(), indent=2) + "\n")

    cmd = [args.klt, "sta", str(request_path), "--format", "json", "--pdk", args.pdk]
    if args.pdk_root:
        cmd += ["--pdk-root", args.pdk_root]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(f"ERROR: klt sta exited {proc.returncode}; {OUT_PATH} not written", file=sys.stderr)
        return 1
    envelope = json.loads(proc.stdout)
    for field in ("def_path", "spef_path"):
        envelope[field] = Path(envelope[field]).relative_to(REPO_ROOT).as_posix()
    OUT_PATH.write_text(json.dumps(envelope, indent=2) + "\n")
    for c in envelope["corners"]:
        print(f"{c['corner']}: setup {c['worst_slack_ns']} ns, hold {c['worst_hold_slack_ns']} ns, {c['timing_status']}")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
