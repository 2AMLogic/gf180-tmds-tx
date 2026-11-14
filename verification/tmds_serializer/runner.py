#!/usr/bin/env python3
"""Cold-start test runner for the TMDS serializer verification bench.

Builds and simulates the DUT under Icarus Verilog via cocotb's Python runner
API, and enforces the same three-leg verification plan as every bench in this
repository (see verification/README.md; orchestration delegated to the shared
skeleton in `verification/_bench_runner.py`):

  - Leg 1 + Leg 2 (`--good-only` or default): `rtl/tmds_serializer.v`, wrapped
    with the real `rtl/tmds_encoder.v` by `rtl/tmds_tx_lane.v` (via
    `tmds_tx_chain.v`), in every SEL_MODE (DR-0018), must pass every
    test in test_tmds_serializer.py with zero failures.
  - Leg 3 (`--broken-only` or default): the *same* test module, run against
    negative_control/tmds_serializer_broken.v, must FAIL -- a bench that has
    never failed is not known to be able to.

The toplevel elaborated in both legs is `tmds_tx_chain`, not the serializer
alone: issue #159's acceptance criterion is specifically correctness "against
`tmds_encoder`'s output", which needs both cells in one elaboration. The
encoder source is identical in both legs; only the serializer source differs.

Exit status is 0 only if both legs behave as expected; this is what CI gates
on (see .github/workflows/ci.yml).

Cold-start invocation (from a clean checkout):

    cd verification/tmds_serializer
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
ENCODER = RTL_DIR / "tmds_encoder.v"
LANE = RTL_DIR / "tmds_tx_lane.v"
CHAIN = HERE / "tmds_tx_chain.v"
GOOD_DUT = RTL_DIR / "tmds_serializer.v"
BROKEN_DUT = HERE / "negative_control" / "tmds_serializer_broken.v"
TEST_MODULE = "test_tmds_serializer"
TOPLEVEL = "tmds_tx_chain"

#: Static configurations of rtl/tmds_tx_lane.v (SEL_MODE), see DR-0018:
#: 2 = runtime select, 0 = encoder only, 1 = external only. All three are
#: elaborated and run against the real serializer; the negative control runs
#: in the runtime-select configuration (the one that exercises every path).
SEL_MODES = (2, 0, 1)


def run_leg(serializer_source: Path, build_subdir: str, sel_mode: int = 2) -> tuple[int, int]:
    """Build + run the bench with `serializer_source` as the serializer."""
    build_dir = HERE / "sim_build" / build_subdir
    runner = get_runner("icarus")
    runner.build(
        verilog_sources=[ENCODER, serializer_source, LANE, CHAIN],
        parameters={"SEL_MODE": sel_mode},
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
        extra_env={"TMDS_SEL_MODE": str(sel_mode)},
    )
    return get_results(results_xml)


def main() -> int:
    return run_three_leg_bench(
        description=__doc__,
        test_module=TEST_MODULE,
        good_dut=GOOD_DUT,
        broken_dut=BROKEN_DUT,
        run_leg=run_leg,
        good_legs=[
            Leg(
                build_subdir="good" if mode == 2 else f"good_sel{mode}",
                label=f" (SEL_MODE={mode})",
                run_kwargs={"sel_mode": mode},
            )
            for mode in SEL_MODES
        ],
        broken_leg=Leg(build_subdir="broken"),
    )


if __name__ == "__main__":
    sys.exit(main())
