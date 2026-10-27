"""Shared pad-ring geometry for `pad_pitch_fit_study.py` and
`gen_pad_ring_assembly.py` (issue #262).

Both generators draw the same DR-0011 pad structure -- DVDD/DVSS ring straps,
a substrate tap, and the `gen_pad_v2.py`-geometry production bond pad with its
folded `diode_nd2ps_06v0` clamp -- and each used to carry its own copy of the
three drawing helpers and the constants they depend on. They now live here
once, so a DRC-driven geometry fix reaches both the fit-study GDS and the
assembly GDS (same relationship `gf180_layers.py` gave the layer table,
issue #255).

The fold arithmetic (`clamp_rows`, `_row_span`, `_row_pitch`) and its
constants moved here from `pad_pitch_fit_study.py` (issue #242's single
implementation); both generators re-export them under their old names.

Via-cut size is the one deliberately *parameterised* value: the fit study's
committed GDS/DRC evidence was drawn with 0.30 um cuts while the assembly
draws the fixed 0.26 um `via*.width.1` square, so each caller passes its own
`via_half` rather than this module picking one and silently changing the
other's geometry.

`klayout.db` stays optional so the pure arithmetic imports in CI's
KLayout-free job (same convention as the two generators).
"""

from __future__ import annotations

try:  # pragma: no cover -- exercised by whichever environment is present
    import klayout.db as db
except ModuleNotFoundError:  # pragma: no cover
    db = None

from gf180_layers import (
    COMP,
    CONTACT,
    DIODE_MK,
    DUALGATE,
    METAL1,
    METAL1_LABEL,
    METAL2,
    METAL3,
    METAL4,
    METAL5,
    METAL5_LABEL,
    NPLUS,
    PAD_LAYER,
    PPLUS,
    VIA1,
    VIA2,
    VIA3,
    VIA4,
    _box,
)

CONTACT_SIZE = 0.22  # klt's contact.width.1 floor
VIA_SIZE = 0.26  # via*.width.1 is a fixed 0.26 x 0.26um square at every level (klt >= 0.7)
VIA_HALF = VIA_SIZE / 2  # default cut half-size; callers may pass their own `via_half`

# Ring supply-strap bands (Metal3/Metal4/Metal5, DR-0011's ring-continuity
# requirement), both comfortably inside RING_DEPTH_UM and clear of the
# diode-pad structures placed above them.
DVSS_BAND = (2.0, 6.0)
DVDD_BAND = (12.0, 16.0)
STRAP_STITCH_PITCH_UM = 50.0  # via3/via4 stitch interval tying M3-M4-M5 together

# Pad + clamp geometry, adopted verbatim from gen_pad_v2.py (issue #87).
PAD_SIDE = 25.0  # um -- gf180mcu_fd_io__bi_t.lef's own PAD pin size
PAD_OPENING_MARGIN = 2.5  # um -- above pad.enclosing.metal5.1's 2.0um floor
PAD_VIA_GAP_UM = 1.5  # x gap from the last finger to the via-stack centre

FINGER_L = 2.0  # um, long (periphery/width) axis of one diode finger
FINGER_DEPTH = 1.0  # um, short axis
FINGER_PITCH = 2.6  # um, x pitch == FINGER_L + 0.6um (>= comp.space.mv.1 0.36um)
ROW_GAP_UM = 0.6  # um, y gap between rows -- the same margin FINGER_PITCH uses

# Metal1 cathode-gather bus width. gen_pad_v2.py's own bus is
# `2*0.13 + CONTACT_SIZE` = 0.48 um, which is what the default reproduces.
# `--bus-width` (pad_pitch_fit_study.py) exists because it is a *measurable*
# budget term, not a cosmetic one: `design/esd-capacitance-budget.md` Sec.9.3
# flagged that an HBM-sized clamp "would need a somewhat longer/wider Metal1
# bus to gather current from more fingers, which would add some additional
# routing capacitance beyond this figure ... not literally re-measured at
# every clamp size". Widening it and re-running `klt extract --parasitics`
# turns that caveat into a number.
DEFAULT_BUS_WIDTH_UM = 2 * 0.13 + CONTACT_SIZE

# Largest round per-row finger count that leaves >= 10um of slot margin at
# each end of a PAD_PITCH_UM slot once the via stack and the 25um Metal5
# plate are accounted for -- see `pad_pitch_fit_study.fit_report` for the
# arithmetic, which is reported rather than asserted so the margin is
# auditable per run.
MAX_FINGERS_PER_ROW = 120


def clamp_rows(n_fingers: int) -> list[int]:
    """Fold `n_fingers` fingers into rows of at most MAX_FINGERS_PER_ROW."""
    if n_fingers < 1:
        raise ValueError("clamp finger count must be >= 1")
    rows: list[int] = []
    remaining = n_fingers
    while remaining > 0:
        take = min(remaining, MAX_FINGERS_PER_ROW)
        rows.append(take)
        remaining -= take
    return rows


def _row_span(fingers_in_row: int) -> float:
    return (fingers_in_row - 1) * FINGER_PITCH + FINGER_L


def _row_pitch(bus_width: float) -> float:
    """y row-to-row pitch: whichever of the diode finger or its Metal1
    gather bus is taller, plus the same ROW_GAP_UM margin FINGER_PITCH uses
    in x. At the default bus width this is the finger-limited 1.6 um."""
    return max(FINGER_DEPTH, bus_width) + ROW_GAP_UM


def _draw_ring_strap(
    top, L, x0: float, x1: float, y0: float, y1: float, via_half: float = VIA_HALF
) -> None:
    """Draw one DVDD/DVSS supply strap, continuous across [x0, x1] on
    Metal3/Metal4/Metal5, via-stitched every STRAP_STITCH_PITCH_UM so the
    three levels form one electrically continuous conductor (DR-0011's
    ring-continuity requirement)."""

    def rect(spec, rx0, ry0, rx1, ry1):
        top.shapes(L(spec)).insert(_box(top.layout(), rx0, ry0, rx1, ry1))

    for metal_spec in (METAL3, METAL4, METAL5):
        rect(metal_spec, x0, y0, x1, y1)
    cy = (y0 + y1) / 2
    x = x0 + STRAP_STITCH_PITCH_UM / 2
    while x < x1:
        rect(VIA3, x - via_half, cy - via_half, x + via_half, cy + via_half)
        rect(VIA4, x - via_half, cy - via_half, x + via_half, cy + via_half)
        x += STRAP_STITCH_PITCH_UM


def _draw_substrate_tap(top, L, ox: float, oy: float, net_name: str, via_half: float = VIA_HALF) -> None:
    """Draw an explicit substrate tap: Pplus-covered Comp *outside* every
    Nwell (these tiles draw no Nwell at the tap), contacted and strapped
    straight up through Metal1/Metal2 into the caller's already-drawn Metal3
    strap at this same (ox, oy).

    Per `klayout_tools/decks/gf180mcu.py`'s issue-#1084 `tap_pplus`
    derivation, this is exactly the drawn structure that ties the deck's
    synthesized `vsubs` global to a real net (`net_name`, wired via the
    Metal2->Metal3 via2 landing below) -- DR-0011's "substrate tap ...
    required on a real net" requirement, not yet exercised by any
    previously-committed cell in this repo.
    """

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(top.layout(), ox + x0, oy + y0, ox + x1, oy + y1))

    def label(spec, text, x, y):
        trans = db.DTrans(db.DPoint(ox + x, oy + y))
        top.shapes(L(spec)).insert(db.DText(text, trans))

    # Same 1x1um Comp + 2-stacked-contact idiom the pre-#149 placeholder
    # cathode used (DRC-clean under the current deck) -- Pplus in place of
    # Nplus/Dualgate, and deliberately no Dualgate/diode_mk here: this is a
    # plain substrate tie, not a diode terminal.
    comp_x0, comp_x1 = 0.0, 1.0
    comp_y0, comp_y1 = 0.0, 1.0
    rect(COMP, comp_x0, comp_y0, comp_x1, comp_y1)
    margin = 0.16
    rect(PPLUS, comp_x0 - margin, comp_y0 - margin, comp_x1 + margin, comp_y1 + margin)

    cx = (comp_x0 + comp_x1) / 2
    c0_y0, c1_y0 = 0.63, 1.15
    for cy0 in (c0_y0, c1_y0):
        rect(CONTACT, cx - CONTACT_SIZE / 2, cy0, cx + CONTACT_SIZE / 2, cy0 + CONTACT_SIZE)
    m1_x0, m1_x1 = cx - 0.31, cx + 0.31
    m1_y0, m1_y1 = c0_y0 - 0.13, c1_y0 + CONTACT_SIZE + 0.13
    rect(METAL1, m1_x0, m1_y0, m1_x1, m1_y1)
    label(METAL1_LABEL, net_name, cx, (m1_y0 + m1_y1) / 2)

    # Straight via1/via2 stack, landing on Metal2 sized to reach up into the
    # Metal3 strap the caller has already drawn at this (ox, oy).
    stack_half = 0.35
    sx0, sx1 = cx - stack_half, cx + stack_half
    sy0, sy1 = m1_y1 - 0.10, m1_y1 + 0.60
    rect(METAL1, sx0, sy0, sx1, sy1)
    rect(METAL2, sx0, sy0, sx1, sy1)
    vcx, vcy = cx, (sy0 + sy1) / 2
    rect(VIA1, vcx - via_half, vcy - via_half, vcx + via_half, vcy + via_half)
    rect(VIA2, vcx - via_half, vcy - via_half, vcx + via_half, vcy + via_half)


def _draw_production_pad(
    top,
    L,
    ox: float,
    oy: float,
    net_name: str,
    n_fingers: int,
    bus_width: float = DEFAULT_BUS_WIDTH_UM,
    via_half: float = VIA_HALF,
) -> dict[str, float]:
    """Draw one `gf180_tmds_pad_v2`-geometry bond pad at origin (ox, oy):
    a folded `diode_nd2ps_06v0` finger array, a shared Metal1 cathode bus
    per row plus a vertical Metal1 spine tying the rows together, a
    Metal1-Metal5 via stack, and the 25x25 um Metal5 plate / 20x20 um
    opening on top (issue #87 geometry, folded per issue #143).

    Returns the absolute (x, y) of row 0's own Metal1 gather-bus centre, for
    the assembly's top-level router to connect the driver's output pin to
    (scope item 5: "land the driver->pad Metal2 routes on the row-0 Metal1
    bus centre"); the fit study ignores it.
    """

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(top.layout(), ox + x0, oy + y0, ox + x1, oy + y1))

    def label(spec, text, x, y):
        top.shapes(L(spec)).insert(db.DText(text, db.DTrans(db.DPoint(ox + x, oy + y))))

    rows = clamp_rows(n_fingers)
    array_x1 = _row_span(max(rows))
    row_pitch = _row_pitch(bus_width)
    array_y1 = (len(rows) - 1) * row_pitch + max(FINGER_DEPTH, bus_width)

    contact_y_off = 0.39  # gen_pad_v2.py's own within-finger contact offset
    bus_cy = contact_y_off + CONTACT_SIZE / 2
    bus_dy0 = bus_cy - bus_width / 2
    bus_dy1 = bus_cy + bus_width / 2
    via_cx = array_x1 + PAD_VIA_GAP_UM

    for r, count in enumerate(rows):
        row_y0 = r * row_pitch
        for i in range(count):
            fx0 = i * FINGER_PITCH
            rect(COMP, fx0, row_y0, fx0 + FINGER_L, row_y0 + FINGER_DEPTH)
            cx = fx0 + FINGER_L / 2
            rect(
                CONTACT,
                cx - CONTACT_SIZE / 2,
                row_y0 + contact_y_off,
                cx + CONTACT_SIZE / 2,
                row_y0 + contact_y_off + CONTACT_SIZE,
            )
        rect(METAL1, -0.10, row_y0 + bus_dy0, via_cx + 0.60, row_y0 + bus_dy1)

    # Implants/markers enclose the whole (possibly multi-row) array: only
    # Comp defines the diffusion, so one rectangle per layer is equivalent to
    # per-row rectangles and introduces no sliver spacing between rows.
    margin = 0.16  # NPLUS-over-COMP margin (gen_pad_v2.py convention)
    rect(NPLUS, -margin, -margin, array_x1 + margin, array_y1 + margin)
    dg = 0.30
    rect(DUALGATE, -dg, -dg, array_x1 + dg, array_y1 + dg)
    mk = 0.40
    rect(DIODE_MK, -mk, -mk, array_x1 + mk, array_y1 + mk)

    # Vertical Metal1 spine: ties every row's bus onto one cathode net.
    spine_half = max(0.60, bus_width / 2)
    rect(METAL1, via_cx - spine_half, bus_dy0, via_cx + spine_half, (len(rows) - 1) * row_pitch + bus_dy1)
    label(METAL1_LABEL, net_name, 1.0, (bus_dy0 + bus_dy1) / 2)

    stack_cy = array_y1 / 2
    for metal_spec in (METAL2, METAL3, METAL4):
        rect(metal_spec, via_cx - 0.60, stack_cy - 0.60, via_cx + 0.60, stack_cy + 0.60)
    for via_spec in (VIA1, VIA2, VIA3, VIA4):
        rect(via_spec, via_cx - via_half, stack_cy - via_half, via_cx + via_half, stack_cy + via_half)

    pad_half = PAD_SIDE / 2
    rect(METAL5, via_cx - pad_half, stack_cy - pad_half, via_cx + pad_half, stack_cy + pad_half)
    opening_half = pad_half - PAD_OPENING_MARGIN
    rect(PAD_LAYER, via_cx - opening_half, stack_cy - opening_half, via_cx + opening_half, stack_cy + opening_half)
    label(METAL5_LABEL, net_name, via_cx, stack_cy)

    # Row 0's own Metal1 gather-bus centre (row_y0 == 0 for row 0): the
    # landing point the top-level router connects to (scope item 5).
    row0_x0, row0_x1 = -0.10, via_cx + 0.60
    return {"x": ox + (row0_x0 + row0_x1) / 2, "y": oy + bus_cy}
