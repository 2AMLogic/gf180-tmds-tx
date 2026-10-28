"""Shared gf180mcu GDS layer table and `_box` helper for the layout generators.

Layer/datatype pairs come from `klayout_tools/decks/gf180mcu.py`
(EXTRACTION_DECK/DECK) and the installed PDK's own `layers_def.py`. This is
the single copy: a layer-number fix lands here once (issue #255).
"""

from __future__ import annotations

try:  # pragma: no cover -- exercised by whichever environment is present
    import klayout.db as db
except ModuleNotFoundError:  # pragma: no cover
    # Importing the layer numbers must work in CI's KLayout-free job; only
    # `_box` needs klayout.db.
    db = None

NWELL = (21, 0)
COMP = (22, 0)
POLY2 = (30, 0)
PPLUS = (31, 0)
NPLUS = (32, 0)
CONTACT = (33, 0)
METAL1 = (34, 0)
METAL1_LABEL = (34, 10)
VIA1 = (35, 0)
METAL2 = (36, 0)
PAD_LAYER = (37, 0)  # passivation/pad-opening marker (geom.drc: grid/angle only)
VIA2 = (38, 0)
VIA3 = (40, 0)
VIA4 = (41, 0)
METAL3 = (42, 0)
METAL4 = (46, 0)
DUALGATE = (55, 0)  # 5V/6V thick-oxide marker -- required by diode_nd2ps_06v0
METAL5 = (81, 0)
METAL5_LABEL = (81, 10)
DIODE_MK = (115, 5)  # junction-diode device-recognition mark

DBU = 0.001  # 1 nm, matches the installed PDK's own GDS files
CONTACT_SIZE = 0.22  # klt's contact.width.1 floor (min-only; max not checked)


def layer_cache(layout):
    """Return `L(spec)`: layer index for a (layer, datatype) pair, created once."""
    layers: dict[tuple[int, int], int] = {}

    def L(spec):
        if spec not in layers:
            layers[spec] = layout.layer(*spec)
        return layers[spec]

    return L


def _box(layout, x0, y0, x1, y1):
    return db.Box(
        db.DPoint(x0, y0).to_itype(layout.dbu),
        db.DPoint(x1, y1).to_itype(layout.dbu),
    )


def make_drawers(layout, top):
    """Return `(L, rect, label)` drawing into cell `top` of `layout`."""
    L = layer_cache(layout)

    def rect(spec, x0, y0, x1, y1):
        top.shapes(L(spec)).insert(_box(layout, x0, y0, x1, y1))

    def label(spec, text, x, y):
        trans = db.DTrans(db.DPoint(x, y))
        top.shapes(L(spec)).insert(db.DText(text, trans))

    return L, rect, label
