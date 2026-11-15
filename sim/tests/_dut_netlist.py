"""SPICE-card parsing and schematic-boundary helpers shared by the
extracted-DUT test suites.

`test_extracted_dut.py` and `test_pad_ring_assembly_dut.py` differ in which
DUT (and which generator) they exercise; the instance-card regexes, the
SPICE scalar parser, the repo-root resolution and the wrapper pin-order
assertion they each carried as a private copy live here so a fix lands once
-- the same call the generator layer already made in
`layout/scripts/_dut_translator_cli.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "layout" / "scripts"

#: The schematic-boundary netlist every extracted DUT is checked against:
#: the ``cml_driver`` pin list it declares is the contract the post-layout
#: wrappers must present.
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
_D_RE = re.compile(
    r"^D(?P<name>\S+)\s+(?P<a>\S+)\s+(?P<c>\S+)\s+(?P<model>\S+)\s*(?P<params>.*)$",
    re.IGNORECASE,
)
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


def assert_wrapper_pin_order(
    test: TestCase, dut_text: str, subckt: str, pins: list[str] | None = None
) -> None:
    """Assert a DUT's wrapper presents the schematic cell's pin order.

    Both post-layout DUTs wrap the same schematic cell, so the ``<subckt>``
    pin list `SCHEMATIC_DUT` declares is the shared boundary contract:
    transposed legs (OUTP/OUTN, INP/INN) still converge in ngspice and still
    produce plausible-looking numbers, so order is asserted, not just set
    membership. ``pins``, when given, additionally pins the exact expected
    order for DUTs whose wrapper must carry a specific list.
    """
    schematic = re.search(
        rf"^\.subckt\s+{re.escape(subckt)}\s+(.*)$",
        SCHEMATIC_DUT.read_text(),
        re.IGNORECASE | re.MULTILINE,
    )
    post_layout = re.search(
        rf"^\.subckt\s+{re.escape(subckt)}\s+(.*)$",
        dut_text,
        re.IGNORECASE | re.MULTILINE,
    )
    test.assertIsNotNone(schematic)
    test.assertIsNotNone(post_layout)
    test.assertEqual(schematic.group(1).split(), post_layout.group(1).split())
    if pins is not None:
        test.assertEqual(post_layout.group(1).split(), pins)
