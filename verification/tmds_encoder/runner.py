#!/usr/bin/env python3
"""Cold-start test runner for the TMDS encoder verification bench.

Builds and simulates the DUT under Icarus Verilog via cocotb's Python
runner API, and enforces the three-leg verification plan documented in
verification/README.md (orchestration delegated to the shared skeleton in
`verification/_bench_runner.py`):

  - Leg 1 + Leg 2 (`--good-only` or default): rtl/tmds_encoder.v must pass
    every test in test_tmds_encoder.py with zero failures.
  - Leg 3 (`--broken-only` or default): the *same* test module, run
    against negative_control/tmds_encoder_broken.v, must FAIL -- a bench
    that has never failed is not known to be able to.

Exit status is 0 only if both legs behave as expected; this is what CI
gates on (see .github/workflows/ci.yml).

Cold-start invocation (from a clean checkout):

    cd verification/tmds_encoder
    python3 -m venv .venv && source .venv/bin/activate   # optional
    pip install -r ../requirements.txt
    python3 runner.py

See verification/README.md for pinned simulator versions and prerequisites.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The shared three-leg skeleton lives at the verification/ root, one level up.
sys.path.insert(0, str(HERE.parent))

from _bench_runner import Leg, run_three_leg_bench  # noqa: E402
from cocotb_tools.runner import get_results, get_runner  # noqa: E402

RTL_DIR = HERE.parent.parent / "rtl"
GOOD_DUT = RTL_DIR / "tmds_encoder.v"
BROKEN_DUT = HERE / "negative_control" / "tmds_encoder_broken.v"
TEST_MODULE = "test_tmds_encoder"
TOPLEVEL = "tmds_encoder"


def run_leg(dut_source: Path, build_subdir: str) -> tuple[int, int]:
    """Build + run the bench against `dut_source`. Returns (num_tests, num_failed)."""
    build_dir = HERE / "sim_build" / build_subdir
    runner = get_runner("icarus")
    runner.build(
        verilog_sources=[dut_source],
        hdl_toplevel=TOPLEVEL,
        build_dir=build_dir,
        always=True,
        build_args=["-g2005"],  # Verilog-2005, no vendor extensions
        timescale=("1ns", "1ps"),
    )
    results_xml = runner.test(
        test_module=TEST_MODULE,
        hdl_toplevel=TOPLEVEL,
        build_dir=build_dir,
        test_dir=HERE,
    )
    return get_results(results_xml)


def main() -> int:
    return run_three_leg_bench(
        description=__doc__,
        test_module=TEST_MODULE,
        good_dut=GOOD_DUT,
        broken_dut=BROKEN_DUT,
        run_leg=run_leg,
        good_legs=[Leg(build_subdir="good")],
        broken_leg=Leg(build_subdir="broken"),
    )


if __name__ == "__main__":
    sys.exit(main())
