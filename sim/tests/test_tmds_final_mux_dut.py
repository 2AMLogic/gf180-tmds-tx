"""Post-layout DUT translation tests for `tmds_final_mux` -- no PDK, no
ngspice, no klt required.

    python3 -m unittest discover -s sim/tests -v

`layout/sim/tmds_final_mux_dut.spice` is the simulatable form of the
LVS-signed-off extraction `layout/gds/tmds_final_mux.spice`, produced by
`layout/scripts/gen_tmds_final_mux_dut.py` (issue #311).

That translation is exactly the kind of step that fails *silently*. Three of
its four mechanical steps have a plausible-looking wrong answer that still
converges in ngspice: a wrong MOS model binding, a body terminal left on the
wrong net, a wrapper pin order that transposes OUTP/OUTN or D0P/D0N. The
fourth is worse -- because the extracted cell and the schematic cell share
the name `tmds_final_mux`, a wrapper that failed to rename the inner
subcircuit would emit two `.subckt tmds_final_mux` definitions in one deck,
and ngspice resolves that silently rather than reporting it. Nothing else in
this repo's automated checks would catch any of these: `sim/check_records.py`
lints record format, not circuit correctness.

So the translation is asserted here, against the three files it must agree
with:

- `layout/gds/tmds_final_mux.spice` -- the extraction it is derived from
  (regeneration is byte-exact, every device is carried over, every extracted
  parameter is preserved);
- `design/netlist/tmds_final_mux.spice` -- the sized schematic, whose own
  10-pin `**.subckt` boundary and order the wrapper must present;
- `layout/lvs/tmds_final_mux.ref.spice` -- the LVS reference the layout was
  signed off against, whose four `ppolyf_u` resistors the DUT's plain
  `R`-elements must match node-pair for node-pair and ohm for ohm.

The DUT is deliberately *not* a drop-in for `sim/tmds-final-mux-eye`, whose
`tb.json` consumes the composite `sim/dut/tmds_output_stage.spice`. What that
testbench does constrain is node naming: its `v(xmux_m.sa)` /
`v(xmux_m.tail)` measurements only resolve if those stay wrapper-internal
nodes of unchanged name, which `TestbenchProbeTests` below asserts by reading
the probes out of `tb.json` rather than hard-coding them.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "layout" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gen_tmds_final_mux_dut as gen  # noqa: E402
from _dut_translator_cli import sha256  # noqa: E402

EXTRACTED = REPO_ROOT / "layout" / "gds" / "tmds_final_mux.spice"
DUT = REPO_ROOT / "layout" / "sim" / "tmds_final_mux_dut.spice"
SCHEMATIC = REPO_ROOT / "design" / "netlist" / "tmds_final_mux.spice"
LVS_REF = REPO_ROOT / "layout" / "lvs" / "tmds_final_mux.ref.spice"
TB_JSON = REPO_ROOT / "sim" / "tmds-final-mux-eye" / "testbench" / "tb.json"

#: Translated MOS: `X<name> <d> <g> <s> <b> <model> <params...>`
_X_RE = re.compile(
    r"^X(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<model>\S+)\s*(?P<params>.*)$",
    re.IGNORECASE,
)
#: Extracted MOS: `M<name> <d> <g> <s> <b> <class> <params...>`
_M_RE = re.compile(
    r"^M(?P<name>\S+)\s+(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<model>\S+)\s*(?P<params>.*)$",
    re.IGNORECASE,
)
#: Translated resistor: `R<name> <n1> <n2> <ohms>` -- body terminal dropped.
_R_PLAIN_RE = re.compile(
    r"^R(?P<name>\S+)\s+(?P<n1>\S+)\s+(?P<n2>\S+)\s+(?P<ohms>\S+)\s*$",
    re.IGNORECASE,
)
#: Extraction/LVS-reference resistor: `R<name> <n1> <n2> <body> <ohms> <class>`
_R_DECK_RE = re.compile(
    r"^R(?P<name>\S+)\s+(?P<n1>\S+)\s+(?P<n2>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<ohms>\S+)\s+(?P<cls>\S+)\s*$",
    re.IGNORECASE,
)

#: The schematic cell boundary, so a silently-reordered `**.subckt` line in
#: design/netlist/ cannot make the pin-order assertion pass vacuously.
EXPECTED_WRAPPER_PINS = [
    "OUTP",
    "OUTN",
    "D0P",
    "D0N",
    "D1P",
    "D1N",
    "CLKP",
    "CLKN",
    "VDD",
    "VSS",
]
_UNITS = {"u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "m": 1e-3}


def _logical_cards(path: Path) -> list[str]:
    """Non-comment, non-blank cards with `+` continuations folded in."""
    out: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            out[-1] = f"{out[-1]} {stripped[1:].strip()}"
            continue
        out.append(stripped)
    return out


def _cards(path: Path, pattern: re.Pattern) -> list[re.Match]:
    return [m for m in (pattern.match(c) for c in _logical_cards(path)) if m]


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


def _schematic_pins() -> list[str]:
    """The 10 pins of the sized schematic's own boundary.

    xschem writes the subcircuit boundary *commented* (`**.subckt ...`), so a
    test grepping `^\\.subckt` on design/netlist/tmds_final_mux.spice matches
    nothing and would pass vacuously. This parses the `**.` form deliberately;
    `sim/dut/tmds_output_stage.spice`'s header documents the same
    un-commenting convention.
    """
    match = re.search(
        r"^\*\*\.subckt\s+tmds_final_mux\s+(?P<pins>.*)$",
        SCHEMATIC.read_text(),
        re.IGNORECASE | re.MULTILINE,
    )
    assert match is not None, (
        f"no '**.subckt tmds_final_mux' line in {SCHEMATIC} -- xschem writes the "
        "boundary commented; see this function's docstring"
    )
    return match.group("pins").split()


def _wrapper_pins() -> list[str]:
    """The DUT's outer `.subckt tmds_final_mux` pins (not the renamed inner)."""
    match = re.search(
        r"^\.subckt\s+tmds_final_mux\s+(?P<pins>.*)$",
        DUT.read_text(),
        re.IGNORECASE | re.MULTILINE,
    )
    assert match is not None, "the DUT defines no outer .subckt tmds_final_mux"
    return match.group("pins").split()


class RegenerationTests(unittest.TestCase):
    """The committed DUT is exactly what the generator produces today."""

    def test_committed_dut_matches_fresh_regeneration(self):
        rendered = gen.translate(
            EXTRACTED.read_text(),
            str(EXTRACTED.relative_to(REPO_ROOT)),
            sha256(EXTRACTED),
        )
        self.assertEqual(
            DUT.read_text(),
            rendered,
            "layout/sim/tmds_final_mux_dut.spice is stale or hand-edited; "
            "regenerate with python3 layout/scripts/gen_tmds_final_mux_dut.py",
        )

    def test_check_mode_agrees(self):
        with io.StringIO() as sink, contextlib.redirect_stdout(sink):
            status = gen.main(["--check"])
        self.assertEqual(status, 0)

    def test_header_records_the_source_sha256(self):
        # An evidence record taken against this DUT cites it, so a
        # re-extraction not followed by a regeneration must be detectable.
        self.assertIn(f"source sha256 : {sha256(EXTRACTED)}", DUT.read_text())


class TranslationErrorTests(unittest.TestCase):
    """A malformed input raises rather than emitting a partial deck."""

    def test_unknown_mos_class_is_an_error(self):
        text = EXTRACTED.read_text().replace(" nfet L=0.28U", " pfet L=0.28U", 1)
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_unknown_resistor_class_is_an_error(self):
        text = EXTRACTED.read_text().replace("103.25 ppolyf_u", "103.25 nplus_u", 1)
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_unhandled_card_is_an_error(self):
        text = EXTRACTED.read_text().replace(
            ".ENDS tmds_final_mux", "C1 OUTP VSS 1f\n.ENDS tmds_final_mux"
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_missing_body_net_pin_is_an_error(self):
        # Drop `vsubs` from the boundary: the wrapper's one explicit body tie
        # would otherwise silently leave every device's bulk floating.
        text = EXTRACTED.read_text().replace("+ VDD VSS vsubs", "+ VDD VSS", 1)
        self.assertIn("+ VDD VSS\n", text)
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_missing_schematic_pin_is_an_error(self):
        # Drop VDD: the wrapper cannot present the schematic boundary.
        text = EXTRACTED.read_text().replace("+ VDD VSS vsubs", "+ VSS vsubs", 1)
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_wrong_extracted_cell_name_is_an_error(self):
        text = EXTRACTED.read_text().replace(
            ".SUBCKT tmds_final_mux ", ".SUBCKT some_other_cell ", 1
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)

    def test_orphan_continuation_line_is_an_error(self):
        with self.assertRaises(gen.TranslationError):
            gen.translate("+ VDD VSS vsubs\n", "synthetic", "0" * 64)

    def test_resistor_body_on_an_unexpected_net_is_an_error(self):
        text = EXTRACTED.read_text().replace(
            "R$659 OUTP TOP vsubs 103.25", "R$659 OUTP TOP VSS 103.25", 1
        )
        with self.assertRaises(gen.TranslationError):
            gen.translate(text, "synthetic", "0" * 64)


class ModelBindingTests(unittest.TestCase):
    """Every extracted transistor reaches a real PDK model, unchanged."""

    def setUp(self):
        self.extracted = _cards(EXTRACTED, _M_RE)
        self.translated = [
            m for m in _cards(DUT, _X_RE) if m.group("name") != "core"
        ]

    def test_device_count_is_preserved(self):
        self.assertEqual(len(self.extracted), 658)
        self.assertEqual(len(self.translated), len(self.extracted))

    def test_no_bare_deck_class_survives_on_a_card(self):
        for card in _logical_cards(DUT):
            self.assertNotRegex(
                card,
                r"\bnfet\b(?!_)",
                "the klt extraction-deck class label 'nfet' is not a model any "
                "PDK ships; every device must bind to nfet_03v3",
            )
            self.assertNotRegex(
                card,
                r"\bppolyf_u\b",
                "the klt extraction-deck resistor class label must not survive "
                "on a card; ppolyf_u bodies become plain ngspice R elements",
            )

    def test_every_device_binds_to_the_pdk_subcircuit(self):
        self.assertTrue(self.translated)
        for match in self.translated:
            self.assertEqual(match.group("model"), "nfet_03v3")

    def test_terminals_and_parameters_are_carried_over_verbatim(self):
        by_name = {m.group("name").lstrip("M"): m for m in self.translated}
        self.assertEqual(len(by_name), len(self.translated))
        for src in self.extracted:
            dst = by_name[src.group("name")]
            self.assertEqual(
                (src.group("d"), src.group("g"), src.group("s"), src.group("b")),
                (dst.group("d"), dst.group("g"), dst.group("s"), dst.group("b")),
            )
            self.assertEqual(_params(src.group("params")), _params(dst.group("params")))

    def test_junction_geometry_is_present_on_every_device(self):
        # `klt extract --pdk` drops AS/AD/PS/PD and nfet_03v3 defaults them to
        # zero -- i.e. no drain-junction capacitance on OUTP/OUTN, the loading
        # term a post-layout eye measurement most depends on. This asserts the
        # AS/AD/PS/PD-bearing form is what we simulate.
        for match in self.translated:
            params = _params(match.group("params"))
            for key in ("as", "ad", "ps", "pd", "w", "l"):
                self.assertIn(key, params, match.group(0))
                self.assertGreater(_value(params[key]), 0.0, match.group(0))

    def test_every_device_body_is_the_deck_synthesized_net(self):
        # If any finger's body were extracted onto some other net, tying
        # vsubs to VSS in the wrapper would silently leave it floating.
        for match in self.translated:
            self.assertEqual(match.group("b"), "vsubs", match.group(0))


class ResistorTests(unittest.TestCase):
    """The four ppolyf_u bodies become plain R elements, ohms unchanged."""

    def setUp(self):
        self.extracted = _cards(EXTRACTED, _R_DECK_RE)
        self.translated = _cards(DUT, _R_PLAIN_RE)

    def test_resistor_count_is_preserved(self):
        self.assertEqual(len(self.extracted), 4)
        self.assertEqual(len(self.translated), 4)

    def test_ohms_and_nodes_are_carried_over_with_the_body_dropped(self):
        by_name = {m.group("name"): m for m in self.translated}
        self.assertEqual(len(by_name), 4)
        for src in self.extracted:
            dst = by_name[src.group("name")]
            self.assertEqual(
                (src.group("n1"), src.group("n2")),
                (dst.group("n1"), dst.group("n2")),
            )
            self.assertEqual(_value(src.group("ohms")), _value(dst.group("ohms")))

    def test_the_extraction_values_are_the_committed_sizing(self):
        # design/tmds-final-mux-sizing.md's "Committed netlist values" table at
        # the res_typical corner (rsh = 350 ohm/sq): RC 46.375, RLP/RLN 103.25,
        # RREF 4340.
        self.assertEqual(
            sorted(_value(m.group("ohms")) for m in self.translated),
            sorted([46.375, 103.25, 103.25, 4340.0]),
        )

    def test_resistors_fold_onto_the_lvs_reference_network(self):
        # The LVS reference the layout was signed off against carries the same
        # four bodies as plain R-elements (RC/RLP/RLN/RREF). Matching it as an
        # unordered node-pair -> ohms multiset catches a resistor landing on
        # the wrong net, which would still converge and still look plausible.
        def network(matches):
            return sorted(
                (
                    tuple(sorted((m.group("n1").upper(), m.group("n2").upper()))),
                    _value(m.group("ohms")),
                )
                for m in matches
            )

        reference = _cards(LVS_REF, _R_DECK_RE)
        self.assertEqual(len(reference), 4)
        self.assertEqual(network(self.translated), network(reference))


class WrapperTests(unittest.TestCase):
    """The wrapper presents the schematic boundary, body tied to VSS."""

    def setUp(self):
        self.text = DUT.read_text()

    def test_the_schematic_level_name_is_defined_exactly_once(self):
        # The extracted cell and the schematic cell share the name
        # `tmds_final_mux`. Two same-named .subckt definitions in one deck are
        # resolved silently by ngspice, so this is the assertion that the
        # inner subcircuit really was renamed.
        definitions = re.findall(
            r"^\.subckt\s+tmds_final_mux\s", self.text, re.IGNORECASE | re.MULTILINE
        )
        self.assertEqual(len(definitions), 1, "expected exactly one wrapper definition")
        inner = re.findall(
            r"^\.subckt\s+tmds_final_mux_extracted\s",
            self.text,
            re.IGNORECASE | re.MULTILINE,
        )
        self.assertEqual(len(inner), 1, "expected exactly one renamed inner subcircuit")

    def test_wrapper_pin_order_matches_the_schematic(self):
        schematic = _schematic_pins()
        self.assertEqual(schematic, EXPECTED_WRAPPER_PINS)
        self.assertEqual(_wrapper_pins(), schematic)

    def test_core_instantiation_ties_the_body_net_to_vss(self):
        core_pins = re.search(
            r"^\.SUBCKT\s+tmds_final_mux_extracted\s+(.*)$",
            self.text,
            re.IGNORECASE | re.MULTILINE,
        ).group(1).split()
        call = re.search(
            r"^xcore\s+(.*)\s+tmds_final_mux_extracted\s*$",
            self.text,
            re.IGNORECASE | re.MULTILINE,
        )
        self.assertIsNotNone(call, "the wrapper must instantiate the extracted cell")
        nets = call.group(1).split()
        self.assertEqual(len(nets), len(core_pins))
        mapping = dict(zip(core_pins, nets))
        self.assertEqual(
            mapping["vsubs"],
            "VSS",
            "the deck-synthesized body net must be tied to VSS -- an NMOS-only "
            "cell in the common p-substrate, matching the sized schematic's B=VSS",
        )
        # Every schematic pin connects to its own same-named wrapper port, so
        # no leg is transposed (OUTP/OUTN or D0P/D0N swapped would still
        # converge and still look plausible).
        for pin in EXPECTED_WRAPPER_PINS:
            self.assertEqual(mapping[pin], pin)

    def test_promoted_internal_nodes_stay_internal(self):
        core_pins = re.search(
            r"^\.SUBCKT\s+tmds_final_mux_extracted\s+(.*)$",
            self.text,
            re.IGNORECASE | re.MULTILINE,
        ).group(1).split()
        wrapper = _wrapper_pins()
        promoted = [p for p in core_pins if p not in wrapper and p != "vsubs"]
        self.assertEqual(promoted, ["IBIAS", "SA", "SB", "TAIL", "TOP"])
        call = re.search(
            r"^xcore\s+(.*)\s+tmds_final_mux_extracted\s*$",
            self.text,
            re.IGNORECASE | re.MULTILINE,
        )
        mapping = dict(zip(core_pins, call.group(1).split()))
        for pin in promoted:
            # Same name, and not a wrapper port: a node of the wrapper.
            self.assertEqual(mapping[pin], pin)
            self.assertNotIn(pin, wrapper)


class TestbenchProbeTests(unittest.TestCase):
    """`v(xmux_m.<node>)` measurements resolve against this wrapper."""

    def test_every_tb_probe_node_is_a_wrapper_internal_node(self):
        # Read the probes out of tb.json rather than hard-coding them, so
        # adding a probe there tells you whether this DUT supports it.
        probes = sorted(
            set(re.findall(r"\bxmux_m\.([a-z0-9_]+)\b", TB_JSON.read_text()))
        )
        self.assertEqual(probes, ["sa", "tail"])

        text = DUT.read_text()
        core_pins = re.search(
            r"^\.SUBCKT\s+tmds_final_mux_extracted\s+(.*)$",
            text,
            re.IGNORECASE | re.MULTILINE,
        ).group(1).split()
        mapping = dict(
            zip(
                core_pins,
                re.search(
                    r"^xcore\s+(.*)\s+tmds_final_mux_extracted\s*$",
                    text,
                    re.IGNORECASE | re.MULTILINE,
                ).group(1).split(),
            )
        )
        wrapper = {p.lower() for p in _wrapper_pins()}
        nodes = {net.lower() for net in mapping.values()}
        for probe in probes:
            # The node exists inside the wrapper...
            self.assertIn(
                probe,
                nodes,
                f"v(xmux_m.{probe}) would not resolve: no such node in the wrapper",
            )
            # ...and is internal to it, not a port (a port would be named
            # from the testbench side as v(<net>), not v(xmux_m.<node>)).
            self.assertNotIn(probe, wrapper)

    def test_tb_json_still_consumes_the_composite_dut(self):
        # This fragment is the mux half only; if tb.json is ever repointed at
        # it directly, that is the deferred composite work landing, and this
        # test's premise (and the generator header's note) needs revisiting.
        self.assertEqual(
            json.loads(TB_JSON.read_text())["dut"], "sim/dut/tmds_output_stage.spice"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
