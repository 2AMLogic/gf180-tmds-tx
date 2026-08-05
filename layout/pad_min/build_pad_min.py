#!/usr/bin/env python3
"""Build the minimal custom TMDS pad cell (issue #2).

Composes two pieces into one GDS:

  1. a substrate/well tap guard ring, generated headlessly by
     `klt gen guard_ring` (klayout-tools' PCell-style layout generator)
  2. a bond-pad-equivalent solid Metal2..Metal5 stack, stitched together
     with Via2/Via3/Via4 arrays, sized to the gf180mcu_fd_io library's own
     documented 60um x 60um bond pad opening (see spec/pad-ring-esd.md
     Sec. 2 for the citation)

This is deliberately NOT a reproduction of the vendor gf180mcu_fd_io bond
pad (a proprietary Cadence-PCell-generated structure we do not have source
for) -- it is a first-cut, DRC-checkable stand-in for the geometry a custom
pad needs, sized and cited against real PDK/DRM facts. See
spec/pad-ring-esd.md for what is and is not modeled, and for the two
klayout-tools gaps (2AMLogic/klayout-tools#542, #543) that currently block
carrying this further (an ESD diode device, and any LVS check at all on a
deviceless structure).

Usage (run with klayout-tools' own venv python, which ships `klayout.db`):

    klt gen guard_ring --params '{"inner_width_um": 64, "inner_height_um": 64,
        "ring_width_um": 2.0, "contacts_per_side": 14}' --pdk gf180mcuC \
        -o ring_only.gds
    <klt-venv-python> build_pad_min.py ring_only.gds gf180_tmds_pad_min.gds
    rm ring_only.gds   # intermediate, not committed

`klt`'s own install layout puts that venv's python at, e.g.:
    ~/.local/share/uv/tools/klayout-tools/bin/python
"""
import sys

import klayout.db as db

RING_GDS = sys.argv[1]
OUT_GDS = sys.argv[2]

# gf180mcu layer/datatype numbers, from klayout_tools/decks/gf180mcu.py's
# module docstring (transcribed from google/globalfoundries-pdk-libs-gf180mcu_fd_pv
# main.drc layer derivations) -- see spec/pad-ring-esd.md Sec. 4 for the
# same table with citations.
METAL2 = (36, 0)
METAL3 = (42, 0)
METAL4 = (46, 0)
METAL5 = (81, 0)
VIA2 = (38, 0)  # Metal2 <-> Metal3
VIA3 = (40, 0)  # Metal3 <-> Metal4
VIA4 = (41, 0)  # Metal4 <-> Metal5
METAL1_LABEL = (34, 10)
METAL5_LABEL = (81, 10)

# Bond-pad-equivalent metal stack: 60um x 60um (gf180mcu_fd_io library's own
# documented bond-pad-opening size -- features.rst, "The bond pad opening is
# 60umx60um"), centered in the guard ring's ~64um x 64um inner clear area
# (guard ring generated with inner_width_um=64, inner_height_um=64,
# ring_width_um=2.0 -> outer bbox (-0.15,-0.15)-(68.15,68.15), inner clear
# area approx (2,2)-(66,66)).
PAD_X0, PAD_Y0, PAD_X1, PAD_Y1 = 4.0, 4.0, 64.0, 64.0

# Via array stitching the metal stack together: modest density, not a dense
# fill -- this curated DRC deck does not yet check Via1-4 width/space
# (2AMLogic/klayout-tools#544), so there is no DRC pressure to pack them
# tightly; a sparse array is enough to demonstrate a real multi-level via
# stack without inflating the GDS with tens of thousands of shapes.
VIA_SIZE = 0.28
VIA_PITCH = 2.0
VIA_INSET = 3.0


def um(v, dbu):
    return int(round(v / dbu))


def add_box(layout, cell, layer_dt, x0, y0, x1, y1, dbu):
    li = layout.layer(layer_dt[0], layer_dt[1])
    cell.shapes(li).insert(db.Box(um(x0, dbu), um(y0, dbu), um(x1, dbu), um(y1, dbu)))


def add_label(layout, cell, layer_dt, text, x, y, dbu):
    li = layout.layer(layer_dt[0], layer_dt[1])
    trans = db.Trans(um(x, dbu), um(y, dbu))
    cell.shapes(li).insert(db.Text(text, trans))


def main():
    layout = db.Layout()
    layout.read(RING_GDS)
    layout.dbu = 0.001
    dbu = layout.dbu

    top = None
    for c in layout.each_cell():
        if c.name == "guard_ring_0":
            top = c
    if top is None:
        raise SystemExit("guard_ring_0 cell not found in ring GDS")

    for layer_dt in (METAL2, METAL3, METAL4, METAL5):
        add_box(layout, top, layer_dt, PAD_X0, PAD_Y0, PAD_X1, PAD_Y1, dbu)

    x = PAD_X0 + VIA_INSET
    xs = []
    while x < PAD_X1 - VIA_INSET:
        xs.append(x)
        x += VIA_PITCH
    y = PAD_Y0 + VIA_INSET
    ys = []
    while y < PAD_Y1 - VIA_INSET:
        ys.append(y)
        y += VIA_PITCH

    for via_dt in (VIA2, VIA3, VIA4):
        for vx in xs:
            for vy in ys:
                add_box(layout, top, via_dt, vx, vy, vx + VIA_SIZE, vy + VIA_SIZE, dbu)

    # Net-name labels for `klt extract` pin promotion (see
    # spec/pad-ring-esd.md Sec. 6 on why extraction/LVS could not actually
    # be completed against these -- 2AMLogic/klayout-tools#543).
    add_label(
        layout,
        top,
        METAL5_LABEL,
        "PAD",
        (PAD_X0 + PAD_X1) / 2,
        (PAD_Y0 + PAD_Y1) / 2,
        dbu,
    )
    # Guard ring Metal1 tap net -- label near the TAP_S port (x=34, y=1 per
    # `klt gen guard_ring`'s own port report for these params).
    add_label(layout, top, METAL1_LABEL, "VSUB", 34.0, 1.0, dbu)

    top.name = "gf180_tmds_pad_min"
    layout.write(OUT_GDS)
    print(f"wrote {OUT_GDS}, top cell {top.name}")


if __name__ == "__main__":
    main()
