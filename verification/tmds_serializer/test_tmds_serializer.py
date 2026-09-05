"""cocotb testbench for the TMDS serializer DUT (`tmds_serializer`), elaborated
together with the real encoder by `tmds_tx_chain.v`.

Two independent things are verified, both required by issue #159 and, for the
second, by DR-0012's own Consequences section ("its own testbench must verify
the resulting half-rate clock's phase alignment to the bit-rate clock and 50%
duty cycle directly"):

  Leg 1 -- **reduction correctness against the encoder's real output.** The
      bench drives the encoder with random active-video and blanking symbols,
      records the encoder's own `tmds` characters as they appear, records the
      serializer's `ser` word stream, and asserts the second is the LSB-first
      serialization of the first. The expected stream comes from
      `serializer_model.py`, which is written from the interface contract, not
      by transcribing the RTL's structure.

  Leg 2 -- **the divide-by-two's phase alignment and duty cycle**, measured
      directly in simulation time: every `clk_half` edge must coincide with a
      `clk_bit` rising edge, and the high and low half-periods must each be
      exactly one `clk_bit` period.

Both legs run at BOTH ratified operating points (720p60's 742.5 Mbps and
480p's 270 Mbps -- spec/tmds-tx.md #1), because a reduction shown to work at
one rate has not been shown to work at the other.

Leg 3 (negative control) is not in this file: runner.py runs this exact same
test module, unmodified, against negative_control/tmds_serializer_broken.v and
asserts it FAILS -- the same three-leg discipline verification/README.md
already applies to the encoder bench.

## On the clock periods used here

The bench uses 1348 ps / 13480 ps (720p60) and 3704 ps / 37040 ps (480p)
rather than the exact 1346.80 ps / 3703.70 ps the ratified rates imply. The
rounding is deliberate and harmless: what this bench checks is FUNCTION (bit
ordering, character cadence, divider ratio and duty cycle), all of which
depend only on the exact 10:1 clk_bit-to-clk_pix ratio, not on the absolute
frequency. Whether the logic closes timing at the real frequency is a static
timing question, not a simulation one -- `flow/serializer_rate_feasibility.py`
and DR-0014 answer that one with measured library arcs, and their answer is
the reason DR-0014 exists.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402
from cocotb.utils import get_sim_time  # noqa: E402

import serializer_model as model  # noqa: E402

#: The two ratified operating points, as (label, clk_bit period ps,
#: clk_pix period ps). The 10:1 ratio is spec/tmds-tx.md #2's; see this
#: module's docstring for why the periods are rounded.
OPERATING_POINTS = (
    ("720p60", 1348, 13480),
    ("480p", 3704, 37040),
)

#: Settling margin used whenever a signal is read after a clock edge, so the
#: read observes the post-edge value rather than racing the nonblocking
#: assignment. Small compared with any half-period used here.
READ_DELAY_PS = 1


def _now_ps() -> int:
    return int(round(get_sim_time(unit="ps")))


class ClockPair:
    """The bit-rate and pixel-rate clocks, started edge-aligned.

    Both are started with `start_high=True` (cocotb's default), so both go
    high at the same instant and their first rising edges land at one period
    later. Because the pixel period is exactly ten bit periods, every pixel
    rising edge then coincides with a bit rising edge -- which is what
    spec/tmds-tx.md #2's "10:1, edge-aligned" relationship means, and what the
    serializer's character-boundary detector assumes.
    """

    def __init__(self, dut, t_bit_ps: int, t_pix_ps: int) -> None:
        assert t_pix_ps == 10 * t_bit_ps, "spec/tmds-tx.md #2 fixes a 10:1 ratio"
        self.t_bit = t_bit_ps
        self.t_pix = t_pix_ps
        self._bit = Clock(dut.clk_bit, t_bit_ps, unit="ps")
        self._pix = Clock(dut.clk_pix, t_pix_ps, unit="ps")

    def start(self) -> None:
        self._bit.start()
        self._pix.start()

    def stop(self) -> None:
        self._bit.stop()
        self._pix.stop()


async def reset_dut(dut) -> None:
    """Assert reset, hold it across both domains, release on a bit-clock edge."""
    dut.rst.value = 1
    dut.data.value = 0
    dut.ctrl.value = 0
    dut.de.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk_pix)
    await RisingEdge(dut.clk_bit)
    dut.rst.value = 0
    await RisingEdge(dut.clk_bit)


# ---------------------------------------------------------------------------
# Leg 2: DR-0012 Decision 1's divide-by-two
# ---------------------------------------------------------------------------


async def _divider_edge_log(dut, n_edges: int) -> list[tuple[int, int]]:
    """Record (sim time ps, new level) for the next `n_edges` clk_half edges."""
    log: list[tuple[int, int]] = []
    while len(log) < n_edges:
        await dut.clk_half.value_change
        log.append((_now_ps(), int(dut.clk_half.value)))
    return log


@cocotb.test()
async def test_divider_duty_cycle_and_phase_alignment(dut):
    """DR-0012 Decision 1: exactly 50% duty, every edge on a clk_bit rising edge.

    Checked at both operating points. This is the check DR-0012's own
    Consequences section requires of this block's testbench, in its own words:
    "must verify the resulting half-rate clock's phase alignment to the
    bit-rate clock and 50% duty cycle directly".
    """
    for label, t_bit, t_pix in OPERATING_POINTS:
        clocks = ClockPair(dut, t_bit, t_pix)
        clocks.start()
        try:
            await reset_dut(dut)

            # Phase alignment is checked against the clk_bit rising-edge GRID
            # rather than against a concurrently-collected list of edge times:
            # a parallel collector races the divider observer within the same
            # timestep, and a race in the checker would make this test's own
            # verdict depend on scheduler order. One reference edge plus the
            # known period is exact and order-independent -- every clk_bit
            # rising edge is at t_ref + k * t_bit, by construction.
            await RisingEdge(dut.clk_bit)
            t_ref = _now_ps()
            edges = await _divider_edge_log(dut, 21)

            for t, _level in edges:
                assert (t - t_ref) % t_bit == 0, (
                    f"{label}: clk_half edge at {t} ps is {(t - t_ref) % t_bit} ps off "
                    f"the clk_bit rising-edge grid (reference edge {t_ref} ps, period "
                    f"{t_bit} ps) -- the divider is not clocked by clk_bit"
                )

            intervals = [b[0] - a[0] for a, b in zip(edges, edges[1:])]
            assert set(intervals) == {t_bit}, (
                f"{label}: clk_half half-periods {sorted(set(intervals))} ps are not "
                f"all exactly one clk_bit period ({t_bit} ps) -- duty is not 50%"
            )

            highs = [b[0] - a[0] for a, b in zip(edges, edges[1:]) if a[1] == 1]
            lows = [b[0] - a[0] for a, b in zip(edges, edges[1:]) if a[1] == 0]
            assert highs and lows, f"{label}: divider did not produce both levels"
            assert sum(highs) / len(highs) == sum(lows) / len(lows), (
                f"{label}: mean high {sum(highs) / len(highs)} ps != mean low "
                f"{sum(lows) / len(lows)} ps"
            )

            periods = [b[0] - a[0] for a, b in zip(edges, edges[2:])]
            assert set(periods) == {2 * t_bit}, (
                f"{label}: clk_half period {sorted(set(periods))} ps is not "
                f"2 x clk_bit ({2 * t_bit} ps) -- this is not a divide-by-two"
            )

            dut._log.info(
                "%s: divider OK -- %d edges, all on clk_bit rising edges, "
                "high=%d ps low=%d ps period=%d ps",
                label,
                len(edges),
                highs[0],
                lows[0],
                periods[0],
            )
        finally:
            clocks.stop()


@cocotb.test()
async def test_reset_forces_known_state(dut):
    """Reset clears the serialized output, with no clk_half edge in between.

    The datapath's reset is asynchronous-assert by necessity -- asserting
    `rst` stops `clk_half`, so a synchronous reset in that domain could never
    take effect (see rtl/tmds_serializer.v's "Reset" header section). This
    test is what makes that claim checkable rather than merely asserted: it
    raises `rst` mid-period and reads `ser` back before any further
    `clk_half` edge can occur.
    """
    label, t_bit, t_pix = OPERATING_POINTS[0]
    clocks = ClockPair(dut, t_bit, t_pix)
    clocks.start()
    try:
        await reset_dut(dut)

        dut.de.value = 1
        for _ in range(6):
            dut.data.value = random.randrange(256)
            await RisingEdge(dut.clk_pix)

        await RisingEdge(dut.clk_half)
        await Timer(READ_DELAY_PS, unit="ps")
        dut.rst.value = 1
        await Timer(READ_DELAY_PS, unit="ps")
        assert int(dut.ser.value) == 0, (
            f"{label}: ser = {dut.ser.value} immediately after rst was asserted, with "
            "no intervening clk_half edge -- the datapath reset is not taking effect"
        )

        await RisingEdge(dut.clk_bit)
        await Timer(READ_DELAY_PS, unit="ps")
        assert int(dut.clk_half.value) == 0, (
            f"{label}: clk_half = 1 one clk_bit edge after rst -- the divider's "
            "synchronous reset is not taking effect"
        )
    finally:
        clocks.stop()


# ---------------------------------------------------------------------------
# Leg 1: reduction correctness against the encoder's real output
# ---------------------------------------------------------------------------


async def _collect_characters(dut, n: int) -> list[int]:
    words: list[int] = []
    while len(words) < n:
        await RisingEdge(dut.clk_pix)
        await Timer(READ_DELAY_PS, unit="ps")
        words.append(int(dut.tmds.value))
    return words


async def _collect_ser_words(dut, n: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    while len(pairs) < n:
        await RisingEdge(dut.clk_half)
        await Timer(READ_DELAY_PS, unit="ps")
        value = int(dut.ser.value)
        pairs.append((value & 1, (value >> 1) & 1))
    return pairs


async def _drive_symbols(dut, n: int, rng: random.Random) -> None:
    for _ in range(n):
        if rng.random() < 0.2:
            dut.de.value = 0
            dut.ctrl.value = rng.randrange(4)
        else:
            dut.de.value = 1
            dut.data.value = rng.randrange(256)
        await RisingEdge(dut.clk_pix)


async def _reduction_check(dut, label: str, t_bit: int, t_pix: int, n_chars: int) -> None:
    rng = random.Random(0xA5 ^ t_bit)
    clocks = ClockPair(dut, t_bit, t_pix)
    clocks.start()
    try:
        await reset_dut(dut)

        driver = cocotb.start_soon(_drive_symbols(dut, n_chars + 10, rng))
        chars_task = cocotb.start_soon(_collect_characters(dut, n_chars))
        ser_task = cocotb.start_soon(_collect_ser_words(dut, 5 * (n_chars + 4)))

        chars = await chars_task
        pairs = await ser_task
        await driver

        # Skip the first two characters: they are emitted while the shift
        # register still holds reset zeros, which is a start-up artifact
        # rather than a reduction result.
        expected = model.chars_to_bitstream(chars[2:])
        observed = model.ser_words_to_bitstream(pairs)

        offset = model.find_alignment(observed, expected)
        assert offset >= 0, (
            f"{label}: the encoder's own character stream never appears on ser.\n"
            f"  expected (first 30 bits): {expected[:30]}\n"
            f"  observed (first 60 bits): {observed[:60]}"
        )

        end = offset + len(expected)
        assert end <= len(observed), (
            f"{label}: aligned at offset {offset} but only {len(observed)} bits were "
            f"captured for {len(expected)} expected -- capture too short"
        )
        assert observed[offset:end] == expected, (
            f"{label}: reduction mismatch at bit "
            + str(
                next(
                    i
                    for i, (a, b) in enumerate(zip(observed[offset:end], expected))
                    if a != b
                )
            )
        )

        dut._log.info(
            "%s: reduction OK -- %d encoder characters (%d bits) reproduced exactly "
            "on ser at offset %d",
            label,
            len(chars) - 2,
            len(expected),
            offset,
        )
    finally:
        clocks.stop()


@cocotb.test()
async def test_reduction_matches_encoder_720p60(dut):
    """10-bit character -> 2-bit half-rate words, LSB first, at the 720p60 point."""
    await _reduction_check(dut, "720p60", 1348, 13480, n_chars=48)


@cocotb.test()
async def test_reduction_matches_encoder_480p(dut):
    """The same check at the 480p fallback point (spec/tmds-tx.md #1)."""
    await _reduction_check(dut, "480p", 3704, 37040, n_chars=48)


@cocotb.test()
async def test_ser_word_pairs_are_lsb_first(dut):
    """`ser[0]` carries the earlier bit of each pair.

    Checked in its own right rather than left implicit in the stream
    comparison: a DUT that emitted every pair swapped would still produce a
    *self-consistent* stream, and would show up here as an odd alignment
    offset -- half a `clk_half` word -- which is exactly the failure mode the
    DDR multiplexer cannot tolerate, since it emits `ser[0]` on the clock's
    high half and `ser[1]` on its low half.
    """
    label, t_bit, t_pix = OPERATING_POINTS[0]
    rng = random.Random(0x5A)
    clocks = ClockPair(dut, t_bit, t_pix)
    clocks.start()
    try:
        await reset_dut(dut)

        driver = cocotb.start_soon(_drive_symbols(dut, 26, rng))
        chars_task = cocotb.start_soon(_collect_characters(dut, 16))
        ser_task = cocotb.start_soon(_collect_ser_words(dut, 5 * 20))
        chars = await chars_task
        pairs = await ser_task
        await driver

        expected = model.chars_to_bitstream(chars[2:])
        observed = model.ser_words_to_bitstream(pairs)
        offset = model.find_alignment(observed, expected)
        assert offset >= 0, f"{label}: could not align the ser stream to the encoder"
        assert offset % 2 == 0, (
            f"{label}: the encoder's character stream aligns to ser at an ODD bit "
            f"offset ({offset}) -- ser[0]/ser[1] are swapped relative to the "
            "LSB-first order the DDR multiplexer's high half emits"
        )

        word_index = offset // 2
        for k, word in enumerate(chars[2:6]):
            want = model.char_to_ser_words(word)
            got = pairs[word_index + 5 * k : word_index + 5 * k + 5]
            assert got == want, (
                f"{label}: character {k} = 0x{word:03x} must serialize as {want}, "
                f"got {got}"
            )
    finally:
        clocks.stop()
