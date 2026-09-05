"""Post-layout DUT translation tests for the assembled driver+pad-ring+ESD
block -- no PDK, no ngspice, no klt required.

    python3 -m unittest discover -s sim/tests -v

`layout/sim/gf180_tmds_pad_ring_assembly_dut.spice` is the simulatable form
of the LVS-signed-off, **parasitics-extracted** netlist `layout/gds/
gf180_tmds_pad_ring_assembly.spice` (`klt extract --deck gf180mcu
--parasitics`), produced by `layout/scripts/gen_pad_ring_assembly_dut.py`
(issue #154 / Epic #542 Phase 3A). It is what `sim/cml-driver-eye`'s
post-layout records for the *assembled block* (as opposed to the bare
`cml_driver_core` cell) are taken against, via `run_corners.py --dut`.

This mirrors `sim/tests/test_extracted_dut.py`'s rationale for
`gen_cml_driver_core_dut.py` -- the translation is exactly the kind of step
that fails silently (a wrong diode-parameter rename, a body net left
floating, a wrapper pin order that transposes OUTP/OUTN would all still
converge in ngspice and still produce plausible-looking numbers) -- adapted
for what is different about this extraction: it is already bound to real
PDK subcircuits (unlike `cml_driver_core.spice`'s bare `nfet` class), it
carries real ESD clamp diodes needing their own parameter rename, and its
substrate net is DC-tied internally rather than exposed as a wrapper pin.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "layout" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gen_pad_ring_assembly_dut as gen  # noqa: E402

EXTRACTED = REPO_ROOT / "layout" / "gds" / "gf180_tmds_pad_ring_assembly.spice"
DUT = REPO_ROOT / "layout" / "sim" / "gf180_tmds_pad_ring_assembly_dut.spice"
LVS_REF = REPO_ROOT / "layout" / "lvs" / "gf180_tmds_pad_ring_assembly.ref.spice"
SCHEMATIC_DUT = (
    REPO_ROOT / "sim" / "cml-driver-eye" / "testbench" / "cml_driver_dut.spice"
)

_X_RE = re.compile(
    r"^X(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<model>\S+)\s*(?P<params>.*)$",
    re.IGNORECASE,
)
_D_RE = re.compile(
    r"^D(?P<name>\S+)\s+(?P<a>\S+)\s+(?P<c>\S+)\s+(?P<model>\S+)\s*(?P<params>.*)$",
    re.IGNORECASE,
)
_UNITS = {"u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "m": 1e-3}


def _cards(path: Path, pattern: re.Pattern) -> list[re.Match]:
    out = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        match = pattern.match(stripped)
        if match:
            out.append(match)
    return out


def _params(text: str) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in (item.split("=", 1) for item in text.split() if "=" in item)
    }


def _value(text: str) -> float:
    """SPICE scalar -> float ('2U' -> 2e-6, '0.42P' -> 4.2e-13)."""
    text = text.strip().lower()
    if text and text[-1] in _UNITS:
        return float(text[:-1]) * _UNITS[text[-1]]
    return float(text)


class RegenerationTests(unittest.TestCase):
    """The committed DUT is exactly what the generator produces today."""

    def test_committed_dut_matches_fresh_regeneration(self):
        rendered = gen.translate(
            EXTRACTED.read_text(),
            str(EXTRACTED.relative_to(REPO_ROOT)),
            gen.sha256(EXTRACTED),
        )
        self.assertEqual(
            DUT.read_text(),
            rendered,
            "layout/sim/gf180_tmds_pad_ring_assembly_dut.spice is stale or "
            "hand-edited; regenerate with "
            "python3 layout/scripts/gen_pad_ring_assembly_dut.py",
        )

    def test_check_mode_agrees(self):
        with io.StringIO() as sink, contextlib.redirect_stdout(sink):
            status = gen.main(["--check"])
        self.assertEqual(status, 0)

    def test_unknown_x_model_is_an_error(self):
        text = EXTRACTED.read_text().replace(
            " nfet_03v3 L=0.5U", " pfet_03v3 L=0.5U", 1
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_unknown_diode_model_is_an_error(self):
        # Target the D-card's own model field, not the preceding
        # "* device instance ... diode_nd2ps_06v0" comment line that names
        # the same string first (str.replace(..., 1) takes the first
        # occurrence in the file, which is that comment).
        text = EXTRACTED.read_text().replace(
            " diode_nd2ps_06v0 A=2P", " diode_pd2nw_06v0 A=2P", 1
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_unknown_diode_parameter_is_an_error(self):
        text = EXTRACTED.read_text().replace(
            "diode_nd2ps_06v0 A=2P P=6U", "diode_nd2ps_06v0 X=2P P=6U", 1
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_exposed_vsubs_pin_is_an_error(self):
        # This extraction's whole premise (module docstring point 3') is
        # that vsubs is *not* a pin -- if that ever changed (e.g. a future
        # redraw removes the real substrate tap), the generator must refuse
        # rather than silently wrap a floating body net.
        text = EXTRACTED.read_text().replace(
            ".SUBCKT gf180_tmds_pad_ring_assembly IBIAS INN INP OUTN OUTP TAIL VSS",
            ".SUBCKT gf180_tmds_pad_ring_assembly IBIAS INN INP OUTN OUTP TAIL VSS vsubs",
            1,
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)


class ModelBindingTests(unittest.TestCase):
    """Every extracted device reaches a real PDK model, unchanged."""

    def setUp(self):
        self.extracted_x = _cards(EXTRACTED, _X_RE)
        self.extracted_d = _cards(EXTRACTED, _D_RE)
        self.translated_x = _cards(DUT, _X_RE)
        self.translated_d = _cards(DUT, _D_RE)

    def test_nfet_device_count_is_preserved(self):
        self.assertEqual(len(self.extracted_x), 338)
        # +1 for the wrapper's own `xcore` instantiation.
        self.assertEqual(len(self.translated_x), len(self.extracted_x) + 1)

    def test_diode_device_count_is_preserved(self):
        self.assertEqual(len(self.extracted_d), 40)  # 20 fingers x 2 pads
        self.assertEqual(len(self.translated_d), len(self.extracted_d))

    def test_no_bare_deck_class_survives(self):
        for line in DUT.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("*") or not stripped:
                continue
            self.assertNotRegex(
                stripped,
                r"\bnfet\b(?!_)",
                "the klt extraction-deck class label 'nfet' is not a model "
                "any PDK ships; every device must bind to nfet_03v3",
            )
            self.assertNotRegex(
                stripped,
                r"\bdiode\b(?!_)",
                "the klt extraction-deck class label 'diode' is not a model "
                "any PDK ships; every clamp must bind to diode_nd2ps_06v0",
            )

    def test_every_nfet_binds_to_the_pdk_subcircuit(self):
        devices = [m for m in self.translated_x if m.group("name") != "core"]
        self.assertTrue(devices)
        for match in devices:
            self.assertEqual(match.group("model"), "nfet_03v3")

    def test_every_diode_binds_to_the_pdk_subcircuit(self):
        self.assertTrue(self.translated_d)
        for match in self.translated_d:
            self.assertEqual(match.group("model"), "diode_nd2ps_06v0")

    def test_diode_parameters_are_renamed_area_pj_not_a_p(self):
        # klt's extraction-deck writes A/P; nfet_03v3's own model recognizes
        # AREA/PJ (see gen_pad_ring_assembly_dut.py's module docstring,
        # point 1'). Assert the renamed form, not the deck-native one.
        for match in self.translated_d:
            params = _params(match.group("params"))
            self.assertIn("area", params, match.group(0))
            self.assertIn("pj", params, match.group(0))
            self.assertNotIn("a", params, match.group(0))
            self.assertNotIn("p", params, match.group(0))

    def test_diode_parameter_values_are_carried_over_unchanged(self):
        by_name = {m.group("name"): m for m in self.translated_d}
        for src in self.extracted_d:
            dst = by_name[src.group("name")]
            src_params = _params(src.group("params"))
            dst_params = _params(dst.group("params"))
            self.assertAlmostEqual(
                _value(src_params["a"]), _value(dst_params["area"]), places=20
            )
            self.assertAlmostEqual(
                _value(src_params["p"]), _value(dst_params["pj"]), places=20
            )
            self.assertEqual(
                (src.group("a"), src.group("c")), (dst.group("a"), dst.group("c"))
            )

    def test_nfet_terminals_and_parameters_are_carried_over_verbatim(self):
        by_name = {
            m.group("name"): m for m in self.translated_x if m.group("name") != "core"
        }
        for src in self.extracted_x:
            dst = by_name[src.group("name")]
            self.assertEqual(
                (src.group("d"), src.group("g"), src.group("s"), src.group("b")),
                (dst.group("d"), dst.group("g"), dst.group("s"), dst.group("b")),
            )
            self.assertEqual(_params(src.group("params")), _params(dst.group("params")))


class WrapperTests(unittest.TestCase):
    """The wrapper presents the schematic cell boundary."""

    def setUp(self):
        self.text = DUT.read_text()

    def test_wrapper_pin_order_matches_the_schematic_dut(self):
        schematic = re.search(
            r"^\.subckt\s+cml_driver\s+(.*)$",
            SCHEMATIC_DUT.read_text(),
            re.IGNORECASE | re.MULTILINE,
        )
        post_layout = re.search(
            r"^\.subckt\s+cml_driver\s+(.*)$", self.text, re.IGNORECASE | re.MULTILINE
        )
        self.assertIsNotNone(schematic)
        self.assertIsNotNone(post_layout)
        self.assertEqual(schematic.group(1).split(), post_layout.group(1).split())
        self.assertEqual(
            post_layout.group(1).split(),
            ["OUTP", "OUTN", "INP", "INN", "IBIAS", "VSS"],
        )

    def test_core_instantiation_connects_every_pin_by_the_same_name(self):
        core_pins = re.search(
            r"^\.SUBCKT\s+gf180_tmds_pad_ring_assembly\s+(.*)$",
            self.text,
            re.MULTILINE,
        ).group(1).split()
        call = re.search(
            r"^xcore\s+(.*)\s+gf180_tmds_pad_ring_assembly\s*$", self.text, re.MULTILINE
        )
        self.assertIsNotNone(call, "the wrapper must instantiate the extracted cell")
        nets = call.group(1).split()
        self.assertEqual(nets, core_pins)
        # No leg is transposed (OUTP/OUTN or INP/INN swapped would still
        # converge and still look plausible).
        for pin in ("OUTP", "OUTN", "INP", "INN", "IBIAS", "VSS", "TAIL"):
            self.assertIn(pin, core_pins)

    def test_no_vsubs_pin_is_exposed(self):
        core_pins = re.search(
            r"^\.SUBCKT\s+gf180_tmds_pad_ring_assembly\s+(.*)$",
            self.text,
            re.MULTILINE,
        ).group(1).split()
        self.assertNotIn("vsubs", [p.lower() for p in core_pins])

    def test_substrate_net_is_dc_tied_internally(self):
        self.assertRegex(
            self.text,
            r"(?im)^Rvsubs_dctie\s+vsubs\s+0\s",
            "the extraction's own internal substrate DC-tie "
            "(Rvsubs_dctie vsubs 0 ...) must survive translation unedited "
            "-- this is what makes the missing vsubs pin electrically sound "
            "rather than a floating node",
        )


#: `klt extract --parasitics` distributes each net's parasitic resistance as
#: a star across that net's device terminals (module docstring's "resistance"
#: bullet, `layout/gds/gf180_tmds_pad_ring_assembly.spice`'s own header):
#: every device terminal lands on a *per-terminal* node named
#: `<net>__t<N>`, tied back to the real schematic net (`<net>`, the "hub")
#: by its own spoke resistor -- no device terminal connects to the bare hub
#: node directly. Folding per-finger devices back onto the LVS reference
#: (written against the real schematic nets) therefore needs the hub name,
#: not the raw per-terminal node.
_HUB_RE = re.compile(r"^(?P<hub>.+)__t\d+$")


def _hub(net: str) -> str:
    match = _HUB_RE.match(net)
    return match.group("hub") if match else net


class TopologyFoldTests(unittest.TestCase):
    """The per-finger extraction folds back onto the LVS reference cell."""

    def setUp(self):
        self.nfets = [m for m in _cards(DUT, _X_RE) if m.group("name") != "core"]
        self.diodes = _cards(DUT, _D_RE)

    def test_every_nfet_terminal_uses_the_per_finger_star_node_form(self):
        # Asserted once, up front, so every other test in this class can
        # rely on _hub() actually stripping something real rather than
        # silently no-op'ing if the extraction's node-naming convention
        # ever changes.
        sample = self.nfets[0]
        for terminal in ("d", "g", "s", "b"):
            self.assertRegex(sample.group(terminal), r"__t\d+$", sample.group(0))

    def _folded_widths(self) -> dict[tuple, float]:
        widths: dict[tuple, float] = defaultdict(float)
        for match in self.nfets:
            params = _params(match.group("params"))
            key = (
                _hub(match.group("g")),
                tuple(sorted((_hub(match.group("d")), _hub(match.group("s"))))),
                round(_value(params["l"]), 12),
            )
            widths[key] += _value(params["w"])
        return dict(widths)

    def test_folded_nfet_widths_match_the_lvs_reference(self):
        # The LVS reference is written in klt lvs's schematic-equivalent
        # plain-element form (M-cards naming the bare 'nfet' class), not the
        # X-card/nfet_03v3 form the extraction and this DUT use.
        m_re = re.compile(
            r"^M(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
            r"(?P<model>\S+)\s*(?P<params>.*)$",
            re.IGNORECASE,
        )
        reference = {}
        for match in _cards(LVS_REF, m_re):
            params = _params(match.group("params"))
            reference[match.group("name")] = (
                match.group("g"),
                tuple(sorted((match.group("d"), match.group("s")))),
                round(_value(params["l"]), 12),
                _value(params["w"]),
            )
        # The four driver devices this assembly's LVS reference carries
        # (same four as cml_driver_core.ref.spice): M1/M2 W=128u L=0.28u,
        # MT W=400u L=0.5u, MB W=20u L=0.5u.
        self.assertEqual(set(reference), {"1", "2", "T", "B"})

        folded = self._folded_widths()
        self.assertEqual(
            len(folded), 4, f"expected 4 folded devices, got {sorted(folded)}"
        )
        for name, (gate, nodes, length, width) in reference.items():
            with self.subTest(device=name):
                self.assertIn((gate, nodes, length), folded)
                self.assertAlmostEqual(
                    folded[(gate, nodes, length)], width, places=12
                )

    def test_differential_pair_is_balanced(self):
        folded = self._folded_widths()
        m1 = folded[("INP", tuple(sorted(("OUTP", "TAIL"))), 0.28e-6)]
        m2 = folded[("INN", tuple(sorted(("OUTN", "TAIL"))), 0.28e-6)]
        self.assertAlmostEqual(m1, m2, places=12)

    def test_bias_mirror_ratio_is_one_to_twenty(self):
        folded = self._folded_widths()
        tail = folded[("IBIAS", tuple(sorted(("TAIL", "VSS"))), 0.5e-6)]
        mirror = folded[("IBIAS", tuple(sorted(("IBIAS", "VSS"))), 0.5e-6)]
        self.assertAlmostEqual(tail / mirror, 20.0, places=9)

    def test_every_nfet_body_is_the_vss_star(self):
        # Unlike cml_driver_core.spice (no drawn substrate tap -> klt ties
        # every body to the deck-synthesized 'vsubs' global), this assembly
        # draws a real substrate tap wired into the VSS ring strap, so klt
        # ties every body straight to the VSS star instead -- exactly the
        # gap DR-0011 flagged and this assembly closes (layout/lvs/
        # gf180_tmds_pad_ring_assembly.ref.spice's own header: "every nfet
        # device's body net is VSS directly ... no separate vsubs net
        # exists at all"). 'vsubs' still appears in this DUT, but only as
        # the internal DC-tie's own node (see test_substrate_net_is_dc_tied_
        # internally) -- not as any device's actual body connection.
        for match in self.nfets:
            self.assertEqual(_hub(match.group("b")), "VSS", match.group(0))

    def _diode_net(self, match: re.Match) -> str:
        terminals = {_hub(match.group("a")), _hub(match.group("c"))}
        terminals.discard("VSS")
        self.assertEqual(
            len(terminals), 1, f"expected exactly one non-VSS terminal: {match.group(0)}"
        )
        return next(iter(terminals))

    def _folded_diode_geometry(self) -> dict[str, tuple]:
        """Sum area/perimeter over fingers, keyed by the protected output
        net (the terminal that is not VSS)."""
        totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for match in self.diodes:
            net = self._diode_net(match)
            params = _params(match.group("params"))
            totals[net][0] += _value(params["area"])
            totals[net][1] += _value(params["pj"])
        return {net: tuple(v) for net, v in totals.items()}

    def test_folded_diode_geometry_matches_the_lvs_reference(self):
        d_re = re.compile(
            r"^D(?P<name>\S+)\s+(?P<a>\S+)\s+(?P<c>\S+)\s+(?P<model>\S+)\s*(?P<params>.*)$",
            re.IGNORECASE,
        )
        reference = {}
        for match in _cards(LVS_REF, d_re):
            terminals = {match.group("a"), match.group("c")}
            terminals.discard("VSS")
            self.assertEqual(len(terminals), 1)
            net = next(iter(terminals))
            params = _params(match.group("params"))
            reference[net] = (_value(params["a"]), _value(params["p"]))

        self.assertEqual(set(reference), {"OUTP", "OUTN"})
        folded = self._folded_diode_geometry()
        self.assertEqual(set(folded), {"OUTP", "OUTN"})
        for net, (area, perim) in reference.items():
            with self.subTest(net=net):
                self.assertAlmostEqual(folded[net][0], area, places=18)
                self.assertAlmostEqual(folded[net][1], perim, places=15)

    def test_diode_finger_count_is_20_per_pad(self):
        folded_counts: dict[str, int] = defaultdict(int)
        for match in self.diodes:
            folded_counts[self._diode_net(match)] += 1
        self.assertEqual(folded_counts, {"OUTP": 20, "OUTN": 20})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
