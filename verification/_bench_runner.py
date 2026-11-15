#!/usr/bin/env python3
"""Shared three-leg verification runner skeleton for this directory's benches.

Each `<bench-name>/runner.py` keeps only what is genuinely bench-specific --
its source layout, its `run_leg` build call, and its leg-1+2 configuration
list -- and delegates everything that must never drift between benches to
this module: the `--good-only` / `--broken-only` argument surface (and their
mutual exclusion), the "real DUT must pass / negative control must fail"
orchestration, the per-leg stdout format, and the OVERALL verdict + exit
code. The three-leg plan itself is documented in verification/README.md:

  - Leg 1 + Leg 2 (`--good-only` or default): the real DUT must pass
    every test with zero failures.
  - Leg 3 (`--broken-only` or default): the same test module, run against
    the bench's negative-control DUT, must FAIL -- a bench that has never
    failed is not known to be able to.

Exit status is 0 only if every leg behaves as expected; this is what CI
gates on (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: Repository root: this module lives at `<repo>/verification/_bench_runner.py`,
#: and the runners print DUT paths relative to it.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: A bench's `run_leg`: build + simulate one configuration, returning
#: (num_tests, num_failed). Called as
#: ``run_leg(dut_source, build_subdir, **run_kwargs)``.
RunLeg = Callable[..., tuple[int, int]]


@dataclass(frozen=True)
class Leg:
    """One configuration of the real DUT (Leg 1+2) or the negative control (Leg 3).

    `label` is interpolated into the leg's stdout lines (e.g.
    ``" (SEL_MODE=2)"``) so every configuration a bench runs stays named in
    its output; `run_kwargs` are forwarded verbatim to the bench's
    `run_leg` (e.g. ``sel_mode=2``).
    """

    build_subdir: str
    label: str = ""
    run_kwargs: dict[str, object] = field(default_factory=dict)


def run_three_leg_bench(
    *,
    description: str,
    test_module: str,
    good_dut: Path,
    broken_dut: Path,
    run_leg: RunLeg,
    good_legs: Sequence[Leg],
    broken_leg: Leg,
) -> int:
    """Run the three-leg plan. Returns the process exit code (0 = PASS)."""
    parser = argparse.ArgumentParser(description=description)
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
        print(f"=== Leg 1+2: {test_module} vs. {good_dut.relative_to(REPO_ROOT)} ===")
        for leg in good_legs:
            n, f = run_leg(good_dut, leg.build_subdir, **leg.run_kwargs)
            print(f"real DUT{leg.label}: {n} test(s), {f} failed")
            if f != 0:
                print(f"FAIL: the real DUT must pass every test{leg.label}.")
                ok = False
            else:
                print(f"PASS: real DUT passed the full bench{leg.label}.")

    if run_broken:
        print(
            f"=== Leg 3 (negative control): {test_module} vs. "
            f"{broken_dut.relative_to(REPO_ROOT)} ==="
        )
        n, f = run_leg(broken_dut, broken_leg.build_subdir, **broken_leg.run_kwargs)
        print(f"broken DUT: {n} test(s), {f} failed")
        if f == 0:
            print(
                "FAIL: negative control did not fail -- this bench is not known to be "
                "able to fail."
            )
            ok = False
        else:
            print(f"PASS: negative control correctly failed ({f}/{n} test(s)).")

    print()
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1
