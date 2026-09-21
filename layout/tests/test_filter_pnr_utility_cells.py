#!/usr/bin/env python3
"""Tests for layout/scripts/filter_pnr_utility_cells.py (issue #84 SPICE
form; ``--form verilog`` added for issue #190).

Stdlib ``unittest``, no PDK, no ``klt``, no KLayout -- run by ``python3 -m
unittest discover -s layout/tests`` locally and by CI's PDK-free ``test``
job.

**What is worth testing here.** The verifier in the Verilog mode is the
load-bearing half: per its own docstring the filter must drop exactly the
empty-connection utility-cell instance lines and abort on anything else a
utility master instantiates, because a fill/tap cell that carries a real
connection is signal-bearing content a silent drop would hide. A silently
wrong version would filter a "power-only" instance that actually carried
connectivity -- the same class of defeat-the-purpose failure
``check_lvs_signoff.py`` exists for on the report side. The SPICE form's
statement dropping is exercised on a small synthetic netlist for the same
reason (and to pin the unchanged behavior of an existing optional tool).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "scripts"))

import filter_pnr_utility_cells as filt  # noqa: E402

REAL_PNR = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / "tmds_encoder.pnr.v"


class FilterVerilogNetlistTest(unittest.TestCase):
    def test_drops_empty_utility_instances_only(self):
        text = dedent(
            """\
            module t (a,
                b);
             input a;
             output b;
             wire n1;
             gf180mcu_fd_sc_mcu9t5v0__inv_1 u1 (.A(a),
                .ZN(n1));
             gf180mcu_fd_sc_mcu9t5v0__buf_1 u2 (.I(n1),
                .Z(b));
             gf180mcu_fd_sc_mcu9t5v0__fill_4 FILLER_0_10 ();
             gf180mcu_fd_sc_mcu9t5v0__filltie TAP_0_5 ();
             gf180mcu_fd_sc_mcu9t5v0__endcap END_0_0 ();
            endmodule
            """
        )
        out, dropped_subckts, dropped_instances = filt.filter_verilog_netlist(text)

        self.assertEqual(dropped_subckts, 0)
        self.assertEqual(dropped_instances, 3)
        # every logic instance and declaration line passes through untouched
        for expected in (
            "module t (a,",
            "wire n1;",
            "gf180mcu_fd_sc_mcu9t5v0__inv_1 u1 (.A(a),",
            "gf180mcu_fd_sc_mcu9t5v0__buf_1 u2 (.I(n1),",
            "endmodule",
        ):
            self.assertIn(expected, out)
        self.assertNotIn("FILLER", out)
        self.assertNotIn("TAP_", out)
        self.assertNotIn("END_", out)

    def test_aborts_on_utility_instance_with_real_connections(self):
        text = (
            "module t (a,\n    b);\n"
            " gf180mcu_fd_sc_mcu9t5v0__fill_4 FILLER_0_10 (.VPWR(a));\n"
            "endmodule\n"
        )
        with self.assertRaises(filt.UtilityInstanceHasConnectionsError) as ctx:
            filt.filter_verilog_netlist(text)
        self.assertIn("line 3", str(ctx.exception))
        self.assertIn("VPWR", str(ctx.exception))

    def test_aborts_on_unterminated_utility_instance(self):
        text = "module t (a,\n    b);\n gf180mcu_fd_sc_mcu9t5v0__endcap END_0_0\nendmodule\n"
        with self.assertRaises(filt.UtilityInstanceHasConnectionsError):
            filt.filter_verilog_netlist(text)

    def test_real_committed_pnr_netlist_filters_exactly_970(self):
        """The committed artifact this filter feeds must reproduce: with #192
        merged, the committed pnr.v carries 970 physical-only instances
        (72 endcap, 19 filltie, 879 fill_*), none with any connection."""
        _, dropped_subckts, dropped_instances = filt.filter_verilog_netlist(
            REAL_PNR.read_text()
        )
        self.assertEqual((dropped_subckts, dropped_instances), (0, 970))


class FilterSpiceNetlistTest(unittest.TestCase):
    def test_drops_utility_subckts_and_instances(self):
        text = dedent(
            """\
            .SUBCKT t a b
            .SUBCKT gf180mcu_fd_sc_mcu9t5v0__fill_1 VDD VSS
            .ENDS gf180mcu_fd_sc_mcu9t5v0__fill_1
            Xu1 a n1 gf180mcu_fd_sc_mcu9t5v0__inv_1
            Xf1 VDD VSS gf180mcu_fd_sc_mcu9t5v0__fill_1
            Xe1 VDD VSS gf180mcu_fd_sc_mcu9t5v0__endcap
            .ENDS t
            """
        )
        out, dropped_subckts, dropped_instances = filt.filter_netlist(text)

        self.assertEqual(dropped_subckts, 1)
        self.assertEqual(dropped_instances, 2)
        self.assertNotIn("__fill_1", out)
        self.assertNotIn("__endcap", out)
        self.assertIn("Xu1", out)


if __name__ == "__main__":
    unittest.main()
