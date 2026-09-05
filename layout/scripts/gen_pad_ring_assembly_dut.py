#!/usr/bin/env python3
"""Derive a simulatable DUT fragment from the LVS-signed-off, parasitics-
extracted assembled block, for issue #154 (Epic #542 Phase 3).

`klt extract --deck gf180mcu --parasitics` writes
`layout/gds/gf180_tmds_pad_ring_assembly.spice`: the full-parasitic
(device + interconnect R/C) extraction of
`layout/gds/gf180_tmds_pad_ring_assembly.gds` (issue #149) -- the driver core
assembled with its diode-clamped pad-ring/ESD structure. Until this issue,
that file had only structural DRC/LVS signoff (`measurements/
characterization.md` item 2); no electrical/PVT simulation of the assembled
block existed.

Unlike `gen_cml_driver_core_dut.py` (the bare `cml_driver_core` extraction,
which required rebinding the klt extraction-deck's `nfet` class to
`nfet_03v3` by hand), this extraction is **already bound to real PDK
subcircuits**: every MOSFET is an `X`-card naming `nfet_03v3` directly, every
ESD clamp diode is a `D`-card naming `diode_nd2ps_06v0` directly, and the
deck-synthesized substrate net `vsubs` is not exposed as a pin at all -- it
is DC-tied internally (`Rvsubs_dctie vsubs 0 1e+12`), because the assembly
draws a real substrate tap wired into the DVSS ring strap (`layout/scripts/
gen_pad_ring_assembly.py`'s own docstring, "A substrate tap on a real net").
So of the three translations `gen_cml_driver_core_dut.py` documents (model
binding, body-net tie, cell-boundary adaptation), only a narrow parameter-
name variant of the first, plus the third, apply here:

1'. **Diode parameter naming.** klt's extraction deck writes each clamp
    diode's junction geometry as `D<name> <a> <c> diode_nd2ps_06v0 A=<area>
    P=<perimeter>` -- `A`/`P` are the *extraction deck's* generic diode
    parameter names (this repo's own `sim/esd-diode-clamp-cv` testbench
    independently confirms the values: 20 fingers x `A=2P` = `area=40p`,
    matching that testbench's `area=40p pj=120u` base-clamp point exactly).
    gf180mcu's ngspice model (`sm141064.ngspice`'s `.model diode_nd2ps_06v0
    d level=3`) does not recognize `A`/`P` as parameter names at all -- it
    takes `AREA`/`PJ` (confirmed against `sim/esd-diode-clamp-cv/testbench/
    esd_diode_clamp_cv.spice`'s own working D-cards) -- so ngspice rejects
    the deck-native card verbatim ("unknown parameter (a)"). This script
    renames the two keys, carrying the numeric values through unchanged; no
    other D-card parameter appears in this extraction (checked: only `A`/`P`
    ever appear on a `D` line here).
3'. **Cell boundary.** The extracted subcircuit is
   `gf180_tmds_pad_ring_assembly IBIAS INN INP OUTN OUTP TAIL VSS` --
   alphabetical pin order, same convention as `cml_driver_core`'s own
   extraction. `sim/cml-driver-eye`'s testbench instantiates
   `cml_driver OUTP OUTN INP INN IBIAS VSS`, the schematic cell's own pin
   order. This script wraps the extracted subcircuit in a `cml_driver`-named
   subcircuit presenting that same boundary, so the *identical* testbench
   deck that already produced the schematic-level and core-extracted records
   runs unchanged against this third DUT too -- `sim/README.md`'s "Post-layout
   re-runs: same testbench, --dut swapped" convention, one level deeper
   (assembly, not just core).

What this DOES add relative to the two existing `sim/cml-driver-eye` records
(state this in the record, per the coverage-honesty requirement):

- **The real diode-clamp ESD structure** (`diode_nd2ps_06v0`, 20-finger array
  per output), previously simulated only in isolation
  (`sim/esd-diode-clamp-cv`), now in circuit with the driver.
- **The real bond pad + interconnect parasitic R/C** the DR-0005 budget
  measures (`design/esd-capacitance-budget.md` Sec.10.5: 0.094 pF `OUTP` /
  0.075 pF `OUTN`), extracted with `klt extract --parasitics` -- a genuine
  interconnect-RC extraction, not the device-level-only extraction
  `cml_driver_core.spice` carries (`measurements/characterization.md` item 2
  states that gap by name: "no interconnect parasitic R/C" on the core-only
  extraction). This DUT closes that gap for the assembled block, though NOT
  for the bare core cell in isolation -- a distinct, still-open remainder,
  named in the record.

What this does NOT add (state this too):

- **No package, no board, no bond wire.** The pad's own drawn parasitics are
  captured; anything beyond the die edge is not. The testbench's own in-deck
  0/1/2 pF pad-capacitance sweep (`cml_driver_eye.spice`'s `c0`/`c1`/`c2`
  copies) now stacks on top of this DUT's real ~0.1 pF on-die parasitic,
  rather than standing in for the whole pad as it did against the bare-core
  DUT -- so those three points should be read as "on-die pad + N pF of
  additional off-die loading" against this DUT, not as three independent
  estimates of the whole pad capacitance. State this in the record.
- **No HBM/CDM stress simulation.** The diodes are in the small-signal/
  operating-point circuit; no ESD pulse event is applied here. HBM/CDM
  qualification remains issue #145's separate, structurally-unaddressable
  (pre-silicon) gap.

Usage (from the repo root):

    python3 layout/scripts/gen_pad_ring_assembly_dut.py \
        -i layout/gds/gf180_tmds_pad_ring_assembly.spice \
        -o layout/sim/gf180_tmds_pad_ring_assembly_dut.spice

The committed output is checked against a fresh regeneration by
`sim/tests/test_pad_ring_assembly_dut.py`, so a hand edit to either file
fails CI.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = REPO_ROOT / "layout" / "gds" / "gf180_tmds_pad_ring_assembly.spice"
DEFAULT_OUTPUT = REPO_ROOT / "layout" / "sim" / "gf180_tmds_pad_ring_assembly_dut.spice"

#: The extracted cell, and the schematic-level cell the wrapper presents --
#: same wrapper name/pin-order convention as gen_cml_driver_core_dut.py, so
#: sim/cml-driver-eye's testbench (which `.include`s whichever DUT fragment
#: tb.json/--dut names) runs unchanged against this DUT too.
CORE_SUBCKT = "gf180_tmds_pad_ring_assembly"
WRAPPER_SUBCKT = "cml_driver"
WRAPPER_PINS = ("OUTP", "OUTN", "INP", "INN", "IBIAS", "VSS")

#: Device classes this extraction is allowed to carry -- already bound to
#: real gf180mcu PDK subcircuits, unlike gen_cml_driver_core_dut.py's input
#: (which still names the klt extraction-deck's bare 'nfet' class). Anything
#: else is an error: silently passing an unrecognized class through would
#: produce a deck that either fails to parse or simulates the wrong device.
KNOWN_X_MODELS = ("nfet_03v3", "diode_nd2ps_06v0")

_SUBCKT_RE = re.compile(r"^\.SUBCKT\s+(?P<name>\S+)\s+(?P<pins>.*)$", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\.ENDS\b", re.IGNORECASE)
_X_RE = re.compile(r"^X\S+\s+(?:\S+\s+){4}(?P<model>\S+)\b")
_D_RE = re.compile(
    r"^D(?P<name>\S+)\s+(?P<a>\S+)\s+(?P<c>\S+)\s+(?P<model>\S+)\s*(?P<params>.*)$"
)
_BARE_DECK_CLASS_RE = re.compile(r"\bnfet\b(?!_)|\bdiode\b(?!_)")

#: klt extraction-deck diode parameter names -> the names gf180mcu's own
#: ngspice model (`sm141064.ngspice`'s `.model diode_nd2ps_06v0 d level=3`)
#: actually recognizes. Confirmed against `sim/esd-diode-clamp-cv`'s working
#: D-cards (`area=40p pj=120u`, ...). Any other D-card parameter is an error
#: (see DIODE_KNOWN_PARAMS below) rather than silently passed through
#: unrenamed, which would produce a deck ngspice rejects outright -- exactly
#: the failure this script exists to catch before a record is minted from it.
DIODE_PARAM_RENAME = {"a": "area", "p": "pj"}


class TranslationError(RuntimeError):
    """The extracted netlist is not the shape this script knows how to bind."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translate(text: str, source_label: str, source_sha256: str) -> str:
    """Return the DUT fragment for one extracted `gf180_tmds_pad_ring_assembly`
    netlist -- a thin pin-reorder wrapper, since the source is already bound
    to real PDK subcircuits with full parasitic R/C (see module docstring)."""
    core_pins: list[str] | None = None
    body: list[str] = []
    x_devices = 0

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            continue
        if stripped.startswith("*"):
            body.append(line)
            continue

        subckt = _SUBCKT_RE.match(stripped)
        if subckt:
            if subckt.group("name") != CORE_SUBCKT:
                raise TranslationError(
                    f"expected .SUBCKT {CORE_SUBCKT}, found {subckt.group('name')!r}"
                )
            core_pins = subckt.group("pins").split()
            body.append(f".SUBCKT {CORE_SUBCKT} {' '.join(core_pins)}")
            continue

        if _ENDS_RE.match(stripped):
            body.append(f".ENDS {CORE_SUBCKT}")
            continue

        if _BARE_DECK_CLASS_RE.search(stripped) and not stripped.upper().startswith(
            ("X", "*")
        ):
            raise TranslationError(
                f"unexpected bare extraction-deck device class on card {stripped!r}; "
                "this script expects an already-PDK-bound extraction "
                "(klt extract --deck gf180mcu with real X-card model names)"
            )

        x_match = _X_RE.match(stripped)
        if x_match:
            model = x_match.group("model")
            if model not in KNOWN_X_MODELS:
                raise TranslationError(
                    f"unknown X-card model {model!r} on card {stripped!r}; "
                    f"this script only recognizes {KNOWN_X_MODELS!r} -- if a new "
                    "device family was added to the assembly, extend this list "
                    "deliberately rather than silently passing it through"
                )
            x_devices += 1
            body.append(line)
            continue

        d_match = _D_RE.match(stripped)
        if d_match:
            model = d_match.group("model")
            if model != "diode_nd2ps_06v0":
                raise TranslationError(
                    f"unknown D-card model {model!r} on card {stripped!r}; "
                    "this script only recognizes 'diode_nd2ps_06v0' -- if a new "
                    "clamp topology was added to the assembly, extend this "
                    "deliberately rather than silently passing it through"
                )
            params = d_match.group("params").strip()
            renamed_parts = []
            for token in params.split():
                if "=" not in token:
                    raise TranslationError(
                        f"unexpected non key=value token {token!r} on D-card "
                        f"{stripped!r}"
                    )
                key, _, value = token.partition("=")
                new_key = DIODE_PARAM_RENAME.get(key.lower())
                if new_key is None:
                    raise TranslationError(
                        f"unrecognized diode parameter {key!r} on card {stripped!r}; "
                        f"this script only knows how to rename {sorted(DIODE_PARAM_RENAME)!r} "
                        "(klt's deck-native A/P) to the gf180mcu model's own "
                        "AREA/PJ names -- extend DIODE_PARAM_RENAME deliberately "
                        "if the extraction started emitting a new one"
                    )
                renamed_parts.append(f"{new_key}={value}")
            body.append(
                f"D{d_match.group('name')} {d_match.group('a')} {d_match.group('c')} "
                f"{model} {' '.join(renamed_parts)}"
            )
            continue

        # R/C/X/continuation ('+') cards, and anything else the extraction
        # emits (parasitic resistors/capacitors), pass through unchanged --
        # they already name real device models or are ideal passives,
        # nothing to rebind.
        body.append(line)

    if core_pins is None:
        raise TranslationError(f"no .SUBCKT {CORE_SUBCKT} found in the input netlist")
    if x_devices == 0:
        raise TranslationError("no recognized X-card devices found in the input netlist")
    missing = [pin for pin in WRAPPER_PINS if pin not in core_pins]
    if missing:
        raise TranslationError(
            f"extracted cell is missing pin(s) {missing} needed by "
            f".subckt {WRAPPER_SUBCKT}; got {core_pins}"
        )
    if "vsubs" in core_pins:
        raise TranslationError(
            "extracted cell unexpectedly exposes a 'vsubs' pin -- this script "
            "assumes the assembly's substrate net is internal (DC-tied via "
            "Rvsubs_dctie), per gen_pad_ring_assembly.py's real-substrate-tap "
            "design. Re-read this script's header before changing the wrapper "
            "if that assumption changed."
        )

    # Map every core pin to the net the wrapper connects it to: its own
    # same-named port for the six schematic pins, and a wrapper-internal node
    # of the same name for anything else the extraction promoted to a pin
    # (TAIL).
    connections = list(core_pins)
    internal = [pin for pin in core_pins if pin not in WRAPPER_PINS]

    header = [
        f"* {DEFAULT_OUTPUT.name} -- post-layout DUT fragment for sim/cml-driver-eye",
        "* (assembled driver+pad-ring+ESD block, issue #154 / Epic #542 Phase 3)",
        "*",
        "* GENERATED by layout/scripts/gen_pad_ring_assembly_dut.py -- do not edit.",
        f"* source        : {source_label}",
        f"* source sha256 : {source_sha256}",
        f"* devices       : {x_devices} extracted X-card devices "
        f"(nfet_03v3 + diode_nd2ps_06v0 ESD clamp), already PDK-bound",
        "*",
        "* Unlike gen_cml_driver_core_dut.py's input (the bare core cell), this",
        "* extraction is already bound to real PDK subcircuits and already carries",
        "* full parasitic R/C (klt extract --parasitics) -- see this script's own",
        "* module docstring for what that does and does not add relative to the",
        "* existing sim/cml-driver-eye schematic/core-extracted records. The one",
        "* mechanical step needed is a pin-order wrapper:",
        f"*   a wrapper presenting the schematic cell boundary "
        f"({WRAPPER_SUBCKT} {' '.join(WRAPPER_PINS)}),",
        "*   so sim/cml-driver-eye's testbench runs unchanged against this DUT too.",
        "*",
        "* NOT modelled here (state this in any record taken against this netlist):",
        "*   - no package, no board, no bond wire -- only the drawn on-die pad;",
        "*   - no HBM/CDM ESD pulse event -- the clamp diodes are in the",
        "*     small-signal/operating-point circuit only (issue #145, separate).",
        "",
        f".subckt {WRAPPER_SUBCKT} {' '.join(WRAPPER_PINS)}",
        f"* {CORE_SUBCKT} pin order is the extraction's own (alphabetical, plus the",
        f"* promoted internal node{'s' if len(internal) != 1 else ''} "
        f"{', '.join(internal) if internal else '(none)'}).",
        f"xcore {' '.join(connections)} {CORE_SUBCKT}",
        ".ends",
        "",
    ]
    return "\n".join(header + body) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"extracted netlist to translate (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"DUT fragment to write (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the existing output differs from a fresh "
        "regeneration (what sim/tests/test_pad_ring_assembly_dut.py asserts)",
    )
    args = parser.parse_args(argv)

    source = args.input.resolve()
    try:
        label = str(source.relative_to(REPO_ROOT))
    except ValueError:
        label = source.name

    try:
        rendered = translate(source.read_text(), label, sha256(source))
    except TranslationError as exc:
        print(f"error: {source}: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not args.output.exists():
            print(f"error: {args.output} does not exist", file=sys.stderr)
            return 1
        if args.output.read_text() != rendered:
            print(
                f"error: {args.output} is stale -- regenerate it with\n"
                f"  python3 {Path(__file__).relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {args.output} matches a fresh regeneration")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
