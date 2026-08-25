#!/usr/bin/env python3
"""Generator for sim/cml-driver-eye-mask/testbench/{cml_driver_eye_mask.spice,tb.json}.

This testbench is large and mechanical (a PRBS7 stimulus, a bank of
phase-tiled "comb" gating windows, and a per-load/per-phase measurement
grid) -- generating it programmatically is the only way to keep it correct
and reviewable, the same rationale sim/cml-driver-eye/testbench/
cml_driver_dut.spice documents for its own regeneration recipe. Both
generated files are committed as static artifacts (the harness's netlist
fragments must be plain, non-templated SPICE/JSON -- sim/harness/
testbench.py forbids .include/.control/etc in a fragment); re-run this
script and re-commit if the methodology changes:

    python3 sim/cml-driver-eye-mask/gen_testbench.py

## Methodology (see sim/cml-driver-eye-mask/testbench/cml_driver_eye_mask.spice
## for the full rationale, and measurements/characterization.md for the
## record's own writeup)

DR-0013 row 6 (spec/decisions/0013-operating-conditions.md) grades a single
combined criterion: eye height >= 200 mV AND eye width >= 0.75 UI, *measured
simultaneously* at the eye's widest opening, with *no fixed sampling instant
assumed*. This generator builds that as a literal box-fits-in-the-aperture
("eye mask") test:

1. Drive the driver with a genuine PRBS7 sequence (ITU-T O.150: x^7+x^6+1,
   all-ones seed, period 127) -- long and pseudo-random enough to develop
   real inter-symbol-interference (ISI) across many distinct bit histories,
   unlike sim/cml-driver-eye's fixed 16-bit deterministic pattern. A
   PREFIX_BITS-bit periodic-history prefix (literally the sequence's own
   tail, prepended) is driven first so the *measured* 127-bit period starts
   from a fully-settled rolling history -- no bit in the measured window is
   penalized (or flattered) by starting from an arbitrary "zero" state.
2. Partition each unit interval into N_PHASES equal-width phase bins
   (tiling the whole UI, not a fixed guessed sampling instant). For each
   bin i and each pad-capacitance load L, build the *worst-case* vertical
   eye opening at that phase:　height_L_i = (minimum differential level
   sampled, across every "1" bit in the measured period, in bin i) minus
   (maximum differential level sampled, across every "0" bit, in bin i).
   This is the standard worst-case-ISI eye-height construction: some "1"
   bits settle low (unfavourable history) and some "0" bits settle high,
   and the eye's vertical opening at that phase is the gap between those
   two worst cases, not a same-bit-value average.
3. Slide a WINDOW_BINS-wide window (WINDOW_BINS = round(WIDTH_UI_MIN *
   N_PHASES), the DR-0013 width floor in bins) across every valid start
   offset; for each offset, compute the minimum height_L_i over the window
   (does the eye stay open >= that height for the *whole* window). The
   largest such per-window minimum, over every offset, is
   "eyemask_margin_<L>": the tallest H for which an H x WIDTH_UI_MIN box
   fits *somewhere* in the open eye -- i.e. exactly the DR-0013 row 6 mask
   test, scanned over every window position rather than one assumed
   instant. Pass iff eyemask_margin_<L> >= 0.2 (DR-0013's 200 mV floor).
4. "eyeh_max_<L>" (informative, not gating) is the single tallest bin
   regardless of width -- the eye's unconstrained peak vertical opening --
   reported so a reader can see how much margin row 6's width requirement
   costs relative to the best achievable height alone.

Known discretization: N_PHASES bins means the *width* floor (0.75 UI) is
tested at whatever WINDOW_BINS/N_PHASES resolves to; this generator picks
N_PHASES so WIDTH_UI_MIN*N_PHASES is an exact integer (8 * 0.75 = 6) so no
rounding either direction is silently introduced. N_PHASES=8 (12.5 % UI
resolution) was chosen over a finer grid (16, 25 % finer) for a runtime
reason, not a rigor one: each phase bin needs a real PWL "comb" gating
element per measured-bit occurrence (see the per-phase construction below),
and doubling N_PHASES from 8 to 16 did not double runtime -- it took a
single PVT point from ~4 s to over 180 s (many, closely-spaced forced solver
breakpoints slow LTE step-size recovery far worse than linearly). Given
every recorded eyemask_margin below clears the DR-0013 0.2 V floor by
4-5x at 8 phase bins, a finer grid is very unlikely to change the verdict;
if a future corner comes back closer to the floor, re-run at a finer
N_PHASES for that corner specifically rather than paying the cost everywhere.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
TB_DIR = HERE / "testbench"

# ---------------------------------------------------------------------------
# PRBS7 (ITU-T O.150): x^7 + x^6 + 1, all-ones seed, period 127.
# ---------------------------------------------------------------------------
def prbs7(n: int) -> list[int]:
    reg = [1] * 7  # reg[0] = newest bit
    bits = []
    for _ in range(n):
        newbit = reg[6] ^ reg[5]
        bits.append(reg[6])
        reg = [newbit] + reg[:6]
    return bits


PERIOD = 127
MAIN_BITS = prbs7(PERIOD)
assert sum(MAIN_BITS) == 64 and len(MAIN_BITS) == 127

# A fixed, pattern-independent 1-0-1 calibration lead-in, driven before any
# PRBS content, so the harness-integrity "ui_ref" measurement (a FALL then
# the very next RISE) always lands in the first two bit periods regardless
# of what bit the PRBS prefix/main sequence happens to start on -- without
# it, "first FALL" and "first RISE" can occur in either order depending on
# the PRBS's own arbitrary leading bits, and ui_ref would occasionally
# measure a multi-UI (or negative) span instead of one UI. Not part of the
# measured period (see PREFIX_LEN/CALIB_LEN below); purely a measurement
# reference.
CALIB_BITS = [1, 0, 1]
CALIB_LEN = len(CALIB_BITS)

PREFIX_LEN = 20
PREFIX_BITS = MAIN_BITS[-PREFIX_LEN:]  # the sequence's own tail: a genuine
# rolling-periodic history, not an arbitrary settle-in pattern.
ALL_BITS = CALIB_BITS + PREFIX_BITS + MAIN_BITS  # length CALIB_LEN + PREFIX_LEN + PERIOD
N_TOTAL_BITS = len(ALL_BITS)
#: Global bit index (within ALL_BITS) of measured bit 0 of MAIN_BITS.
MEASURED_BASE = CALIB_LEN + PREFIX_LEN

# ---------------------------------------------------------------------------
# Phase grid / eye-mask window
# ---------------------------------------------------------------------------
N_PHASES = 8
WIDTH_UI_MIN = 0.75  # DR-0013 row 6
WINDOW_BINS = round(WIDTH_UI_MIN * N_PHASES)
assert abs(WINDOW_BINS - WIDTH_UI_MIN * N_PHASES) < 1e-9, "N_PHASES*WIDTH_UI_MIN must be exact"
HEIGHT_MIN_V = 0.2  # DR-0013 row 6

LOADS = ("c0", "c1", "c2")  # 0 pF / 1 pF / DR-0005's full 2 pF pad budget
LOAD_CAP_PF = {"c0": 0.0, "c1": 1.0, "c2": 2.0}

TEDGE_PS = 80  # matches sim/cml-driver-eye/testbench/cml_driver_eye.spice

# Comb-window gate edge width (seconds). Deliberately NOT a fast (~1 ps)
# edge: a comb gate is a real PWL circuit element, and a very fast edge
# forces the transient solver to collapse its internal step near every one
# of the (measured bits) x (phase bins) x 2 breakpoints, then slowly regrow
# it back toward transient.tmax_s -- with hundreds of breakpoints this
# dominated runtime in an earlier iteration of this generator. An edge
# matched to the solver's own print step does not ask the solver to resolve
# anything finer than it already tracks.
COMB_EDGE_S = 20e-12


def fmt(x: float) -> str:
    """Compact float formatting for generated SPICE param expressions."""
    return repr(x)


def bit_windows(bit_value: int) -> list[list[int]]:
    """Which of the PERIOD measured bits (0-indexed within MAIN_BITS) equal
    ``bit_value``? Global bit index (within ALL_BITS) is MEASURED_BASE + k."""
    return [k for k, b in enumerate(MAIN_BITS) if b == bit_value]


def gen_spice() -> str:
    lines: list[str] = []
    lines.append(
        "* cml-driver-eye-mask -- GENERATED by sim/cml-driver-eye-mask/gen_testbench.py"
    )
    lines.append("* DO NOT HAND-EDIT. Re-run the generator and re-commit instead.")
    lines.append("*")
    lines.append(
        "* Netlist FRAGMENT (sim/harness/README.md convention): the harness supplies"
    )
    lines.append(
        "* the title, gf180mcu model .include/.lib, .temp, the DUT .include"
    )
    lines.append(
        "* (cml_driver_dut.spice, shared with sim/cml-driver-eye/), .control/.endc/.end,"
    )
    lines.append(
        "* and vdd_val/vdd_nom/temp_c/rate_val. See tb.json's \"dut\" key."
    )
    lines.append("*")
    lines.append(
        "* METHODOLOGY: see this directory's gen_testbench.py module docstring for the"
    )
    lines.append(
        "* full derivation. Summary: a PRBS7 (period 127, ITU-T O.150 x^7+x^6+1, "
        "all-ones"
    )
    lines.append(
        f"* seed) stimulus, preceded by a {PREFIX_LEN}-bit rolling-history prefix (the"
    )
    lines.append(
        "* sequence's own tail) so the measured 127-bit period starts fully settled, in"
    )
    lines.append(
        f"* turn preceded by a fixed {CALIB_LEN}-bit 1-0-1 calibration lead-in (ui_ref's"
    )
    lines.append(
        "* reference, independent of the PRBS's own leading bits -- see gen_testbench.py)."
    )
    lines.append(f"* {N_TOTAL_BITS} bits driven in total, only the last {PERIOD} measured."
    )
    lines.append(
        f"* Each UI is tiled into {N_PHASES} equal phase bins (no fixed sampling instant"
    )
    lines.append(
        "* assumed); per bin, the worst-case vertical eye opening is the gap between the"
    )
    lines.append(
        "* minimum sampled level over every measured \"1\" bit and the maximum sampled"
    )
    lines.append(
        "* level over every measured \"0\" bit, at that phase. DR-0013 row 6's combined"
    )
    lines.append(
        f"* height/width criterion is graded as a sliding {WINDOW_BINS}-bin "
        f"({WIDTH_UI_MIN:g} UI) window"
    )
    lines.append(
        "* eye-mask test in tb.json's measure section (eyemask_margin_c0/c1/c2)."
    )
    lines.append("*")
    lines.append(
        "* WHICH RAIL THE MANDATED +/-10 % SUPPLY AXIS IS APPLIED TO / INPUT MODEL:"
    )
    lines.append(
        "* identical to sim/cml-driver-eye/testbench/cml_driver_eye.spice -- see that"
    )
    lines.append(
        "* file's header for the full rationale (vdd_val is the on-chip 3.3 V core rail"
    )
    lines.append(
        "* driving the DR-0003 final multiplexer's ideal-source model; avcc is the"
    )
    lines.append("* receiver's separate termination rail, held at nominal here since this")
    lines.append(
        "* bench's claim is row 6 only -- avcc sensitivity is sim/cml-driver-eye's job)."
    )
    lines.append("")
    lines.append(f".param tbit_s   = '1e-6/rate_val'")
    lines.append(f".param avcc_nom = 3.3")
    lines.append(f".param rterm    = 50")
    lines.append(f".param iref     = 500u")
    lines.append(f".param vih      = '0.85*vdd_val'")
    lines.append(f".param vil      = '0.55*vdd_val'")
    lines.append(f".param tedge    = {TEDGE_PS}p")
    lines.append("")
    lines.append("* ---- rails ---------------------------------------------------------------")
    lines.append("vavcc   avcc   0 dc {avcc_nom}")
    lines.append("")

    # ---- differential stimulus over all N_TOTAL_BITS bits -----------------
    def pwl_points(levels_high_first: bool) -> list[str]:
        """levels_high_first=True -> INP polarity (bit=1 -> vih); False -> INN."""
        def level(bit: int) -> str:
            hi = "{vih}" if levels_high_first else "{vil}"
            lo = "{vil}" if levels_high_first else "{vih}"
            return hi if bit == 1 else lo

        pts = [f"0 '{level(ALL_BITS[0])}'"]
        for n in range(1, N_TOTAL_BITS):
            pts.append(f"'{{{n}*tbit_s}}' '{level(ALL_BITS[n - 1])}'")
            pts.append(f"'{{{n}*tbit_s+tedge}}' '{level(ALL_BITS[n])}'")
        # hold flat to the end of the pattern
        pts.append(f"'{{{N_TOTAL_BITS}*tbit_s}}' '{level(ALL_BITS[-1])}'")
        return pts

    lines.append("* ---- stimulus: PRBS7 (see header) -----------------------------------------")
    lines.append("vinp inp 0 PWL(" + pwl_points(True)[0])
    for pt in pwl_points(True)[1:]:
        lines.append("+ " + pt)
    lines.append("+ r=0 td=0)")
    lines.append("vinn inn 0 PWL(" + pwl_points(False)[0])
    for pt in pwl_points(False)[1:]:
        lines.append("+ " + pt)
    lines.append("+ r=0 td=0)")
    lines.append("")
    lines.append(
        "* Differential input probe (VCVS workaround -- v(a,b) does not parse inside a"
    )
    lines.append(
        "* meas TRIG/TARG expression; confirmed while developing sim/smoke-cml-pair)."
    )
    lines.append("einref inref 0 inp inn 1")
    lines.append("")

    # ---- phase-bin comb windows --------------------------------------------
    lines.append(
        f"* ---- {N_PHASES} phase-tiled comb windows, split by measured bit value --------"
    )
    lines.append(
        "* comb1_<i> is high (1) during phase bin i of every MEASURED bit equal to 1;"
    )
    lines.append("* comb0_<i> likewise for measured bits equal to 0. Only the measured")
    lines.append(
        f"* {PERIOD}-bit period (global bit index {MEASURED_BASE}..{N_TOTAL_BITS - 1}) is"
    )
    lines.append(
        f"* windowed -- the first {MEASURED_BASE} bits ({CALIB_LEN}-bit calibration lead-in"
    )
    lines.append(f"* + {PREFIX_LEN}-bit rolling-history prefix) are not measured.")
    ones = bit_windows(1)
    zeros = bit_windows(0)

    def _t(gk: int, frac: float, edge_sign: int) -> str:
        """Time expression for global bit ``gk``, phase fraction ``frac``
        of its UI, offset by one comb edge width in the given direction
        (``edge_sign`` -1/0/+1) -- a single brace expression, matching
        this repo's existing PWL-time-expression convention (e.g.
        ``'{10.3*tbit_s+1p}'`` in sim/cml-driver-eye's testbench)."""
        if edge_sign == 0:
            return f"'{{({gk}+{fmt(frac)})*tbit_s}}'"
        sign = "+" if edge_sign > 0 else "-"
        return f"'{{({gk}+{fmt(frac)})*tbit_s{sign}{fmt(COMB_EDGE_S)}}}'"

    for i in range(N_PHASES):
        bin_lo = i / N_PHASES
        bin_hi = (i + 1) / N_PHASES
        for bitval, occurrences, name in ((1, ones, f"comb1_{i}"), (0, zeros, f"comb0_{i}")):
            pts: list[str] = ["0 0"]
            for k in occurrences:
                gk = MEASURED_BASE + k  # global bit index
                pts.append(f"{_t(gk, bin_lo, 0)} 0")
                pts.append(f"{_t(gk, bin_lo, +1)} 1")
                pts.append(f"{_t(gk, bin_hi, -1)} 1")
                pts.append(f"{_t(gk, bin_hi, 0)} 0")
            src_line = f"v{name} {name} 0 PWL(" + pts[0]
            lines.append(src_line)
            for pt in pts[1:]:
                lines.append("+ " + pt)
            lines.append("+ )")
    lines.append("")

    # ---- driver copies: 0/1/2 pF pad capacitance, same cml_driver cell -----
    lines.append(
        "* ---- driver copies: 0/1/2 pF pad capacitance (design/cml-driver-sizing.md #5) -"
    )
    for load in LOADS:
        cap_pf = LOAD_CAP_PF[load]
        lines.append(f"x{load} outp_{load} outn_{load} inp inn ib_{load} 0 cml_driver")
        lines.append(f"ib_{load}src 0 ib_{load} dc {{iref}}")
        lines.append(f"rp_{load} avcc outp_{load} {{rterm}}")
        lines.append(f"rn_{load} avcc outn_{load} {{rterm}}")
        if cap_pf > 0:
            lines.append(f"cp_{load} outp_{load} 0 {cap_pf:g}p")
            lines.append(f"cn_{load} outn_{load} 0 {cap_pf:g}p")
        lines.append(f"ediff_{load} vd_{load} 0 outn_{load} outp_{load} 1")
        lines.append("")

    return "\n".join(lines) + "\n"


def gen_tbjson() -> dict:
    measure: dict[str, str] = {}
    checks: dict[str, dict] = {}

    # harness-integrity check: the rate axis must actually move the input UI.
    measure["ui_ref"] = "TRIG v(inref) VAL=0 FALL=1 TARG v(inref) VAL=0 RISE=1"
    checks["ui_ref"] = {
        "min_spread_pct": 50.0,
        "description": (
            "Harness-integrity check, not a design claim: the measured unit interval "
            "must differ across the rate grid, confirming rate_val actually reached "
            "the stimulus (same convention as sim/cml-driver-eye)."
        ),
    }

    for load in LOADS:
        cap_pf = LOAD_CAP_PF[load]
        for i in range(N_PHASES):
            name = f"height_{load}_{i}"
            measure[name] = (
                f"vecmin(v(vd_{load})+10*(1-v(comb1_{i})))"
                f"-vecmax(v(vd_{load})-10*(1-v(comb0_{i})))"
            )

        # eyeh_max_<load>: informative peak vertical opening, unconstrained by width.
        expr = f"m_height_{load}_0"
        for i in range(1, N_PHASES):
            expr = f"max({expr},m_height_{load}_{i})"
        measure[f"eyeh_max_{load}"] = expr

        # eyemask_margin_<load>: DR-0013 row 6's gating quantity -- best
        # achievable per-window minimum height over every WINDOW_BINS-wide
        # sliding window position (i.e. does an H x 0.75 UI box fit anywhere).
        window_terms = []
        for j in range(N_PHASES - WINDOW_BINS + 1):
            win_expr = f"m_height_{load}_{j}"
            for i in range(j + 1, j + WINDOW_BINS):
                win_expr = f"min({win_expr},m_height_{load}_{i})"
            window_terms.append(win_expr)
        margin_expr = window_terms[0]
        for term in window_terms[1:]:
            margin_expr = f"max({margin_expr},{term})"
        measure[f"eyemask_margin_{load}"] = margin_expr
        checks[f"eyemask_margin_{load}"] = {
            "min": HEIGHT_MIN_V,
            "description": (
                f"DR-0013 row 6 (spec/decisions/0013-operating-conditions.md): does a "
                f"{HEIGHT_MIN_V*1000:g} mV x {WIDTH_UI_MIN:g} UI box fit somewhere in the "
                f"open eye, {cap_pf:g} pF pad. Scanned over every "
                f"{WINDOW_BINS}-of-{N_PHASES}-bin window position (no fixed sampling "
                "instant assumed); PASS iff the best achievable per-window minimum "
                f"vertical opening is >= {HEIGHT_MIN_V} V."
            ),
        }

    manifest = {
        "name": "cml-driver-eye-mask",
        "description": (
            "DR-0013 row 6 (combined swing+jitter passing-eye criterion) for one lane "
            "of the CML output driver (design/cml_driver.sch), against the DR-0002 load, "
            "swept over pad capacitance 0/1/2 pF in-deck, at both spec/tmds-tx.md #1 "
            "operating points, across the full PVT matrix. Drives a genuine PRBS7 "
            "(period 127) pattern -- long enough to develop real ISI, unlike "
            "sim/cml-driver-eye's fixed 16-bit pattern -- tiles each UI into "
            f"{N_PHASES} phase bins, and grades whether a {HEIGHT_MIN_V*1000:g} mV x "
            f"{WIDTH_UI_MIN:g} UI eye-mask box fits anywhere in the resulting open eye."
        ),
        "claim": (
            "spec/decisions/0013-operating-conditions.md#row-6 -- eye height >= "
            f"{HEIGHT_MIN_V*1000:g} mV AND eye width >= {WIDTH_UI_MIN:g} UI, measured "
            "simultaneously at the eye's widest opening, no fixed sampling instant "
            "assumed, at both spec/tmds-tx.md #1 operating points (742.5 Mbps/lane "
            "target, 270 Mbps/lane fallback)."
        ),
        "netlist": "cml_driver_eye_mask.spice",
        "dut": "sim/cml-driver-eye/testbench/cml_driver_dut.spice",
        "corners": ["mos"],
        "rates_mbps": [742.5, 270.0],
        "transient": {
            "tstep_s": 20e-12,
            "tstop_s": 560e-9,
            "tmax_s": 40e-12,
            "reltol": 1e-6,
            "abstol": 1e-9,
            "vntol": 1e-6,
            "pattern": (
                f"prbs7 (ITU-T O.150, x^7+x^6+1, all-ones seed, period {PERIOD}), "
                f"preceded by a {PREFIX_LEN}-bit rolling-history prefix (the "
                "sequence's own tail) so the measured period starts fully settled; "
                f"{N_TOTAL_BITS} bits driven, {PERIOD} measured -- see "
                "sim/cml-driver-eye-mask/gen_testbench.py"
            ),
        },
        "analyses": ["tran 20e-12 560e-9 0 40e-12"],
        "measure": measure,
        "checks": checks,
    }
    return manifest


def main() -> None:
    TB_DIR.mkdir(parents=True, exist_ok=True)
    spice_path = TB_DIR / "cml_driver_eye_mask.spice"
    spice_path.write_text(gen_spice())
    tbjson_path = TB_DIR / "tb.json"
    tbjson_path.write_text(json.dumps(gen_tbjson(), indent=2) + "\n")
    print(f"wrote {spice_path} ({spice_path.stat().st_size} bytes)")
    print(f"wrote {tbjson_path} ({tbjson_path.stat().st_size} bytes)")
    print(f"N_PHASES={N_PHASES} WINDOW_BINS={WINDOW_BINS} PREFIX_LEN={PREFIX_LEN} "
          f"N_TOTAL_BITS={N_TOTAL_BITS}")


if __name__ == "__main__":
    main()
