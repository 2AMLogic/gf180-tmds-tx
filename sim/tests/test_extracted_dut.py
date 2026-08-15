"""Post-layout DUT translation tests -- no PDK, no ngspice, no klt required.

    python3 -m unittest discover -s sim/tests -v

`layout/sim/cml_driver_core_dut.spice` is the simulatable form of the
LVS-signed-off extraction `layout/gds/cml_driver_core.spice`, produced by
`layout/scripts/gen_cml_driver_core_dut.py` (issue #34). It is what
`sim/cml-driver-eye`'s post-layout records are taken against, via
`run_corners.py --dut`.

That translation is exactly the kind of step that fails *silently*: a wrong
model binding, a bulk terminal left on the wrong net, or a wrapper pin order
that transposes OUTP/OUTN all still converge in ngspice and still produce
plausible-looking swing/common-mode numbers. Nothing else in this repo's
automated checks would catch it -- `sim/check_records.py` lints record
format, not circuit correctness. So the translation is asserted here,
against the two files it must agree with:

- `layout/gds/cml_driver_core.spice` -- the extraction it is derived from
  (regeneration is byte-exact, every device is carried over, every extracted
  parameter is preserved);
- `layout/lvs/cml_driver_core.ref.spice` -- the LVS reference the layout was
  signed off against, whose four devices' total widths the per-finger
  extraction must fold back into, on the topology the schematic specifies.
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

import gen_cml_driver_core_dut as gen  # noqa: E402

EXTRACTED = REPO_ROOT / "layout" / "gds" / "cml_driver_core.spice"
DUT = REPO_ROOT / "layout" / "sim" / "cml_driver_core_dut.spice"
LVS_REF = REPO_ROOT / "layout" / "lvs" / "cml_driver_core.ref.spice"
SCHEMATIC_DUT = (
    REPO_ROOT / "sim" / "cml-driver-eye" / "testbench" / "cml_driver_dut.spice"
)

_X_RE = re.compile(
    r"^X(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<model>\S+)\s*(?P<params>.*)$",
    re.IGNORECASE,
)
_M_RE = re.compile(
    r"^M(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<model>\S+)\s*(?P<params>.*)$",
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
            "layout/sim/cml_driver_core_dut.spice is stale or hand-edited; "
            "regenerate with python3 layout/scripts/gen_cml_driver_core_dut.py",
        )

    def test_check_mode_agrees(self):
        with io.StringIO() as sink, contextlib.redirect_stdout(sink):
            status = gen.main(["--check"])
        self.assertEqual(status, 0)

    def test_unknown_device_class_is_an_error(self):
        text = EXTRACTED.read_text().replace(" nfet L=0.5U", " pfet L=0.5U", 1)
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_unhandled_card_is_an_error(self):
        text = EXTRACTED.read_text().replace(
            ".ENDS cml_driver_core", "R1 OUTP VSS 50\n.ENDS cml_driver_core"
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)


class ModelBindingTests(unittest.TestCase):
    """Every extracted device reaches a real PDK model, unchanged."""

    def setUp(self):
        self.extracted = _cards(EXTRACTED, _M_RE)
        self.translated = _cards(DUT, _X_RE)

    def test_device_count_is_preserved(self):
        self.assertEqual(len(self.extracted), 338)
        # +1 for the wrapper's own `xcore` instantiation.
        self.assertEqual(len(self.translated), len(self.extracted) + 1)

    def test_no_bare_deck_class_survives(self):
        for line in DUT.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("*") or not stripped:
                continue
            self.assertNotRegex(
                stripped,
                r"\bnfet\b(?!_)",
                "the klt extraction-deck class label 'nfet' is not a model any "
                "PDK ships; every device must bind to nfet_03v3",
            )

    def test_every_device_binds_to_the_pdk_subcircuit(self):
        devices = [m for m in self.translated if m.group("name") != "core"]
        self.assertTrue(devices)
        for match in devices:
            self.assertEqual(match.group("model"), "nfet_03v3")

    def test_terminals_and_parameters_are_carried_over_verbatim(self):
        by_name = {
            m.group("name").lstrip("M"): m
            for m in self.translated
            if m.group("name") != "core"
        }
        for src in self.extracted:
            dst = by_name[src.group("name")]
            self.assertEqual(
                (src.group("d"), src.group("g"), src.group("s"), src.group("b")),
                (dst.group("d"), dst.group("g"), dst.group("s"), dst.group("b")),
            )
            self.assertEqual(_params(src.group("params")), _params(dst.group("params")))

    def test_junction_geometry_is_present_on_every_device(self):
        # `klt extract --pdk` drops AS/AD/PS/PD and nfet_03v3 defaults them to
        # zero -- i.e. no drain-junction capacitance on OUTP/OUTN, the one
        # post-layout loading term this cell's eye measurement most depends
        # on. This asserts the AS/AD/PS/PD-bearing form is what we simulate.
        for match in self.translated:
            if match.group("name") == "core":
                continue
            params = _params(match.group("params"))
            for key in ("as", "ad", "ps", "pd", "w", "l"):
                self.assertIn(key, params, match.group(0))
                self.assertGreater(_value(params[key]), 0.0, match.group(0))


class WrapperTests(unittest.TestCase):
    """The wrapper presents the schematic cell boundary, body tied to VSS."""

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

    def test_core_instantiation_ties_the_body_net_to_vss(self):
        core_pins = re.search(
            r"^\.SUBCKT\s+cml_driver_core\s+(.*)$", self.text, re.MULTILINE
        ).group(1).split()
        call = re.search(r"^xcore\s+(.*)\s+cml_driver_core\s*$", self.text, re.MULTILINE)
        self.assertIsNotNone(call, "the wrapper must instantiate cml_driver_core")
        nets = call.group(1).split()
        self.assertEqual(len(nets), len(core_pins))
        mapping = dict(zip(core_pins, nets))
        self.assertEqual(
            mapping["vsubs"],
            "VSS",
            "the deck-synthesized body net must be tied to VSS -- an NMOS-only "
            "cell in the common p-substrate (design/cml-driver-sizing.md sec 0)",
        )
        # Every schematic pin connects to its own same-named wrapper port, so
        # no leg is transposed (OUTP/OUTN or INP/INN swapped would still
        # converge and still look plausible).
        for pin in ("OUTP", "OUTN", "INP", "INN", "IBIAS", "VSS"):
            self.assertEqual(mapping[pin], pin)
        # TAIL is promoted to a pin by the extraction; it stays an internal
        # node of the wrapper, which is what makes the testbench's device
        # stress measurements (v(xvhi.tail)) resolve unchanged.
        self.assertEqual(mapping["TAIL"], "TAIL")


class TopologyFoldTests(unittest.TestCase):
    """The per-finger extraction folds back onto the LVS reference cell."""

    def setUp(self):
        self.devices = [m for m in _cards(DUT, _X_RE) if m.group("name") != "core"]

    def _folded(self) -> dict[tuple, float]:
        """Sum W over fingers, keyed by (gate, {channel nodes}, L)."""
        widths: dict[tuple, float] = defaultdict(float)
        for match in self.devices:
            params = _params(match.group("params"))
            key = (
                match.group("g"),
                tuple(sorted((match.group("d"), match.group("s")))),
                round(_value(params["l"]), 12),
            )
            widths[key] += _value(params["w"])
        return dict(widths)

    def test_folded_widths_match_the_lvs_reference(self):
        reference = {}
        for match in _cards(LVS_REF, _M_RE):
            params = _params(match.group("params"))
            reference["M" + match.group("name")] = (
                match.group("g"),
                tuple(sorted((match.group("d"), match.group("s")))),
                round(_value(params["l"]), 12),
                _value(params["w"]),
            )
        # The four devices the layout was signed off against (issue #22):
        # M1/M2 W=128u L=0.28u, MT W=400u L=0.5u, MB W=20u L=0.5u.
        self.assertEqual(set(reference), {"M1", "M2", "MT", "MB"})

        folded = self._folded()
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
        folded = self._folded()
        m1 = folded[("INP", tuple(sorted(("OUTP", "TAIL"))), 0.28e-6)]
        m2 = folded[("INN", tuple(sorted(("OUTN", "TAIL"))), 0.28e-6)]
        self.assertAlmostEqual(m1, m2, places=12)

    def test_bias_mirror_ratio_is_one_to_twenty(self):
        folded = self._folded()
        tail = folded[("IBIAS", tuple(sorted(("TAIL", "VSS"))), 0.5e-6)]
        mirror = folded[("IBIAS", tuple(sorted(("IBIAS", "VSS"))), 0.5e-6)]
        self.assertAlmostEqual(tail / mirror, 20.0, places=9)

    def test_every_device_body_is_the_deck_synthesized_net(self):
        # If any finger's body were extracted onto some other net, tying
        # vsubs to VSS in the wrapper would silently leave it floating.
        for match in self.devices:
            self.assertEqual(match.group("b"), "vsubs", match.group(0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
