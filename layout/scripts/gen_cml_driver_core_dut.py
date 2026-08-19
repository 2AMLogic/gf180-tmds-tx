#!/usr/bin/env python3
"""Derive a simulatable DUT fragment from the LVS-signed-off extracted netlist.

`klt extract --deck gf180mcu` writes `layout/gds/cml_driver_core.spice`: the
device-level, LVS-verified extraction of `layout/gds/cml_driver_core.gds`
(issue #22). That file is the LVS signoff artifact and is **not** directly
simulatable, for three reasons this script -- and only this script --
mechanically resolves. Nothing here is a hand edit: run it and diff.

1. **Model binding.** Every extracted device is an `M`-card naming the bare
   class label `nfet`:

       M$1 TAIL IBIAS VSS vsubs nfet L=0.5U W=2U AS=0.42P ...

   `nfet` is klt's own extraction-deck device class (`klt lvs`'s
   schematic-equivalent contract), not a model any PDK ships -- gf180mcu
   ships its primitive MOS as a `.subckt nfet_03v3`, so ngspice would reject
   the deck outright. This script rewrites each `M`-card as the
   corresponding `X`-subcircuit call against the real PDK device, carrying
   every extracted parameter through unchanged:

       X$1 TAIL IBIAS VSS vsubs nfet_03v3 L=0.5U W=2U AS=0.42P ...

   `klt extract --pdk gf180mcuC` performs the same binding itself, but as of
   klt 0.2.0 its `--pdk` output **drops the per-device AS/AD/PS/PD** that the
   deck-class form carries, and `nfet_03v3` defaults those to zero -- i.e.
   zero drain-junction capacitance on OUTP/OUTN, the one post-layout loading
   term this cell's eye measurement most depends on. Rewriting the
   AS/AD/PS/PD-bearing form here keeps the drawn junction geometry in the
   simulated netlist. (Filed generically as a tool gap; see
   `layout/README.md`.)

2. **Body/bulk net.** gf180mcu has no distinct substrate-tap layer, so klt's
   extraction deck ties every NMOS body to one deck-synthesized global net,
   `vsubs`, and exposes it as an extra pin -- the same documented tool
   limitation `layout/lvs/cml_driver_core.ref.spice` already works around
   for LVS (there it surfaces as klt's `device.body_unverified` warning).
   The physically-intended tie is VSS: this is an NMOS-only cell in the
   common p-substrate, "no isolated well is used or needed"
   (`design/cml-driver-sizing.md` section 0), and the sized schematic
   (`design/netlist/cml_driver.spice`) wires B=VSS on all four devices. The
   wrapper below therefore ties `vsubs` to `VSS` **explicitly, in one place**
   rather than leaving it dangling or floating it into the testbench.

3. **Cell boundary.** The extracted subcircuit is
   `cml_driver_core IBIAS INN INP OUTN OUTP TAIL VSS vsubs` -- alphabetical
   pin order, plus `TAIL` (an internal node that carries a label in the
   layout and so promotes to a pin) and `vsubs`. `sim/cml-driver-eye`'s
   testbench instantiates `cml_driver OUTP OUTN INP INN IBIAS VSS`, the
   schematic cell's own pin order. The wrapper adapts one to the other so
   the *identical* testbench deck can be run against either netlist with no
   testbench edit -- which is the whole point of the comparison. `TAIL`
   stays a node of the wrapper, so the testbench's device-stress
   measurements (`v(xvhi.tail)`) resolve unchanged.

What this does NOT add, and the record must say so (`sim/README.md`,
`measurements/characterization.md`'s coverage-honesty requirement):

- **No parasitic RC.** `layout/gds/cml_driver_core.spice` is a
  schematic-equivalent (device + connectivity) extraction; `klt extract`'s
  `--parasitics` flag was not used for it. Interconnect resistance and
  capacitance inside the cell are therefore absent from this DUT.
- **No S/D diffusion resistance.** The extraction carries AS/AD/PS/PD but no
  NRD/NRS, so `nfet_03v3`'s defaults (0) apply. The schematic DUT states
  NRD/NRS explicitly; this is a real schematic-vs-extracted difference, not
  a translation choice, and it is called out in the evidence record.

Usage (from the repo root, or `cd layout` and drop the `layout/` prefixes):

    python3 layout/scripts/gen_cml_driver_core_dut.py \
        -i layout/gds/cml_driver_core.spice \
        -o layout/sim/cml_driver_core_dut.spice

The committed output is checked against a fresh regeneration by
`sim/tests/test_extracted_dut.py`, so a hand edit to either file fails CI.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = REPO_ROOT / "layout" / "gds" / "cml_driver_core.spice"
DEFAULT_OUTPUT = REPO_ROOT / "layout" / "sim" / "cml_driver_core_dut.spice"

#: The klt extraction-deck device class this script knows how to bind, and
#: the gf180mcu PDK subcircuit it binds to. Any other class is an error --
#: silently passing an unknown device through would produce a deck that
#: either fails to parse or, worse, simulates the wrong device.
DEVICE_CLASS = "nfet"
PDK_SUBCKT = "nfet_03v3"

#: The extracted cell, and the schematic-level cell the wrapper presents.
CORE_SUBCKT = "cml_driver_core"
WRAPPER_SUBCKT = "cml_driver"
WRAPPER_PINS = ("OUTP", "OUTN", "INP", "INN", "IBIAS", "VSS")

#: `M<name> <d> <g> <s> <b> <class> <params...>`
_MOS_RE = re.compile(
    r"^M(?P<name>\S+)\s+"
    r"(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<cls>\S+)\s*(?P<params>.*)$"
)
_SUBCKT_RE = re.compile(r"^\.SUBCKT\s+(?P<name>\S+)\s+(?P<pins>.*)$", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\.ENDS\b", re.IGNORECASE)


class TranslationError(RuntimeError):
    """The extracted netlist is not the shape this script knows how to bind."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translate(text: str, source_label: str, source_sha256: str) -> str:
    """Return the DUT fragment for one extracted `cml_driver_core` netlist."""
    core_pins: list[str] | None = None
    body: list[str] = []
    devices = 0

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

        mos = _MOS_RE.match(stripped)
        if mos:
            if mos.group("cls") != DEVICE_CLASS:
                raise TranslationError(
                    f"unknown device class {mos.group('cls')!r} on card {stripped!r}; "
                    f"this script only binds {DEVICE_CLASS!r} -> {PDK_SUBCKT!r}"
                )
            params = mos.group("params").strip()
            body.append(
                f"XM{mos.group('name')} {mos.group('d')} {mos.group('g')} "
                f"{mos.group('s')} {mos.group('b')} {PDK_SUBCKT}"
                + (f" {params}" if params else "")
            )
            devices += 1
            continue

        raise TranslationError(f"unhandled card in extracted netlist: {stripped!r}")

    if core_pins is None:
        raise TranslationError(f"no .SUBCKT {CORE_SUBCKT} found in the input netlist")
    if devices == 0:
        raise TranslationError("no devices found in the input netlist")
    missing = [pin for pin in WRAPPER_PINS if pin not in core_pins]
    if missing:
        raise TranslationError(
            f"extracted cell is missing pin(s) {missing} needed by "
            f".subckt {WRAPPER_SUBCKT}; got {core_pins}"
        )
    if "vsubs" not in core_pins:
        raise TranslationError(
            "extracted cell has no 'vsubs' pin -- the deck-synthesized body net "
            "this wrapper is written to tie to VSS. Re-read this script's header "
            "before changing the wrapper."
        )

    # Map every core pin to the net the wrapper connects it to: its own
    # same-named port for the six schematic pins, VSS for the synthesized
    # body net, and a wrapper-internal node of the same name for anything
    # else the extraction promoted to a pin (TAIL).
    connections = ["VSS" if pin == "vsubs" else pin for pin in core_pins]
    internal = [pin for pin in core_pins if pin not in WRAPPER_PINS and pin != "vsubs"]

    header = [
        f"* {DEFAULT_OUTPUT.name} -- post-layout DUT fragment for sim/cml-driver-eye",
        "*",
        "* GENERATED by layout/scripts/gen_cml_driver_core_dut.py -- do not edit.",
        f"* source        : {source_label}",
        f"* source sha256 : {source_sha256}",
        f"* devices       : {devices} extracted per-finger {DEVICE_CLASS} devices, "
        f"bound to {PDK_SUBCKT}",
        "*",
        "* Three mechanical translations, all documented in the generator's header:",
        f"*   1. device class {DEVICE_CLASS!r} -> PDK subcircuit {PDK_SUBCKT!r} "
        "(M-card -> X-card),",
        "*      carrying the extracted AS/AD/PS/PD junction geometry through unchanged;",
        "*   2. the deck-synthesized body net 'vsubs' tied to VSS in the wrapper below",
        "*      (NMOS-only cell in the common p-substrate -- the sized schematic's own",
        "*      B=VSS; see design/cml-driver-sizing.md section 0);",
        f"*   3. a wrapper presenting the schematic cell boundary "
        f"({WRAPPER_SUBCKT} {' '.join(WRAPPER_PINS)}),",
        "*      so sim/cml-driver-eye's testbench runs unchanged against either netlist.",
        "*",
        "* NOT modelled here (state this in any record taken against this netlist):",
        "*   - no parasitic RC: the source extraction is schematic-equivalent",
        "*     (devices + connectivity); klt extract --parasitics was not used;",
        "*   - no NRD/NRS: the extraction carries no diffusion sheet counts, so",
        "*     nfet_03v3's defaults (0) apply, unlike the schematic DUT.",
        "",
        f".subckt {WRAPPER_SUBCKT} {' '.join(WRAPPER_PINS)}",
        f"* {CORE_SUBCKT} pin order is the extraction's own (alphabetical, plus the",
        f"* promoted internal node{'s' if len(internal) != 1 else ''} "
        f"{', '.join(internal) if internal else '(none)'} and the body net vsubs).",
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
        "regeneration (what sim/tests/test_extracted_dut.py asserts)",
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
