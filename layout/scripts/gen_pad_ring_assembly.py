#!/usr/bin/env python3
"""Assemble a single block-level layout: `cml_driver_core` (issue #22) plus a
drawn ESD/pad-ring structure for its two differential outputs (issue #86,
T1 item 2 analog).

`layout/README.md`'s "not the final TMDS driver pad" / "ESD/pad-ring
integration is explicitly out of scope" disclosures (issues #2 / #22) mark
exactly the gap this script closes for a first concrete increment: it
combines the CML driver core (imported as a flattened GDS instance) with two
integrated, diode-clamped bond pads -- one per differential output (OUTP,
OUTN) -- laid out at DR-0011's ratified 350 um pad pitch, plus the physical
structures DR-0011 flagged as **not yet exercised by any committed cell**:

- **DVDD/DVSS ring continuity** through Metal3/Metal4/Metal5 straps, drawn
  continuously across the full two-pad span (not stopping at each pad's own
  footprint) and via-stitched at intervals so the three metal levels form one
  electrically continuous conductor per net -- the requirement DR-0011 states
  neither `gf180_tmds_pad_min` nor its own diode draft exercises.
- **A substrate tap on a real net**: an explicit Pplus/Comp region outside
  every Nwell, contacted and wired into the DVSS strap. Per
  `klayout_tools/decks/gf180mcu.py`'s issue-#1084 derivation (`tap_pplus`),
  this is exactly the mechanism that ties the deck's synthesized `vsubs`
  global to a real, drawn net -- resolving the `device.body_unverified`-class
  warning DR-0011 flags as open for the eventual driver-integrated pad.

**Scope, deliberately bounded** (see the issue's own decomposition
guardrail -- "this issue's job is to get the assembly started ... not to
guarantee it finishes in one PR"):

- Two pads only (this driver's own OUTP/OUTN), not a full multi-lane TMDS
  ring (3 data lanes + clock, each needing its own differential pair) --
  that is a follow-up increment once this pattern is proven.
- Clamp topology is `diode_nd2ps_06v0` only (pad-to-substrate/VSS), reusing
  the exact geometry `gen_pad_diode_draft.py` already proved DRC/LVS-clean
  (issue #9/DR-0011), translated and relabelled per pad. DR-0011's
  symmetric `diode_pd2nw_06v0` VDD-side leg (needing its own Nwell + well
  tap) is not drawn here -- deferred, since this cell's driver has no VDD
  pin to begin with (`cml_driver_core` is an NMOS-only differential pair +
  tail source, per `design/netlist/cml_driver.spice`); the DVDD strap is
  still drawn (ring continuity is a ring-wide requirement, independent of
  whether *this* driver instance sinks current from it) but carries no
  clamp leg in this increment.
- INP/INN/IBIAS (driver inputs, off-chip from a digital/bias source) are not
  routed to pads here -- out of scope for the *output* pad-ring integration
  this issue targets.
- Pad-opening size (2x2 um, matching the verified diode-draft) is
  DRC-legal (the deck's only hard bond-pad rule, `pad.enclosing.metal5.1`,
  checks *enclosure* margin, not opening size -- `PAD.1`/`PAD.2` opening
  guidelines are explicitly out of this deck's curated scope) but not a
  production wire-bond target; sizing the pad opening for a real bond
  process is #87's capacitance-budget redesign, not this issue's.

Layer numbers and DRC thresholds are taken from `klt`'s own curated gf180mcu
deck (`klayout_tools/decks/gf180mcu.py`), not assumed -- see DR-0011 and
this module's own inline citations.
"""

from __future__ import annotations

import argparse

import klayout.db as db

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
PAD_LAYER = (37, 0)  # passivation/pad-opening marker (geom.drc: grid/angle only)

DBU = 0.001  # 1 nm, matches every other GDS in this repo

CONTACT_SIZE = 0.22  # klt's contact.width.1 floor
VIA_SIZE = 0.30  # comfortably clears via*.width.1's 0.26um floor (all levels)

# ---------------------------------------------------------------------------
# DR-0011 (spec/decisions/0011-pad-esd-strategy.md): 350um pad pitch / 75um
# ring depth, from `gf180mcu_fd_io__bi_t.lef`'s `SIZE 75.000 BY 350.000`.
# ---------------------------------------------------------------------------
PAD_PITCH_UM = 350.0
RING_DEPTH_UM = 75.0

# Ring supply-strap bands (Metal3/Metal4/Metal5, DR-0011's ring-continuity
# requirement), both comfortably inside RING_DEPTH_UM and clear of the
# diode-pad structures placed above them.
DVSS_BAND = (2.0, 6.0)
DVDD_BAND = (12.0, 16.0)
STRAP_STITCH_PITCH_UM = 50.0  # via3/via4 stitch interval tying M3-M4-M5 together

# y-offset of each pad's diode-clamp structure (see _draw_diode_pad's own
# docstring for the exact footprint this reuses from gen_pad_diode_draft.py).
PAD_STRUCT_OY_UM = 25.0


def _box(layout, x0, y0, x1, y1):
    return db.Box(
        db.DPoint(x0, y0).to_itype(layout.dbu),
        db.DPoint(x1, y1).to_itype(layout.dbu),
    )


def _draw_diode_pad(top, L, ox: float, oy: float, net_name: str) -> dict[str, float]:
    """Draw one `diode_nd2ps_06v0`-clamped bond pad at origin (ox, oy),
    labelled with `net_name` instead of the verification draft's generic
    "PAD" text. Geometry is `gen_pad_diode_draft.py`'s own DRC/LVS-clean
    cathode + via-stack + bond-pad structure (issue #9/DR-0011), translated
    here rather than re-derived, to keep this assembly on already-verified
    geometry. Local bbox (before translation): x[-2.8, 3.8], y[-0.9, 5.7]
    (6.6 x 6.6um) -- tiny relative to the 350um pad slot it sits in.

    Returns the absolute (x, y) of the cathode's own Metal1 net landing
    point, for the top-level router to connect the driver's output pin to.
    """

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(top.layout(), ox + x0, oy + y0, ox + x1, oy + y1))

    def label(spec, text, x, y):
        trans = db.DTrans(db.DPoint(ox + x, oy + y))
        top.shapes(L(spec)).insert(db.DText(text, trans))

    comp_x0, comp_x1 = 0.0, 1.0
    comp_y0, comp_y1 = 0.0, 1.0
    rect(COMP, comp_x0, comp_y0, comp_x1, comp_y1)
    margin = 0.16
    rect(NPLUS, comp_x0 - margin, comp_y0 - margin, comp_x1 + margin, comp_y1 + margin)
    dg_margin = 0.30
    rect(DUALGATE, comp_x0 - dg_margin, comp_y0 - dg_margin, comp_x1 + dg_margin, comp_y1 + dg_margin)
    mk_margin = 0.40
    rect(DIODE_MK, comp_x0 - mk_margin, comp_y0 - mk_margin, comp_x1 + mk_margin, comp_y1 + mk_margin)

    cath_cx = (comp_x0 + comp_x1) / 2
    c0_y0, c1_y0 = 0.63, 1.15
    for cy0 in (c0_y0, c1_y0):
        rect(CONTACT, cath_cx - CONTACT_SIZE / 2, cy0, cath_cx + CONTACT_SIZE / 2, cy0 + CONTACT_SIZE)
    m1_x0, m1_x1 = cath_cx - 0.31, cath_cx + 0.31
    m1_y0, m1_y1 = c0_y0 - 0.13, c1_y0 + CONTACT_SIZE + 0.13
    rect(METAL1, m1_x0, m1_y0, m1_x1, m1_y1)
    label(METAL1_LABEL, net_name, cath_cx, (m1_y0 + m1_y1) / 2)

    stack_cx, stack_cy = cath_cx, (m1_y0 + m1_y1) / 2 + 1.4
    stack_half = 0.60
    stack_x0, stack_x1 = stack_cx - stack_half, stack_cx + stack_half
    stack_y0, stack_y1 = stack_cy - stack_half, stack_cy + stack_half
    rect(METAL1, stack_x0, m1_y1 - 0.10, stack_x1, stack_y1)
    for metal_spec in (METAL2, METAL3, METAL4):
        rect(metal_spec, stack_x0, stack_y0, stack_x1, stack_y1)
    via_half = 0.15
    for via_spec in (VIA1, VIA2, VIA3, VIA4):
        rect(via_spec, stack_cx - via_half, stack_cy - via_half, stack_cx + via_half, stack_cy + via_half)
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
    label(METAL5_LABEL, net_name, stack_cx, stack_cy)

    return {"x": ox + cath_cx, "y": oy + (m1_y0 + m1_y1) / 2, "y0": oy + m1_y0, "y1": oy + m1_y1}


def _draw_substrate_tap(top, L, ox: float, oy: float, net_name: str) -> None:
    """Draw an explicit substrate tap: Pplus-covered Comp *outside* every
    Nwell (this assembly draws no Nwell at all, so that condition holds
    trivially), contacted and strapped straight up through Metal1/Metal2
    into the caller's already-drawn Metal3 strap at this same (ox, oy).

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

    # Same 1x1um Comp + 2-stacked-contact idiom gen_pad_diode_draft.py's own
    # cathode uses (DRC-clean under the current deck) -- Pplus in place of
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
    via_half = 0.15
    vcx, vcy = cx, (sy0 + sy1) / 2
    rect(VIA1, vcx - via_half, vcy - via_half, vcx + via_half, vcy + via_half)
    rect(VIA2, vcx - via_half, vcy - via_half, vcx + via_half, vcy + via_half)


def _draw_ring_strap(top, L, x0: float, x1: float, y0: float, y1: float) -> None:
    """Draw one DVDD/DVSS supply strap, continuous across [x0, x1] on
    Metal3/Metal4/Metal5, via-stitched every STRAP_STITCH_PITCH_UM so the
    three levels form one electrically continuous conductor (DR-0011's
    ring-continuity requirement)."""

    def rect(spec, rx0, ry0, rx1, ry1):
        top.shapes(L(spec)).insert(_box(top.layout(), rx0, ry0, rx1, ry1))

    for metal_spec in (METAL3, METAL4, METAL5):
        rect(metal_spec, x0, y0, x1, y1)
    cy = (y0 + y1) / 2
    via_half = 0.15
    x = x0 + STRAP_STITCH_PITCH_UM / 2
    while x < x1:
        rect(VIA3, x - via_half, cy - via_half, x + via_half, cy + via_half)
        rect(VIA4, x - via_half, cy - via_half, x + via_half, cy + via_half)
        x += STRAP_STITCH_PITCH_UM


def _route(top, L, waypoints: list[tuple[float, float]], width: float, metal_spec) -> None:
    """Draw a Manhattan metal path through `waypoints` (each consecutive
    pair sharing one coordinate) on a single metal layer.

    Every segment is over-extended by `width / 2` at *both* ends (not just
    squared off at its own two endpoints). Without this, a corner waypoint
    sits exactly on the centreline of the perpendicular segment meeting it
    there, so the two rectangles overlap over only half the trace width at
    the joint -- a sub-minimum-width sliver `metal2.width.1` (and the
    equivalent rule on any other metal level) correctly flags. Over-
    extending guarantees a full-width square overlap at every corner, and a
    harmless small overshoot into whatever via/pad landing sits at each
    path's true start/end.
    """

    def rect(x0, y0, x1, y1):
        top.shapes(L(metal_spec)).insert(_box(top.layout(), x0, y0, x1, y1))

    half = width / 2
    for (x0, y0), (x1, y1) in zip(waypoints, waypoints[1:]):
        if x0 == x1:
            rect(x0 - half, min(y0, y1) - half, x1 + half, max(y0, y1) + half)
        elif y0 == y1:
            rect(min(x0, x1) - half, y0 - half, max(x0, x1) + half, y1 + half)
        else:
            raise ValueError(f"non-Manhattan segment: ({x0},{y0}) -> ({x1},{y1})")


def _land_via_stack(top, L, x: float, y: float, size: float = 0.4) -> None:
    """Drop a Metal1<->Metal2 via1 stack at (x, y): a small Metal1 pad (to
    overlap whatever net already occupies that point -- a driver pin, or a
    pad's own cathode landing) plus Metal2 pad and the via1 cut joining
    them, so a Metal2 router segment can pick up an M1-level net."""

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(top.layout(), x0, y0, x1, y1))

    half = size / 2
    rect(METAL1, x - half, y - half, x + half, y + half)
    rect(METAL2, x - half, y - half, x + half, y + half)
    via_half = 0.15
    rect(VIA1, x - via_half, y - via_half, x + via_half, y + via_half)


def build(driver_gds: str, shorted: bool = False) -> db.Layout:
    layout = db.Layout()
    layout.dbu = DBU
    top_name = "gf180_tmds_pad_ring_assembly_shorted" if shorted else "gf180_tmds_pad_ring_assembly"
    top = layout.create_cell(top_name)

    layers: dict[tuple[int, int], int] = {}

    def L(spec):
        if spec not in layers:
            layers[spec] = layout.layer(*spec)
        return layers[spec]

    # -- Import the driver core as a flattened instance --------------------
    # `Layout.read` merges the source GDS's cells directly into the
    # destination `Layout` object (no name collisions here, so no
    # auto-renaming); the driver's own dbu (0.001, checked against every
    # other GDS this repo commits) must match this layout's for the imported
    # coordinates below to be correct without an extra rescale.
    if layout.dbu != DBU:  # pragma: no cover - defensive, DBU is a constant
        raise RuntimeError("layout dbu changed out from under this import")
    layout.read(driver_gds)  # merges the source cells into `layout` in place
    driver_top_index = layout.cell_by_name("cml_driver_core")
    driver_top = layout.cell(driver_top_index)

    # Locate OUTP/OUTN/VSS pin coordinates from the driver's own Metal1
    # label layer (34/10) -- the same convention gen_cml_driver_core.py's
    # `klt gen-compose` output and gen_pad_min.py/gen_pad_diode_draft.py's
    # hand-drawn labels both already use.
    label_layer = L((34, 10))
    pins: dict[str, tuple[float, float]] = {}
    for shape in driver_top.shapes(label_layer).each():
        if shape.is_text():
            t = shape.text
            pins[t.string] = (t.x * layout.dbu, t.y * layout.dbu)
    for required in ("OUTP", "OUTN", "VSS"):
        if required not in pins:
            raise RuntimeError(f"driver GDS {driver_gds!r} has no {required!r} pin label")

    # Place the driver below the ring, x-centred under the OUTP/OUTN pad
    # gap so both output routes run roughly symmetric distances.
    driver_bbox = driver_top.bbox().to_dtype(layout.dbu)
    pad0_cx = PAD_PITCH_UM / 2
    pad1_cx = PAD_PITCH_UM * 1.5
    gap_cx = (pad0_cx + pad1_cx) / 2
    driver_local_cx = (driver_bbox.left + driver_bbox.right) / 2
    tx = gap_cx - driver_local_cx
    ty = -30.0  # comfortably below the ring's y=0 edge, room for routing jogs

    top.insert(db.CellInstArray(driver_top_index, db.Trans(db.DVector(tx, ty).to_itype(layout.dbu))))

    outp_x, outp_y = pins["OUTP"][0] + tx, pins["OUTP"][1] + ty
    outn_x, outn_y = pins["OUTN"][0] + tx, pins["OUTN"][1] + ty
    vss_x, vss_y = pins["VSS"][0] + tx, pins["VSS"][1] + ty

    # -- Ring supply straps (DR-0011 ring continuity) -----------------------
    total_width = 2 * PAD_PITCH_UM
    _draw_ring_strap(top, L, 0.0, total_width, *DVSS_BAND)
    _draw_ring_strap(top, L, 0.0, total_width, *DVDD_BAND)

    # -- Substrate tap, tied into the DVSS strap at the pad-pair gap -------
    tap_x = PAD_PITCH_UM - 0.5
    tap_y = DVSS_BAND[0]
    _draw_substrate_tap(top, L, tap_x, tap_y, "VSS")

    # -- Two diode-clamped pads: OUTP (west slot), OUTN (east slot) --------
    pad0 = _draw_diode_pad(top, L, pad0_cx - 0.5, PAD_STRUCT_OY_UM, "OUTP")
    pad1 = _draw_diode_pad(top, L, pad1_cx - 0.5, PAD_STRUCT_OY_UM, "OUTN")

    # -- Route driver outputs up to their pads, on Metal2 -------------------
    _land_via_stack(top, L, outp_x, outp_y)
    _land_via_stack(top, L, pad0["x"], pad0["y0"] + 0.15)
    _route(
        top,
        L,
        [(outp_x, outp_y), (outp_x, outp_y - 3.0), (pad0["x"], outp_y - 3.0), (pad0["x"], pad0["y0"] + 0.15)],
        0.35,
        METAL2,
    )

    _land_via_stack(top, L, outn_x, outn_y)
    _land_via_stack(top, L, pad1["x"], pad1["y0"] + 0.15)
    _route(
        top,
        L,
        [(outn_x, outn_y), (outn_x, outn_y + 3.0), (pad1["x"], outn_y + 3.0), (pad1["x"], pad1["y0"] + 0.15)],
        0.35,
        METAL2,
    )

    # -- Route driver VSS into the substrate tap / DVSS strap ---------------
    tap_land_x, tap_land_y = tap_x + 0.5, tap_y + 1.5
    _land_via_stack(top, L, vss_x, vss_y)
    _land_via_stack(top, L, tap_land_x, tap_land_y)
    _route(
        top,
        L,
        [(vss_x, vss_y), (vss_x, tap_land_y), (tap_land_x, tap_land_y)],
        0.35,
        METAL2,
    )

    if shorted:
        # LVS negative control (mirroring every other cell's own `_shorted`
        # variant, e.g. gen_pad_min.py, gen_cml_driver_core.py): bridge
        # OUTP's pad-net landing directly to the VSS ring strap with one
        # extra Metal2 wire -- a pure connectivity (net.merged) defect, not
        # a new DRC-illegal shape. Must FAIL `klt lvs` against the same
        # reference netlist the unshorted assembly passes.
        _land_via_stack(top, L, pad0["x"] + 0.9, pad0["y0"] + 0.15)
        _land_via_stack(top, L, tap_land_x + 0.9, tap_land_y)
        _route(
            top,
            L,
            [
                (pad0["x"] + 0.9, pad0["y0"] + 0.15),
                (pad0["x"] + 0.9, tap_land_y),
                (tap_land_x + 0.9, tap_land_y),
            ],
            0.35,
            METAL2,
        )
        _route(
            top,
            L,
            [(pad0["x"] + 0.9, pad0["y0"] + 0.15), (pad0["x"], pad0["y0"] + 0.15)],
            0.35,
            METAL1,
        )
        _route(
            top,
            L,
            [(tap_land_x + 0.9, tap_land_y), (tap_land_x, tap_land_y)],
            0.35,
            METAL1,
        )

    top.flatten(True)
    return layout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", required=True, help="output GDS path")
    ap.add_argument(
        "--driver-gds",
        default="gds/cml_driver_core.gds",
        help="cml_driver_core GDS to import (default: gds/cml_driver_core.gds)",
    )
    ap.add_argument(
        "--shorted",
        action="store_true",
        help="emit the LVS negative-control (OUTP-shorted-to-VSS) variant",
    )
    args = ap.parse_args()

    layout = build(args.driver_gds, shorted=args.shorted)
    layout.write(args.output)
    top = layout.top_cell()
    bbox = top.bbox()
    print(f"wrote {args.output}: cell {top.name!r}, bbox {bbox.to_dtype(layout.dbu)}")


if __name__ == "__main__":
    main()
