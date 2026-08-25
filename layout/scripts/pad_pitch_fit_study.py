#!/usr/bin/env python3
"""Draw the DR-0011 pad-pitch fit study asked for by issue #143.

**The question.** `design/esd-capacitance-budget.md` Sec.9 validated the
<= 2 pF DR-0005/DR-0011 pad-capacitance budget against
`layout/gds/gf180_tmds_pad_v2.gds` -- a *standalone* cell with a production
25x25 um bond pad. The block-level ring
(`layout/gds/gf180_tmds_pad_ring_assembly.gds`, issue #86) still draws
`gen_pad_diode_draft.py`'s 2x2 um placeholder opening, which
`layout/README.md` itself calls "DRC-legal but not a production wire-bond
target". Nobody had checked whether the production pad geometry *fits*
DR-0011's ratified 350 um pad pitch / 75 um ring depth once the DVDD/DVSS
ring straps and an HBM-sized clamp array are also in the slot -- the issue's
own words: performed, "not by estimate".

**What this script draws.** A two-slot block-level pad-ring tile at
DR-0011's ratified pitch, carrying everything that competes for the slot:

- DVDD/DVSS ring straps on Metal3/Metal4/Metal5, continuous across the full
  two-slot span and via-stitched every `STRAP_STITCH_PITCH_UM` -- DR-0011's
  ring-continuity requirement, at the same band positions
  `gen_pad_ring_assembly.py` already uses;
- a substrate tap (Pplus-covered Comp outside every Nwell) wired into the
  DVSS strap, DR-0011's "required on a real net" tap;
- per slot, `gen_pad_v2.py`'s **production** pad geometry verbatim: a
  25x25 um Metal5 bond pad with a 20x20 um opening (a 2.5 um margin, above
  `pad.enclosing.metal5.1`'s 2.0 um floor), a Metal1-Metal5 via stack, and a
  `diode_nd2ps_06v0` multi-finger clamp array (2.0 x 1.0 um fingers on a
  2.6 um pitch) gathered onto a shared Metal1 cathode bus.

`--clamp-fingers` sweeps the clamp across
`design/esd-capacitance-budget.md` Sec.2b's HBM-sizing window. Each finger
contributes `FINGER_L` (2.0 um) of clamp width, so 111 / 222 / 334 fingers
are the 222 / 444 / 667 um total-width points Sec.9.4 grades the budget at,
and 20 is `gf180_tmds_pad_v2`'s own as-drawn array.

**What it deliberately does not draw.** The CML driver core, the driver->pad
routing, and the LVS negative-control short -- all three belong to
`gen_pad_ring_assembly.py`, and none of them bear on a *geometric fit*
question. This script answers "does the production pad geometry fit the
ratified pitch", not "is this the final integrated block"; folding the
answer back into the assembly generator is separate, LVS-bearing work (see
`layout/README.md`'s issue-#143 section for why it could not land in the
same pass).

**The fold, and why it is not cosmetic.** A single row of `n` fingers spans
`(n-1)*FINGER_PITCH + FINGER_L` um, and the structure needs a further
`PAD_VIA_GAP_UM + PAD_SIDE/2` um of x past the last finger for the via stack
and the Metal5 plate centred on it. At the top of the HBM-sizing window
(667 um of clamp width = 334 fingers) a single row is **867.8 um wide, ~2.5x
DR-0011's ratified 350 um pitch**. Folding into rows is therefore mandatory
at that end of the window, not a style choice -- and finding that out is
most of what this study is for.

Layer numbers and DRC thresholds are taken from `klt`'s own curated gf180mcu
deck (`klayout_tools/decks/gf180mcu.py`), not assumed -- same convention
every other generator in this directory already follows.

Usage:

    python3 scripts/pad_pitch_fit_study.py -o gds/pad_pitch_fit_n20.gds \\
        --clamp-fingers 20 --report gds/pad_pitch_fit_n20.fit.json
    klt drc --deck gf180mcu gds/pad_pitch_fit_n20.gds
"""

from __future__ import annotations

import argparse
import json

try:  # pragma: no cover -- exercised by whichever environment is present
    import klayout.db as db
except ModuleNotFoundError:  # pragma: no cover
    # The fit *arithmetic* below (`clamp_rows`, `fit_report`) is pure stdlib
    # and is the load-bearing claim this study makes -- it is unit-tested in
    # layout/tests/, which runs in CI's deliberately PDK-free, KLayout-free
    # job (see .github/workflows/ci.yml). Only `build()` needs klayout.db, and
    # it says so with a clean error rather than an import traceback.
    db = None

# ---------------------------------------------------------------------------
# gf180mcu GDS layer/datatype pairs (klayout_tools/decks/gf180mcu.py
# EXTRACTION_DECK/DECK and the installed PDK's own layers_def.py).
# ---------------------------------------------------------------------------
COMP = (22, 0)
PPLUS = (31, 0)
NPLUS = (32, 0)
DUALGATE = (55, 0)  # 5V/6V thick-oxide marker -- required by diode_nd2ps_06v0
DIODE_MK = (115, 5)  # junction-diode device-recognition mark
CONTACT = (33, 0)
METAL1 = (34, 0)
METAL1_LABEL = (34, 10)
VIA1 = (35, 0)
METAL2 = (36, 0)
VIA2 = (38, 0)
METAL3 = (42, 0)
VIA3 = (40, 0)
METAL4 = (46, 0)
VIA4 = (41, 0)
METAL5 = (81, 0)
METAL5_LABEL = (81, 10)
PAD_LAYER = (37, 0)  # passivation/pad-opening marker

DBU = 0.001  # 1 nm, matches every other GDS in this repo

CONTACT_SIZE = 0.22  # klt's contact.width.1 floor
VIA_HALF = 0.15  # 0.30um square vias, clearing via*.width.1's 0.26um floor

# ---------------------------------------------------------------------------
# DR-0011 (spec/decisions/0011-pad-esd-strategy.md): 350um pad pitch / 75um
# ring depth, from `gf180mcu_fd_io__bi_t.lef`'s `SIZE 75.000 BY 350.000`.
# Ratified; this script checks geometry against it and never widens it.
# ---------------------------------------------------------------------------
PAD_PITCH_UM = 350.0
RING_DEPTH_UM = 75.0

# Ring supply-strap bands, identical to gen_pad_ring_assembly.py's.
DVSS_BAND = (2.0, 6.0)
DVDD_BAND = (12.0, 16.0)
STRAP_STITCH_PITCH_UM = 50.0

# ---------------------------------------------------------------------------
# Pad + clamp geometry, adopted verbatim from gen_pad_v2.py (issue #87).
# ---------------------------------------------------------------------------
PAD_SIDE = 25.0  # um -- gf180mcu_fd_io__bi_t.lef's own PAD pin size
PAD_OPENING_MARGIN = 2.5  # um -- above pad.enclosing.metal5.1's 2.0um floor
PAD_VIA_GAP_UM = 1.5  # x gap from the last finger to the via-stack centre

FINGER_L = 2.0  # um, long (periphery/width) axis of one diode finger
FINGER_DEPTH = 1.0  # um, short axis
FINGER_PITCH = 2.6  # um, x pitch == FINGER_L + 0.6um (>= comp.space.mv.1 0.36um)
ROW_GAP_UM = 0.6  # um, y gap between rows -- the same margin FINGER_PITCH uses

# Metal1 cathode-gather bus width. gen_pad_v2.py's own bus is
# `2*0.13 + CONTACT_SIZE` = 0.48 um, which is what the default reproduces.
# `--bus-width` exists because it is a *measurable* budget term, not a
# cosmetic one: `design/esd-capacitance-budget.md` Sec.9.3 flagged that an
# HBM-sized clamp "would need a somewhat longer/wider Metal1 bus to gather
# current from more fingers, which would add some additional routing
# capacitance beyond this figure ... not literally re-measured at every
# clamp size". Widening it here and re-running `klt extract --parasitics`
# turns that caveat into a number.
DEFAULT_BUS_WIDTH_UM = 2 * 0.13 + CONTACT_SIZE

# Largest round per-row finger count that leaves >= 10um of slot margin at
# each end of a PAD_PITCH_UM slot once the via stack and the 25um Metal5
# plate are accounted for -- see `fit_report` for the arithmetic, which is
# reported rather than asserted so the margin is auditable per run.
MAX_FINGERS_PER_ROW = 120

# y-origin of each slot's clamp array. The Metal5 plate is centred on the
# array, so its lower edge is `PAD_STRUCT_OY_UM + array_height/2 - PAD_SIDE/2`;
# at the single-row minimum that is 18.0 um, clearing DVDD_BAND's 16.0 um top
# edge by 2.0 um (7x metal5.space.1's 0.28 um floor).
PAD_STRUCT_OY_UM = 30.0


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


def fit_report(n_fingers: int, bus_width: float = DEFAULT_BUS_WIDTH_UM) -> dict[str, object]:
    """The whole point of this script, computed rather than eyeballed: what a
    given clamp size costs in x (against DR-0011's 350 um pitch) and in y
    (against its 75 um ring depth), folded and unfolded."""
    rows = clamp_rows(n_fingers)
    array_x = _row_span(max(rows))
    array_y = (len(rows) - 1) * _row_pitch(bus_width) + max(FINGER_DEPTH, bus_width)
    struct_x = array_x + PAD_VIA_GAP_UM + PAD_SIDE / 2
    unfolded_x = _row_span(n_fingers) + PAD_VIA_GAP_UM + PAD_SIDE / 2
    plate_y0 = PAD_STRUCT_OY_UM + array_y / 2 - PAD_SIDE / 2
    plate_y1 = plate_y0 + PAD_SIDE
    return {
        "clamp_fingers": n_fingers,
        "clamp_width_um": round(n_fingers * FINGER_L, 3),
        "bus_width_um": round(bus_width, 3),
        "rows": rows,
        "row_count": len(rows),
        "pad_pitch_um": PAD_PITCH_UM,
        "ring_depth_um": RING_DEPTH_UM,
        "struct_width_um": round(struct_x, 3),
        "slot_margin_um": round(PAD_PITCH_UM - struct_x, 3),
        "slot_margin_each_side_um": round((PAD_PITCH_UM - struct_x) / 2, 3),
        "fits_pitch": struct_x <= PAD_PITCH_UM,
        "unfolded_width_um": round(unfolded_x, 3),
        "unfolded_fits_pitch": unfolded_x <= PAD_PITCH_UM,
        "pad_plate_y_um": [round(plate_y0, 3), round(plate_y1, 3)],
        "dvdd_strap_clearance_um": round(plate_y0 - DVDD_BAND[1], 3),
        "ring_depth_headroom_um": round(RING_DEPTH_UM - plate_y1, 3),
        "fits_ring_depth": plate_y1 <= RING_DEPTH_UM and plate_y0 > DVDD_BAND[1],
    }


def _box(layout, x0, y0, x1, y1):
    return db.Box(
        db.DPoint(x0, y0).to_itype(layout.dbu),
        db.DPoint(x1, y1).to_itype(layout.dbu),
    )


def _draw_ring_strap(top, L, x0: float, x1: float, y0: float, y1: float) -> None:
    """One DVDD/DVSS supply strap: Metal3/Metal4/Metal5 drawn continuously
    across [x0, x1] and via-stitched every STRAP_STITCH_PITCH_UM, so the
    three levels form one electrically continuous conductor (DR-0011's
    ring-continuity requirement). Same construction as
    `gen_pad_ring_assembly.py`'s already-signed-off strap."""

    def rect(spec, rx0, ry0, rx1, ry1):
        top.shapes(L(spec)).insert(_box(top.layout(), rx0, ry0, rx1, ry1))

    for metal_spec in (METAL3, METAL4, METAL5):
        rect(metal_spec, x0, y0, x1, y1)
    cy = (y0 + y1) / 2
    x = x0 + STRAP_STITCH_PITCH_UM / 2
    while x < x1:
        rect(VIA3, x - VIA_HALF, cy - VIA_HALF, x + VIA_HALF, cy + VIA_HALF)
        rect(VIA4, x - VIA_HALF, cy - VIA_HALF, x + VIA_HALF, cy + VIA_HALF)
        x += STRAP_STITCH_PITCH_UM


def _draw_substrate_tap(top, L, ox: float, oy: float, net_name: str) -> None:
    """Pplus-covered Comp outside every Nwell (this tile draws no Nwell at
    all), contacted and strapped up through Metal1/Metal2 into the Metal3
    DVSS strap the caller has already drawn at this (ox, oy)."""

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(top.layout(), ox + x0, oy + y0, ox + x1, oy + y1))

    def label(spec, text, x, y):
        top.shapes(L(spec)).insert(db.DText(text, db.DTrans(db.DPoint(ox + x, oy + y))))

    rect(COMP, 0.0, 0.0, 1.0, 1.0)
    margin = 0.16
    rect(PPLUS, -margin, -margin, 1.0 + margin, 1.0 + margin)

    cx = 0.5
    c0_y0, c1_y0 = 0.63, 1.15
    for cy0 in (c0_y0, c1_y0):
        rect(CONTACT, cx - CONTACT_SIZE / 2, cy0, cx + CONTACT_SIZE / 2, cy0 + CONTACT_SIZE)
    m1_y0, m1_y1 = c0_y0 - 0.13, c1_y0 + CONTACT_SIZE + 0.13
    rect(METAL1, cx - 0.31, m1_y0, cx + 0.31, m1_y1)
    label(METAL1_LABEL, net_name, cx, (m1_y0 + m1_y1) / 2)

    sx0, sx1 = cx - 0.35, cx + 0.35
    sy0, sy1 = m1_y1 - 0.10, m1_y1 + 0.60
    rect(METAL1, sx0, sy0, sx1, sy1)
    rect(METAL2, sx0, sy0, sx1, sy1)
    vcy = (sy0 + sy1) / 2
    rect(VIA1, cx - VIA_HALF, vcy - VIA_HALF, cx + VIA_HALF, vcy + VIA_HALF)
    rect(VIA2, cx - VIA_HALF, vcy - VIA_HALF, cx + VIA_HALF, vcy + VIA_HALF)


def _draw_production_pad(
    top, L, ox: float, oy: float, net_name: str, n_fingers: int, bus_width: float
) -> None:
    """One `gf180_tmds_pad_v2`-geometry bond pad at (ox, oy): a folded
    `diode_nd2ps_06v0` finger array, a shared Metal1 cathode bus per row plus
    a vertical Metal1 spine tying the rows together, a Metal1-Metal5 via
    stack, and the 25x25 um Metal5 plate / 20x20 um opening on top."""

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
        rect(via_spec, via_cx - VIA_HALF, stack_cy - VIA_HALF, via_cx + VIA_HALF, stack_cy + VIA_HALF)

    pad_half = PAD_SIDE / 2
    rect(METAL5, via_cx - pad_half, stack_cy - pad_half, via_cx + pad_half, stack_cy + pad_half)
    opening_half = pad_half - PAD_OPENING_MARGIN
    rect(PAD_LAYER, via_cx - opening_half, stack_cy - opening_half, via_cx + opening_half, stack_cy + opening_half)
    label(METAL5_LABEL, net_name, via_cx, stack_cy)


def build(
    n_fingers: int,
    cell_name: str = "gf180_tmds_pad_pitch_fit",
    bus_width: float = DEFAULT_BUS_WIDTH_UM,
) -> tuple[db.Layout, dict[str, object]]:
    report = fit_report(n_fingers, bus_width)
    if not report["fits_pitch"]:
        raise ValueError(
            f"a {n_fingers}-finger clamp needs {report['struct_width_um']} um of x, which does not fit "
            f"DR-0011's ratified {PAD_PITCH_UM:.0f} um pad pitch even folded at "
            f"MAX_FINGERS_PER_ROW={MAX_FINGERS_PER_ROW}. DR-0011 is ratified: widen the fold, not the pitch."
        )

    if db is None:  # pragma: no cover -- environment-dependent
        raise RuntimeError(
            "drawing this study needs the `klayout` PyPI package (klayout.db); "
            "the fit report itself (`fit_report`) needs no such thing -- run "
            "without -o for a report-only run"
        )

    layout = db.Layout()
    layout.dbu = DBU
    top = layout.create_cell(cell_name)

    layers: dict[tuple[int, int], int] = {}

    def L(spec):
        if spec not in layers:
            layers[spec] = layout.layer(*spec)
        return layers[spec]

    total_width = 2 * PAD_PITCH_UM
    _draw_ring_strap(top, L, 0.0, total_width, *DVSS_BAND)
    _draw_ring_strap(top, L, 0.0, total_width, *DVDD_BAND)

    # Substrate tap in the inter-slot gap, tied into the DVSS strap.
    _draw_substrate_tap(top, L, PAD_PITCH_UM - 0.5, DVSS_BAND[0], "VSS")

    struct_w = float(report["struct_width_um"])
    for slot, net in ((0, "OUTP"), (1, "OUTN")):
        slot_cx = PAD_PITCH_UM * (slot + 0.5)
        _draw_production_pad(top, L, slot_cx - struct_w / 2, PAD_STRUCT_OY_UM, net, n_fingers, bus_width)

    top.flatten(True)
    return layout, report


def _format_report(r: dict[str, object]) -> str:
    lines = [
        f"clamp:        {r['clamp_fingers']} fingers = {r['clamp_width_um']} um total width, "
        f"{r['row_count']} row(s) of {r['rows']}, {r['bus_width_um']} um Metal1 gather bus",
        f"x fit:        {r['struct_width_um']} um structure in DR-0011's {r['pad_pitch_um']:.0f} um pitch "
        f"-> {r['slot_margin_um']} um margin ({r['slot_margin_each_side_um']} um each side) "
        f"[{'FITS' if r['fits_pitch'] else 'DOES NOT FIT'}]",
        f"x fit, unfolded (single row): {r['unfolded_width_um']} um "
        f"[{'FITS' if r['unfolded_fits_pitch'] else 'DOES NOT FIT -- fold required'}]",
        f"y fit:        Metal5 plate spans {r['pad_plate_y_um']} um of the "
        f"{r['ring_depth_um']:.0f} um ring depth -> {r['dvdd_strap_clearance_um']} um DVDD-strap clearance, "
        f"{r['ring_depth_headroom_um']} um depth headroom "
        f"[{'FITS' if r['fits_ring_depth'] else 'DOES NOT FIT'}]",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", help="output GDS path (omit for a report-only run)")
    ap.add_argument(
        "--clamp-fingers",
        type=int,
        default=20,
        help=(
            "diode_nd2ps_06v0 fingers per pad, each contributing 2.0 um of clamp width "
            "(default: 20, gf180_tmds_pad_v2's own as-drawn array; 111/222/334 == the "
            "222/444/667 um HBM-sizing window of design/esd-capacitance-budget.md Sec.2b/9.4)"
        ),
    )
    ap.add_argument("--cell-name", default="gf180_tmds_pad_pitch_fit", help="top cell name")
    ap.add_argument(
        "--bus-width",
        type=float,
        default=DEFAULT_BUS_WIDTH_UM,
        help=(
            "Metal1 cathode-gather bus width in um (default: "
            f"{DEFAULT_BUS_WIDTH_UM:.2f}, gen_pad_v2.py's own). Widening it is how "
            "design/esd-capacitance-budget.md Sec.9.3's 'an HBM-sized clamp needs a "
            "wider gather bus' caveat gets measured instead of estimated"
        ),
    )
    ap.add_argument("--report", help="also write the fit report as JSON to this path")
    args = ap.parse_args()

    if args.output:
        layout, report = build(args.clamp_fingers, cell_name=args.cell_name, bus_width=args.bus_width)
        layout.write(args.output)
        bbox = layout.top_cell().bbox().to_dtype(layout.dbu)
        report["gds"] = args.output
        report["bbox_um"] = [bbox.left, bbox.bottom, bbox.right, bbox.top]
        print(f"wrote {args.output}: cell {layout.top_cell().name!r}, bbox {bbox}")
    else:
        report = fit_report(args.clamp_fingers, args.bus_width)
    print(_format_report(report))
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"wrote {args.report}")


if __name__ == "__main__":
    main()
