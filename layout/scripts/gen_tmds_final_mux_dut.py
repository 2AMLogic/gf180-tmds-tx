#!/usr/bin/env python3
"""Derive a simulatable DUT fragment from the LVS-signed-off extracted mux.

`klt extract --deck gf180mcu` writes `layout/gds/tmds_final_mux.spice`: the
device-level, LVS-verified extraction of `layout/gds/tmds_final_mux.gds`
(issue #177). That file is the LVS signoff artifact and is **not** directly
simulatable. This script -- and only this script -- mechanically resolves
the four reasons why. Nothing here is a hand edit: run it and diff.

1. **MOS model binding.** Every extracted transistor is an `M`-card naming
   the bare class label `nfet`:

       M$1 OUTP D0P SA vsubs nfet L=0.28U W=2U AS=1P AD=0.58P PS=5U PD=2.58U

   `nfet` is klt's own extraction-deck device class, not a model any PDK
   ships -- gf180mcu ships its primitive MOS as a `.subckt nfet_03v3`, so
   ngspice would reject the deck outright. Each `M`-card is rewritten as the
   corresponding `X`-subcircuit call against the real PDK device, carrying
   every extracted parameter -- including the AS/AD/PS/PD junction geometry
   -- through unchanged. This is the identical binding
   `gen_cml_driver_core_dut.py` performs for the driver core; see that
   script's header for why the AS/AD/PS/PD-bearing deck-class form is
   translated here rather than taking `klt extract --pdk`'s own binding.

2. **Poly resistors.** Unlike the driver core, this cell contains four drawn
   `ppolyf_u` bodies, which the deck reports as ohms-valued `R`-cards with a
   body terminal and a trailing class label:

       R$659 OUTP TOP vsubs 103.25 ppolyf_u

   These are emitted as plain ngspice `R` elements carrying the extraction's
   own ohms and dropping the body terminal (`R$659 OUTP TOP 103.25`) -- the
   same convention `layout/lvs/tmds_final_mux.ref.spice` already adopted for
   LVS signoff (see `layout/README.md`'s signoff note). The deck gives ohms
   only, with no `r_width`/`r_length`, and `R = rsh * r_length/r_width` fixes
   only the ratio, so the drawn geometry is not uniquely recoverable from the
   extraction -- binding these to the PDK's geometry-parameterized resistor
   subcircuit would mean importing geometry from the *schematic*, making this
   DUT a reconstruction that papers over any drawn-vs-schematic resistor
   difference. It stays a pure translation of the extraction instead.

   **This has a real cost, and it lands on whoever runs this DUT, not here.**
   `design/tmds-final-mux-sizing.md` section 3 argues that `RC`/`RLP`/`RLN`/
   `RREF` track one another across process corners precisely *because* they
   share one `rsh_ppolyf_u`, which is what makes this cell's output levels
   `rsh`-invariant. Fixed-ohms `R` elements are corner-invariant, so a
   multi-corner run against this DUT does not sweep the poly sheet-rho axis
   at all. That is stated in the generated header so a later re-simulation
   inherits the caveat rather than misreading the resulting
   schematic-vs-extracted difference as a layout effect.

3. **Body/bulk net.** gf180mcu has no distinct substrate-tap layer, so klt's
   extraction deck ties every NMOS body to one deck-synthesized global net,
   `vsubs`, and exposes it as an extra pin -- the same documented tool
   limitation `layout/lvs/tmds_final_mux.ref.spice` works around for LVS
   (there it surfaces as klt's `device.body_unverified` warning). The
   physically-intended tie is VSS: this is an NMOS-only cell in the common
   p-substrate and the sized schematic (`design/netlist/tmds_final_mux.spice`)
   wires B=VSS throughout. The wrapper below ties `vsubs` to `VSS`
   **explicitly, in one place**.

4. **Cell boundary, and a name collision the driver core does not have.**
   The extracted subcircuit is `tmds_final_mux CLKN CLKP D0N D0P D1N D1P
   IBIAS OUTN OUTP SA SB TAIL TOP VDD VSS vsubs` -- 16 pins in alphabetical
   order, comprising the schematic's 10 plus the internal nodes that carry a
   label in the layout and so promote to pins (`IBIAS`/`SA`/`SB`/`TAIL`/
   `TOP`) and the body net. The schematic cell boundary is
   `tmds_final_mux OUTP OUTN D0P D0N D1P D1N CLKP CLKN VDD VSS`.

   Here the extracted cell and the schematic cell **share one name** -- where
   the driver core's two (`cml_driver_core` extracted, `cml_driver` wrapper)
   differ. Emitting a wrapper that kept both would put two
   `.subckt tmds_final_mux` definitions in one deck, which ngspice resolves
   silently rather than erroring. The inner extracted subcircuit is
   therefore renamed to `tmds_final_mux_extracted`, so this fragment defines
   `tmds_final_mux` exactly once.

   `SA`, `SB`, `TAIL`, `TOP` and `IBIAS` stay wrapper-internal nodes of
   unchanged name, which is what makes `sim/tmds-final-mux-eye`'s
   `v(xmux_m.sa)` / `v(xmux_m.tail)` measurements resolve unchanged.

What this does NOT add, and the record must say so (`sim/README.md`,
`measurements/characterization.md`'s coverage-honesty requirement):

- **No parasitic RC.** `layout/gds/tmds_final_mux.spice` is a
  schematic-equivalent (device + connectivity) extraction; `klt extract`'s
  `--parasitics` flag was not used for it. Interconnect resistance and
  capacitance inside the cell are absent from this DUT.
- **No NRD/NRS.** The extraction carries AS/AD/PS/PD but no diffusion sheet
  counts, so `nfet_03v3`'s defaults (0) apply. This is a real
  schematic-vs-extracted difference, not a translation choice.
- **No poly sheet-rho corner dependence**, per 2 above.

This fragment is **not** a drop-in `--dut` for `sim/tmds-final-mux-eye`:
that testbench's `tb.json` points at `sim/dut/tmds_output_stage.spice`, a
composite defining both `tmds_final_mux` and `cml_driver` because the deck
instantiates a real driver alongside the mux. Building that composite, and
running it, are deliberately out of scope here (issue #311).

Usage (from the repo root, or `cd layout` and drop the `layout/` prefixes):

    python3 layout/scripts/gen_tmds_final_mux_dut.py \
        -i layout/gds/tmds_final_mux.spice \
        -o layout/sim/tmds_final_mux_dut.spice

The committed output is checked against a fresh regeneration by
`sim/tests/test_tmds_final_mux_dut.py` and by `.github/scripts/lint.sh`, so
a hand edit to either file fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from _dut_translator_cli import TranslationError, run_cli

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = REPO_ROOT / "layout" / "gds" / "tmds_final_mux.spice"
DEFAULT_OUTPUT = REPO_ROOT / "layout" / "sim" / "tmds_final_mux_dut.spice"

#: The klt extraction-deck MOS class this script binds, and the gf180mcu PDK
#: subcircuit it binds to. Any other class is an error -- silently passing an
#: unknown device through would produce a deck that either fails to parse or,
#: worse, simulates the wrong device.
DEVICE_CLASS = "nfet"
PDK_SUBCKT = "nfet_03v3"

#: The klt extraction-deck resistor class this script knows how to emit as a
#: plain ngspice R element. See the module header, point 2.
RESISTOR_CLASS = "ppolyf_u"

#: The extracted cell, the name it is renamed to so the schematic-level name
#: is defined exactly once, and the schematic cell boundary the wrapper
#: presents (`design/netlist/tmds_final_mux.spice`'s own `**.subckt` order).
EXTRACTED_SUBCKT = "tmds_final_mux"
CORE_SUBCKT = "tmds_final_mux_extracted"
WRAPPER_SUBCKT = "tmds_final_mux"
WRAPPER_PINS = (
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
)

#: The deck-synthesized body net the extraction exposes as an extra pin.
BODY_NET = "vsubs"

#: `M<name> <d> <g> <s> <b> <class> <params...>`
_MOS_RE = re.compile(
    r"^M(?P<name>\S+)\s+"
    r"(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<cls>\S+)\s*(?P<params>.*)$"
)
#: `R<name> <n1> <n2> <body> <ohms> <class>`
_RES_RE = re.compile(
    r"^R(?P<name>\S+)\s+"
    r"(?P<n1>\S+)\s+(?P<n2>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<ohms>\S+)\s+(?P<cls>\S+)\s*$"
)
_SUBCKT_RE = re.compile(r"^\.SUBCKT\s+(?P<name>\S+)\s+(?P<pins>.*)$", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\.ENDS\b", re.IGNORECASE)


def _fold_continuations(text: str) -> list[str]:
    """Join SPICE `+` continuation lines onto the card they continue.

    The extraction wraps the 16-pin `.SUBCKT` line (`+ VDD VSS vsubs`), which
    `gen_cml_driver_core_dut.py` never has to handle -- the driver core's
    boundary fits on one line. Folding here keeps the main loop working in
    whole logical cards. Comments are passed through untouched; a `+` with no
    card to continue is an error rather than a silent drop.
    """
    folded: list[str] = []
    last_card: int | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            continue
        if stripped.startswith("*"):
            folded.append(line)
            continue
        if stripped.startswith("+"):
            if last_card is None:
                raise TranslationError(
                    f"continuation line with no card to continue: {stripped!r}"
                )
            folded[last_card] = f"{folded[last_card]} {stripped[1:].strip()}".rstrip()
            continue

        folded.append(line)
        last_card = len(folded) - 1

    return folded


def translate(text: str, source_label: str, source_sha256: str) -> str:
    """Return the DUT fragment for one extracted `tmds_final_mux` netlist."""
    core_pins: list[str] | None = None
    body: list[str] = []
    devices = 0
    resistors = 0

    for line in _fold_continuations(text):
        stripped = line.strip()

        if stripped.startswith("*"):
            body.append(line)
            continue

        subckt = _SUBCKT_RE.match(stripped)
        if subckt:
            if subckt.group("name") != EXTRACTED_SUBCKT:
                raise TranslationError(
                    f"expected .SUBCKT {EXTRACTED_SUBCKT}, "
                    f"found {subckt.group('name')!r}"
                )
            core_pins = subckt.group("pins").split()
            # Renamed: the extracted cell and the schematic cell share one
            # name, so keeping both would define .subckt tmds_final_mux twice
            # in a deck and ngspice would resolve it silently (header, 4).
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

        res = _RES_RE.match(stripped)
        if res:
            if res.group("cls") != RESISTOR_CLASS:
                raise TranslationError(
                    f"unknown resistor class {res.group('cls')!r} on card "
                    f"{stripped!r}; this script only emits {RESISTOR_CLASS!r} "
                    "bodies as plain ngspice R elements"
                )
            if res.group("b") != BODY_NET:
                raise TranslationError(
                    f"resistor card {stripped!r} has body terminal "
                    f"{res.group('b')!r}, not the deck-synthesized "
                    f"{BODY_NET!r} this translation drops"
                )
            # Plain ngspice R element: the extraction's own ohms, body
            # terminal dropped (header, 2 -- same convention as
            # layout/lvs/tmds_final_mux.ref.spice).
            body.append(
                f"R{res.group('name')} {res.group('n1')} {res.group('n2')} "
                f"{res.group('ohms')}"
            )
            resistors += 1
            continue

        raise TranslationError(f"unhandled card in extracted netlist: {stripped!r}")

    if core_pins is None:
        raise TranslationError(
            f"no .SUBCKT {EXTRACTED_SUBCKT} found in the input netlist"
        )
    if devices == 0:
        raise TranslationError("no devices found in the input netlist")
    if resistors == 0:
        raise TranslationError(
            f"no {RESISTOR_CLASS!r} resistors found in the input netlist -- this "
            "cell's load network and bias reference are drawn poly bodies; an "
            "extraction without them is not this cell"
        )
    missing = [pin for pin in WRAPPER_PINS if pin not in core_pins]
    if missing:
        raise TranslationError(
            f"extracted cell is missing pin(s) {missing} needed by "
            f".subckt {WRAPPER_SUBCKT}; got {core_pins}"
        )
    if BODY_NET not in core_pins:
        raise TranslationError(
            f"extracted cell has no {BODY_NET!r} pin -- the deck-synthesized body "
            "net this wrapper is written to tie to VSS. Re-read this script's "
            "header before changing the wrapper."
        )

    # Map every core pin to the net the wrapper connects it to: its own
    # same-named port for the ten schematic pins, VSS for the synthesized
    # body net, and a wrapper-internal node of the same name for everything
    # else the extraction promoted to a pin (IBIAS/SA/SB/TAIL/TOP).
    connections = ["VSS" if pin == BODY_NET else pin for pin in core_pins]
    internal = [
        pin for pin in core_pins if pin not in WRAPPER_PINS and pin != BODY_NET
    ]

    header = [
        f"* {DEFAULT_OUTPUT.name} -- post-layout DUT fragment for "
        f"{WRAPPER_SUBCKT} (issue #311)",
        "*",
        "* GENERATED by layout/scripts/gen_tmds_final_mux_dut.py -- do not edit.",
        f"* source        : {source_label}",
        f"* source sha256 : {source_sha256}",
        f"* devices       : {devices} extracted per-finger {DEVICE_CLASS} devices, "
        f"bound to {PDK_SUBCKT}",
        f"* resistors     : {resistors} extracted {RESISTOR_CLASS} bodies, emitted "
        "as plain ngspice R elements",
        "*",
        "* Four mechanical translations, all documented in the generator's header:",
        f"*   1. MOS class {DEVICE_CLASS!r} -> PDK subcircuit {PDK_SUBCKT!r} "
        "(M-card -> X-card),",
        "*      carrying the extracted AS/AD/PS/PD junction geometry through"
        " unchanged;",
        f"*   2. {RESISTOR_CLASS} R-cards -> plain ngspice R elements carrying the",
        "*      extraction's own ohms, body terminal dropped (the same convention",
        "*      layout/lvs/tmds_final_mux.ref.spice uses for LVS signoff);",
        f"*   3. the deck-synthesized body net {BODY_NET!r} tied to VSS in the"
        " wrapper below",
        "*      (NMOS-only cell in the common p-substrate -- the sized schematic's",
        "*      own B=VSS);",
        f"*   4. the extracted cell renamed {EXTRACTED_SUBCKT} -> {CORE_SUBCKT}, so"
        " that the",
        f"*      schematic-level name {WRAPPER_SUBCKT} is defined exactly once by"
        " the wrapper",
        "*      below -- two same-named .subckt definitions in one deck are"
        " resolved",
        "*      silently by ngspice rather than reported.",
        "*",
        "* NOT modelled here (state this in any record taken against this netlist):",
        "*   - no parasitic RC: the source extraction is schematic-equivalent",
        "*     (devices + connectivity); klt extract --parasitics was not used;",
        "*   - no NRD/NRS: the extraction carries no diffusion sheet counts, so",
        "*     nfet_03v3's defaults (0) apply, unlike the schematic DUT;",
        f"*   - NO POLY SHEET-RHO CORNER DEPENDENCE. The {RESISTOR_CLASS} bodies are",
        "*     fixed-ohms R elements (translation 2), because the extraction reports",
        "*     ohms with no r_width/r_length and R = rsh*(r_length/r_width) fixes",
        "*     only the ratio. They therefore do NOT move with the",
        "*     res_typical/res_ss/res_ff corner (350/420/280 ohm/sq, a +/-20%",
        "*     spread). design/tmds-final-mux-sizing.md section 3's",
        "*     process-invariance argument -- that RC/RLP/RLN/RREF cancel because",
        "*     they share one rsh_ppolyf_u -- is NOT exercised by a multi-corner run",
        "*     against this DUT: the resistor sheet-rho axis is absent, not swept.",
        "*     Do not attribute the resulting schematic-vs-extracted difference to",
        "*     a layout effect.",
        "*     This is a property of the INPUT, not a klt limitation: klt's --pdk",
        "*     binding is geometry-parameterized for gf180mcu ppolyf_u (r_length/",
        "*     r_width, read off the extracted device), so the way to recover the",
        "*     corner dependence is a --pdk-bound re-extraction feeding a variant of",
        "*     this translator -- NOT a change to the resistor branch below, which",
        "*     has only ohms to work from. Re-verify what that form carries on the",
        "*     MOS side before switching: the committed input is the --deck form",
        "*     precisely because it carries per-device AS/AD/PS/PD.",
        "*",
        "* Not a drop-in --dut for sim/tmds-final-mux-eye: that testbench consumes",
        "*   the composite sim/dut/tmds_output_stage.spice (mux + a real cml_driver).",
        "*   This fragment is the mux half only.",
        "",
        f".subckt {WRAPPER_SUBCKT} {' '.join(WRAPPER_PINS)}",
        f"* {CORE_SUBCKT} pin order is the extraction's own (alphabetical: the",
        f"* schematic's {len(WRAPPER_PINS)} pins, the promoted internal node"
        f"{'s' if len(internal) != 1 else ''} "
        f"{', '.join(internal) if internal else '(none)'}, and the body net"
        f" {BODY_NET}).",
        f"* {', '.join(internal)} stay wrapper-internal nodes of unchanged name, so",
        "* sim/tmds-final-mux-eye's v(xmux_m.sa) / v(xmux_m.tail) resolve unchanged.",
        f"xcore {' '.join(connections)} {CORE_SUBCKT}",
        ".ends",
        "",
    ]
    return "\n".join(header + body) + "\n"


def main(argv: list[str] | None = None) -> int:
    return run_cli(
        translate,
        argv,
        script=Path(__file__).resolve(),
        repo_root=REPO_ROOT,
        doc=__doc__,
        default_input=DEFAULT_INPUT,
        default_output=DEFAULT_OUTPUT,
        check_test="test_tmds_final_mux_dut.py",
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
