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
- **A production 25x25 um bond pad per output** (issue #149, folding in
  issue #143's fit study), not a DRC-legal-but-not-a-production-target
  placeholder: a 25x25 um Metal5 plate with a 20x20 um opening (2.5 um
  `pad.enclosing.metal5.1`-clearing margin) and a folded multi-finger
  `diode_nd2ps_06v0` clamp array, exactly `gen_pad_v2.py`'s own geometry
  (issue #87) -- see `_draw_production_pad` below, ported from
  `pad_pitch_fit_study.py`'s already-DRC-clean reference implementation
  (issue #143).

**Scope, deliberately bounded** (see the issue's own decomposition
guardrail -- "this issue's job is to get the assembly started ... not to
guarantee it finishes in one PR"):

- Two pads only (this driver's own OUTP/OUTN), not a full multi-lane TMDS
  ring (3 data lanes + clock, each needing its own differential pair) --
  that is a follow-up increment once this pattern is proven.
- Clamp topology is DR-0011's dual-diode pair per output: `diode_nd2ps_06v0`
  (pad-to-substrate/VSS, `gen_pad_v2.py`'s own DRC/LVS-clean multi-finger
  array geometry, issue #87/#143, translated and relabelled per pad) and the
  symmetric `diode_pd2nw_06v0` VDD-side leg (issue #210): the same folded
  finger array drawn as Pplus/Dualgate/diode_mk Comp inside its own Nwell
  above the first array, anode on the pad net, plus an Nplus Nwell tap that
  carries the Nwell (the cathode) to the DVDD strap through Metal1/Metal2/
  via2. The strap is labelled `VDD` at those taps. The driver itself still
  has no VDD pin (`cml_driver_core` is an NMOS-only differential pair + tail
  source, per `design/netlist/cml_driver.spice`), so VDD is carried by the
  ring clamps and the Nwell tap only.
- INP/INN/IBIAS (driver inputs, off-chip from a digital/bias source) are not
  routed to pads here -- out of scope for the *output* pad-ring integration
  this issue targets.
- Clamp size is `N_FINGERS` (20 fingers, `gf180_tmds_pad_v2`'s own as-drawn
  array) -- a representative, DRC/LVS-provable size, not yet the final
  HBM-qualified one (`design/esd-capacitance-budget.md` Sec.2a/9.6). The
  row-fold this module ports from `pad_pitch_fit_study.py`
  (`clamp_rows`/`_draw_production_pad`) means a future larger clamp is a
  constant change here, not a redesign -- issue #143 already checked the
  whole HBM-sizing window folds inside DR-0011's ratified 350 um pitch.

Layer numbers and DRC thresholds are taken from `klt`'s own curated gf180mcu
deck (`klayout_tools/decks/gf180mcu.py`), not assumed -- see DR-0011 and
this module's own inline citations.
"""

from __future__ import annotations

import argparse

from pad_ring_cells import (  # noqa: F401 -- re-exported; single source (issues #242, #262)
    CONTACT_SIZE,
    DEFAULT_BUS_WIDTH_UM,
    DVDD_BAND,
    DVSS_BAND,
    FINGER_DEPTH,
    FINGER_L,
    FINGER_PITCH,
    MAX_FINGERS_PER_ROW,
    PAD_OPENING_MARGIN,
    PAD_SIDE,
    PAD_VIA_GAP_UM,
    ROW_GAP_UM,
    STRAP_STITCH_PITCH_UM,
    VIA_HALF,
    VIA_SIZE,
    _draw_production_pad,
    _draw_ring_strap,
    _draw_substrate_tap,
    _row_pitch,
    _row_span,
    clamp_rows,
)

try:  # pragma: no cover -- exercised by whichever environment is present
    import klayout.db as db
except ModuleNotFoundError:  # pragma: no cover
    # The pure arithmetic below (`clamp_rows`, `_row_span`, `_row_pitch`,
    # `_struct_width_um`) is stdlib and unit-tested in layout/tests/, which
    # runs in CI's deliberately PDK-free, KLayout-free job (same convention
    # `pad_pitch_fit_study.py` established, issue #143). Only `build()` needs
    # klayout.db, and it says so with a clean error rather than an import
    # traceback.
    db = None

# ---------------------------------------------------------------------------
# gf180mcu GDS layer/datatype pairs (klayout_tools/decks/gf180mcu.py
# EXTRACTION_DECK/DECK and the installed PDK's own layers_def.py).
# ---------------------------------------------------------------------------
from gf180_layers import (  # noqa: F401 -- shared layer table (issue #255)
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
    NWELL,
    PAD_LAYER,
    PPLUS,
    VIA1,
    VIA2,
    VIA3,
    VIA4,
    _box,
)

DBU = 0.001  # 1 nm, matches every other GDS in this repo

# ---------------------------------------------------------------------------
# DR-0011 (spec/decisions/0011-pad-esd-strategy.md): 350um pad pitch / 75um
# ring depth, from `gf180mcu_fd_io__bi_t.lef`'s `SIZE 75.000 BY 350.000`.
# ---------------------------------------------------------------------------
PAD_PITCH_UM = 350.0
RING_DEPTH_UM = 75.0

# The shared pad/strap constants (DVSS_BAND, DVDD_BAND, STRAP_STITCH_PITCH_UM,
# PAD_SIDE, PAD_OPENING_MARGIN, PAD_VIA_GAP_UM, FINGER_*, ROW_GAP_UM,
# DEFAULT_BUS_WIDTH_UM, MAX_FINGERS_PER_ROW), the fold arithmetic
# (`clamp_rows`, `_row_span`, `_row_pitch`) and the strap / substrate-tap /
# production-pad drawing helpers have one definition, in pad_ring_cells.py
# (issue #262; the fold itself was pad_pitch_fit_study.py's, issue #143/#242),
# shared with pad_pitch_fit_study.py and imported at the top of this module.

# This driver's own as-drawn clamp size -- gf180_tmds_pad_v2's own 20-finger
# array (issue #87), not yet the final HBM-qualified size
# (design/esd-capacitance-budget.md Sec.2a/9.6 -- literature-bounded, still
# open). `clamp_rows` below folds any larger future size into rows, so
# raising this later is a constant change, not a redesign.
N_FINGERS = 20

# y-origin of each pad's clamp array/via-stack/plate structure. The Metal5
# plate is centred on the array; at 30.0 um its lower edge clears
# DVDD_BAND's 16.0 um top edge by 2.0 um (issue #143 -- 25.0 um, this
# module's pre-#149 value, put the plate straight through the DVDD strap
# band once the plate grew from the placeholder's 6.6um to 25um).
PAD_STRUCT_OY_UM = 30.0

# VDD-side clamp (`diode_pd2nw_06v0`, DR-0011's symmetric P-clamp-toward-VDD
# leg): the second finger array of each pad sits this far above the first
# array's top edge. Wide enough that the Nwell (NWELL_MARGIN_UM past the
# Pplus fingers) clears the VSS-side N+ diode's Nplus/Dualgate/diode_mk
# halos with room to spare.
VDD_CLAMP_GAP_UM = 7.0
NWELL_MARGIN_UM = 0.7  # Nwell overlap of the Pplus fingers (clears NW enclosure)
# x of the Nwell tap's Comp, left of the VDD clamp array. Far enough that the
# tap's Nplus clears the array's Pplus/diode_mk, near enough to stay in the
# same Nwell island.
NWELL_TAP_X_UM = -3.4


def _struct_width_um(n_fingers: int, bus_width: float = DEFAULT_BUS_WIDTH_UM) -> float:
    """Total x footprint (rows folded) of one production pad structure --
    the number DR-0011's 350um pad-pitch slot has to hold."""
    rows = clamp_rows(n_fingers)
    array_x = _row_span(max(rows))
    return array_x + PAD_VIA_GAP_UM + PAD_SIDE / 2


def _draw_vdd_clamp(
    top,
    L,
    ox: float,
    oy: float,
    net_name: str,
    n_fingers: int = N_FINGERS,
    bus_width: float = DEFAULT_BUS_WIDTH_UM,
) -> dict[str, float]:
    """Draw one pad's VDD-side clamp: a folded `diode_pd2nw_06v0` finger
    array (Pplus/Dualgate/diode_mk Comp inside an Nwell -- anode = the pad
    net, cathode = the Nwell), plus an Nplus Comp Nwell tap that carries the
    Nwell (the diode cathode) to VDD. Same finger geometry and row fold as
    the VSS-side `_draw_production_pad` array so both legs present the same
    area/periphery (`A=40P P=120U` at 20 fingers) to `klt extract`.

    (ox, oy) is the array's own origin; the anode's Metal1 gather bus runs
    out to x = via_cx (this pad's cathode-spine column, `_draw_production_pad`
    at the same ox) so the caller can tie it to the pad net with a vertical
    Metal1 spine. Returns the absolute (x, y) of the Nwell tap's Metal2
    landing, for the caller to route down to the DVDD strap.
    """

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(top.layout(), ox + x0, oy + y0, ox + x1, oy + y1))

    def label(spec, text, x, y):
        top.shapes(L(spec)).insert(db.DText(text, db.DTrans(db.DPoint(ox + x, oy + y))))

    rows = clamp_rows(n_fingers)
    array_x1 = _row_span(max(rows))
    row_pitch = _row_pitch(bus_width)
    array_y1 = (len(rows) - 1) * row_pitch + max(FINGER_DEPTH, bus_width)

    contact_y_off = 0.39
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

    margin = 0.16
    rect(PPLUS, -margin, -margin, array_x1 + margin, array_y1 + margin)
    dg = 0.30
    rect(DUALGATE, -dg, -dg, array_x1 + dg, array_y1 + dg)
    mk = 0.40
    rect(DIODE_MK, -mk, -mk, array_x1 + mk, array_y1 + mk)

    # Vertical Metal1 spine joining the rows' anode buses (also the column the
    # caller's pad-net spine arrives on).
    spine_half = max(0.60, bus_width / 2)
    rect(METAL1, via_cx - spine_half, bus_dy0, via_cx + spine_half, (len(rows) - 1) * row_pitch + bus_dy1)

    # Nwell tap: Nplus-covered 1x1 um Comp left of the array, inside the same
    # Nwell. No Dualgate / diode_mk -- a plain well tie, not a diode terminal.
    tap_x0 = NWELL_TAP_X_UM
    tap_x1 = tap_x0 + 1.0
    tap_y0, tap_y1 = 0.0, 1.0
    rect(COMP, tap_x0, tap_y0, tap_x1, tap_y1)
    rect(NPLUS, tap_x0 - margin, tap_y0 - margin, tap_x1 + margin, tap_y1 + margin)
    tcx = (tap_x0 + tap_x1) / 2
    tcy = (tap_y0 + tap_y1) / 2
    rect(CONTACT, tcx - CONTACT_SIZE / 2, tcy - CONTACT_SIZE / 2, tcx + CONTACT_SIZE / 2, tcy + CONTACT_SIZE / 2)
    m1_half = 0.35
    rect(METAL1, tcx - m1_half, tcy - m1_half, tcx + m1_half, tcy + m1_half)
    label(METAL1_LABEL, net_name, tcx, tcy)

    # One Nwell over the tap and every Pplus finger.
    rect(
        NWELL,
        tap_x0 - NWELL_MARGIN_UM,
        -NWELL_MARGIN_UM,
        array_x1 + NWELL_MARGIN_UM,
        array_y1 + NWELL_MARGIN_UM,
    )

    # Via1 + Metal2 landing on the tap's Metal1 pad; the caller runs Metal2
    # from here down to the DVDD strap.
    via_half = VIA_HALF
    rect(VIA1, tcx - via_half, tcy - via_half, tcx + via_half, tcy + via_half)
    rect(METAL2, tcx - m1_half, tcy - m1_half, tcx + m1_half, tcy + m1_half)
    return {"x": ox + tcx, "y": oy + tcy, "spine_x": ox + via_cx, "bus_y": oy + bus_cy}


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
    via_half = VIA_HALF
    rect(VIA1, x - via_half, y - via_half, x + via_half, y + via_half)


def build(
    driver_gds: str,
    shorted: bool = False,
    n_fingers: int = N_FINGERS,
    bus_width: float = DEFAULT_BUS_WIDTH_UM,
) -> db.Layout:
    if db is None:  # pragma: no cover -- environment-dependent
        raise RuntimeError(
            "drawing this assembly needs the `klayout` PyPI package (klayout.db); "
            "the pure fold/fit arithmetic (clamp_rows, _struct_width_um) needs no "
            "such thing and is exercised directly by layout/tests/"
        )

    # Scope item 4: centre each pad structure in its own PAD_PITCH_UM slot,
    # and raise a hard error rather than silently overrunning the slot if the
    # requested clamp size cannot be folded to fit -- DR-0011 is ratified,
    # the fold widens (MAX_FINGERS_PER_ROW), never the pitch.
    struct_width = _struct_width_um(n_fingers, bus_width)
    if struct_width > PAD_PITCH_UM:
        raise ValueError(
            f"a {n_fingers}-finger clamp needs {struct_width:.3f} um of x, which does "
            f"not fit DR-0011's ratified {PAD_PITCH_UM:.0f} um pad pitch even folded at "
            f"MAX_FINGERS_PER_ROW={MAX_FINGERS_PER_ROW}. DR-0011 is ratified: widen the "
            f"fold, not the pitch."
        )

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
    # Each structure is centred in its own PAD_PITCH_UM slot (scope item 4)
    # rather than offset by the pre-#149 placeholder's fixed 0.5um, which was
    # fine for a 6.6um plate and is not for a struct_width-um one.
    pad0 = _draw_production_pad(top, L, pad0_cx - struct_width / 2, PAD_STRUCT_OY_UM, "OUTP", n_fingers, bus_width)
    pad1 = _draw_production_pad(top, L, pad1_cx - struct_width / 2, PAD_STRUCT_OY_UM, "OUTN", n_fingers, bus_width)

    # -- VDD-side clamp per pad: pd2nw array + Nwell tap -> DVDD strap ------
    # (DR-0011's symmetric P-clamp-toward-VDD leg, issue #210.) Each array
    # sits above its pad's VSS-side array; a Metal1 spine ties its anode bus
    # to the pad net, and the Nwell tap's Metal2 runs down onto the DVDD
    # strap's Metal3 through one via2.
    rows = clamp_rows(n_fingers)
    array_top = (len(rows) - 1) * _row_pitch(bus_width) + max(FINGER_DEPTH, bus_width)
    vdd_oy = PAD_STRUCT_OY_UM + array_top + VDD_CLAMP_GAP_UM
    strap_cy = (DVDD_BAND[0] + DVDD_BAND[1]) / 2
    for slot_cx, net in ((pad0_cx, "OUTP"), (pad1_cx, "OUTN")):
        ox = slot_cx - struct_width / 2
        clamp = _draw_vdd_clamp(top, L, ox, vdd_oy, "VDD", n_fingers, bus_width)
        # anode bus -> pad net: Metal1 spine from the pad's own bus up to this
        # array's bus, on the column both arrays' buses already reach.
        spine_half = max(0.60, bus_width / 2)
        top.shapes(L(METAL1)).insert(
            _box(
                top.layout(),
                clamp["spine_x"] - spine_half,
                PAD_STRUCT_OY_UM,
                clamp["spine_x"] + spine_half,
                clamp["bus_y"] + bus_width / 2,
            )
        )
        # Nwell tap -> DVDD strap: Metal2 straight down, via2 into Metal3.
        _route(top, L, [(clamp["x"], clamp["y"]), (clamp["x"], strap_cy)], 0.7, METAL2)
        top.shapes(L(VIA2)).insert(
            _box(top.layout(), clamp["x"] - VIA_HALF, strap_cy - VIA_HALF, clamp["x"] + VIA_HALF, strap_cy + VIA_HALF)
        )

    # -- Route driver outputs up to their pads, on Metal2 -------------------
    # Landing point is each pad's row-0 Metal1 bus centre (scope item 5).
    _land_via_stack(top, L, outp_x, outp_y)
    _land_via_stack(top, L, pad0["x"], pad0["y"])
    _route(
        top,
        L,
        [(outp_x, outp_y), (outp_x, outp_y - 3.0), (pad0["x"], outp_y - 3.0), (pad0["x"], pad0["y"])],
        0.35,
        METAL2,
    )

    _land_via_stack(top, L, outn_x, outn_y)
    _land_via_stack(top, L, pad1["x"], pad1["y"])
    _route(
        top,
        L,
        [(outn_x, outn_y), (outn_x, outn_y + 3.0), (pad1["x"], outn_y + 3.0), (pad1["x"], pad1["y"])],
        0.35,
        METAL2,
    )

    # -- Route driver VSS into the substrate tap / DVSS strap ---------------
    # Coincide exactly with the tap's own via1 (`_draw_substrate_tap`'s vcy =
    # 1.75) -- two 0.26um vias 0.25um apart would merge into one 0.26 x 0.51um
    # via, which via1.width.1's fixed square size rejects.
    tap_land_x, tap_land_y = tap_x + 0.5, tap_y + 1.75
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
        _land_via_stack(top, L, pad0["x"] + 0.9, pad0["y"])
        _land_via_stack(top, L, tap_land_x + 0.9, tap_land_y)
        _route(
            top,
            L,
            [
                (pad0["x"] + 0.9, pad0["y"]),
                (pad0["x"] + 0.9, tap_land_y),
                (tap_land_x + 0.9, tap_land_y),
            ],
            0.35,
            METAL2,
        )
        _route(
            top,
            L,
            [(pad0["x"] + 0.9, pad0["y"]), (pad0["x"], pad0["y"])],
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
