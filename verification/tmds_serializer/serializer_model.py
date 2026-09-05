"""Independent reference model for `rtl/tmds_serializer.v`.

Written from the interface contract in the RTL's own header comment and in
`spec/decisions/0014-serializer-rate-ceiling-and-microarchitecture.md` --
deliberately NOT by transcribing the RTL's shift-register structure, so an
error in the structure cannot be reproduced identically here. This module
knows only:

  * a TMDS character is transmitted **LSB first** (bit 0 of the encoder's
    `tmds[9:0]` is the first bit on the wire);
  * the serializer emits it as five successive 2-bit words, `ser[0]` being
    the earlier bit of each pair;
  * the divide-by-two output is high for exactly one `clk_bit` period and
    low for exactly one, starting low out of reset.

Everything the bench asserts is derived from those three sentences.
"""

from __future__ import annotations


def char_to_bits(word: int) -> list[int]:
    """One 10-bit TMDS character as its on-the-wire bit order (LSB first)."""
    if not 0 <= word < 1024:
        raise ValueError(f"not a 10-bit TMDS character: {word!r}")
    return [(word >> i) & 1 for i in range(10)]


def char_to_ser_words(word: int) -> list[tuple[int, int]]:
    """One character as the five (ser[0], ser[1]) pairs the DUT must emit."""
    bits = char_to_bits(word)
    return [(bits[2 * k], bits[2 * k + 1]) for k in range(5)]


def chars_to_bitstream(words: list[int]) -> list[int]:
    """Concatenate characters into the bit sequence that must appear on the wire."""
    stream: list[int] = []
    for word in words:
        stream.extend(char_to_bits(word))
    return stream


def ser_words_to_bitstream(pairs: list[tuple[int, int]]) -> list[int]:
    """Flatten observed (ser[0], ser[1]) pairs into a wire-order bit sequence."""
    stream: list[int] = []
    for lo, hi in pairs:
        stream.append(lo)
        stream.append(hi)
    return stream


def find_alignment(observed: list[int], expected: list[int], probe_len: int = 60) -> int:
    """Index in `observed` where `expected` starts, or -1.

    The DUT has a fixed but deliberately-unspecified pipeline latency (the
    RTL header states three `clk_half` cycles; the bench does not hard-code
    that, so a latency change is not a bench change). The alignment is found
    by searching for a probe taken from the middle of `expected` -- not from
    its start, because the very first character out of reset is emitted
    while the shift register still holds reset zeros.
    """
    if len(expected) < probe_len:
        raise ValueError("expected stream shorter than the alignment probe")
    probe = expected[:probe_len]
    limit = len(observed) - probe_len
    for offset in range(max(limit, 0) + 1):
        if observed[offset : offset + probe_len] == probe:
            return offset
    return -1
