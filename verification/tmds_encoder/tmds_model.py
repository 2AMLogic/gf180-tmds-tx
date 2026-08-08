"""Independent Python golden model for the DVI-mode TMDS encoder.

This is a from-scratch, separately-authored transcription of the same
cited algorithm as ``rtl/tmds_encoder.v`` -- it exists to catch coding
mistakes made only in the RTL (Leg 1 of the verification plan in
verification/README.md), not to re-derive the algorithm independently.
The independent cross-checks that catch a *shared* misreading of the
standard are Leg 2 (the invariant checks in test_tmds_encoder.py, which
do not consult this model) and Leg 3 (the negative control).

Citation
--------
Digital Display Working Group, "Digital Visual Interface (DVI),
Revision 1.0", 2 April 1999 -- Section 3.3 "TMDS Encoding" (stage 1:
transition minimization, Figure 3-5; stage 2: DC balancing) and the
control-token values transmitted during blanking.

Cross-check (not the primary source): the same algorithm and control
tokens are reproduced in the public "Transition-minimized differential
signaling" Wikipedia article, which also documents the well-known
invariant that exactly 460 of the 1024 possible 10-bit codes are valid
TMDS data characters -- ``discover_reachable_states`` below independently
re-derives that count from this transcription (see verification/README.md
for the reported value), which corroborates the transcription without
substituting for the primary citation.
"""

from __future__ import annotations

from collections import deque

# The four fixed control characters, indexed by ctrl = {C1, C0} as a
# 2-bit integer (0..3), matching rtl/tmds_encoder.v's `ctrl` port and its
# `case (ctrl)` statement bit-for-bit.
CONTROL_CODES: dict[int, int] = {
    0b00: 0b1101010100,  # C1=0, C0=0
    0b01: 0b0010101011,  # C1=0, C0=1
    0b10: 0b0101010100,  # C1=1, C0=0
    0b11: 0b1010101011,  # C1=1, C0=1
}


def count_ones(d: int) -> int:
    """Number of set bits in the 8-bit value `d`."""
    return bin(d & 0xFF).count("1")


def _stage1(d: int) -> tuple[list[int], int]:
    """Transition-minimized XOR/XNOR encode.

    Returns (qm, qm8) where qm is a list of 8 bits (qm[0]..qm[7], LSB
    first) and qm8 is 1 if the XOR chain was used, 0 if XNOR was used --
    matching rtl/tmds_encoder.v's `stage1` function exactly.
    """
    n1 = count_ones(d)
    use_xnor = (n1 > 4) or (n1 == 4 and (d & 1) == 0)
    qm = [0] * 8
    qm[0] = d & 1
    for i in range(1, 8):
        di = (d >> i) & 1
        if use_xnor:
            qm[i] = 1 - (qm[i - 1] ^ di)
        else:
            qm[i] = qm[i - 1] ^ di
    qm8 = 0 if use_xnor else 1
    return qm, qm8


def _stage2(qm: list[int], qm8: int, cnt: int) -> tuple[int, int, list[int], int]:
    """DC-balance stage. Returns (q9, q8, data_bits, next_cnt)."""
    n1 = sum(qm)
    n0 = 8 - n1
    disparity = n1 - n0  # even, in [-8, 8]

    if cnt == 0 or disparity == 0:
        q9 = 1 - qm8
        q8 = qm8
        data = qm[:] if qm8 else [1 - b for b in qm]
        next_cnt = cnt + (disparity if qm8 else -disparity)
    elif (cnt > 0 and disparity > 0) or (cnt < 0 and disparity < 0):
        q9 = 1
        q8 = qm8
        data = [1 - b for b in qm]
        next_cnt = cnt + (2 if qm8 else 0) - disparity
    else:
        q9 = 0
        q8 = qm8
        data = qm[:]
        next_cnt = cnt + disparity - (0 if qm8 else 2)

    return q9, q8, data, next_cnt


def _pack(q9: int, q8: int, data: list[int]) -> int:
    val = (q9 << 9) | (q8 << 8)
    for i, b in enumerate(data):
        val |= b << i
    return val


def encode(data: int, cnt: int) -> tuple[int, int]:
    """Encode one 8-bit data word under running disparity `cnt`.

    Returns (code, next_cnt): the 10-bit TMDS character (as an int,
    bit 9 is MSB matching rtl/tmds_encoder.v's `tmds[9:0]`) and the
    updated running-disparity accumulator.
    """
    qm, qm8 = _stage1(data)
    q9, q8, out_data, next_cnt = _stage2(qm, qm8, cnt)
    return _pack(q9, q8, out_data), next_cnt


def encode_control(ctrl: int) -> int:
    """Fixed control character for ctrl = {C1, C0} (0..3)."""
    return CONTROL_CODES[ctrl & 0b11]


def decode(code: int) -> int:
    """Recover the original 8-bit data word from a 10-bit *data* character.

    Stateless: unlike encoding, TMDS decoding does not need the running
    disparity, because bit 9 records whether the 8 data-derived bits were
    inverted and bit 8 records which of the XOR/XNOR chains encoded them
    -- both are carried in the character itself. Only valid for data
    characters (i.e. `code` produced by `encode`, not `encode_control`);
    behavior on a control character is unspecified by this function.
    """
    q9 = (code >> 9) & 1
    q8 = (code >> 8) & 1
    raw = code & 0xFF
    qm07 = (
        [(raw >> i) & 1 for i in range(8)]
        if q9 == 0
        else [1 - ((raw >> i) & 1) for i in range(8)]
    )

    use_xnor = q8 == 0
    d = [0] * 8
    d[0] = qm07[0]
    for i in range(1, 8):
        if use_xnor:
            d[i] = 1 - (qm07[i - 1] ^ qm07[i])
        else:
            d[i] = qm07[i - 1] ^ qm07[i]
    value = 0
    for i, b in enumerate(d):
        value |= b << i
    return value


def transitions(code: int) -> int:
    """Number of bit-to-bit transitions among the 8 data-derived bits
    (code[7:0]) of a *data* character -- the property the transition-
    minimization stage (DVI 1.0 Sec 3.3, stage 1) bounds. Full derivation
    of the exact bound is in verification/README.md."""
    bits = [(code >> i) & 1 for i in range(8)]
    return sum(1 for i in range(1, 8) if bits[i] != bits[i - 1])


def discover_reachable_states(start: int = 0) -> dict[int, list[int]]:
    """Breadth-first search of the running-disparity accumulator's
    reachable state space, starting from `start` (the post-reset /
    post-blanking value).

    Returns a dict mapping each reachable state to a *witness* sequence
    of data words: driving `start` through `encode` for each word in the
    sequence, in order, reaches that state. This lets the exhaustive bench
    re-establish any reachable state on real hardware without needing to
    read the DUT's internal accumulator register.
    """
    parent: dict[int, tuple[int | None, int | None]] = {start: (None, None)}
    queue: deque[int] = deque([start])
    while queue:
        state = queue.popleft()
        for d in range(256):
            _, next_state = encode(d, state)
            if next_state not in parent:
                parent[next_state] = (state, d)
                queue.append(next_state)

    witnesses: dict[int, list[int]] = {}
    for state in parent:
        seq: list[int] = []
        cur = state
        while parent[cur][0] is not None:
            prev_state, d = parent[cur]
            seq.append(d)  # type: ignore[arg-type]
            cur = prev_state  # type: ignore[assignment]
        seq.reverse()
        witnesses[state] = seq
    return witnesses
