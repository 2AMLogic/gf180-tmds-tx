#!/usr/bin/env python3
"""Generate the realistic-pad-size, diode-clamped TMDS pad cell (issue #87).

Redesign of ``gf180_tmds_pad_min`` (issue #2) against the DR-0005/DR-0011
<=2 pF pad-capacitance budget. Two things changed relative to that cell and
`gf180_tmds_pad_diode_draft` (issue #9/DR-0011's clamp-device verification
draft), both required to close the capacitance-budget gap
`design/esd-capacitance-budget.md` reported (issue #87):

1. **A real 25x25 um Metal5 bond pad**, not a 0.62x1.00 um via-landing
   square (`gf180_tmds_pad_min`) or a 6.6x6.6 um placeholder
   (`gf180_tmds_pad_diode_draft`). 25x25 um is the gf180mcu_fd_io I/O
   library's own established bond-pad-opening size
   (`spec/pad-ring-esd-survey.md` Sec.1, `gf180mcu_fd_io__bi_t.lef`'s `PAD`
   pin), the same size `design/esd-capacitance-budget.md` Sec.4b already
   used for its (analytic-only) "realistic pad" estimate. Drawing it for
   real means `klt extract --parasitics` can now measure that number
   directly instead of hand-computing it -- see this issue's redesign
   record for why the previous analytic figure was reported 1000x too high
   (a units-label bug, aF mislabelled fF and fF mislabelled pF in
   `design/esd-capacitance-budget.md` Sec.4b's original text -- corrected
   in the same commit as this file).

2. **A diode_nd2ps_06v0 ESD clamp**, per DR-0011's ratified clamp-device
   choice (reaffirming DR-0005; supersedes `gf180_tmds_pad_min`'s GGNMOS,
   which was only a tooling-driven substitute -- see DR-0011 Sec. "The
   clamp-device contingency, resolved"). Drawn as a 20-finger array (each
   finger 2.0 x 1.0 um Comp/Nplus/Dualgate/diode_mk, per DR-0011's own
   verified `gf180_tmds_pad_diode_draft` finger geometry) tied in parallel
   on both terminals -- cathode (Comp/Nplus/Dualgate side) to `PAD` via a
   shared Metal1 bus, anode (substrate) to the deck's synthesized
   `substrate_net` global, which this cell's own explicit substrate tap (3)
   below promotes onto a real, verified net. A 20-finger array is a
   representative, DRC/LVS-provable multifinger ESD structure, not yet
   the final HBM-2kV-qualified size -- `sim/esd-diode-clamp-cv` sizes and
   measures the clamp's own capacitance as a function of *total* finger
   count/periphery purely in SPICE (same "draw a small multi-finger unit,
   size the full clamp analytically/in-SPICE" split
   `gf180_tmds_pad_min`/`sim/esd-clamp-cv` already established for the
   GGNMOS clamp -- see `design/esd-capacitance-budget.md` Sec.1-3).

3. **A real substrate tap** (Pplus-covered Comp outside every Nwell, tied
   to a `VSS` net through Metal1), addressing DR-0011's flagged
   requirement ("the eventual driver-integrated pad ... must draw a real
   tap" -- `gf180_tmds_pad_min` and `gf180_tmds_pad_diode_draft` both
   deliberately omit one and both carry an LVS `device.body_unverified`
   warning as a result). `klt`'s gf180mcu deck derives an equivalent tap
   region from `tap_pplus`/`tap_nplus` implants (issue #1084) rather than
   needing a dedicated tap mask, and globally connects it to the same
   `substrate_net` (`vsubs`) global every unconnected device body/anode in
   this deck already uses -- so wiring this tap's own Metal1 to a real
   `VSS`-labelled net promotes that global from an anonymous synthesized
   node into a real, verified net.

Ring continuity (DVDD/DVSS straps at the 350/75 um pad-ring pitch DR-0011
also ratifies) and a second (P-toward-VDD) clamp leg are explicitly **not**
drawn here -- both are block-level pad-ring *assembly* concerns (issue #86,
which this issue's own body says to coordinate with, not duplicate), not
this issue's own capacitance-budget-redesign scope. This cell answers "does
a real-size pad plus a real (diode) ESD clamp actually fit the <=2 pF
budget", not "is this the final integrated pad".

Layer numbers and DRC thresholds are taken from `klt`'s own curated
gf180mcu deck (`klayout_tools/decks/gf180mcu.py`), not assumed -- same
convention `gen_pad_min.py`/`gen_pad_diode_draft.py` already established.
"""

from __future__ import annotations

import argparse

import klayout.db as db

# ---------------------------------------------------------------------------
# gf180mcu GDS layer/datatype pairs (klayout_tools/decks/gf180mcu.py
# EXTRACTION_DECK/DECK and the installed PDK's own layers_def.py).
# ---------------------------------------------------------------------------
COMP = (22, 0)
POLY2 = (30, 0)
NPLUS = (32, 0)
PPLUS = (31, 0)
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
PAD_LAYER = (37, 0)  # passivation/pad-opening marker (geom.drc: grid/angle only)

DBU = 0.001  # 1 nm, matches every other GDS file in this directory

CONTACT_SIZE = 0.22  # klt's contact.width.1 floor (min-only; max not checked)

# -- Diode finger array geometry -------------------------------------------
N_FINGERS = 20
FINGER_L = 2.0  # um, long (periphery) axis
FINGER_DEPTH = 1.0  # um, short axis (matches gen_pad_diode_draft's comp depth)
FINGER_PITCH = 2.6  # um, center-to-center == FINGER_L + 0.6um comp.space.mv.1 margin
# Aggregate periphery/area this array presents to `klt extract`'s diode
# recognition (informational; not itself DRC/LVS-checked):
#   P_total = N_FINGERS * 2*(FINGER_L + FINGER_DEPTH) = 20 * 2*3.0 = 120 um
#   A_total = N_FINGERS * FINGER_L * FINGER_DEPTH     = 20 * 2.0  = 40 um^2

# -- Bond pad ---------------------------------------------------------------
PAD_SIDE = 25.0  # um -- gf180mcu_fd_io__bi_t.lef's own PAD pin size
PAD_OPENING_MARGIN = 2.5  # um -- comfortably above pad.enclosing.metal5.1's 2.0um floor


def _box(layout, x0, y0, x1, y1):
    return db.Box(
        db.DPoint(x0, y0).to_itype(layout.dbu),
        db.DPoint(x1, y1).to_itype(layout.dbu),
    )


def build(shorted: bool = False) -> db.Layout:
    layout = db.Layout()
    layout.dbu = DBU
    top_name = "gf180_tmds_pad_v2_shorted" if shorted else "gf180_tmds_pad_v2"
    top = layout.create_cell(top_name)

    layers: dict[tuple[int, int], int] = {}

    def L(spec):
        if spec not in layers:
            layers[spec] = layout.layer(*spec)
        return layers[spec]

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(layout, x0, y0, x1, y1))

    def label(spec, text, x, y):
        trans = db.DTrans(db.DPoint(x, y))
        top.shapes(L(spec)).insert(db.DText(text, trans))

    # -- diode_nd2ps_06v0 clamp: 20-finger array, cathode -> PAD ------------
    finger_boxes = []
    for i in range(N_FINGERS):
        x0 = i * FINGER_PITCH
        x1 = x0 + FINGER_L
        finger_boxes.append((x0, x1))
        rect(COMP, x0, 0.0, x1, FINGER_DEPTH)
        # per-finger contact, centred
        cx = (x0 + x1) / 2
        rect(
            CONTACT,
            cx - CONTACT_SIZE / 2,
            0.39,
            cx + CONTACT_SIZE / 2,
            0.39 + CONTACT_SIZE,
        )

    array_x0, array_x1 = finger_boxes[0][0], finger_boxes[-1][1]
    margin = 0.16  # NPLUS-over-COMP margin (gen_pad_min.py convention)
    rect(NPLUS, array_x0 - margin, 0.0 - margin, array_x1 + margin, FINGER_DEPTH + margin)
    dg_margin = 0.30  # comfortable Dualgate-over-Comp margin
    rect(
        DUALGATE,
        array_x0 - dg_margin,
        0.0 - dg_margin,
        array_x1 + dg_margin,
        FINGER_DEPTH + dg_margin,
    )
    mk_margin = 0.40  # diode_mk covers the whole recognised-junction footprint
    rect(
        DIODE_MK,
        array_x0 - mk_margin,
        0.0 - mk_margin,
        array_x1 + mk_margin,
        FINGER_DEPTH + mk_margin,
    )

    # -- Metal1 cathode bus: ties every finger's contact onto one PAD net --
    bus_y0, bus_y1 = 0.39 - 0.13, 0.39 + CONTACT_SIZE + 0.13
    via_stack_cx = array_x1 + 1.5  # via stack sits just past the last finger
    rect(METAL1, array_x0 - 0.10, bus_y0, via_stack_cx + 0.6, bus_y1)

    # -- Via stack, Metal1 through Metal5, up to the real 25x25um bond pad --
    stack_cy = FINGER_DEPTH / 2
    stack_half = 0.60
    stack_x0, stack_x1 = via_stack_cx - stack_half, via_stack_cx + stack_half
    stack_y0, stack_y1 = stack_cy - stack_half, stack_cy + stack_half
    for metal_spec in (METAL2, METAL3, METAL4):
        rect(metal_spec, stack_x0, stack_y0, stack_x1, stack_y1)
    via_half = 0.15  # 0.30um square vias, clearing via*.width.1's 0.26um floor
    for via_spec in (VIA1, VIA2, VIA3, VIA4):
        rect(
            via_spec,
            via_stack_cx - via_half,
            stack_cy - via_half,
            via_stack_cx + via_half,
            stack_cy + via_half,
        )
    pad_half = PAD_SIDE / 2
    rect(
        METAL5,
        via_stack_cx - pad_half,
        stack_cy - pad_half,
        via_stack_cx + pad_half,
        stack_cy + pad_half,
    )
    opening_half = pad_half - PAD_OPENING_MARGIN
    rect(
        PAD_LAYER,
        via_stack_cx - opening_half,
        stack_cy - opening_half,
        via_stack_cx + opening_half,
        stack_cy + opening_half,
    )
    label(METAL5_LABEL, "PAD", via_stack_cx, stack_cy)

    # -- Substrate tap: Pplus-covered Comp outside every Nwell, tied to VSS -
    tap_x0, tap_x1 = array_x0, array_x0 + 2.0
    tap_y0, tap_y1 = -3.0, -1.0  # >=1.0um clear of the diode array (y=0..FINGER_DEPTH)
    rect(COMP, tap_x0, tap_y0, tap_x1, tap_y1)
    rect(PPLUS, tap_x0 - margin, tap_y0 - margin, tap_x1 + margin, tap_y1 + margin)
    tap_cx = (tap_x0 + tap_x1) / 2
    tap_cy = (tap_y0 + tap_y1) / 2
    rect(
        CONTACT,
        tap_cx - CONTACT_SIZE / 2,
        tap_cy - CONTACT_SIZE / 2,
        tap_cx + CONTACT_SIZE / 2,
        tap_cy + CONTACT_SIZE / 2,
    )
    tap_m1_half = 0.31
    rect(
        METAL1,
        tap_cx - tap_m1_half,
        tap_cy - tap_m1_half,
        tap_cx + tap_m1_half,
        tap_cy + tap_m1_half,
    )
    label(METAL1_LABEL, "VSS", tap_cx, tap_cy)

    # -- Negative control: short PAD to VSS with one extra Metal1 bridge ----
    # Genuinely overlaps (not just edge-touches) both the tap's own Metal1
    # square and the cathode bus -- an edge-touching rect here previously
    # produced a degenerate zero-width DRC violation at the seam.
    if shorted:
        overlap = 0.10
        rect(
            METAL1,
            tap_cx - tap_m1_half - overlap,
            tap_cy + tap_m1_half - overlap,
            tap_cx + tap_m1_half + overlap,
            bus_y0 + overlap,
        )

    top.flatten(True)
    return layout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", required=True, help="output GDS path")
    ap.add_argument(
        "--shorted",
        action="store_true",
        help="emit the LVS negative-control (PAD-shorted-to-VSS) variant",
    )
    args = ap.parse_args()

    layout = build(shorted=args.shorted)
    layout.write(args.output)
    top = layout.top_cell()
    bbox = top.bbox()
    print(f"wrote {args.output}: cell {top.name!r}, bbox {bbox.to_dtype(layout.dbu)}")


if __name__ == "__main__":
    main()
