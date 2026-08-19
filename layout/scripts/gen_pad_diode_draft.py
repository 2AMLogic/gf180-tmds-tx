#!/usr/bin/env python3
"""Generate a diode-clamp draft of the gf180mcu TMDS-pad cell (issue #9,
DR-0011 verification).

`spec/pad-ring-esd-survey.md` (issue #2) recorded that its *first* draft of
the custom pad used a hand-transcribed `diode_nd2ps_06v0` clamp, but that
`klt extract`'s gf180mcu deck had **no diode device class at all** at the
time -- forcing a redraw as the grounded-gate NMOS (GGNMOS) clamp this repo's
signed-off `gf180_tmds_pad_min` cell actually uses
(`2AMLogic/klayout-tools#541`). That draft itself was never committed to this
repository -- only the final GGNMOS cell was.

`2AMLogic/klayout-tools#542` closed 2026-08-05, shipping diode device
recognition (`kdb.DeviceExtractorDiode`-backed, `decks/gf180mcu.py`'s
`diodes=(...)` entries for `diode_nd2ps_06v0`/`diode_pd2nw_06v0`). DR-0011
(`spec/decisions/0011-pad-esd-strategy.md`) reaffirms DR-0005's diode-based
clamp *contingent on* a real `klt drc`/`klt extract`/`klt lvs` run against a
diode-clamp draft proving extraction now works -- this script draws that
draft and the LVS reference/reports live alongside it, the same pattern
`gen_pad_min.py` already established for the GGNMOS cell.

Draws a **`diode_nd2ps_06v0`** clamp (n+ diffusion in p-substrate, the same
flavour DR-0005's Decision names first, and the flavour the stock
`gf180mcu_fd_io__asig_5p0` pad's own CDL clamp toward VSS uses,
`D0 DVSS DVDD diode_nd2ps_06v0`): a Comp region marked `Nplus` + `Dualgate` +
`diode_mk` (the cathode, extractable per
`klayout_tools/decks/gf180mcu.py`'s `diode_nd2ps_06v0` entry), wired straight
up a Metal1-Metal5 via stack to the bond pad (`PAD` net). The anode is the
p-substrate -- gf180mcu draws no mask for it, so `klt extract` ties it to the
deck's synthesized `substrate_net` global (`vsubs`), exactly the same
"body_unverified"-class limitation `gf180_tmds_pad_min`'s NMOS body already
carries (see `docs/cli/extract.md` "Junction diodes (issue #542)").

Layer numbers and DRC thresholds are taken from `klt`'s own curated gf180mcu
deck (`klayout_tools/decks/gf180mcu.py`), not assumed -- see DR-0011.
"""

from __future__ import annotations

import argparse

import klayout.db as db

# ---------------------------------------------------------------------------
# gf180mcu GDS layer/datatype pairs (klayout_tools/decks/gf180mcu.py
# EXTRACTION_DECK/DECK's `diodes=(...)` entry for `diode_nd2ps_06v0`, and the
# installed PDK's own layers_def.py; see DR-0011).
# ---------------------------------------------------------------------------
COMP = (22, 0)
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
PAD_LAYER = (37, 0)  # passivation/pad-opening marker (geom.drc: grid/angle only)

DBU = 0.001  # 1 nm, matches the installed PDK's own GDS files

CONTACT_SIZE = 0.22  # klt's contact.width.1 floor


def _box(layout, x0, y0, x1, y1):
    return db.Box(
        db.DPoint(x0, y0).to_itype(layout.dbu),
        db.DPoint(x1, y1).to_itype(layout.dbu),
    )


def build() -> db.Layout:
    layout = db.Layout()
    layout.dbu = DBU
    top_name = "gf180_tmds_pad_diode_draft"
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

    # -- diode_nd2ps_06v0 cathode: Comp, marked Nplus + Dualgate ------------
    # comp.width.mv.1 (klt's gf180mcu deck) requires >=0.30um width for any
    # Comp polygon that overlaps Dualgate; 1.0 x 1.0um clears that with
    # comfortable margin and leaves room for a 2-contact array.
    comp_x0, comp_x1 = 0.0, 1.0
    comp_y0, comp_y1 = 0.0, 1.0
    rect(COMP, comp_x0, comp_y0, comp_x1, comp_y1)
    margin = 0.16  # matches gen_pad_min.py's NPLUS-over-COMP margin convention
    rect(
        NPLUS,
        comp_x0 - margin,
        comp_y0 - margin,
        comp_x1 + margin,
        comp_y1 + margin,
    )
    dg_margin = 0.30  # comfortable Dualgate-over-Comp margin (no klt rule to clear)
    rect(
        DUALGATE,
        comp_x0 - dg_margin,
        comp_y0 - dg_margin,
        comp_x1 + dg_margin,
        comp_y1 + dg_margin,
    )
    # diode_mk covers the whole recognised-junction footprint -- both
    # terminals (cathode's Comp/Nplus/Dualgate stack, and the substrate-
    # formed anode) are scoped to `diode_mk & <layer>` by extract.py, so
    # drawing it only over the cathode's own footprint (plus margin) is
    # sufficient: the anode's substrate-formed terminal region is this same
    # marker footprint, narrowed by anode_excludes=(Nwell, DNWELL) -- neither
    # of which this draft draws, so nothing subtracts from it.
    mk_margin = 0.40
    rect(
        DIODE_MK,
        comp_x0 - mk_margin,
        comp_y0 - mk_margin,
        comp_x1 + mk_margin,
        comp_y1 + mk_margin,
    )

    # -- Cathode contact array (Metal1, over the Comp/Nplus/Dualgate stack) -
    # contact.space.1 needs >=0.25um edge-to-edge; 0.63/1.15 gives a 0.30um
    # edge gap (matches gen_pad_min.py's own contact pitch convention).
    cath_cx = (comp_x0 + comp_x1) / 2
    c0_y0, c1_y0 = 0.63, 1.15
    for cy0 in (c0_y0, c1_y0):
        rect(
            CONTACT,
            cath_cx - CONTACT_SIZE / 2,
            cy0,
            cath_cx + CONTACT_SIZE / 2,
            cy0 + CONTACT_SIZE,
        )
    m1_x0, m1_x1 = cath_cx - 0.31, cath_cx + 0.31
    m1_y0, m1_y1 = c0_y0 - 0.13, c1_y0 + CONTACT_SIZE + 0.13
    rect(METAL1, m1_x0, m1_y0, m1_x1, m1_y1)
    label(METAL1_LABEL, "PAD", cath_cx, (m1_y0 + m1_y1) / 2)

    # -- Via stack, Metal1 through Metal5, up to the bond pad ---------------
    # Sized generously above the currently-installed klt gf180mcu deck's
    # via*.width.1 (>=0.26um each dimension) so this draft is DRC-clean
    # under the deck as it stands today -- not just under the (older, less
    # complete) deck `gf180_tmds_pad_min` was originally signed off against;
    # see DR-0011's note on that pre-existing regression.
    stack_cx, stack_cy = cath_cx, (m1_y0 + m1_y1) / 2 + 1.4
    stack_half = 0.60
    stack_x0, stack_x1 = stack_cx - stack_half, stack_cx + stack_half
    stack_y0, stack_y1 = stack_cy - stack_half, stack_cy + stack_half
    # Metal1 landing pad for the via stack, plus a strap down to the
    # cathode's own Metal1 so the two Metal1 shapes above merge into one net.
    rect(METAL1, stack_x0, m1_y1 - 0.10, stack_x1, stack_y1)
    for metal_spec in (METAL2, METAL3, METAL4):
        rect(metal_spec, stack_x0, stack_y0, stack_x1, stack_y1)
    via_half = 0.15  # 0.30um square vias, clearing via*.width.1's 0.26um floor
    for via_spec in (VIA1, VIA2, VIA3, VIA4):
        rect(
            via_spec,
            stack_cx - via_half,
            stack_cy - via_half,
            stack_cx + via_half,
            stack_cy + via_half,
        )
    # pad.enclosing.metal5.1 needs Metal5 to overlap the pad opening by
    # >=2.0um on every side; the 1.2 x 1.2um stack above is the Metal5 via
    # landing, not the bond-pad opening itself -- widen Metal5 alone into a
    # generous bond-pad-sized square and inset the pad opening (37/0) well
    # past the 2.0um floor.
    pad_metal5_half = 3.3
    rect(
        METAL5,
        stack_cx - pad_metal5_half,
        stack_cy - pad_metal5_half,
        stack_cx + pad_metal5_half,
        stack_cy + pad_metal5_half,
    )
    pad_opening_half = 1.0
    rect(
        PAD_LAYER,
        stack_cx - pad_opening_half,
        stack_cy - pad_opening_half,
        stack_cx + pad_opening_half,
        stack_cy + pad_opening_half,
    )
    label(METAL5_LABEL, "PAD", stack_cx, stack_cy)

    top.flatten(True)
    return layout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", required=True, help="output GDS path")
    args = ap.parse_args()

    layout = build()
    layout.write(args.output)
    top = layout.top_cell()
    bbox = top.bbox()
    print(f"wrote {args.output}: cell {top.name!r}, bbox {bbox.to_dtype(layout.dbu)}")


if __name__ == "__main__":
    main()
