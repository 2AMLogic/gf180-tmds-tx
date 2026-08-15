#!/usr/bin/env python3
"""Generate the CML output driver *core* cell (issue #22): the differential
switch pair (M1/M2) + tail current source (MT) + 1:20 bias-mirror reference
device (MB), per the sized schematic (`design/cml_driver.sch` /
`design/netlist/cml_driver.spice`, issue #11). ESD/pad-ring integration is
explicitly out of scope for this cell -- that is downstream work once this
core lands (see the issue).

Unlike `gen_pad_min.py` (issue #2), which predates `klt gen`'s PCell
generator family and draws every shape directly via `klayout.db`, this cell
is built through `klt gen`'s `mos_array` primitive -- family 1 of the
analog primitive generators, `docs/design/layout-generator-spike.md` section
4 in klayout-tools -- one folded multi-finger NMOS device per schematic
device, composed into one circuit via `klt gen-compose`'s explicit placement
+ two-pin routing. This *is* "the flow proven out by
`layout/scripts/gen_pad_min.py`" in the sense the issue asks for: a
generator-tool-backed, reproducible script committed alongside its output,
not a hand-authored one-off -- `klt gen`/`klt gen-compose` are exactly the
generator machinery `docs/design/design-pipeline.md`'s S7 (layout
generation) stage exists to route this kind of cell through, which gf180mcu
gen_pad_min.py's own era (issue #2) predates.

Device mapping (`design/netlist/cml_driver.spice`, all four devices are
`nfet_03v3` with a 2 um/finger unit cell per `design/cml-driver-sizing.md`
section 1.3 -- every W/L below is therefore expressed as
`fingers = nf (or nf * m)`, `w_um = 2.0` (per-finger width), matching the
spice model directly so `klt lvs`'s `options.combine_devices` folds the
per-finger extraction back into the one device each schematic line states):

  M1/M2 (switch pair)     nf=64        W=128u  L=0.28u  -> fingers=64,  l_um=0.28
  MT    (tail, m=20)      nf=10, m=20  W=400u  L=0.5u   -> fingers=200, l_um=0.5
  MB    (bias ref, m=1)   nf=10, m=1   W=20u   L=0.5u   -> fingers=10,  l_um=0.5

`gate_contact=true` on a single-unit (`rows=1, cols=1`) `mos_array` call draws
a real strapped multi-finger device (source rail / drain rail / gate comb,
all contacted) rather than the bare, uncontactable series stripes the
generator's pre-#497 default drew. `mos_array`'s `topology` param
('array'/'common_centroid') only matters for multi-position grids and is
irrelevant here; there is no separate finger-topology toggle -- see `klt gen
--list`'s own `gate_contact` description.

Floorplan hazard found during bring-up (worth recording since it is a
klayout-tools friction item, not a design defect -- filed generically per
this repo's CLAUDE.md friction protocol): routing two *same-facing* ports
(`mt`'s and `mb`'s `U0_S`, both west-facing) with `klt gen-compose`'s default
same-facing-pair backbone placed the connecting stub's centerline just
outside `mt`'s own bounding box, but the *drawn path*'s width (extending
`routing.width_um / 2` past the centerline on each side) clipped back
*inside* `mt`'s bbox -- silently shorting `mt`'s source rail to its drain
rail through the routed metal, because `klt gen-compose`'s obstacle check
tests the backbone centerline against block bboxes, not the drawn path's
actual (width-inflated) footprint. `klt drc` did not catch it (a routed
short is legal geometry, not a spacing/width violation), and it was only
visible via `klt extract`'s net count. Worked around with an explicit
`connectivity[].waypoints_um` detour (`VSS_WAYPOINT_X_UM`, several microns
clear of every block) rather than the default backbone -- see
`VSS_WAYPOINT_X_UM` below. TAIL/IBIAS's own opposite-facing routes were not
affected (their jogs land in the open gap between blocks, comfortably past
`routing.width_um / 2` clearance).

Two cells are written by default (mirroring `gen_pad_min.py`'s own
clean/negative-control pair):

- ``cml_driver_core``          -- the real candidate: OUTP/OUTN/INP/INN/
  IBIAS/VSS wired per the sized schematic.
- ``cml_driver_core_shorted``  -- an LVS negative control: identical
  topology, except OUTP is wired directly to VSS instead of being left as
  an independent output pin (a `net.merged` connectivity defect). Must FAIL
  `klt lvs` against the same reference netlist the unshorted cell passes.

Requires `klt` (klayout-tools) on `$PATH` and a resolvable gf180mcu PDK
install (`klt pdk find --pdk gf180mcuD`) -- see `klt gen`/`klt gen-compose`
docs (`docs/cli/gen.md`, `docs/cli/gen-compose.md` in klayout-tools) for the
request/response contract this script drives via subprocess calls, and
`spec/tmds-tx.md`'s own `gf180mcuD` pin (mirrored by `sim/pdk.json`) for why
that variant, not another gf180mcu flavour, is this repo's default going
forward (the earlier `gf180mcuC`-vs-`gf180mcuD` provenance question on
`gf180_tmds_pad_min` itself is issue #9's open item, not resolved here).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Device sizing (design/netlist/cml_driver.spice, design/cml-driver-sizing.md
# section 1.3's 2 um/finger unit-cell convention).
# ---------------------------------------------------------------------------
W_UM = 2.0  # per-finger width (um), shared by every device in this cell

DEVICES: dict[str, dict[str, Any]] = {
    "m1": {"fingers": 64, "l_um": 0.28},  # switch, W=128u L=0.28u
    "m2": {"fingers": 64, "l_um": 0.28},  # switch, W=128u L=0.28u
    "mt": {"fingers": 200, "l_um": 0.5},  # tail, nf=10 m=20 -> 200 fingers, W=400u
    "mb": {"fingers": 10, "l_um": 0.5},  # bias reference, nf=10 m=1, W=20u
}

# Row-placement gap between adjacent blocks (um) -- generous relative to
# routing.width_um (below) so every opposite-facing-pair jog lands with
# comfortable clearance of both blocks' bboxes (see the floorplan-hazard
# note above for why "generous" matters here).
GAP_UM = 5.0

# routing width for every connectivity net (um) -- clears gf180mcu's
# metal1.width.1 minimum (0.23um, per layout/scripts/gen_pad_min.py's own
# comment) with margin.
ROUTE_WIDTH_UM = 0.3

# Explicit detour (see the floorplan-hazard note above) for the VSS net
# (mt.U0_S <-> mb.U0_S, a same-facing west/west pair): several microns west
# of every block's x=0 edge, clear of routing.width_um/2 by more than an
# order of magnitude.
VSS_WAYPOINT_X_UM = -3.0

DEFAULT_PDK = "gf180mcuD"  # see module docstring's provenance note


def _run_klt(klt: str, args: list[str]) -> dict[str, Any]:
    """Run a `klt` subcommand with --format json and return the parsed
    response. Raises CalledProcessError (with stderr surfaced) on failure."""
    cmd = [klt, *args, "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 3):  # 3 == klt gen-compose partial success
        sys.stderr.write(proc.stderr)
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


def _gen_block(
    klt: str, pdk: str, work_dir: Path, block_id: str, fingers: int, l_um: float
) -> dict[str, Any]:
    gds_path = work_dir / f"{block_id}.gds"
    params = {
        "w_um": W_UM,
        "l_um": l_um,
        "fingers": fingers,
        "rows": 1,
        "cols": 1,
        "dummy": 0,
        "gate_contact": True,
    }
    report = _run_klt(
        klt,
        [
            "gen",
            "mos_array",
            "--pdk",
            pdk,
            "--params",
            json.dumps(params),
            "--cell-name",
            f"{block_id}_unit",
            "-o",
            str(gds_path),
        ],
    )
    report_path = work_dir / f"{block_id}.json"
    report_path.write_text(json.dumps(report))
    return report


def _compose_request(
    pdk: str,
    blocks: dict[str, dict[str, Any]],
    work_dir: Path,
    cell_name: str,
    output: Path,
    shorted: bool,
) -> dict[str, Any]:
    """Build the `klt gen-compose` request document for either the clean
    cell or the OUTP-shorted-to-VSS negative control (`shorted=True`)."""
    mt_h = blocks["mt"]["bbox_um"]["y1"]
    mt_w = blocks["mt"]["bbox_um"]["x1"]
    m1_h = blocks["m1"]["bbox_um"]["y1"]

    origins = {
        "mt": {"x": 0.0, "y": 0.0},
        "mb": {"x": 0.0, "y": mt_h + GAP_UM},
        "m1": {"x": mt_w + GAP_UM, "y": 0.0},
        "m2": {"x": mt_w + GAP_UM, "y": m1_h + GAP_UM},
    }

    connectivity = [
        {"net": "TAIL", "pins": [{"block": "mt", "port": "U0_D"}, {"block": "m1", "port": "U0_S"}]},
        {"net": "TAIL", "pins": [{"block": "mt", "port": "U0_D"}, {"block": "m2", "port": "U0_S"}]},
        {"net": "IBIAS", "pins": [{"block": "mb", "port": "U0_D"}, {"block": "mb", "port": "U0_G"}]},
        {"net": "IBIAS", "pins": [{"block": "mb", "port": "U0_D"}, {"block": "mt", "port": "U0_G"}]},
        {
            "net": "VSS",
            "pins": [{"block": "mt", "port": "U0_S"}, {"block": "mb", "port": "U0_S"}],
            "waypoints_um": [
                [VSS_WAYPOINT_X_UM, origins["mt"]["y"] + 0.21],
                [VSS_WAYPOINT_X_UM, origins["mb"]["y"] + 0.21],
            ],
        },
    ]
    pins = [
        {"net": "OUTN", "block": "m2", "port": "U0_D"},
        {"net": "INP", "block": "m1", "port": "U0_G"},
        {"net": "INN", "block": "m2", "port": "U0_G"},
    ]

    if shorted:
        # Negative control (issue #22, mirroring gen_pad_min.py's own
        # shorted variant): wire OUTP directly to VSS instead of leaving it
        # as an independent pin -- a pure connectivity (net.merged) defect,
        # routed via an explicit detour well clear of every block so the
        # corruption itself isn't also a routing-obstacle failure.
        top_y = max(
            origins["mb"]["y"] + blocks["mb"]["bbox_um"]["y1"],
            origins["m2"]["y"] + blocks["m2"]["bbox_um"]["y1"],
        )
        east_x = origins["m1"]["x"] + blocks["m1"]["bbox_um"]["x1"]
        detour_y = top_y + GAP_UM
        connectivity.append(
            {
                "net": "OUTP",
                "pins": [{"block": "m1", "port": "U0_D"}, {"block": "mt", "port": "U0_S"}],
                "waypoints_um": [
                    [east_x + 0.5, 0.21],
                    [east_x + 0.5, detour_y],
                    [VSS_WAYPOINT_X_UM, detour_y],
                    [VSS_WAYPOINT_X_UM, 0.21],
                ],
            }
        )
    else:
        pins.append({"net": "OUTP", "block": "m1", "port": "U0_D"})

    return {
        "pdk": {"variant": pdk},
        "blocks": [{"id": bid, "generator_report": f"{bid}.json"} for bid in ("mt", "mb", "m1", "m2")],
        "placement": {
            "strategy": "explicit",
            "order": ["mt", "mb", "m1", "m2"],
            "origins_um": origins,
        },
        "connectivity": connectivity,
        "pins": pins,
        "routing": {"layer_role": "metal", "width_um": ROUTE_WIDTH_UM},
        "options": {"cell_name": cell_name, "output": str(output)},
    }


def build(klt: str, pdk: str, output: Path, shorted: bool) -> dict[str, Any]:
    cell_name = "cml_driver_core_shorted" if shorted else "cml_driver_core"
    with tempfile.TemporaryDirectory(prefix="gen_cml_driver_core_") as tmp:
        work_dir = Path(tmp)
        blocks = {
            bid: _gen_block(klt, pdk, work_dir, bid, dev["fingers"], dev["l_um"])
            for bid, dev in DEVICES.items()
        }
        request = _compose_request(pdk, blocks, work_dir, cell_name, output, shorted)
        request_path = work_dir / "compose_request.json"
        request_path.write_text(json.dumps(request, indent=2))
        cmd = [klt, "gen-compose", str(request_path), "--format", "json"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode not in (0, 3):
            sys.stderr.write(proc.stderr)
            raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
        result = json.loads(proc.stdout)
        if result.get("unrouted_nets"):
            raise RuntimeError(f"unrouted nets: {result['unrouted_nets']}")
        return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", required=True, help="output GDS/OASIS path")
    ap.add_argument("--shorted", action="store_true", help="emit the LVS negative-control (OUTP-shorted-to-VSS) variant")
    ap.add_argument("--pdk", default=DEFAULT_PDK, help=f"PDK variant to resolve (default: {DEFAULT_PDK})")
    ap.add_argument("--klt", default="klt", help="klt executable (default: klt on $PATH)")
    args = ap.parse_args()

    result = build(args.klt, args.pdk, Path(args.output), args.shorted)
    print(
        f"wrote {result['gds_path']}: cell {result['cell_name']!r}, "
        f"bbox {result['bbox_um']}, {len(result['blocks'])} blocks, "
        f"{len(result['nets'])} nets routed"
    )


if __name__ == "__main__":
    main()
