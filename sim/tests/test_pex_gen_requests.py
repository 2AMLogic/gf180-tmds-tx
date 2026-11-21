"""PEX request measurement-translation tests -- no PDK, no ngspice required.

    python3 -m unittest sim.tests.test_pex_gen_requests -v

Pins ``sim/pex/gen_requests.py::_translate_measurements``'s emission
contract (issue #382): raw ``.meas`` cards first, ``PARAM`` cards after the
raw cards they read, ``expr`` entries in dependency-respecting order, the
``xvhi.tail`` -> ``xvhi.xcore.tail`` wrapper-node rewrite holding for every
emitted form that can carry a node reference, and the rejection of a
measurement whose dependencies span both a ``.meas`` card result and an
expression result -- readable in neither ``klt sim`` form (the issue #371
fixture finding). ``--check`` byte-compares generated files, so it catches
a translator regression only once someone regenerates them; these tests
pin the semantics directly, on synthetic benches shaped like the real
manifests' raw TRIG/TARG cards, PARAM formulas and expr chains.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))
PEX_DIR = SIM_DIR / "pex"
if str(PEX_DIR) not in sys.path:
    sys.path.insert(0, str(PEX_DIR))

import gen_requests as gen  # noqa: E402
from harness import testbench as tb_mod  # noqa: E402


def _tb(measure: dict[str, str]) -> SimpleNamespace:
    """A minimal bench stand-in: the translator reads ``name`` + ``measure``."""
    return SimpleNamespace(name="unit-bench", measure=measure)


RAW_UI = "TRIG v(inref) VAL=0 FALL=1 TARG v(inref) VAL=0 RISE=1"
RAW_TRISE = "TRIG v(vd_c0) VAL=-0.4 RISE=1 TARG v(vd_c0) VAL=0.4 RISE=1"


class EmissionOrderTests(unittest.TestCase):
    """Raw cards, then PARAM cards, then dependency-ordered expr entries."""

    def test_forms_and_order(self):
        entries = gen._translate_measurements(_tb({
            "ui_ref": RAW_UI,
            "trise_c0": RAW_TRISE,
            # PARAM form: every m_ dep is a raw card result (the shape of
            # the real benches' trise_ui_*/dj_ui_* formulas).
            "trise_ui_c0": "m_trise_c0/m_ui_ref",
            # Declared BEFORE the entries it depends on, so the
            # topological pass has to reorder around it.
            "eyeh_max_c0": "max(m_height_c0_0, m_height_c0_1)",
            "height_c0_0": "vecmin(v(vd_c0))",
            "height_c0_1": "vecmax(v(vd_c0))",
        }))
        # Raw cards first in declared order; the PARAM card after the raw
        # cards it reads (ui_ref, trise_c0); expr entries last, in
        # dependency-respecting (topological, stable) order.
        self.assertEqual(
            [entry["name"] for entry in entries],
            [
                "ui_ref",
                "trise_c0",
                "trise_ui_c0",
                "height_c0_0",
                "height_c0_1",
                "eyeh_max_c0",
            ],
        )
        self.assertEqual(entries[0]["spice"], f".meas tran ui_ref {RAW_UI}")
        self.assertEqual(entries[1]["spice"], f".meas tran trise_c0 {RAW_TRISE}")
        self.assertEqual(
            entries[2]["spice"],
            ".meas tran trise_ui_c0 PARAM='trise_c0/ui_ref'",
        )
        self.assertEqual(
            entries[3]["expr"],
            "vecmin(v(vd_c0))",
        )
        self.assertEqual(
            entries[5]["expr"],
            "max(height_c0_0, height_c0_1)",
        )

    def test_no_measurement_lost_or_renamed(self):
        measures = {
            "ui_ref": RAW_UI,
            "trise_c0": RAW_TRISE,
            "trise_ui_c0": "m_trise_c0/m_ui_ref",
            "vgs_sw_max": "vecmax((v(inp)-v(xvhi.tail))*v(win))",
            "eyeh_max_c0": "max(m_height_c0_0, m_height_c0_1)",
            "height_c0_0": "vecmin(v(vd_c0))",
            "height_c0_1": "vecmax(v(vd_c0))",
        }
        entries = gen._translate_measurements(_tb(measures))
        self.assertEqual(
            sorted(entry["name"] for entry in entries), sorted(measures)
        )


class NodeRewriteTests(unittest.TestCase):
    """The wrapper node rewrite holds for every form that can carry a node
    reference -- the residual assertion runs over raw and PARAM entries
    too, not just expr entries."""

    def test_rewrite_applied_to_expr_and_param_entries(self):
        entries = gen._translate_measurements(_tb({
            "ui_ref": RAW_UI,
            "vds_tail_max": "vecmax(v(xvhi.tail)*v(win))",  # expr form
            "scaled": "m_ui_ref*v(xvhi.tail)",               # PARAM form
        }))
        by_name = {entry["name"]: entry for entry in entries}
        self.assertEqual(
            by_name["vds_tail_max"]["expr"],
            "vecmax(v(xvhi.xcore.tail)*v(win))",
        )
        self.assertEqual(
            by_name["scaled"]["spice"],
            ".meas tran scaled PARAM='ui_ref*v(xvhi.xcore.tail)'",
        )
        for entry in entries:
            text = entry["spice"] if "spice" in entry else entry["expr"]
            self.assertNotIn(
                "xvhi.tail", text, f"un-rewritten node in {entry['name']!r}"
            )

    def test_raw_card_referencing_wrapper_node_rejected(self):
        # Raw cards are emitted verbatim, so a card probing a wrapper-
        # hidden node cannot be fixed by the translator: generation fails
        # here instead of emitting a card that dies on an unknown node at
        # run time.
        with self.assertRaises(SystemExit) as ctx:
            gen._translate_measurements(_tb({
                "ui_ref": RAW_UI,
                "tail_rise": (
                    "TRIG v(xvhi.tail) VAL=0 FALL=1"
                    " TARG v(xvhi.tail) VAL=0 RISE=1"
                ),
            }))
        self.assertIn("node rewrite", str(ctx.exception))
        self.assertIn("tail_rise", str(ctx.exception))


class MixedDependencyRejectionTests(unittest.TestCase):
    """A dependency spanning a ``.meas`` card result and an expression
    result is readable in neither ``klt sim`` form (the issue #371 fixture
    finding: a later control-block expression could read neither spelling
    of a card result) and must fail at generation time."""

    def test_raw_and_expr_deps_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            gen._translate_measurements(_tb({
                "ui_ref": RAW_UI,
                "height_c0_0": "vecmin(v(vd_c0))",
                "bad": "m_ui_ref*m_height_c0_0",
            }))
        self.assertIn("bad", str(ctx.exception))
        self.assertIn("ui_ref", str(ctx.exception))
        self.assertIn("#371", str(ctx.exception))
        self.assertIn("cannot be expressed in either", str(ctx.exception))

    def test_param_and_expr_deps_rejected(self):
        # trise_ui_c0 lands in PARAM form; an expr reading BOTH it and an
        # expr result is the same unreadable-vector failure.
        with self.assertRaises(SystemExit) as ctx:
            gen._translate_measurements(_tb({
                "ui_ref": RAW_UI,
                "trise_c0": RAW_TRISE,
                "trise_ui_c0": "m_trise_c0/m_ui_ref",  # -> PARAM form
                "height_c0_0": "vecmin(v(vd_c0))",
                "bad": "m_trise_ui_c0*m_height_c0_0",
            }))
        self.assertIn("bad", str(ctx.exception))
        self.assertIn("trise_ui_c0", str(ctx.exception))
        self.assertIn("cannot be expressed in either", str(ctx.exception))

    def test_expr_depending_only_on_param_result_rejected(self):
        # PARAM-form names are removed from the expr set before the
        # topological pass, so an expr reading ONLY a PARAM card's result
        # used to pass silently as an expr entry reading an unknown
        # vector. An expr left in expr form must have all its deps among
        # expr-form names.
        with self.assertRaises(SystemExit) as ctx:
            gen._translate_measurements(_tb({
                "ui_ref": RAW_UI,
                "trise_c0": RAW_TRISE,
                "trise_ui_c0": "m_trise_c0/m_ui_ref",  # -> PARAM form
                "bad": "m_trise_ui_c0*2",
            }))
        self.assertIn("bad", str(ctx.exception))
        self.assertIn("trise_ui_c0", str(ctx.exception))
        self.assertIn("cannot be expressed in either", str(ctx.exception))


class RealManifestSmokeTests(unittest.TestCase):
    """The guards reject nothing in today's bench manifests: both benches
    still translate, with every declared measurement present exactly once
    under its own name (issue #382 verified no measurement mixes forms)."""

    def test_both_benches_translate_every_measure(self):
        for slug in gen.BENCHES:
            with self.subTest(slug=slug):
                tb = tb_mod.load(SIM_DIR / slug)
                entries = gen._translate_measurements(tb)
                self.assertEqual(
                    sorted(entry["name"] for entry in entries),
                    sorted(tb.measure),
                )


if __name__ == "__main__":
    unittest.main()
