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

3. **Real substrate taps** (Pplus-covered Comp outside every Nwell, tied
   to a `VSS` net through Metal1), addressing DR-0011's flagged
   requirement ("the eventual driver-integrated pad ... must draw a real
   tap" -- `gf180_tmds_pad_min` and `gf180_tmds_pad_diode_draft` both
   deliberately omit one and both carry an LVS `device.body_unverified`
   warning as a result). Distributed along the finger row, one per
   `TAP_MAX_PITCH_UM`: DRM DF.14_MV's 15um NCOMP-to-PCOMP reach
   (`comp.tap_distance.psub.mv.1`) gained deck coverage after this cell's
   signoff, and the single one-end tap the cell originally drew left 13 of
   the 20 fingers beyond it (issue #422). `klt`'s gf180mcu deck derives
   an equivalent tap region from `tap_pplus`/`tap_nplus` implants
   (issue #1084) rather than
   needing a dedicated tap mask, and globally connects it to the same
   `substrate_net` (`vsubs`) global every unconnected device body/anode in
   this deck already uses -- so wiring each tap's own Metal1 to a real
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
from math import ceil

import klayout.db as db

# ---------------------------------------------------------------------------
# gf180mcu GDS layer/datatype pairs (klayout_tools/decks/gf180mcu.py
# EXTRACTION_DECK/DECK and the installed PDK's own layers_def.py).
# ---------------------------------------------------------------------------
from gf180_layers import (
    COMP,
    CONTACT,
    CONTACT_SIZE,
    DBU,
    METAL1,
    METAL1_LABEL,
    PPLUS,
    make_drawers,
)
from pad_ring_cells import _draw_production_pad, _row_span, clamp_rows

N_FINGERS = 20  # this cell's clamp size; pad/clamp geometry lives in pad_ring_cells

# DRM DF.14_MV (`comp.tap_distance.psub.mv.1`): NCOMP outside Nwell must stay
# within 15um of a PCOMP substrate tap. The rule gained deck coverage after
# this cell's signoff (issue #422) and flagged 13 of the 20 fingers against
# the single one-end tap the cell originally drew, so taps are now
# distributed along the finger row instead. Via cuts come from the shared
# helper's 0.26um `via*.width.1`-fixed default for the same reason: this
# cell's old 0.30um override violated the max side of that very rule.
TAP_WIDTH_UM = 2.0
TAP_MAX_PITCH_UM = 25.0  # worst finger point lands ~11.4um from a tap (rule: 15um)


def tap_count(row_span: float) -> int:
    """Taps needed so adjacent-tap pitch never exceeds ``TAP_MAX_PITCH_UM``.

    Taps span ``row_span - TAP_WIDTH_UM`` (first tap's left edge to last tap's
    left edge) in ``n - 1`` equal gaps, so the pitch bound needs
    ``ceil(span / pitch) + 1`` taps, not ``ceil(row_span / pitch)``.
    """
    return max(2, ceil((row_span - TAP_WIDTH_UM) / TAP_MAX_PITCH_UM) + 1)


def build(shorted: bool = False) -> db.Layout:
    layout = db.Layout()
    layout.dbu = DBU
    top_name = "gf180_tmds_pad_v2_shorted" if shorted else "gf180_tmds_pad_v2"
    top = layout.create_cell(top_name)

    L, rect, label = make_drawers(layout, top)

    # -- diode_nd2ps_06v0 clamp + 25x25um bond pad (shared with the ring) ---
    _draw_production_pad(top, L, 0.0, 0.0, "PAD", N_FINGERS)
    array_x0 = 0.0
    margin = 0.16  # PPLUS-over-COMP margin (same convention as the clamp's NPLUS)
    bus_y0 = 0.39 - 0.13  # bottom edge of the clamp's Metal1 bus (DEFAULT_BUS_WIDTH_UM)

    # -- Substrate taps: Pplus-covered Comp outside every Nwell, tied to VSS -
    # One tap per TAP_MAX_PITCH_UM of finger row (DRM DF.14_MV's 15um
    # NCOMP-to-PCOMP reach, issue #422), each contacted and VSS-labelled so
    # the deck's substrate global stays promoted onto a real, verified net.
    row_span = _row_span(max(clamp_rows(N_FINGERS)))
    n_taps = tap_count(row_span)
    tap_y0, tap_y1 = -3.0, -1.0  # >=1.0um clear of the diode array (y=0..FINGER_DEPTH)
    tap_m1_half = 0.31
    bridge_cx = bridge_cy = 0.0  # anchor of the _shorted bridge: the LAST tap
    for i in range(n_taps):
        tap_x0 = array_x0 + i * (row_span - TAP_WIDTH_UM) / (n_taps - 1)
        tap_x1 = tap_x0 + TAP_WIDTH_UM
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
        rect(
            METAL1,
            tap_cx - tap_m1_half,
            tap_cy - tap_m1_half,
            tap_cx + tap_m1_half,
            tap_cy + tap_m1_half,
        )
        label(METAL1_LABEL, "VSS", tap_cx, tap_cy)
        bridge_cx, bridge_cy = tap_cx, tap_cy  # last iteration wins, by intent

    # -- Negative control: short PAD to VSS with one extra Metal1 bridge ----
    # Anchored explicitly on the LAST tap (bridge_cx/cy). Genuinely overlaps
    # (not just edge-touches) both that tap's own Metal1
    # square and the cathode bus -- an edge-touching rect here previously
    # produced a degenerate zero-width DRC violation at the seam.
    if shorted:
        overlap = 0.10
        rect(
            METAL1,
            bridge_cx - tap_m1_half - overlap,
            bridge_cy + tap_m1_half - overlap,
            bridge_cx + tap_m1_half + overlap,
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
