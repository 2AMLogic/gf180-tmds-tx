#!/usr/bin/env python3
"""Generate the layout-side `tmds_encoder_shorted` LVS negative control (issue #146).

    python3 layout/scripts/gen_tmds_encoder_shorted.py \\
        --gds layout/gds/tmds_encoder.gds \\
        --def flow/tmds_encoder/pnr/tmds_encoder.def \\
        -o layout/gds/tmds_encoder_shorted.gds

Every other cell in this repo ships its LVS negative control as a real extra
metal bridge drawn into the layout (`gen_pad_v2.py --shorted`,
`cml_driver_core_shorted`, `gf180_tmds_pad_ring_assembly_shorted`;
`layout/README.md`'s "Every LVS signoff is a pair" section) -- `tmds_encoder`
was the one exception (issue #142), because building this control requires
`klt extract --abstract-cells`, and the installed `klt` 0.3.0 mis-bound
abstracted-cell pins on this design (klayout-tools#1366) badly enough that a
layout-side control built on top of it could not be trusted. That upstream
issue is fixed (klayout-tools#1374); this script restores the layout-side
twin now that a `klt` build carrying the fix is available.

**What it draws, and why it is derived rather than hard-coded.** A prior,
uncommitted attempt at this same control (written during #142, discarded
because 0.3.0 could not verify it) hand-picked a bridge rectangle from a
one-time read of the DEF. That is exactly the shape of mistake issue #129
warns about: a bridge whose coordinates silently stop matching the actual
pin geometry (because the DEF, the P&R run, or the pin assignment changed
under it) draws a short that shorts nothing, producing a negative control
that *passes* -- which is worse than shipping no control at all, since it
looks like coverage without being any.

So this script re-derives the bridge every time it runs, from the routed
DEF's own `PINS` block, and refuses to draw anything if its assumptions no
longer hold:

  * `ctrl[0]` and `data[3]` (both top-level `DIRECTION INPUT` pins, logically
    unrelated to each other) must both still exist in the DEF, on the same
    metal layer, and that layer name must resolve to a real drawn shape on
    the committed GDS at the DEF-implied location (cross-checked against the
    actual layout, not assumed from a layer-name/GDS-layer table).
  * They must be laterally **adjacent** on that layer's pin row -- no third
    pin's geometry may fall between them in x. A bridge spanning three pins
    would short more nets than the two named ones and misrepresent what the
    control tests.
  * Both pins' geometry must share one y-range (i.e. sit on the same pin
    "row"), which is what makes a single rectangle bridge both.

Any of those failing raises `ShortGeometryError` rather than silently
drawing a no-op or wrong bridge.

The bridge itself is one `Metal4` rectangle spanning the union of both pins'
bounding boxes -- deliberately wider than either pin alone (rather than a
minimal stub between them) so the short is robust to the exact pin shape:
it fully overlaps both pins' drawn metal, guaranteeing a real electrical
short under `klt extract`, not just a geometric near-miss.

This does not re-run place-and-route or re-merge the DEF into GDS -- it
loads the already-committed, already-verified `tmds_encoder.gds` and adds
one shape plus a top-cell rename. The DEF is read only for pin geometry
(coordinates in the same DBU grid the GDS itself uses -- both are 0.0005 um,
i.e. `UNITS DISTANCE MICRONS 2000` -- confirmed empirically against the
committed GDS's own pin shapes below, not merely assumed from the header).
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover -- exercised by whichever environment is present
    import klayout.db as db
except ModuleNotFoundError:  # pragma: no cover
    # `parse_def_pins` and `compute_bridge` below are pure stdlib and are the
    # load-bearing "derive from the DEF, fail loudly" claim this generator
    # makes -- unit-tested in layout/tests/, which runs in CI's deliberately
    # PDK-free, KLayout-free job (see .github/workflows/ci.yml and
    # pad_pitch_fit_study.py's own use of this same pattern). Only
    # `_gds_layer_at`/`build` need klayout.db, and they say so with a clean
    # error rather than an import traceback.
    db = None

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEF = REPO_ROOT / "flow" / "tmds_encoder" / "pnr" / "tmds_encoder.def"
DEFAULT_GDS = REPO_ROOT / "layout" / "gds" / "tmds_encoder.gds"
DEFAULT_OUTPUT = REPO_ROOT / "layout" / "gds" / "tmds_encoder_shorted.gds"

BRIDGE_PIN_A = "ctrl[0]"
BRIDGE_PIN_B = "data[3]"
SHORTED_TOP_NAME = "tmds_encoder_shorted"

# klt's curated gf180mcu deck's own GDS layer/datatype for drawn Metal4
# (klayout_tools/decks/gf180mcu.py -- same convention gen_pad_v2.py's own
# layer table already documents). Used only as the *expected* pair to check
# the DEF's "Metal4" layer name against; the bridge's actual (layer,
# datatype) is re-derived by finding real drawn shapes at the DEF-implied
# pin locations in the committed GDS (see `_gds_layer_at`), not assumed from
# this table alone.
EXPECTED_METAL4_GDS_LAYER = (46, 0)


class ShortGeometryError(RuntimeError):
    """Raised when the DEF/GDS no longer support a trustworthy short.

    Deliberately loud: a caught-and-ignored version of this exception is
    exactly the #129 failure mode (a negative control that quietly stops
    testing anything and reports a false `match`).
    """


@dataclass(frozen=True)
class DefPin:
    name: str
    net: str
    direction: str
    layer: str
    # Absolute DEF-DBU bounding box (x0, y0, x1, y1).
    bbox: tuple[int, int, int, int]


_PIN_ENTRY_RE = re.compile(
    r"-\s+(?P<name>\S+)\s+\+\s+NET\s+(?P<net>\S+)"
    r"(?P<body>.*?)"
    r"(?=\n\s*-\s+\S+\s+\+\s+NET|\Z)",
    re.DOTALL,
)
_DIRECTION_RE = re.compile(r"\+\s+DIRECTION\s+(\S+)")
_LAYER_RE = re.compile(
    r"\+\s*LAYER\s+(?P<layer>\S+)\s*\(\s*(?P<x0>-?\d+)\s+(?P<y0>-?\d+)\s*\)\s*"
    r"\(\s*(?P<x1>-?\d+)\s+(?P<y1>-?\d+)\s*\)"
)
_PLACEMENT_RE = re.compile(
    r"\+\s*(?:FIXED|PLACED|COVER)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\S+)\s*;"
)


def parse_def_pins(def_text: str) -> dict[str, DefPin]:
    """Parse the DEF's `PINS ... END PINS` block into per-pin geometry.

    Only the first `LAYER` entry per pin is used (every signal pin in this
    design's `PINS` block has exactly one `PORT`/`LAYER` entry; the two
    power pins have two, for two straps -- neither `BRIDGE_PIN_A` nor
    `BRIDGE_PIN_B` is a power pin, so this is not exercised for them, but is
    documented rather than silently wrong if that ever changes).
    """
    match = re.search(r"^PINS\s+\d+\s*;(.*?)^END PINS", def_text, re.DOTALL | re.MULTILINE)
    if not match:
        raise ShortGeometryError("could not find a 'PINS ... END PINS' block in the DEF")
    body = match.group(1)

    pins: dict[str, DefPin] = {}
    for entry in _PIN_ENTRY_RE.finditer(body):
        name = entry.group("name")
        net = entry.group("net")
        entry_body = entry.group("body")

        direction_m = _DIRECTION_RE.search(entry_body)
        direction = direction_m.group(1) if direction_m else ""

        layer_m = _LAYER_RE.search(entry_body)
        placement_m = _PLACEMENT_RE.search(entry_body)
        if layer_m is None or placement_m is None:
            # Pins with no PORT/LAYER (shouldn't occur in this design) are
            # simply not usable as short endpoints -- skip rather than fail,
            # since neither BRIDGE_PIN_A/B is expected to hit this.
            continue

        layer = layer_m.group("layer")
        rel_x0, rel_y0 = int(layer_m.group("x0")), int(layer_m.group("y0"))
        rel_x1, rel_y1 = int(layer_m.group("x1")), int(layer_m.group("y1"))
        origin_x, origin_y = int(placement_m.group(1)), int(placement_m.group(2))
        orient = placement_m.group(3)
        if orient != "N":
            raise ShortGeometryError(
                f"pin {name!r} has orientation {orient!r}, not 'N' -- this script's "
                "relative-offset-to-absolute-bbox math assumes north (unrotated) "
                "placement, which every pin in this design currently has; refusing "
                "to silently mis-place the bridge under an orientation it was never "
                "checked against"
            )

        bbox = (
            origin_x + rel_x0,
            origin_y + rel_y0,
            origin_x + rel_x1,
            origin_y + rel_y1,
        )
        pins[name] = DefPin(name=name, net=net, direction=direction, layer=layer, bbox=bbox)

    return pins


def _gds_layer_at(top: db.Cell, dbu: float, bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    """Return the single (layer, datatype) pair with real drawn metal fully
    covering `bbox` in the committed GDS, cross-validating the DEF-derived
    pin location against the actual layout rather than trusting the DEF's
    layer *name* alone.
    """
    layout = top.layout()
    query = db.Box(bbox[0], bbox[1], bbox[2], bbox[3])
    candidates: set[tuple[int, int]] = set()
    for layer_index in layout.layer_indexes():
        info = layout.get_info(layer_index)
        for shape in top.shapes(layer_index).each_overlapping(query):
            shape_bbox = shape.bbox()
            if (shape_bbox & query) == query:
                candidates.add((info.layer, info.datatype))
    # Text/pin-label datatypes (e.g. Metal4's "10") also live on nearby
    # layer numbers but never *contain* the full pin rectangle (they are
    # zero-area label points) -- filtering by full containment above already
    # excludes them, so no separate datatype-10 exclusion is needed. But
    # guard the "more than one real metal candidate" case explicitly rather
    # than picking arbitrarily.
    if not candidates:
        raise ShortGeometryError(
            f"no drawn GDS shape fully covers the DEF-implied pin box {bbox} -- "
            "the DEF and the committed GDS have diverged; refusing to draw a "
            "bridge whose endpoints may not land on real metal"
        )
    if len(candidates) > 1:
        raise ShortGeometryError(
            f"ambiguous GDS layer at pin box {bbox}: candidates {sorted(candidates)} -- "
            "expected exactly one real-metal layer/datatype pair"
        )
    return candidates.pop()


def compute_bridge(
    pins: dict[str, DefPin],
    pin_a_name: str = BRIDGE_PIN_A,
    pin_b_name: str = BRIDGE_PIN_B,
) -> tuple[tuple[int, int, int, int], DefPin, DefPin]:
    """Derive the bridge rectangle (absolute DEF/GDS DBU) from the DEF's own
    pin geometry, failing loudly if any of this script's structural
    assumptions about the two named pins no longer hold.
    """
    if pin_a_name not in pins or pin_b_name not in pins:
        missing = [n for n in (pin_a_name, pin_b_name) if n not in pins]
        raise ShortGeometryError(f"pin(s) not found in DEF PINS block: {missing}")

    pin_a, pin_b = pins[pin_a_name], pins[pin_b_name]

    for pin in (pin_a, pin_b):
        if pin.direction != "INPUT":
            raise ShortGeometryError(
                f"pin {pin.name!r} has DIRECTION {pin.direction!r}, expected INPUT -- "
                "this control is written for two input pins; shorting a different "
                "pin-type mix changes what it tests and is not silently substituted"
            )

    if pin_a.layer != pin_b.layer:
        raise ShortGeometryError(
            f"{pin_a.name!r} is on layer {pin_a.layer!r} but {pin_b.name!r} is on "
            f"layer {pin_b.layer!r} -- expected the same layer so one rectangle "
            "can bridge both"
        )

    # Row alignment: both pins' y-range must match exactly, or a single
    # rectangle cannot cleanly cover both without also touching unrelated
    # geometry above/below the row.
    if (pin_a.bbox[1], pin_a.bbox[3]) != (pin_b.bbox[1], pin_b.bbox[3]):
        raise ShortGeometryError(
            f"{pin_a.name!r} y-range {pin_a.bbox[1], pin_a.bbox[3]} does not match "
            f"{pin_b.name!r} y-range {pin_b.bbox[1], pin_b.bbox[3]} -- pins are no "
            "longer on the same row"
        )

    # Adjacency: no third pin on the same layer/row may have any x-extent
    # inside the open interval between the two pins' facing edges.
    left, right = sorted((pin_a, pin_b), key=lambda p: p.bbox[0])
    gap_lo, gap_hi = left.bbox[2], right.bbox[0]
    if gap_lo >= gap_hi:
        raise ShortGeometryError(
            f"{pin_a.name!r} and {pin_b.name!r} overlap or touch in x "
            f"({left.name}: {left.bbox}, {right.name}: {right.bbox}) -- expected a "
            "gap between two genuinely separate pins"
        )
    same_row = [
        p
        for p in pins.values()
        if p.name not in (pin_a.name, pin_b.name)
        and p.layer == pin_a.layer
        and (p.bbox[1], p.bbox[3]) == (pin_a.bbox[1], pin_a.bbox[3])
    ]
    intruders = [p for p in same_row if p.bbox[0] < gap_hi and p.bbox[2] > gap_lo]
    if intruders:
        raise ShortGeometryError(
            f"{[p.name for p in intruders]} lie between {pin_a.name!r} and "
            f"{pin_b.name!r} -- they are no longer adjacent, so a single bridge "
            "rectangle spanning both would also short the intervening pin(s)"
        )

    bridge_bbox = (
        min(pin_a.bbox[0], pin_b.bbox[0]),
        min(pin_a.bbox[1], pin_b.bbox[1]),
        max(pin_a.bbox[2], pin_b.bbox[2]),
        max(pin_a.bbox[3], pin_b.bbox[3]),
    )
    return bridge_bbox, pin_a, pin_b


def build(def_path: Path, gds_path: Path) -> db.Layout:
    if db is None:
        raise ModuleNotFoundError(
            "drawing the shorted GDS needs the `klayout` PyPI package "
            "(klayout.db); `parse_def_pins`/`compute_bridge` alone do not"
        )

    def_text = def_path.read_text()
    pins = parse_def_pins(def_text)
    bridge_bbox, pin_a, pin_b = compute_bridge(pins)

    layout = db.Layout()
    layout.read(str(gds_path))
    top = layout.top_cell()

    layer_a = _gds_layer_at(top, layout.dbu, pin_a.bbox)
    layer_b = _gds_layer_at(top, layout.dbu, pin_b.bbox)
    if layer_a != layer_b:
        raise ShortGeometryError(
            f"{pin_a.name!r} resolves to GDS layer {layer_a} but {pin_b.name!r} "
            f"resolves to {layer_b} -- expected one shared bridge layer"
        )
    if layer_a != EXPECTED_METAL4_GDS_LAYER:
        raise ShortGeometryError(
            f"pins resolved to GDS layer {layer_a}, expected the deck's Metal4 "
            f"{EXPECTED_METAL4_GDS_LAYER} -- the pin layer assignment has changed "
            "since this script's assumptions were written"
        )

    layer_index = layout.layer(*layer_a)
    top.shapes(layer_index).insert(db.Box(*bridge_bbox))
    top.name = SHORTED_TOP_NAME

    return layout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--def", dest="def_path", type=Path, default=DEFAULT_DEF)
    ap.add_argument("--gds", dest="gds_path", type=Path, default=DEFAULT_GDS)
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    layout = build(args.def_path, args.gds_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(args.output))
    print(f"wrote {args.output} (top cell {SHORTED_TOP_NAME!r})")


if __name__ == "__main__":
    main()
