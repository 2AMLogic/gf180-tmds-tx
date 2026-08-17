"""cocotb testbench for the TMDS encoder DUT (`tmds_encoder`).

Implements Leg 1 (exhaustive equivalence against the independent Python
golden model in tmds_model.py) and Leg 2 (invariant checks, evaluated
directly against the sweep rather than against the model) of the
three-leg verification plan documented in verification/README.md.

Leg 3 (negative control) is not in this file: runner.py runs this exact
same test suite, unmodified, against
negative_control/tmds_encoder_broken.v and asserts it *fails* -- a bench
that only ever runs against a correct DUT is not known to be able to
fail.

This same test module is used against both DUT variants regardless of
their filename, because both declare `module tmds_encoder` with the same
port list; only the Verilog *source* passed to the builder differs
(see runner.py).

## DR-0009 four-clock latency, and why this bench streams rather than
## "hold and re-read"

Per spec/tmds-tx.md DR-0009 (which supersedes DR-0008's two-clock
contract), the DUT is a four-stage pipeline: `data`/`de`/`ctrl` reach the
registered `tmds` output **`LATENCY_CYCLES` = 4** clock cycles after being
driven, and every single clock edge unconditionally samples whatever is
currently on `data`/`de`/`ctrl` into the first pipeline register -- there
is no stall/valid signal. That matters for how this bench drives the DUT:
holding a symbol's inputs steady for extra cycles to "wait for the
pipeline to catch up" (the naive fix, tried and found wrong while
implementing DR-0008) re-latches the *same* symbol into the pipeline a
second time; the moment any further real symbol is pushed after that, the
DUT's final output register consumes that stale, already-read symbol
*again* -- silently corrupting the running-disparity accumulator `cnt`
later, with no assertion failure at the point the corruption happens
(only downstream, when a later encode's disparity looks wrong). This was
caught directly, not assumed: an early version of this bench's
`apply_data` held inputs for two cycles and failed the
exhaustive-equivalence test at `state=-8, data=0x00` with an output that
turned out to be `stage1(0)` re-consumed against the *already-updated*
`cnt`, not corruption in the model or the RTL.

The fix (`SymbolPipe` below): push exactly one real symbol per clock
cycle (matching the DUT's native, un-stalled throughput), and read each
pushed symbol's registered `tmds` code with the correct
**`LATENCY_CYCLES - 1` call lag** (`push_data`/`push_control` return the
code of the symbol pushed `LATENCY_CYCLES - 1` calls ago, not this call's
-- it is not registered yet). The lag is derived from the single
`LATENCY_CYCLES` constant below rather than hard-coded, so a further
latency change is a one-line edit here, not a rewrite of every test.

Chains of `push_data`/`push_control` calls compose correctly with no
intervening resets needed, because every push is a real, intentional
symbol; `drain()` (`LATENCY_CYCLES - 1` further pushes, contents
irrelevant) shifts out the final pushed symbol's code, and is only used
directly before `reset_dut()`, which unconditionally clears every
pipeline register regardless of `drain()`'s own leftover content (see
rtl/tmds_encoder.v's `rst` handling, and DR-0008's "rst is not pipelined"
consequence, carried forward by DR-0009) -- so nothing about `drain()`'s
arbitrary inputs ever gets silently reprocessed as a real symbol.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import FallingEdge, RisingEdge, Timer  # noqa: E402

import tmds_model as model  # noqa: E402

# Overridable via TMDS_SIM_CLOCK_PERIOD_NS so the gate-level, SDF-annotated
# leg (issue #85; see flow/gate_level_sim_tmds_encoder.py) can drive this exact same,
# unmodified test module at a slower, conservatively-margined period than
# the RTL/negative-control legs' default 10 ns -- see that module's
# docstring for why, and verification/README.md's "gate-level SDF-annotated
# leg" section for the full rationale (this is not an operating-frequency
# claim, the same disclaimer flow/pnr_tmds_encoder.py's own one
# `create_clock` already carries for the identical reason).
CLOCK_PERIOD_NS = int(os.environ.get("TMDS_SIM_CLOCK_PERIOD_NS", "10"))

# The DUT's registered input-to-`tmds` latency, in clock cycles, per
# spec/tmds-tx.md DR-0009 (four pipeline stages: S1 popcount/threshold,
# S2 transition-minimized word, S3 disparity candidates, S4 DC-balance
# decision + accumulator). Every lag in this bench is derived from this
# one constant -- see the module docstring.
LATENCY_CYCLES = 4


async def start_clock(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())
    # `clk` is X until the Clock coroutine's first edge; without this, the
    # very first `await RisingEdge(dut.clk)` below can observe a spurious
    # X->0 transition at t=0 instead of a real 0->1 edge, silently shifting
    # every subsequent cycle by one. See verification/README.md, "cocotb
    # clocking gotchas".
    await Timer(1, unit="ns")


async def clock_edge(dut) -> None:
    """Drive inputs (set by the caller before this call) through one rising
    edge, then settle at the following falling edge before returning, so
    that registered outputs (`tmds`, `cnt`) reflect this edge's
    non-blocking assignments before the caller reads them -- and so the
    caller can immediately write new inputs afterward. Reading immediately
    after a bare `await RisingEdge` can observe pre-edge register values on
    Icarus, and cocotb's `ReadOnly` phase (the more common fix for that)
    forbids writing new stimulus before the next trigger -- sampling at the
    following `FallingEdge` instead avoids both problems. See
    verification/README.md, "cocotb clocking gotchas"."""
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)


async def reset_dut(dut) -> None:
    """Synchronous reset. Per DR-0008 (carried forward by DR-0009), `rst`
    is *not* pipelined -- every pipeline register and the final tmds/cnt
    register clear on the same edge `rst` is sampled asserted, so this
    keeps the same one-cycle-to-effect latency the pre-pipeline DUT had.
    It also unconditionally discards any pipeline content a preceding
    `SymbolPipe.drain()` may have left behind (see module docstring)."""
    dut.rst.value = 1
    dut.de.value = 0
    dut.data.value = 0
    dut.ctrl.value = 0
    await clock_edge(dut)
    dut.rst.value = 0
    await clock_edge(dut)


class SymbolPipe:
    """Drives `tmds_encoder`'s `data`/`de`/`ctrl` one real symbol per clock
    cycle (its native, un-stalled throughput) and reads back each pushed
    symbol's registered `tmds` code with the correct `LATENCY_CYCLES - 1`
    call lag -- see this module's docstring for why holding/repeating a
    symbol's inputs to fake an immediate read is unsafe instead.

    Every push returns a code; that code belongs to the symbol pushed
    `LATENCY_CYCLES - 1` calls earlier, so the first `LATENCY_CYCLES - 1`
    returns after a reset are pipeline-fill artifacts with no symbol
    behind them. `pushes` counts calls since construction so a caller can
    tell which returns are meaningful; `has_output` says the same thing
    directly.
    """

    #: How many pushes after a symbol's own push its code comes back.
    LAG = LATENCY_CYCLES - 1

    def __init__(self, dut) -> None:
        self.dut = dut
        self.pushes = 0

    @property
    def has_output(self) -> bool:
        """True once enough pushes have happened that the last push's
        return value belongs to a real, caller-supplied symbol."""
        return self.pushes > self.LAG

    async def push_data(self, data: int, ctrl: int = 0) -> int:
        """Push one active-video symbol. Returns the registered `tmds`
        code of the symbol pushed `LAG` calls ago (this call's own code is
        not registered for another `LAG` pushes -- see `drain()`)."""
        return await self._push(de=1, data=data, ctrl=ctrl)

    async def push_control(self, ctrl: int) -> int:
        """Push one blanking symbol. Returns the code of the symbol pushed
        `LAG` calls ago."""
        return await self._push(de=0, data=0, ctrl=ctrl)

    async def drain(self) -> int:
        """`LAG` further pushes, with arbitrary inputs, to shift out the
        most recently pushed real symbol's code (returned). Only safe to
        call immediately before `reset_dut()` (or another `drain()`) --
        see module docstring."""
        codes = await self.drain_all()
        return codes[-1]

    async def drain_all(self) -> list[int]:
        """`LAG` further pushes, returning every code they shift out --
        i.e. the codes of the last `LAG` real symbols pushed, oldest
        first. Same safety caveat as `drain()`."""
        return [await self._push(de=1, data=0, ctrl=0) for _ in range(self.LAG)]

    async def _push(self, de: int, data: int, ctrl: int) -> int:
        self.dut.de.value = de
        self.dut.data.value = data
        self.dut.ctrl.value = ctrl
        await clock_edge(self.dut)
        self.pushes += 1
        return int(self.dut.tmds.value)


@cocotb.test()
async def test_control_characters_and_blanking_reset(dut):
    """The four fixed control characters, and the blanking-resets-the-
    accumulator behavior (DVI 1.0 blanking behaviour, cited in
    rtl/tmds_encoder.v)."""
    await start_clock(dut)
    await reset_dut(dut)

    for ctrl in range(4):
        await reset_dut(dut)
        pipe = SymbolPipe(dut)
        await pipe.push_control(ctrl)
        actual = await pipe.drain()
        expected = model.encode_control(ctrl)
        assert actual == expected, (
            f"control character mismatch: ctrl={ctrl:#04b} dut={actual:#05x} "
            f"model={expected:#05x}"
        )
    dut._log.info("All 4 control characters match the cited DVI 1.0 values.")

    # Drive the accumulator away from zero with active video, then blank,
    # then confirm the very next data word is encoded as if from cnt=0 --
    # i.e. blanking really did reset the accumulator, not just emit a
    # control character. This is one continuous stream (no resets in
    # between): SymbolPipe's one-call-lag reads compose correctly across
    # it, unlike a hold-and-repeat design would (see module docstring).
    await reset_dut(dut)
    pipe = SymbolPipe(dut)
    rnd = random.Random(1)
    for _ in range(16):
        await pipe.push_data(rnd.randint(0, 255))  # fire-and-forget: only cnt matters here
    await pipe.push_control(rnd.randint(0, 3))  # fire-and-forget blank; seeds de_p1=0

    for d in range(256):
        expected_code, _ = model.encode(d, 0)
        # This push's own code isn't available yet (`SymbolPipe.LAG`-call
        # lag) -- the LAG'th following push's return value is this
        # push_data's code. Those following pushes are deliberately
        # *blanking* symbols, so they also re-blank `cnt` to zero ahead of
        # the next `d`, which is the property this loop is testing.
        await pipe.push_data(d)
        actual_code = -1
        for _ in range(SymbolPipe.LAG):
            actual_code = await pipe.push_control(0)
        assert actual_code == expected_code, (
            f"post-blanking data mismatch (accumulator not reset?): data={d:#04x} "
            f"dut={actual_code:#05x} model={expected_code:#05x}"
        )
    dut._log.info(
        "Blanking correctly resets the running-disparity accumulator (256/256 checked)."
    )


@cocotb.test()
async def test_exhaustive_equivalence_and_invariants(dut):
    """Leg 1 + Leg 2.

    Leg 1: DUT and the independent Python golden model agree on every
    point of the full enumerated (reachable running-disparity state) x
    (256 data words) space -- discovered and reported here, not assumed.

    Leg 2 (checked directly against the sweep, not against the model):
      - transition bound: observed max transitions among the 8
        data-derived output bits, compared to the bound the DVI 1.0
        transition-minimization stage guarantees (see
        verification/README.md for the derivation: <= 3).
      - control/data distinguishability: none of the reachable data
        codes collide with any of the 4 fixed control codes.
      - round-trip decode: an independent decode model recovers the
        original 8-bit word for every (data, accumulator-state) pair.
    """
    await start_clock(dut)

    witnesses = model.discover_reachable_states()
    states = sorted(witnesses)
    dut._log.info(
        f"Discovered {len(states)} reachable running-disparity states: {states}"
    )
    max_accumulator_excursion = max(abs(s) for s in states)
    dut._log.info(
        f"Leg 2 (accumulator excursion): observed max magnitude = {max_accumulator_excursion} "
        f"(reachable range [{min(states)}, {max(states)}]) -- confirmed against the DUT below, "
        "since every state in this set is established on real hardware via a witness sequence "
        "and its resulting encodes are checked against the model"
    )

    total_vectors = len(states) * 256
    checked = 0
    max_transitions_observed = 0
    reachable_data_codes: set[int] = set()
    roundtrip_failures = 0

    for state in states:
        for d in range(256):
            # Re-establish `state` from a clean reset via its witness
            # sequence (every reachable state here has a witness of
            # length 0 or 1 -- see verification/README.md), then apply
            # the data word under test. Witness words are pushed
            # fire-and-forget (single real symbol per push, no drain --
            # see module docstring); only the final target word `d` needs
            # its code read back, via `drain()` right before the next
            # iteration's `reset_dut()`.
            await reset_dut(dut)
            pipe = SymbolPipe(dut)
            for witness_data in witnesses[state]:
                await pipe.push_data(witness_data)

            expected_code, _expected_next_cnt = model.encode(d, state)
            await pipe.push_data(d)
            actual_code = await pipe.drain()

            assert actual_code == expected_code, (
                f"equivalence mismatch: state={state} data={d:#04x} "
                f"dut={actual_code:#05x} model={expected_code:#05x}"
            )
            checked += 1

            t = model.transitions(actual_code)
            max_transitions_observed = max(max_transitions_observed, t)
            reachable_data_codes.add(actual_code)

            if model.decode(actual_code) != d:
                roundtrip_failures += 1

    dut._log.info(
        f"Leg 1 (exhaustive equivalence): checked {checked} of {total_vectors} "
        f"enumerated (state, data) vectors ({len(states)} reachable states x "
        "256 data words) -- full coverage, not a sample."
    )
    assert checked == total_vectors, "did not cover the full enumerated space"

    dut._log.info(
        f"Leg 2 (transition bound): observed max transitions = {max_transitions_observed}"
    )
    assert max_transitions_observed <= 3, (
        f"observed {max_transitions_observed} transitions among the 8 data-derived "
        "output bits, expected <= 3 (DVI 1.0 Sec 3.3 transition-minimization stage; "
        "derivation in verification/README.md)"
    )

    dut._log.info(
        f"Leg 2 (round-trip decode): {roundtrip_failures} failures over {checked} vectors"
    )
    assert roundtrip_failures == 0, f"{roundtrip_failures} round-trip decode failures"

    control_codes = set(model.CONTROL_CODES.values())
    overlap = reachable_data_codes & control_codes
    dut._log.info(
        f"Leg 2 (control/data distinguishability): {len(reachable_data_codes)} distinct "
        f"reachable data codes (of 1024 possible), {len(overlap)} collide with the "
        "4 control codes"
    )
    assert not overlap, f"data/control character collision: {overlap}"


@cocotb.test()
async def test_long_run_cumulative_disparity_bound(dut):
    """Leg 2: over a long pseudo-random stream with realistic blanking
    intervals, the cumulative bit-level disparity of the serial TMDS
    output stays bounded. This is the property the line is DC-coupled on
    (CLAUDE.md, DR-0002).

    Discovered nuance (recorded here rather than silently assumed away):
    the per-*data*-character disparity is tightly bounded by the running-
    disparity accumulator (+-8, reset every blanking interval), but two of
    the four fixed *control* characters carry nonzero disparity themselves
    (CTRL_10 = -2, CTRL_11 = +2 -- see verification/README.md). Nothing in
    the encoder equalizes control-character usage, so a stream that
    selects among the 4 control codes uniformly at random (as this test
    does, deliberately, to stress the property rather than flatter it) is
    a *bounded-step random walk*, not a fixed-constant-bounded signal --
    its magnitude grows roughly with sqrt(symbol count), not O(1). A real
    DVI/TMDS link does not hit this worst case (control codes encode
    HSYNC/VSYNC, which are far from uniformly distributed over a real
    blanking interval), but this bench does not get to assume that; it
    reports what it actually observes and bounds it structurally instead
    of with an arbitrary constant.

    The assertion below is therefore a random-walk sanity bound
    (a small constant times sqrt(symbol count), not a value stated by the
    DVI 1.0 citation) -- large enough to tolerate that expected sqrt(n)
    growth, tight enough to still catch a genuine DC-balance regression
    (e.g. an accumulator that never corrects, which grows linearly in n
    and blows through this bound quickly). The *observed* value is
    reported regardless of the assertion, per the acceptance criteria.

    Reads every pushed symbol's code over one continuous stream (200
    burst/blank groups, no resets in between) via `SymbolPipe`'s
    `LATENCY_CYCLES - 1` call lag: each push's return is the code of the
    symbol pushed that many calls earlier, so the first `LAG` pushes
    (right after reset, nothing meaningful in flight yet) are discarded
    via `has_output`, and one trailing `drain_all()` reads back the last
    `LAG` real symbols once the stream ends."""
    await start_clock(dut)
    await reset_dut(dut)
    pipe = SymbolPipe(dut)

    rnd = random.Random(0xC0FFEE)
    cumulative = 0
    max_abs_cumulative = 0
    n_symbols = 0

    def record(code: int) -> None:
        nonlocal cumulative, max_abs_cumulative, n_symbols
        cumulative += bin(code).count("1") * 2 - 10
        max_abs_cumulative = max(max_abs_cumulative, abs(cumulative))
        n_symbols += 1

    for _ in range(200):
        burst_len = rnd.randint(1, 64)
        for _ in range(burst_len):
            code = await pipe.push_data(rnd.randint(0, 255))
            if pipe.has_output:
                record(code)

        blank_len = rnd.randint(1, 16)
        for _ in range(blank_len):
            code = await pipe.push_control(rnd.randint(0, 3))
            if pipe.has_output:
                record(code)

    for code in await pipe.drain_all():
        record(code)

    dut._log.info(
        f"Leg 2 (long-run cumulative disparity): {n_symbols} symbols, "
        f"observed max |cumulative disparity| = {max_abs_cumulative}"
    )
    random_walk_bound = 5 * (n_symbols**0.5)
    dut._log.info(
        f"Leg 2 (long-run cumulative disparity): sanity bound = {random_walk_bound:.1f}"
    )
    assert max_abs_cumulative < random_walk_bound, (
        f"cumulative disparity grew to {max_abs_cumulative} over {n_symbols} symbols, "
        f"exceeding the {random_walk_bound:.1f} random-walk sanity bound -- this looks like "
        "unbounded (e.g. linear) drift, not the expected sqrt(n)-scale random-walk fluctuation"
    )
