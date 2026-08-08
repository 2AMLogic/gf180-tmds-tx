#!/usr/bin/env python3
"""Cold-start test runner for the TMDS encoder verification bench.

Builds and simulates the DUT under Icarus Verilog via cocotb's Python
runner API, and enforces the three-leg verification plan documented in
verification/README.md:

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
    pip install -r requirements.txt
    python3 runner.py

See verification/README.md for pinned simulator versions and prerequisites.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner

HERE = Path(__file__).resolve().parent
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--good-only", action="store_true", help="only run Leg 1+2 against the real DUT"
    )
    parser.add_argument(
        "--broken-only",
        action="store_true",
        help="only run Leg 3 against the negative control",
    )
    args = parser.parse_args()

    if args.good_only and args.broken_only:
        parser.error("--good-only and --broken-only are mutually exclusive")

    run_good = not args.broken_only
    run_broken = not args.good_only

    ok = True

    if run_good:
        print(
            f"=== Leg 1+2: {TEST_MODULE} vs. {GOOD_DUT.relative_to(HERE.parent.parent)} ==="
        )
        n, f = run_leg(GOOD_DUT, "good")
        print(f"real DUT: {n} test(s), {f} failed")
        if f != 0:
            print("FAIL: the real DUT must pass every test in the bench.")
            ok = False
        else:
            print("PASS: real DUT passed the full bench.")

    if run_broken:
        print(
            f"=== Leg 3 (negative control): {TEST_MODULE} vs. {BROKEN_DUT.relative_to(HERE.parent.parent)} ==="
        )
        n, f = run_leg(BROKEN_DUT, "broken")
        print(f"broken DUT: {n} test(s), {f} failed")
        if f == 0:
            print(
                "FAIL: negative control did not fail -- this bench is not known to be able to fail."
            )
            ok = False
        else:
            print(f"PASS: negative control correctly failed ({f}/{n} test(s)).")

    print()
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
