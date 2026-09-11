#!/usr/bin/env python3
"""Generate the DR-0003 custom final 2:1 (DDR) multiplexer cell (issue #177),
laid out from the sized schematic `design/tmds_final_mux.sch` /
`design/netlist/tmds_final_mux.spice` (issue #159, with issue #169's
`RLP`/`RLN` `r_length=5.90u` widening already in the committed netlist).

Shaped like `layout/scripts/gen_cml_driver_core.py` (issue #22): every device
is drawn by a `klt gen` analog primitive generator invoked as a subprocess,
and the blocks are placed and wired by `klt gen-compose`. Nothing is drawn by
hand here except the one merge step "Two routing layers, two compose passes"
below explains.

Device mapping (`design/netlist/tmds_final_mux.spice`). Every `nfet_03v3` in
this cell has the same 2 um/finger unit cell `design/cml-driver-sizing.md`
section 1.3 established for the driver, so each device is one
`klt gen mos_array` unit (`rows=1, cols=1`, `gate_contact=True` for a real
strapped source-rail/drain-rail/gate-comb device, `finger_topology="parallel"`
so the fingers are one folded device rather than a series chain) with
`fingers = nf * m` and `w_um = 2.0`:

  MU0P/MU0N/MU1P/MU1N  nf=64        W=128u L=0.28u  -> fingers=64,  l_um=0.28
  MCP/MCN              nf=96        W=192u L=0.28u  -> fingers=96,  l_um=0.28
  MT  (tail, m=20)     nf=10, m=20  W=400u L=0.5u   -> fingers=200, l_um=0.5
  MB  (bias ref, m=1)  nf=10, m=1   W=20u  L=0.5u   -> fingers=10,  l_um=0.5

**`MT`'s `m=20` is drawn as ONE 200-finger strapped array, not 20 composed
units.** Two reasons, in order: (1) it is what `cml_driver_core` already does
for the identical device (`gen_cml_driver_core.py`'s `mt` entry, `fingers=200`)
and this cell's `MT`/`MB` pair is deliberately the same 1:20 mirror geometry
(`design/tmds-final-mux-sizing.md` section 0), so drawing it differently here
would make the two cells' tail devices incomparable for no gain; (2) `klt
lvs`'s `options.combine_devices` folds a strapped array's per-finger extraction
back into the single `W=400u` device the reference netlist states either way,
so 20 separately-placed units would add 19 more blocks, 19 more source/drain/
gate routes, and 19 more chances to short a rail — all to reach the same
extracted device. The multiplicity is a netlist spelling of total width, not a
drawn-matching requirement: nothing in `design/tmds-final-mux-sizing.md` asks
for a common-centroid tail.

Every `ppolyf_u` resistor is one `klt gen res_array` unit (`num=1, dummy=0`,
`flavor="generic"`, which is the flavour that resolves to `ppolyf_u` on
gf180mcu per `klt gen --list`; the high-sheet-rho `ppolyf_u_1k` flavours are a
different device this cell does not use). `r_width`/`r_length` map directly
onto `width_um`/`length_um`:

  RC        r_width=20u  r_length=2.65u  -> 46.375 ohm
  RLP/RLN   r_width=20u  r_length=5.90u  -> 103.25 ohm
  RREF      r_width=2u   r_length=24.8u  -> 4340 ohm

Those three numbers are not this file's arithmetic — `klt extract --deck
gf180mcu` reports exactly `r_ohm: 46.375 / 103.25 / 4340.0` for the three
generated cells, matching `design/tmds-final-mux-sizing.md` section 2's own
`rsh = 350 ohm/sq` table entry for entry. The sibling repo `gf180-rcosc`'s
`layout/build_cells.py` is the in-fleet precedent for `res_array` on gf180mcu;
neither quirk it documents applies here: its `patch_high_sheet_resistors()`
workaround (klayout-tools#1550) is for the `ppolyf_u_1k` flavour, which
`res_array` now selects natively through `params.flavor`, and its 219 nm
end-contact quirk (klayout-tools#1551) reproduces only at a body length on an
exact half-nanometre grid tie — none of this cell's three lengths is, and all
three generated resistor cells are `klt drc` clean standalone.

Two routing layers, two compose passes
--------------------------------------
**This cell cannot be routed on one metal layer, and that is a property of the
netlist, not of the floorplan.** Take the nets as vertices and each device as
an edge between the nets it joins: `OUTP`/`OUTN`/`TAIL` on one side and
`SA`/`SB`/`TOP` on the other are pairwise connected --- `MU0P`/`MU1P`/`RLP`,
`MU0N`/`MU1N`/`RLN`, `MCP`/`MCN`, and (through `MT`'s gate, `RREF`, and `RC`)
the path `TAIL`-`IBIAS`-`VDD`-`TOP`. That is a K3,3 subdivision, so by
Kuratowski the net graph is non-planar and no single-layer placement of these
twelve blocks can avoid a crossing.

`klt gen-compose` resolves exactly one `routing.layer_role` for a whole
composition (`routing.cross_block_layer_role` is a per-leg fallback for
same-block self-nets only), so one call cannot draw this cell. This generator
therefore runs `klt gen-compose` twice over the *same* twelve blocks at the
*same* explicit origins:

  pass 1  `layer_role="metal"`   (Metal1) -- VDD, TOP, OUTP, OUTN, SA, SB,
                                 TAIL, VSS, plus the six gate `pins[]` labels.
                                 These eight nets are planar once IBIAS is
                                 removed, and the floorplan below realises
                                 that embedding.
  pass 2  `layer_role="metal2"`  (Metal2, via-dropping to each pin's own
                                 Metal1 pad through Via1) -- IBIAS alone,
                                 which is exactly the edge whose removal makes
                                 the rest planar.

and then copies pass 2's *top-cell own shapes* (its Metal2 backbone, Via1
drops, Metal1 landing pads and net label -- the placed blocks are sub-cell
instances and are deliberately not copied) into pass 1's output. Each pass
keeps every one of `klt gen-compose`'s routability checks for its own nets;
what no pass checks is a pass-1 route against a pass-2 route, which is the
whole point: they are on different layers and cannot short. `klt drc` and
`klt lvs` remain the authority on both.

Filed generically per this repo's CLAUDE.md friction protocol as
[klayout-tools#1655](https://github.com/2AMLogic/klayout-tools/issues/1655)
(no per-net/per-leg routing layer, so a non-planar netlist needs N calls plus
a caller-side merge) and
[klayout-tools#1656](https://github.com/2AMLogic/klayout-tools/issues/1656)
(the obstacle-overlap check is layer-agnostic: a `metal2` backbone is rejected
for crossing a block that draws no metal2 and cannot short to it).

Floorplan (the planar embedding, bottom to top)
-----------------------------------------------
The eight Metal1 nets embed as a ring: the four `MU*` devices form a cycle
`OUTP`-`MU0P`-`SA`-`MU0N`-`OUTN`-`MU1N`-`SB`-`MU1P`-`OUTP` around the middle
channel, with `OUTP` as the ring's west side and `OUTN` as its east side.
`TAIL`/`VSS` and their devices live *inside* that ring (the middle channel);
`TOP`/`VDD` and the load/reference resistors live *outside* it (above). Each
`MU*`/`MCN` block on the west or centre column is `mirror_x`-oriented so the
node it shares with its partner faces the centre gap and the node that leaves
the row faces outward.

  row D  RC | RREF               VDD between them, TOP up from RC
  row C  RLP | RLN               OUTP/OUTN at their outer ends, TOP inward
  row B  MU1P | MU1N             SB in the centre gap
  ------ middle channel (inside the ring) ------
         MCN                     SB up, TAIL out east
         MT                      TAIL east, VSS west, IBIAS gate (Metal2)
         MB                      VSS west, IBIAS gate+drain (Metal2)
         MCP                     SA down, TAIL out west
  row A  MU0P | MU0N             SA in the centre gap

West-corridor column order is forced and worth recording: `OUTP` (outermost),
then `TAIL`, then `VSS` (innermost). `TAIL`'s stub out of `MCP` would cross an
`OUTP` trunk placed east of it, and `VSS`'s two stubs out of `MT`/`MB` would
cross a `TAIL` trunk placed east of *them*. That ordering is what makes the
`_shorted` twin's `OUTP`-to-`VSS` bridge a Metal2 jumper (below) rather than a
Metal1 one: `TAIL` sits physically between the two nets it would have to join.

Two cells are written (the pair `layout/README.md`'s "Every LVS signoff is a
pair" section requires):

- ``tmds_final_mux``          -- the real candidate.
- ``tmds_final_mux_shorted``  -- the LVS negative control: identical geometry
  plus one extra Metal2 jumper joining `RLP`'s `OUTP` terminal to `MB`'s `VSS`
  terminal, i.e. `OUTP` bridged to `VSS` (a `net.merged` defect). Must FAIL
  `klt lvs` against the same reference netlist the intact cell passes.

Requires `klt` (klayout-tools) on `$PATH`, a resolvable gf180mcu PDK install
(`klt pdk find --pdk gf180mcuD`), and -- for the one merge step above -- the
`klayout` Python module, imported lazily so `layout/tests/` can import this
module with neither (the same convention `gen_pad_ring_assembly.py` follows).
`DEFAULT_PDK` is `gf180mcuD` per DR-0010 (`spec/decisions/0010-pdk-variant.md`,
issue #9, as amended by issue #127).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_PDK = "gf180mcuD"  # DR-0010 -- see module docstring

# ---------------------------------------------------------------------------
# Device sizing (design/netlist/tmds_final_mux.spice).
# ---------------------------------------------------------------------------
W_UM = 2.0  # per-finger width (um), shared by every nfet_03v3 in this cell

MOS_DEVICES: dict[str, dict[str, Any]] = {
    "mu0p": {"fingers": 64, "l_um": 0.28},  # W=128u L=0.28u nf=64
    "mu0n": {"fingers": 64, "l_um": 0.28},
    "mu1p": {"fingers": 64, "l_um": 0.28},
    "mu1n": {"fingers": 64, "l_um": 0.28},
    "mcp": {"fingers": 96, "l_um": 0.28},  # W=192u L=0.28u nf=96
    "mcn": {"fingers": 96, "l_um": 0.28},
    "mt": {"fingers": 200, "l_um": 0.5},  # W=20u nf=10 m=20 -> 400u total
    "mb": {"fingers": 10, "l_um": 0.5},  # W=20u nf=10 m=1
}

RES_DEVICES: dict[str, dict[str, Any]] = {
    "rc": {"length_um": 2.65, "width_um": 20.0},  # 46.375 ohm
    "rlp": {"length_um": 5.90, "width_um": 20.0},  # 103.25 ohm
    "rln": {"length_um": 5.90, "width_um": 20.0},
    "rref": {"length_um": 24.8, "width_um": 2.0},  # 4340 ohm
}

BLOCK_ORDER = (
    "mu0p",
    "mu0n",
    "mcp",
    "mb",
    "mt",
    "mcn",
    "mu1p",
    "mu1n",
    "rlp",
    "rln",
    "rc",
    "rref",
)

# ---------------------------------------------------------------------------
# Floorplan. Each entry is (orientation, x_left_um, y_bottom_um) -- the block's
# desired composed-frame lower-left corner, from which the `placement.origins_um`
# offset gen-compose actually wants is derived (`_origins`), so the numbers here
# read as the floorplan rather than as offsets into each block's own local bbox.
# ---------------------------------------------------------------------------
ROW_A_Y = 0.0  # MU0P | MU0N          (bottom of the ring)
MCP_Y = 14.46  # middle channel, bottom
MB_Y = 28.92
MT_Y = 43.38
MCN_Y = 59.84  # middle channel, top
ROW_B_Y = 74.30  # MU1P | MU1N        (top of the ring)
ROW_C_Y = 88.76  # RLP | RLN
ROW_D_Y = 118.76  # RC
RREF_Y = ROW_D_Y + 9.0  # RREF is 2 um tall; +9 puts its port on RC's port row

COL_P_X = 32.5  # west (P-side) MU column, left edge
COL_N_X = 128.46  # east (N-side) MU column, left edge

PLACEMENT: dict[str, tuple[str, float, float]] = {
    "mu0p": ("mirror_x", COL_P_X, ROW_A_Y),
    "mu0n": ("none", COL_N_X, ROW_A_Y),
    "mcp": ("none", 24.52, MCP_Y),
    "mb": ("none", 0.0, MB_Y),
    "mt": ("none", 0.0, MT_Y),
    "mcn": ("mirror_x", 109.0, MCN_Y),
    "mu1p": ("mirror_x", COL_P_X, ROW_B_Y),
    "mu1n": ("none", COL_N_X, ROW_B_Y),
    "rlp": ("none", COL_P_X, ROW_C_Y),
    "rln": ("none", 177.68, ROW_C_Y),
    "rc": ("none", 105.0, ROW_D_Y),
    "rref": ("none", 115.0, RREF_Y),
}

# Routing columns (um). West corridor order is forced: OUTP outermost, then
# TAIL, then VSS innermost -- see the module docstring.
X_OUTP = -10.0  # OUTP trunk, west corridor
X_TAIL_W = -7.0  # TAIL's climb out of MCP, west corridor
X_VSS = -4.0  # VSS between MT and MB, west corridor
X_SB = 102.0  # SB's climb from MCN into row B's centre gap
X_SA = 115.0  # SA's descent from MCP into row A's centre gap
X_TAIL_E = 225.0  # TAIL's descent from MCN onto MT's drain, east of MT
X_OUTN = 235.0  # OUTN trunk, east corridor
X_TOP_W = 45.0  # TOP's climb out of RLP
X_TOP_E = 170.0  # TOP's climb out of RLN
X_TOP_RC = 100.0  # TOP's descent onto RC's west terminal

# Routing tracks (um).
Y_TAIL = 54.0  # TAIL's trunk, in the MT/MCN gap
Y_TOP = 113.0  # TOP's trunk, in the row C/row D gap

# Metal2 (pass 2) columns and tracks.
X_IBIAS_E = 250.0  # east of every block
X_IBIAS_W = -20.0  # west of every block and every Metal1 route
X_IBIAS_MB = 18.0  # east of MB, west of nothing
Y_IBIAS_MT = 51.0  # MT/MCN gap
Y_IBIAS_MB = 38.0  # MB/MT gap
X_SHORT = -25.0  # _shorted twin's Metal2 OUTP->VSS jumper

ROUTE_WIDTH_UM = 0.3  # clears gf180mcu metal1.width.1 (0.23 um) with margin
ROUTE_WIDTH_M2_UM = 0.4  # clears metal2.width.1 with margin

# Layers copied out of pass 2's top cell (see `_merge_top_shapes`): everything
# it drew. Restricting by layer would silently drop a layer a future klt build
# adds to a via-drop ladder, so the copy is unconditional and the *cell* (own
# shapes only, no instances) is what bounds it.


def _run(cmd: list[str], ok: tuple[int, ...] = (0,)) -> dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in ok:
        sys.stderr.write(proc.stderr)
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


def _gen_mos(klt: str, pdk: str, work: Path, bid: str) -> dict[str, Any]:
    dev = MOS_DEVICES[bid]
    params = {
        "w_um": W_UM,
        "l_um": dev["l_um"],
        "fingers": dev["fingers"],
        "finger_topology": "parallel",
        "rows": 1,
        "cols": 1,
        "dummy": 0,
        "gate_contact": True,
    }
    return _run(
        [
            klt, "gen", "mos_array", "--pdk", pdk,
            "--params", json.dumps(params),
            "--cell-name", f"{bid}_unit",
            "-o", str(work / f"{bid}.gds"),
            "--format", "json",
        ]
    )


def _gen_res(klt: str, pdk: str, work: Path, bid: str) -> dict[str, Any]:
    dev = RES_DEVICES[bid]
    params = {
        "length_um": dev["length_um"],
        "width_um": dev["width_um"],
        "num": 1,
        "dummy": 0,
        "flavor": "generic",  # -> ppolyf_u on gf180mcu
    }
    return _run(
        [
            klt, "gen", "res_array", "--pdk", pdk,
            "--params", json.dumps(params),
            "--cell-name", f"{bid}_unit",
            "-o", str(work / f"{bid}.gds"),
            "--format", "json",
        ]
    )


def generate_blocks(klt: str, pdk: str, work: Path) -> dict[str, dict[str, Any]]:
    """Run one `klt gen` per schematic device and return the reports by id."""
    reports: dict[str, dict[str, Any]] = {}
    for bid in BLOCK_ORDER:
        report = _gen_mos(klt, pdk, work, bid) if bid in MOS_DEVICES else _gen_res(klt, pdk, work, bid)
        (work / f"{bid}.json").write_text(json.dumps(report))
        reports[bid] = report
    return reports


def _origins(reports: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Translate the floorplan's desired lower-left corners into the
    `placement.origins_um` offsets `klt gen-compose` applies to each block's
    own (orientation-transformed) bbox."""
    out: dict[str, dict[str, float]] = {}
    for bid, (orient, x_left, y_bot) in PLACEMENT.items():
        bbox = reports[bid]["bbox_um"]
        if orient == "mirror_x":
            ox = x_left + bbox["x1"]  # mirrored bbox is [-x1, -x0]
        elif orient == "none":
            ox = x_left - bbox["x0"]
        else:  # pragma: no cover - no other orientation is used by this cell
            raise ValueError(f"unsupported orientation {orient!r}")
        out[bid] = {"x": ox, "y": y_bot - bbox["y0"]}
    return out


def port_xy(
    reports: dict[str, dict[str, Any]], origins: dict[str, dict[str, float]], bid: str, port: str
) -> tuple[float, float]:
    """Composed-frame position of one block port, orientation included."""
    orient = PLACEMENT[bid][0]
    for p in reports[bid]["ports"]:
        if p["name"] == port:
            x = -p["x_um"] if orient == "mirror_x" else p["x_um"]
            return (x + origins[bid]["x"], p["y_um"] + origins[bid]["y"])
    raise KeyError(f"{bid} has no port {port!r}")


def _pin(bid: str, port: str) -> dict[str, str]:
    return {"block": bid, "port": port}


def _leg(a: tuple[str, str], b: tuple[str, str], waypoints: list[list[float]] | None = None) -> dict[str, Any]:
    leg: dict[str, Any] = {"from_pin": _pin(*a), "to_pin": _pin(*b)}
    if waypoints is not None:
        leg["waypoints_um"] = waypoints
    return leg


def metal1_connectivity(
    reports: dict[str, dict[str, Any]], origins: dict[str, dict[str, float]], shorted: bool
) -> list[dict[str, Any]]:
    """The eight Metal1 nets, with every leg's path stated explicitly.

    Nothing here is left to the router's nearest-first spanning tree: each net
    declares its own `legs[]` so the drawn geometry is the floorplan's own
    planar embedding rather than whatever the search happens to find.
    """
    p = lambda bid, port: port_xy(reports, origins, bid, port)  # noqa: E731

    mu0p_d = p("mu0p", "U0_D")
    mu1p_d = p("mu1p", "U0_D")
    rlp_a = p("rlp", "R0_A")
    mu0n_d = p("mu0n", "U0_D")
    mu1n_d = p("mu1n", "U0_D")
    rln_b = p("rln", "R0_B")
    mu0p_s = p("mu0p", "U0_S")
    mu0n_s = p("mu0n", "U0_S")
    mcp_d = p("mcp", "U0_D")
    mu1p_s = p("mu1p", "U0_S")
    mu1n_s = p("mu1n", "U0_S")
    mcn_d = p("mcn", "U0_D")
    mcp_s = p("mcp", "U0_S")
    mcn_s = p("mcn", "U0_S")
    mt_d = p("mt", "U0_D")
    mt_s = p("mt", "U0_S")
    mb_s = p("mb", "U0_S")
    rlp_b = p("rlp", "R0_B")
    rln_a = p("rln", "R0_A")
    rc_a = p("rc", "R0_A")
    rc_b = p("rc", "R0_B")
    rref_a = p("rref", "R0_A")

    outp = {
        "net": "OUTP",
        "pins": [_pin("mu0p", "U0_D"), _pin("mu1p", "U0_D"), _pin("rlp", "R0_A")],
        "legs": [
            _leg(("mu0p", "U0_D"), ("mu1p", "U0_D"), [[X_OUTP, mu0p_d[1]], [X_OUTP, mu1p_d[1]]]),
            _leg(("mu1p", "U0_D"), ("rlp", "R0_A"), [[X_OUTP, mu1p_d[1]], [X_OUTP, rlp_a[1]]]),
        ],
    }

    vss_pins = [_pin("mt", "U0_S"), _pin("mb", "U0_S")]
    vss_legs = [_leg(("mt", "U0_S"), ("mb", "U0_S"), [[X_VSS, mt_s[1]], [X_VSS, mb_s[1]]])]

    nets: list[dict[str, Any]] = [
        outp,
        {
            "net": "OUTN",
            "pins": [_pin("mu0n", "U0_D"), _pin("mu1n", "U0_D"), _pin("rln", "R0_B")],
            "legs": [
                _leg(("mu0n", "U0_D"), ("mu1n", "U0_D"), [[X_OUTN, mu0n_d[1]], [X_OUTN, mu1n_d[1]]]),
                _leg(("mu1n", "U0_D"), ("rln", "R0_B"), [[X_OUTN, mu1n_d[1]], [X_OUTN, rln_b[1]]]),
            ],
        },
        {
            "net": "SA",
            "pins": [_pin("mu0p", "U0_S"), _pin("mu0n", "U0_S"), _pin("mcp", "U0_D")],
            "legs": [
                _leg(("mu0p", "U0_S"), ("mu0n", "U0_S")),
                _leg(("mcp", "U0_D"), ("mu0n", "U0_S"), [[X_SA, mcp_d[1]], [X_SA, mu0n_s[1]]]),
            ],
        },
        {
            "net": "SB",
            "pins": [_pin("mu1p", "U0_S"), _pin("mu1n", "U0_S"), _pin("mcn", "U0_D")],
            "legs": [
                _leg(("mu1p", "U0_S"), ("mu1n", "U0_S")),
                _leg(("mcn", "U0_D"), ("mu1p", "U0_S"), [[X_SB, mcn_d[1]], [X_SB, mu1p_s[1]]]),
            ],
        },
        {
            "net": "TAIL",
            "pins": [_pin("mcp", "U0_S"), _pin("mcn", "U0_S"), _pin("mt", "U0_D")],
            "legs": [
                _leg(("mcn", "U0_S"), ("mt", "U0_D"), [[X_TAIL_E, mcn_s[1]], [X_TAIL_E, mt_d[1]]]),
                _leg(
                    ("mcp", "U0_S"),
                    ("mt", "U0_D"),
                    [
                        [X_TAIL_W, mcp_s[1]],
                        [X_TAIL_W, Y_TAIL],
                        [X_TAIL_E, Y_TAIL],
                        [X_TAIL_E, mt_d[1]],
                    ],
                ),
            ],
        },
        {"net": "VSS", "pins": vss_pins, "legs": vss_legs},
        {
            "net": "TOP",
            "pins": [_pin("rlp", "R0_B"), _pin("rln", "R0_A"), _pin("rc", "R0_A")],
            "legs": [
                _leg(
                    ("rlp", "R0_B"),
                    ("rc", "R0_A"),
                    [
                        [X_TOP_W, rlp_b[1]],
                        [X_TOP_W, Y_TOP],
                        [X_TOP_RC, Y_TOP],
                        [X_TOP_RC, rc_a[1]],
                    ],
                ),
                _leg(
                    ("rln", "R0_A"),
                    ("rc", "R0_A"),
                    [
                        [X_TOP_E, rln_a[1]],
                        [X_TOP_E, Y_TOP],
                        [X_TOP_RC, Y_TOP],
                        [X_TOP_RC, rc_a[1]],
                    ],
                ),
            ],
        },
        {
            "net": "VDD",
            "pins": [_pin("rc", "R0_B"), _pin("rref", "R0_A")],
        },
    ]
    # rc_b/rref_a are read only to assert the VDD pair really is a facing pair
    # on one row -- a floorplan edit that broke it would otherwise show up as a
    # routing failure with no explanation.
    assert abs(rc_b[1] - rref_a[1]) < 1e-9, "VDD's two terminals must share a row"
    assert rc_b[0] < rref_a[0], "RC must sit west of RREF"
    del mu0p_s, mu1n_s, mt_d  # positions used only via the leg lists above
    return nets


def metal2_connectivity(
    reports: dict[str, dict[str, Any]], origins: dict[str, dict[str, float]], shorted: bool
) -> list[dict[str, Any]]:
    """IBIAS (always) plus, for the negative control, the OUTP->VSS jumper."""
    p = lambda bid, port: port_xy(reports, origins, bid, port)  # noqa: E731
    rref_b = p("rref", "R0_B")
    mt_g = p("mt", "U0_G")
    mb_g = p("mb", "U0_G")
    mb_d = p("mb", "U0_D")
    rlp_a = p("rlp", "R0_A")
    mb_s = p("mb", "U0_S")

    nets: list[dict[str, Any]] = [
        {
            "net": "IBIAS",
            "pins": [
                _pin("rref", "R0_B"),
                _pin("mt", "U0_G"),
                _pin("mb", "U0_G"),
                _pin("mb", "U0_D"),
            ],
            "legs": [
                _leg(
                    ("rref", "R0_B"),
                    ("mt", "U0_G"),
                    [[X_IBIAS_E, rref_b[1]], [X_IBIAS_E, Y_IBIAS_MT], [mt_g[0], Y_IBIAS_MT]],
                ),
                _leg(
                    ("mt", "U0_G"),
                    ("mb", "U0_G"),
                    [
                        [mt_g[0], Y_IBIAS_MT],
                        [X_IBIAS_W, Y_IBIAS_MT],
                        [X_IBIAS_W, Y_IBIAS_MB],
                        [mb_g[0], Y_IBIAS_MB],
                    ],
                ),
                _leg(
                    ("mb", "U0_G"),
                    ("mb", "U0_D"),
                    [[mb_g[0], Y_IBIAS_MB], [X_IBIAS_MB, Y_IBIAS_MB], [X_IBIAS_MB, mb_d[1]]],
                ),
            ],
        }
    ]
    if shorted:
        # The negative control (layout/README.md's "Every LVS signoff is a
        # pair"): OUTP bridged straight to VSS. It is drawn on Metal2 because
        # TAIL's own Metal1 trunk physically separates the OUTP and VSS trunks
        # in the west corridor (module docstring) -- a Metal1 jumper between
        # them would be a route-vs-route collision klt gen-compose rejects, so
        # the defect could not be drawn at all on that layer.
        nets.append(
            {
                "net": "VSS",
                "pins": [_pin("mb", "U0_S"), _pin("rlp", "R0_A")],
                "waypoints_um": [[X_SHORT, mb_s[1]], [X_SHORT, rlp_a[1]]],
            }
        )
    return nets


def gate_pins() -> list[dict[str, str]]:
    """The six input gates, labelled but not routed (`klt gen-compose`'s
    `pins[]`), exactly as `cml_driver_core` labels INP/INN."""
    return [
        {"net": "D0P", "block": "mu0p", "port": "U0_G"},
        {"net": "D0N", "block": "mu0n", "port": "U0_G"},
        {"net": "D1P", "block": "mu1p", "port": "U0_G"},
        {"net": "D1N", "block": "mu1n", "port": "U0_G"},
        {"net": "CLKP", "block": "mcp", "port": "U0_G"},
        {"net": "CLKN", "block": "mcn", "port": "U0_G"},
    ]


def _compose_request(
    pdk: str,
    origins: dict[str, dict[str, float]],
    connectivity: list[dict[str, Any]],
    pins: list[dict[str, str]],
    layer_role: str,
    width_um: float,
    cell_name: str,
    output: Path,
) -> dict[str, Any]:
    return {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": pdk},
        "blocks": [
            {
                "id": bid,
                "generator_report": f"{bid}.json",
                "orientation": PLACEMENT[bid][0],
            }
            for bid in BLOCK_ORDER
        ],
        "placement": {
            "strategy": "explicit",
            "order": list(BLOCK_ORDER),
            "origins_um": origins,
        },
        "connectivity": connectivity,
        "pins": pins,
        "routing": {"layer_role": layer_role, "width_um": width_um},
        "options": {"cell_name": cell_name, "output": str(output)},
    }


def _compose(klt: str, work: Path, request: dict[str, Any], name: str) -> dict[str, Any]:
    path = work / f"{name}_request.json"
    path.write_text(json.dumps(request, indent=2))
    result = _run([klt, "gen-compose", str(path), "--format", "json"], ok=(0, 3))
    if result.get("unrouted_nets"):
        notes = result.get("drc_hints", {}).get("notes", [])
        raise RuntimeError(f"{name}: unrouted nets {result['unrouted_nets']}: {notes}")
    for net in result.get("nets", []):
        for leg in net.get("legs", []):
            if not leg.get("routed"):
                raise RuntimeError(f"{name}: net {net['net']} leg not routed: {leg.get('reason')}")
    return result


def _merge_top_shapes(base_gds: Path, base_cell: str, overlay_gds: Path, overlay_cell: str) -> int:
    """Copy the overlay composition's *own* top-cell shapes (its Metal2/Via1
    routing, landing pads and net labels) into the base composition's top cell,
    in place. Sub-cell instances are deliberately not copied: both passes
    placed the identical blocks at identical origins, so the base already
    carries every device exactly once."""
    import klayout.db as kdb  # lazy: layout/tests/ must import this module without KLayout

    base = kdb.Layout()
    base.read(str(base_gds))
    overlay = kdb.Layout()
    overlay.read(str(overlay_gds))
    if abs(base.dbu - overlay.dbu) > 1e-12:
        raise RuntimeError(f"dbu mismatch: base {base.dbu} vs overlay {overlay.dbu}")
    bt = base.cell(base_cell)
    ot = overlay.cell(overlay_cell)
    if bt is None or ot is None:
        raise RuntimeError(f"missing top cell ({base_cell!r} / {overlay_cell!r})")
    copied = 0
    for li in overlay.layer_indexes():
        info = overlay.get_info(li)
        target = base.layer(info)
        for shape in ot.shapes(li).each():
            bt.shapes(target).insert(shape)
            copied += 1
    if copied == 0:
        raise RuntimeError("overlay pass drew nothing -- refusing to write an unrouted cell")
    base.write(str(base_gds))
    return copied


def build(klt: str, pdk: str, output: Path, shorted: bool) -> dict[str, Any]:
    cell_name = "tmds_final_mux_shorted" if shorted else "tmds_final_mux"
    with tempfile.TemporaryDirectory(prefix="gen_tmds_final_mux_") as tmp:
        work = Path(tmp)
        reports = generate_blocks(klt, pdk, work)
        origins = _origins(reports)

        m1 = _compose_request(
            pdk,
            origins,
            metal1_connectivity(reports, origins, shorted),
            gate_pins(),
            "metal",
            ROUTE_WIDTH_UM,
            cell_name,
            output,
        )
        pass1 = _compose(klt, work, m1, "metal1")

        overlay_gds = work / "metal2.gds"
        m2 = _compose_request(
            pdk,
            origins,
            metal2_connectivity(reports, origins, shorted),
            [],
            "metal2",
            ROUTE_WIDTH_M2_UM,
            f"{cell_name}_m2",
            overlay_gds,
        )
        pass2 = _compose(klt, work, m2, "metal2")

        copied = _merge_top_shapes(output, cell_name, overlay_gds, f"{cell_name}_m2")
        pass1["merged_overlay_shapes"] = copied
        pass1["overlay_nets"] = [n["net"] for n in pass2.get("nets", [])]
        return pass1


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-o", "--output", required=True, help="output GDS/OASIS path")
    ap.add_argument(
        "--shorted",
        action="store_true",
        help="emit the LVS negative-control (OUTP-bridged-to-VSS) variant",
    )
    ap.add_argument("--pdk", default=DEFAULT_PDK, help=f"PDK variant (default: {DEFAULT_PDK})")
    ap.add_argument("--klt", default="klt", help="klt executable (default: klt on $PATH)")
    args = ap.parse_args()

    result = build(args.klt, args.pdk, Path(args.output), args.shorted)
    print(
        f"wrote {result['gds_path']}: cell {result['cell_name']!r}, "
        f"bbox {result['bbox_um']}, {len(result['blocks'])} blocks, "
        f"{len(result['nets'])} Metal1 nets routed, "
        f"{len(result['overlay_nets'])} Metal2 net(s) merged "
        f"({result['merged_overlay_shapes']} shapes)"
    )


if __name__ == "__main__":
    main()
