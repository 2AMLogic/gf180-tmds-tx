#!/usr/bin/env python3
"""Generate the minimal custom gf180mcu TMDS-pad cell (issue #2).

Draws a small standalone layout using ``klayout.db`` directly (no PDK PCell
dependency -- ``gdsfactory``, which the PDK's own PCell generators need, is
not installed in this environment; see ``spec/pad-ring-esd-survey.md``
section 3 for that finding, and section 4 for why this cell's ESD element
is a grounded-gate NMOS (GGNMOS) clamp rather than the diode this repo's
first draft used).

Two cells are written:

- ``gf180_tmds_pad_min``         -- the real candidate: a Metal5 bond pad
  (PAD net) wired straight down a Metal1-5 via stack to the drain of a
  grounded-gate NMOS clamp; the transistor's gate and source both land on a
  separate VSS net. `klt extract` recognises this as a real ``nfet`` device
  (issue #2's PDK survey found `klt`'s gf180mcu extraction deck has *no*
  diode device class at all, which is what forced this redesign -- see the
  spec doc and the linked klayout-tools issue).
- ``gf180_tmds_pad_min_shorted``  -- an LVS negative control (`klt lvs`'s own
  documented "two independent corruptions" guidance, docs/cli/lvs.md
  "Negative controls"): identical layout, plus one extra Metal1 bridge
  shorting the PAD net directly to VSS. This must FAIL `klt lvs` against the
  same reference netlist the unshorted cell passes -- proving the LVS check
  actually distinguishes connected from disconnected, not a vacuous pass.

Layer numbers and DRC thresholds are taken from `klt`'s own curated gf180mcu
deck (`klayout_tools/decks/gf180mcu.py`), not assumed -- see the spec doc.
Every dimension below clears klt's checked minimums with comfortable
margin -- the whole point of a "minimal" cell is that tight, real-DRM
minimums are not required to prove the DRC/LVS flow at the pad boundary.
"""

from __future__ import annotations

import argparse

import klayout.db as db

# ---------------------------------------------------------------------------
# gf180mcu GDS layer/datatype pairs (klayout_tools/decks/gf180mcu.py
# EXTRACTION_DECK/DECK and the installed PDK's layers_def.py; see spec doc).
# ---------------------------------------------------------------------------
COMP = (22, 0)
POLY2 = (30, 0)
NPLUS = (32, 0)
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

DBU = 0.001  # 1 nm, matches the installed PDK's own GDS files

CONTACT_SIZE = 0.22  # klt's contact.width.1 floor


def _box(layout, x0, y0, x1, y1):
    return db.Box(
        db.DPoint(x0, y0).to_itype(layout.dbu),
        db.DPoint(x1, y1).to_itype(layout.dbu),
    )


def build(shorted: bool = False) -> db.Layout:
    layout = db.Layout()
    layout.dbu = DBU
    top_name = "gf180_tmds_pad_min_shorted" if shorted else "gf180_tmds_pad_min"
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

    # -- Grounded-gate NMOS (GGNMOS) ESD clamp: drain=PAD, gate=source=VSS --
    W = 2.0  # transistor width (um)
    Lg = 0.4  # gate length (um), comfortably above the 3.3V minimum
    sd_len = 1.0  # source/drain diffusion length (um), room for contacts

    src_x0, src_x1 = 0.0, sd_len
    gate_x0, gate_x1 = src_x1, src_x1 + Lg
    drn_x0, drn_x1 = gate_x1, gate_x1 + sd_len
    active_y0, active_y1 = 0.0, W

    # Active (source-gate-drain) diffusion, one continuous strip.
    rect(COMP, src_x0, active_y0, drn_x1, active_y1)
    # NPLUS covers the whole nfet body (no Nwell drawn -> nfet region).
    rect(NPLUS, src_x0 - 0.16, active_y0 - 0.16, drn_x1 + 0.16, active_y1 + 0.16)
    # Poly2 gate, extended past the active strip (top) to land its own contact.
    gate_y0, gate_y1 = active_y0 - 0.18, active_y1 + 0.70
    rect(POLY2, gate_x0, gate_y0, gate_x1, gate_y1)

    # -- Source (tied to VSS) ------------------------------------------------
    src_cx = (src_x0 + src_x1) / 2
    src_c0_y0, src_c1_y0 = 0.63, 1.15  # two stacked contacts, 0.30 gap
    for cy0 in (src_c0_y0, src_c1_y0):
        rect(
            CONTACT,
            src_cx - CONTACT_SIZE / 2,
            cy0,
            src_cx + CONTACT_SIZE / 2,
            cy0 + CONTACT_SIZE,
        )
    src_m1_x0, src_m1_x1 = src_cx - 0.31, src_cx + 0.31
    src_m1_y0, src_m1_y1 = 0.50, 1.50
    rect(METAL1, src_m1_x0, src_m1_y0, src_m1_x1, src_m1_y1)

    # -- Gate contact + strap tying the gate to the source/VSS net ----------
    gate_cx = (gate_x0 + gate_x1) / 2
    gate_c_y0 = gate_y1 - 0.30
    rect(
        CONTACT,
        gate_cx - CONTACT_SIZE / 2,
        gate_c_y0,
        gate_cx + CONTACT_SIZE / 2,
        gate_c_y0 + CONTACT_SIZE,
    )
    gate_m1_x0, gate_m1_x1 = gate_cx - 0.31, gate_cx + 0.31
    gate_m1_y0 = gate_c_y0 - 0.08
    gate_m1_y1 = gate_c_y0 + CONTACT_SIZE + 0.08
    rect(METAL1, gate_m1_x0, gate_m1_y0, gate_m1_x1, gate_m1_y1)

    # Metal1 strap: connects the gate's metal1 landing to the source's
    # metal1 landing. Source and gate are not x-aligned (the gate contact
    # must land within the poly2 footprint), so this is an L-shape built
    # from two rects, each overlapping (not just touching) its neighbour
    # by >= 0.10um -- a real polygon merge, not an edge-adjacency corner
    # case -- and each individually clearing metal1.width.1 (0.23um).
    strap_v_x0, strap_v_x1 = src_cx - 0.15, src_cx + 0.15
    strap_v_y0, strap_v_y1 = src_m1_y1 - 0.10, gate_m1_y0 + 0.08
    rect(METAL1, strap_v_x0, strap_v_y0, strap_v_x1, strap_v_y1)
    strap_h_y0, strap_h_y1 = gate_m1_y0 - 0.02, gate_m1_y0 + 0.25
    rect(METAL1, strap_v_x0, strap_h_y0, gate_m1_x1, strap_h_y1)
    label(METAL1_LABEL, "VSS", src_cx, (src_m1_y0 + src_m1_y1) / 2)

    # -- Drain (PAD): via stack from metal1 straight up to the bond pad -----
    drn_cx = (drn_x0 + drn_x1) / 2
    drn_c0_y0, drn_c1_y0 = 0.63, 1.15
    for cy0 in (drn_c0_y0, drn_c1_y0):
        rect(
            CONTACT,
            drn_cx - CONTACT_SIZE / 2,
            cy0,
            drn_cx + CONTACT_SIZE / 2,
            cy0 + CONTACT_SIZE,
        )
    stack_x0, stack_x1 = drn_cx - 0.31, drn_cx + 0.31
    stack_y0, stack_y1 = 0.50, 1.50
    for metal_spec in (METAL1, METAL2, METAL3, METAL4, METAL5):
        rect(metal_spec, stack_x0, stack_y0, stack_x1, stack_y1)
    via_inset = 0.20  # single via, centred, inside the 0.62x1.00um metal square
    for via_spec in (VIA1, VIA2, VIA3, VIA4):
        rect(
            via_spec,
            stack_x0 + via_inset,
            stack_y0 + 0.34,
            stack_x1 - via_inset,
            stack_y1 - 0.34,
        )
    pad_inset = 0.08
    rect(
        PAD_LAYER,
        stack_x0 + pad_inset,
        stack_y0 + pad_inset,
        stack_x1 - pad_inset,
        stack_y1 - pad_inset,
    )
    label(METAL5_LABEL, "PAD", drn_cx, (stack_y0 + stack_y1) / 2)

    # -- Negative control: short PAD to VSS with one extra Metal1 bridge ----
    if shorted:
        mid_y = (src_m1_y0 + src_m1_y1) / 2
        rect(METAL1, src_m1_x1, mid_y - 0.15, stack_x0, mid_y + 0.15)

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
