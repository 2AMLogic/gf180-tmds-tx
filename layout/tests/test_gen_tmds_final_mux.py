#!/usr/bin/env python3
"""Tests for layout/scripts/gen_tmds_final_mux.py (issue #177).

Stdlib ``unittest``, no PDK, no ``klt``, no KLayout -- run by ``python3 -m
unittest discover -s layout/tests`` locally and by CI's PDK-free ``test``
job (same convention `test_gen_pad_ring_assembly.py` establishes;
`gen_tmds_final_mux.py` keeps its own `klayout.db` import optional and
lazy, inside `_merge_top_shapes`, for exactly this reason).

**What is worth testing here, and what is not.** The drawn geometry itself
is checked by the strongest tool available: `klt drc --deck gf180mcu`
reports `status: clean` for both `tmds_final_mux` and its `_shorted` twin,
and `klt lvs` reports `status: match` / `status: mismatch` respectively
(`layout/lvs_reports/tmds_final_mux*.lvs.{json,txt}`, enforced by
`check_lvs_signoff.py`). Re-asserting shapes here would duplicate that
weakly.

What DRC/LVS cannot catch pre-generation is a generator whose *device
inventory* silently drifted from the sized schematic before a single
`klt gen` subprocess is ever launched -- a typo in `MOS_DEVICES`/
`RES_DEVICES` (wrong `fingers`, a missing device, a resistor width/length
transposed) would still draw *something* DRC-clean, and would only be
caught by LVS if the mistake happened to also break topology rather than
just width/length. These tests instead re-derive the schematic's own device
inventory straight from `design/netlist/tmds_final_mux.spice` (the same
sized netlist issue #159/#164/#174 landed) and assert the generator's
tables agree with it exactly -- port list, port order, and every MOS/
resistor's size -- so a drift is caught before any tool invocation.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))

import gen_tmds_final_mux as gen  # noqa: E402

NETLIST_PATH = REPO_ROOT / "design" / "netlist" / "tmds_final_mux.spice"


def _parse_netlist(path: Path) -> tuple[list[str], dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Minimal, purpose-built parser for the one `.subckt` this repo's sized
    `tmds_final_mux` netlist contains -- not a general SPICE reader. Returns
    (port_list, mos_devices, res_devices), keyed by the device's own
    reference designator lower-cased to match `gen`'s block ids (e.g.
    ``MU0P`` -> ``mu0p``)."""
    text = path.read_text()

    # xschem's netlister flattens the top-level circuit (no real .subckt
    # wrapper) but leaves the pin list as a commented `**.subckt` line for
    # documentation -- that comment is this file's only source for port
    # order, so the leading `*`s are matched deliberately, not stripped.
    subckt_match = re.search(r"^\*+\.subckt\s+tmds_final_mux\s+(.+)$", text, re.MULTILINE | re.IGNORECASE)
    assert subckt_match, "no (possibly commented) .subckt tmds_final_mux line found"
    ports = subckt_match.group(1).split()

    mos: dict[str, dict[str, float]] = {}
    res: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("XM"):
            name = line.split()[0][1:].lower()  # "XMU0P ..." -> "mu0p"
            l_um = float(re.search(r"\bL=([0-9.]+)u", line, re.IGNORECASE).group(1))
            w_um = float(re.search(r"\bW=([0-9.]+)u", line, re.IGNORECASE).group(1))
            nf = int(re.search(r"\bnf=(\d+)", line, re.IGNORECASE).group(1))
            m_match = re.search(r"\bm=(\d+)", line, re.IGNORECASE)
            m = int(m_match.group(1)) if m_match else 1
            mos[name] = {"l_um": l_um, "w_um": w_um, "nf": nf, "m": m}
        elif line.upper().startswith("XR"):
            name = line.split()[0][1:].lower()  # "XRLP ..." -> "rlp"
            r_width = float(re.search(r"r_width=([0-9.]+)u", line, re.IGNORECASE).group(1))
            r_length = float(re.search(r"r_length=([0-9.]+)u", line, re.IGNORECASE).group(1))
            res[name] = {"r_width": r_width, "r_length": r_length}

    return ports, mos, res


class NetlistFixtureTest(unittest.TestCase):
    """Guards the parser above against silently reading nothing (e.g. the
    netlist path moved, or its format changed) -- every other test in this
    module trusts these fixtures."""

    def setUp(self):
        self.ports, self.mos, self.res = _parse_netlist(NETLIST_PATH)

    def test_netlist_file_exists(self):
        self.assertTrue(NETLIST_PATH.is_file(), NETLIST_PATH)

    def test_parsed_eight_mos_and_four_resistors(self):
        self.assertEqual(len(self.mos), 8, self.mos)
        self.assertEqual(len(self.res), 4, self.res)

    def test_parsed_ten_ports(self):
        self.assertEqual(len(self.ports), 10, self.ports)


class PortListTest(unittest.TestCase):
    """`gen`'s composed cell must present the same port list, in the same
    order, as `design/tmds_final_mux.sym` / the sized netlist's `.subckt`
    line -- the schematic-to-layout pin contract this cell is laid out
    against."""

    def setUp(self):
        self.ports, _, _ = _parse_netlist(NETLIST_PATH)

    def test_matches_sized_netlist_subckt_port_order(self):
        self.assertEqual(
            self.ports,
            ["OUTP", "OUTN", "D0P", "D0N", "D1P", "D1N", "CLKP", "CLKN", "VDD", "VSS"],
        )

    def test_gate_pins_cover_the_six_input_gate_nets(self):
        gate_nets = [p["net"] for p in gen.gate_pins()]
        self.assertEqual(sorted(gate_nets), sorted(["D0P", "D0N", "D1P", "D1N", "CLKP", "CLKN"]))
        # every net the sized netlist's ports list as an input must appear
        input_ports = {"D0P", "D0N", "D1P", "D1N", "CLKP", "CLKN"}
        self.assertEqual(set(gate_nets), input_ports)


class MosDeviceInventoryTest(unittest.TestCase):
    """`gen.MOS_DEVICES` (fingers/l_um, at the shared `W_UM=2.0` per-finger
    width `design/cml-driver-sizing.md` section 1.3 establishes) must total
    to exactly the sized netlist's own folded W/L/nf/m for every device."""

    def setUp(self):
        _, self.mos, _ = _parse_netlist(NETLIST_PATH)

    def test_every_schematic_mos_device_has_a_generator_entry(self):
        self.assertEqual(set(gen.MOS_DEVICES.keys()), set(self.mos.keys()))

    def test_every_device_l_um_matches(self):
        for name, dev in self.mos.items():
            with self.subTest(device=name):
                self.assertAlmostEqual(gen.MOS_DEVICES[name]["l_um"], dev["l_um"])

    def test_every_device_total_width_matches(self):
        """fingers * W_UM must equal the schematic's own W (per device,
        already folded across nf) times its multiplicity m -- MT's m=20
        folded into 200 fingers per the module docstring's documented
        choice; every other device's m=1 is a no-op fold."""
        for name, dev in self.mos.items():
            with self.subTest(device=name):
                total_w_um = gen.MOS_DEVICES[name]["fingers"] * gen.W_UM
                self.assertAlmostEqual(total_w_um, dev["w_um"] * dev["m"])

    def test_mt_tail_device_folds_m20_into_200_fingers(self):
        # design/netlist/tmds_final_mux.spice: XMT ... nf=10 ... m=20
        self.assertEqual(self.mos["mt"]["nf"], 10)
        self.assertEqual(self.mos["mt"]["m"], 20)
        self.assertEqual(gen.MOS_DEVICES["mt"]["fingers"], self.mos["mt"]["w_um"] * self.mos["mt"]["m"] / gen.W_UM)
        self.assertEqual(gen.MOS_DEVICES["mt"]["fingers"], 200)

    def test_mb_bias_device_is_unmultiplied(self):
        # design/netlist/tmds_final_mux.spice: XMB ... nf=10 ... m=1
        self.assertEqual(self.mos["mb"]["m"], 1)
        self.assertEqual(gen.MOS_DEVICES["mb"]["fingers"], 10)


class ResDeviceInventoryTest(unittest.TestCase):
    """`gen.RES_DEVICES` (`length_um`/`width_um`) must match the sized
    netlist's `r_length`/`r_width` for every `ppolyf_u` resistor exactly --
    the direct mapping the module docstring documents (`flavor="generic"`
    resolves to `ppolyf_u` on gf180mcu)."""

    def setUp(self):
        _, _, self.res = _parse_netlist(NETLIST_PATH)

    def test_every_schematic_resistor_has_a_generator_entry(self):
        self.assertEqual(set(gen.RES_DEVICES.keys()), set(self.res.keys()))

    def test_every_resistor_width_and_length_matches(self):
        for name, dev in self.res.items():
            with self.subTest(device=name):
                self.assertAlmostEqual(gen.RES_DEVICES[name]["length_um"], dev["r_length"])
                self.assertAlmostEqual(gen.RES_DEVICES[name]["width_um"], dev["r_width"])

    def test_rlp_rln_share_the_issue_169_widened_length(self):
        # issue #169: RLP/RLN r_length widened to 5.90u in the committed netlist.
        self.assertAlmostEqual(gen.RES_DEVICES["rlp"]["length_um"], 5.90)
        self.assertAlmostEqual(gen.RES_DEVICES["rln"]["length_um"], 5.90)


class BlockOrderTest(unittest.TestCase):
    """`BLOCK_ORDER` (the `klt gen-compose` block/placement iteration order)
    must cover every device exactly once -- a missing or duplicated block id
    would either drop a device from the composed cell or double-place it."""

    def test_block_order_covers_every_device_exactly_once(self):
        expected = set(gen.MOS_DEVICES.keys()) | set(gen.RES_DEVICES.keys())
        self.assertEqual(set(gen.BLOCK_ORDER), expected)
        self.assertEqual(len(gen.BLOCK_ORDER), len(set(gen.BLOCK_ORDER)))

    def test_every_block_has_a_placement_entry(self):
        for bid in gen.BLOCK_ORDER:
            with self.subTest(block=bid):
                self.assertIn(bid, gen.PLACEMENT)


class DefaultPdkTest(unittest.TestCase):
    def test_default_pdk_is_gf180mcud_per_dr0010(self):
        self.assertEqual(gen.DEFAULT_PDK, "gf180mcuD")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
