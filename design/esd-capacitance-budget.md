# ESD clamp sizing vs. the DR-0005 capacitance budget — a measurement study

Status: measurement study for issue #12, per the 2026-08-14 operator ruling
on that issue. **Not a decision record and makes no change to `spec/`.**
Per the operator's explicit guardrail, if the two targets this document
validates prove incompatible, the trade-off is reported here with its
evidence and returned to the operator — this document does not revise
DR-0005 (or any other decision record) to make the numbers work.

## 0. What this document answers, and what it does not

DR-0005 (`spec/tmds-tx.md`) sets two targets and explicitly declines to
show they are simultaneously achievable:

- **ESD**: HBM ≥ 2 kV (JEDEC JS-001), CDM ≥ 500 V (JEDEC JS-002).
- **Pad capacitance**: ≤ 2 pF per data/clock pad, *"ESD diodes + pad
  parasitic combined"*.

The 2026-08-14 operator ruling on issue #12 narrows the original four-part
architect proposal to exactly this: size the ESD clamp **that is actually
drawn** on the real pad cell from issue #2
(`layout/gds/gf180_tmds_pad_min.gds`) against the HBM/CDM targets, measure
the resulting pad-node capacitance (clamp + real Metal5 pad) against the
2 pF budget, and report a verdict. The clamp on that cell is a
grounded-gate NMOS (GGNMOS), not the diode primitives DR-0005's original
text named — `spec/pad-ring-esd-survey.md` §4 explains why (`klt`'s
gf180mcu extraction deck has no diode device class,
[2AMLogic/klayout-tools#541](https://github.com/2AMLogic/klayout-tools/issues/541)),
and the operator ruling settles the device-family question directly from
the real, already-built cell rather than waiting on a separate
decision-record issue.

**Out of scope here** (per the ruling): a `gf180mcuC`-vs-`gf180mcuD` metal-
stack comparison curve, a formally uncertainty-budgeted pad-parasitic
estimate, and redesigning the clamp device family. This document does not
attempt any of those.

**Verdict, up front** (derived in §5): the ESD side of the budget is easy
to satisfy — a clamp sized generously past JEDEC JS-001's 2 kV target costs
well under 1 pF at every PVT corner measured. The budget is not closed by
the clamp. It is closed, decisively, by the **pad's own parasitic
capacitance once any realistic bond-pad size is used** — a plain Metal5
plate at the PDK's own established 25×25 µm bond-pad-opening size already
costs 6.4–7.1 pF, more than three times the entire 2 pF budget, before any
clamp capacitance is added. Under the literal as-drawn pad geometry (a
0.62×1.00 µm via-landing square, not a real bond pad — `spec/pad-ring-esd-
survey.md` §4 flags this explicitly), the two targets *do* coexist with
large margin. **The honest, realistic-pad-size reading is a "no
intersection" result, and per the guardrail it is reported here rather
than used to revise DR-0005.**

## 1. Establishing the simulatable device (blocking step, per the issue)

### 1a. Sizing interpretation

The real pad cell's clamp is drawn at `L=0.4U W=2U`
(`layout/gds/gf180_tmds_pad_min.spice`, `layout/lvs/gf180_tmds_pad_min.ref.spice`)
— below the PDK's own `ESD.pl` rule, a 0.8 µm minimum gate length for a
"5V/6V gate NMOS" ESD device (`spec/pad-ring-esd-survey.md` §2, citing
`libs.tech/klayout/tech/drc/rule_decks/esd.drc`). The cell also draws no
`Dualgate` implant layer at all (`layout/scripts/gen_pad_min.py` only
touches `Comp`/`Poly2`/`Nplus`/`Contact`/`Metal1-5`) — i.e. as drawn today
it is a plain 3.3 V-core-device-scaled NMOS wired as a GGNMOS, not a real
5V/6V ESD-implant device at all. `ESD.pl` strictly speaking governs the
latter, not the former.

**Interpretation used here**: re-size the clamp freely (both `W` and `L`),
keeping its topology (drain=`PAD`, gate=source=body=`VSS`) and its device
family (3.3 V core NMOS — see §1b for why no 5/6V-implant alternative is
available), but **grow `L` to the `ESD.pl` floor (0.8 µm)** as the closest
available PDK guidance for an ESD-role NMOS gate length, even though this
device does not carry the ESD-implant layer that rule technically
addresses. This is the more conservative of the two readings the issue's
curated body offered (either is acceptable) — it does not just accept the
under-`ESD.pl` `L=0.4 µm` as-drawn value for the sizing exercise. Every
device swept in this study (§3) other than the literal as-drawn baseline
uses `L=0.8 µm` for this reason.

### 1b. Model-card mapping

`layout/gds/gf180_tmds_pad_min.spice`'s extracted netlist and
`layout/lvs/gf180_tmds_pad_min.ref.spice`'s LVS reference both call the
device model `nfet` — `klt`'s internal LVS device-class label, not a
citable ngspice model card.

**Mapping used here: `nfet` → `nfet_03v3`**
(`libs.tech/ngspice/sm141064.ngspice:47042`, the PDK's 3.3 V core NMOS
subcircuit). Rationale:

- The cell as drawn carries no `Dualgate` layer (§1a), so electrically it
  is built from 3.3 V core-device layers, not the PDK's 5V/6V devices
  (`nfet_05v0`/`nfet_06v0`, `sm141064.ngspice:47099`/`:47125`) — mapping it
  to the 3.3 V model is the mapping that matches what is actually drawn,
  not an arbitrary default.
- `design/netlist/cml_driver.spice` (issue #11) already uses `nfet_03v3` at
  a comparable `L` scale for this block's other custom silicon, so this is
  a reused mapping decision, not a new one.
- The PDK ships **no** dedicated ESD-implant/ESD-clamp SPICE model at all —
  confirmed by grepping `sm141064.ngspice` for `esd`/`ggnmos`/`clamp`/
  `snapback`/`trigger`: zero matches. There is no more-specific citable
  model to prefer over `nfet_03v3` even if the sizing interpretation in
  §1a had gone the other way.

This mapping decision, and the `ESD.pl`-floor gate length from §1a, are
what every simulated result in §3 is measured against — stated and sourced
before any sweep result, per the issue's blocking-step requirement.

## 2. ESD sizing, honestly bounded (design-margin estimate, not qualification)

**This section is a design-margin estimate, not an ESD qualification.**
This repo has no tester and no parts; `measurements/` stays empty by
design until tape-out, per CLAUDE.md and the issue's own framing. Every
number below is either cited to a file/line in the installed PDK or
explicitly marked as drawn from general ESD-design literature, not the
PDK.

### 2a. What the PDK's own sources say (and are silent on)

- `libs.tech/klayout/tech/drc/rule_decks/esd.drc`'s `ESD.*` rules
  (`spec/pad-ring-esd-survey.md` §2) are real, checkable geometry rules for
  an ESD-implant-based device (minimum implant width/area, gate length,
  overlaps) — but say nothing about failure current, breakdown voltage, or
  snapback/trigger behavior.
- `libs.tech/ngspice/sm141064.ngspice` (the PDK's ngspice model library)
  has zero ESD-specific device models or parameters (§1b). Its BSIM4
  `nfet_03v3` model cards do carry a gate-oxide thickness
  (`toxe=8e-9` m, `sm141064.ngspice:795` in the `nfet_03v3.0` bin) usable
  for an order-of-magnitude gate-oxide-rupture estimate (§2c), but no
  drain-junction avalanche/secondary-breakdown current-density data, no
  TLP (transmission-line-pulse) I-V data, and no parasitic-BJT
  snapback/holding-voltage parameters — all of which a real GGNMOS ESD
  sizing exercise needs and which this PDK does not provide.
- **The PDK source is silent on ESD device failure behavior.** This
  matches `spec/pad-ring-esd-survey.md` §8's own finding ("diode SPICE
  parameters (breakdown voltage, avalanche/TLP behavior)" as something the
  survey did not establish) and extends it explicitly to the GGNMOS clamp
  actually in use, per this issue's plan.

### 2b. HBM sizing (quantitative, current-density-based)

**Network**: JEDEC JS-001 human-body-model network — 100 pF charged to the
target voltage, discharged through a 1500 Ω series resistor into the DUT.
**Not sourced from the gf180mcu PDK** (which defines no ESD test networks
at all) — this is the JEDEC JS-001 standard's own fixed network, external
to this PDK.

**Peak current** (first-order estimate): `I_pk = V_HBM / R = 2000 V /
1500 Ω = 1.333 A`. This is the standard textbook first-order estimate
(peak of the idealized double-exponential HBM discharge waveform); a real
tester's waveform typically peaks somewhat below `V/R` because of finite
rise time, so `V/R` is the more conservative (larger, hence larger
required clamp width) of the two figures a first-order analysis would
produce.

**Failure threshold / current density**: the gf180mcu PDK is silent on
this (§2a). **Explicitly unsourced from the PDK**: this document adopts a
commonly cited range from general ESD-design literature for a salicided-
drain grounded-gate NMOS *without* a dedicated ESD implant — roughly
**2–6 mA/µm of drain width** HBM failure-current density (a range
frequently cited in ESD-design references such as Amerasekera & Duvvury,
*ESD in Silicon Integrated Circuits*, and Voldman, *ESD: Circuits and
Devices*; no specific edition/page is cited here because this document has
no access to page-level citation and is deliberately marking this as an
external, not-PDK-sourced assumption rather than presenting it as if it
had one). The clamp as drawn carries no ESD implant (§1a), so the
lower-robustness end of this range (without the ESD-implant improvement a
real `ESD.*`-compliant device would add) is the more defensible one to
design against.

**Required width**: `W = I_pk / density`:

| Assumed density | Required total width `W` |
|---|---|
| 6 mA/µm (favorable end) | 222 µm |
| 3 mA/µm (mid-range) | 444 µm |
| 2 mA/µm (conservative end) | 667 µm |

§3 simulates capacitance at 222 µm and 444 µm directly and reports 667 µm
by linear extrapolation (the simulated curve is effectively linear in
width — see §3c) rather than re-running the matrix a third time.

### 2c. Secondary constraint: clamping voltage (qualitative)

A complete first-order sizing also has to check that the clamp's *on-state
voltage drop* during the 1.33 A HBM pulse keeps the pad below the
breakdown voltage of whatever it protects (here: the gate oxide of any
other device tied to the same pad net). This requires the clamp's
on-resistance/holding-voltage during ESD conduction (parasitic-BJT
snapback behavior) — data this PDK does not provide (§2a). As an
order-of-magnitude cross-check only: `nfet_03v3`'s own `toxe=8 nm` gate
oxide, combined with a commonly cited SiO2 breakdown field of roughly
8–10 MV/cm (**general dielectric-breakdown literature, not the gf180mcu
PDK**), implies a rupture voltage on the order of 6.4–8 V for a directly
stressed gate — comfortably above a well-sized GGNMOS's typical few-volt
snapback holding voltage, but this document cannot verify the actual
clamping voltage without on-resistance/holding-voltage data the PDK does
not supply. **Marked explicitly as an unverified design-margin note, not a
result.**

### 2d. CDM — a turn-on/di-dt requirement, not a second peak-current number

Per the issue's plan, CDM 500 V (JEDEC JS-002) is treated as a different
kind of problem: a fast (sub-nanosecond), package- and tester-dependent
discharge that stresses the clamp's **turn-on speed** (how fast the
parasitic-BJT snapback triggers) far more than its average current
handling. A GGNMOS's CDM robustness is governed by trigger voltage and
turn-on delay, which require either TLP characterization or mixed-mode
TCAD data — neither of which the open gf180mcu PDK provides (§2a: zero
snapback/trigger parameters in `sm141064.ngspice`; no `ESD.*` electrical
data, only geometry rules, in the DRC deck). **This document reports no
CDM-driven width number.** "The source is silent" is the finding here,
exactly as the issue's plan anticipated as a legitimate outcome.

## 3. Clamp capacitance vs. size, at 0 V and at the TMDS operating bias, full PVT

### 3a. Testbench

`sim/esd-clamp-cv/testbench/esd_clamp_cv.spice` (manifest:
`sim/esd-clamp-cv/testbench/tb.json`). Twelve independent branches — six
device sizes × two DC bias states — each its own AC voltage source driving
its own `nfet_03v3` instance (drain=probed node, gate=source=body=`VSS`),
so one ngspice invocation per PVT point measures the whole curve with no
cross-loading between branches.

**Devices simulated**:

| Label | `L` | Total `W` | `nf` (finger count) | Note |
|---|---|---|---|---|
| `base` | 0.4 µm | 2 µm | 1 | as-drawn today, verbatim `AS`/`AD`/`PS`/`PD` from `layout/lvs/gf180_tmds_pad_min.ref.spice` |
| `w2` | 0.8 µm | 2 µm | 1 | `ESD.pl`-floor `L`, as-drawn `W` |
| `w20` | 0.8 µm | 20 µm | 10 | |
| `w100` | 0.8 µm | 100 µm | 50 | |
| `w222` | 0.8 µm | 222 µm | 111 | 6 mA/µm HBM-density estimate (§2b) |
| `w444` | 0.8 µm | 444 µm | 222 | 3 mA/µm HBM-density estimate (§2b) |

Every device's per-finger width is held at 2 µm (matching the drawn cell)
so every device sits in the same BSIM4 model bin (`nfet_03v3.9`, `L`
∈[0.5,1.2) µm × `W` ∈[1.2,10) µm, `sm141064.ngspice`) across the whole
sweep — this avoids a bin-boundary discontinuity artifact in the curve and
keeps every finger inside the model's own characterized width range
(`wmax`=100 µm per bin; a naive single-finger `W=444 µm` instance is
outside every bin and ngspice refuses to resolve a model for it — confirmed
directly by trying it before adopting the multi-finger form).
`AS`/`AD`/`PS`/`PD` scale linearly with total width from the drawn cell's
own per-µm source/drain diffusion depth (1 µm): `AS=AD=W×1µm`,
`PS=PD=2×(W+1µm)` — i.e. total diffusion area/perimeter as one equivalent
non-fingered strip, not a specific real many-finger layout (a real
interdigitated layout could read higher or lower than this depending on
how much source/drain diffusion adjacent fingers share — this is a
reasonable first-order estimate, not a layout deliverable, and is not
claimed to be a bound in either direction).

**Bias**: `DC=0` is the "easy to quote" reference point on every device.
`DC='vdd_val'` reuses the harness's own supply-tolerance PVT axis
(2.97/3.30/3.63 V) as the TMDS operating-bias proxy. This is a direct,
sourced choice, not an arbitrary stand-in: DR-0006 (`spec/tmds-tx.md`)
already establishes that this driver's DC-coupled, open-drain-to-`AVCC`
topology makes the pad's common-mode voltage track the supply rail at
approximately 1:1 (confirmed directly against `design/cml-driver-
sizing.md` §8 and `sim/cml-driver-eye/records/20260810-041436-a2c358b.md`'s
own `vcm_avcclo`/`vcm_avcchi` columns) — so sweeping `vdd_val` across the
mandated ±10 % supply corners *is* sweeping the pad's real operating bias
across its DR-0006-ratified 2.711–3.384 V envelope (which itself brackets
DR-0002's nominal 2.8–3.3 V window), at every PVT point, using the same
grid axis the harness already runs for every other record.

**Extraction method**: small-signal AC analysis, single point at 100 MHz
(`ac lin 1 100meg 100meg`), `C = |Im(I)| / (2π·f·1V)` from each branch's
1 V AC probe current. 100 MHz is far below any intrinsic RC pole of these
devices — `klt`'s own extracted parasitic resistance for the drawn cell's
`PAD` net is 0.145 Ω (§4a), and even the largest simulated capacitance
(≈0.93 pF) against gate/diffusion resistances of order tens of ohms
implies a pole in the multi-GHz range, so the measured value is the
device's incremental capacitance, not a frequency-dependent artifact.

### 3b. Results (full PVT matrix)

Record: `sim/esd-clamp-cv/records/20260814-193222-dd48630.md`. Corner
matrix: process ∈ {tt, ff, ss, fs, sf} (the `mos` corner set — same subset
choice `sim/cml-driver-eye`'s record for issue #11 already used as its
"full PVT matrix" reading; see that record's own "Corner matrix run"
field) × temperature ∈ {−40, 27, 125} °C × supply ∈ {2.97, 3.30, 3.63} V —
45 points, 45/45 `ok`. All twelve measurements at every corner in the
record; summarized here:

| Device | 0 V, min–max (binding corner) | Operating bias, min–max (binding corner) |
|---|---|---|
| `base` (as-drawn) | 3.856–4.544 fF (min `ff_-40c`, max `ss_125c`) | 2.416–2.748 fF (min `ff_-40c_3.63v`, max `ss_125c_2.97v`) |
| `w2` | 3.856–4.540 fF | 2.416–2.748 fF |
| `w20` | 35.85–42.41 fF | 21.87–24.92 fF |
| `w100` | 178.1–210.7 fF | 108.4–123.4 fF |
| `w222` | 394.9–467.4 fF | 240.2–273.7 fF |
| `w444` | 789.6–934.4 fF | 480.2–547.1 fF |

**Binding corner (worst-case, i.e. largest capacitance) across every
device and both bias points: `ss` process, 125 °C, 2.97 V supply**
(`ss_125c_2.97v`) — slow/high-temperature widens junction capacitance, and
the lowest supply corner minimizes the operating-bias device's reverse
bias, both pushing capacitance up together. This is the single corner-id
this document cites for every "worst-case" number below.

**Which bias point the budget is graded on, and why**: the operating-bias
number, not the 0 V number. DR-0005's 2 pF budget exists *"to preserve
742.5 Mbps eye margin"* — i.e. it is a constraint on the capacitance the
driver's edges see while driving data, which is the pad sitting near its
DR-0006 operating common-mode point, not near 0 V. 0 V would only be
physically relevant to an actual ESD strike transient, a completely
separate regime this document does not model (§2). Every "the clamp costs
X pF" figure in §5's verdict uses the operating-bias, `ss_125c_2.97v`
column.

### 3c. Linear extrapolation to the 2 mA/µm (667 µm) HBM case

The curve above is effectively linear in total width (junction area,
perimeter, and gate overlap all scale linearly with a fixed per-finger
geometry replicated `nf` times) — confirmed directly: `w444`'s
operating-bias worst-case value (547.1 fF) is `444/222 = 2.0×` `w222`'s
(273.7 fF) to within 0.03 %. Linearly extrapolating `w444`'s worst-case
values by `667/444 = 1.502×`:

- 0 V, worst case: 934.4 fF × 1.502 ≈ **1.404 pF** (extrapolated, not simulated).
- Operating bias, worst case: 547.1 fF × 1.502 ≈ **0.822 pF** (extrapolated, not simulated).

Both remain under the entire 2 pF budget on their own, at the most
pessimistic HBM-density assumption in §2b's range.

## 4. Pad parasitic capacitance

DR-0005's 2 pF budget is *"ESD diodes + pad parasitic combined"* — §3
covers the clamp; this section covers the Metal5 pad itself, separately.

### 4a. Literal drawn geometry — `klt`-extracted (not an analytic estimate)

**Correction to the issue's own inherited framing**: the original
architect proposal text (preserved at the bottom of issue #12) states
*"Parasitic extraction is not available in the toolchain today"* and
`spec/pad-ring-esd-survey.md` §7/§8 (written for issue #2) likewise
describes no such capability. **That is no longer accurate against the
installed `klt` 0.2.0** — `klt extract --parasitics` (added by
`2AMLogic/klayout-tools#217`, closed 2026-08-01, before this issue's own
2026-08-14 curation pass) exists and works against this exact cell:

```
$ klt extract --deck gf180mcu --parasitics --pdk gf180mcuD \
    layout/gds/gf180_tmds_pad_min.gds --format json
...
"parasitics": {
  "nets": [
    {"net": "PAD", "resistance_ohm": 0.1452, "capacitance_ff": 0.146356},
    {"net": "VSS", "resistance_ohm": 43.466, "capacitance_ff": 0.534782}
  ]
}
```

**The real, `klt`-extracted `PAD`-net parasitic capacitance of the literal
as-drawn cell is 0.146 fF (0.000146 pF)** — negligible against the 2 pF
budget, five orders of magnitude below it, regardless of process corner.
This is a first-order lumped estimate (`klt`'s own curated sheet-
resistance/capacitance table), not a full field solve, but it is a real
tool-measured number against the real drawn geometry, not the analytic
estimate the issue anticipated might be necessary. `spec/pad-ring-esd-
survey.md` §4 is explicit that this shape — `0.62×1.00 µm`, the via-landing
square only — is *"sized generously above every rule `klt`'s gf180mcu deck
checks... not proving area efficiency"* and is **not a real bond-pad
footprint**; that caveat is restated here in full per the issue's explicit
instruction not to report this number without it.

**Cross-check**: computing the same quantity by hand from the PDK's own
`libs.tech/magic/gf180mcuD.tech` `defaultareacap`/`defaultperimeter`
coefficients for Metal1 (the layer dominating this tiny via-stack's
capacitance to substrate, being the closest layer: nominal corner
`29.304 aF/µm²` area, `39.431 aF/µm` perimeter — file citation, "taken
directly from the source document PDS_035_03, in units of aF/um^2 for area
caps and aF/um for perimeter and sidewall caps" per that file's own header
comment at line 3175) against the drawn `0.62×1.00 µm` footprint:
`0.62×1.00×29.304 + 2×(0.62+1.00)×39.431 ≈ 18.2 + 127.8 = 146.0 aF` —
**0.146 fF, matching the `klt`-extracted value to within 0.3 %.** This
agreement is a real, independent cross-validation of both methods, and is
why §4b below reuses the same magic-tech-file coefficients (rather than a
fresh, unvalidated method) for the case `klt` cannot extract directly.

### 4b. Realistic bond-pad-sized assumption — analytic (PDK-cited coefficients)

`klt` can only extract capacitance from geometry that is actually drawn;
`gf180_tmds_pad_min.gds` draws only the tiny via-landing square, not a real
bond pad, so there is no larger real-pad geometry to run `klt` against
without drawing new layout (out of scope for this measurement-only issue —
see the issue's explicit exclusion of "a separate, formally-uncertainty-
budgeted analytic estimate," which this is not: it is a single,
PDK-cited coefficient lookup against one stated, precedented area, not a
new uncertainty model).

**Area assumption**: 25×25 µm² — the gf180mcu_fd_io I/O library's own
established bond-pad opening size (`spec/pad-ring-esd-survey.md` §1, citing
`libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__bi_t.lef`'s `PAD` pin: `RECT
25.000 20.000 50.000 45.000`). This is explicitly the **stated realistic
bond-pad-sized assumption** option the issue's curated body names as
acceptable (as an alternative to the literal drawn shape), cited directly
to the PDK's own shipped library rather than invented.

**Method**: the same `defaultareacap`/`defaultperimeter` Metal5
coefficients validated in §4a, applied to a 25×25 µm² (625 µm² area,
100 µm perimeter) Metal5-only plate — a **lower bound** for a real bond
pad, since the PDK's own reference bond-pad structure
(`Bondpad_5LM`, `spec/pad-ring-esd-survey.md` §1) is a redundant
Metal1-through-Metal5 via lattice, not a Metal5-only plate; the lower
metals in a real structure sit much closer to substrate (Metal1's own
area-cap coefficient is over 5× Metal5's, per §4a) and would only add
capacitance, not remove it. **Explicitly marked analytic, not extracted**,
per `libs.tech/magic/gf180mcuD.tech`'s three named process corners:

| Corner (`gf180mcuD.tech` block) | Metal5 area coeff. | Metal5 perimeter coeff. | 25×25 µm² pad capacitance |
|---|---|---|---|
| Minimum (`hrlc`/`lrlc`) | 5.414 aF/µm² | 29.752 aF/µm | 625×5.414 + 100×29.752 = 6358.95 aF ≈ **6.36 pF** |
| Nominal | 5.798 aF/µm² | 30.386 aF/µm | 625×5.798 + 100×30.386 = 6662.9 aF ≈ **6.66 pF** |
| Maximum (`hrhc`/`lrhc`) | 6.240 aF/µm² | 32.259 aF/µm | 625×6.240 + 100×32.259 = 7125.9 aF ≈ **7.13 pF** |

**A realistic 25×25 µm bond pad on Metal5 alone costs 6.4–7.1 pF** —
**3.2–3.6× the entire 2 pF DR-0005 budget, before adding any clamp
capacitance at all**, and this is a lower bound against the PDK's own
reference multi-layer bond-pad structure.

## 5. Budget split and verdict

Total pad-node capacitance = clamp (§3, operating-bias-graded,
`ss_125c_2.97v` binding corner) + pad parasitic (§4).

Clamp figures below span the §2b HBM-sizing window (222–667 µm total
width, i.e. the 6/3/2 mA/µm density range), operating-bias-graded,
`ss_125c_2.97v` binding corner throughout: **0.240 pF** (222 µm, best-case
corner low end) up to **0.822 pF** (667 µm extrapolated, worst-case corner
high end). The as-drawn `base` device (2 µm, which does not come close to
meeting HBM ≥ 2 kV — that is the entire reason to grow it) costs an
even smaller 0.00242–0.00275 pF and is not part of the sizing window.

| Pad-area reading | Clamp (§3, 222–667 µm HBM window) | Pad parasitic (§4) | Total (worst case) | vs. 2 pF budget |
|---|---|---|---|---|
| Literal drawn (0.62×1.00 µm) | 0.240–0.822 pF | 0.000146 pF | 0.822 pF | **Fits, large margin (1.18 pF headroom, 59 %)** |
| Realistic bond pad (25×25 µm) | 0.240–0.822 pF | 6.36–7.13 pF | 7.95 pF | **Fails by 5.95 pF (4.0× over budget)** |

**Verdict: the ESD and capacitance targets do not coexist under any
realistic bond-pad size, and this document reports that shortfall rather
than revising DR-0005, per the operator's guardrail.**

The two readings above are both computed honestly and both cited; they
disagree by roughly four orders of magnitude in the pad term because the
literal drawn geometry is not a real bond pad (§4a explicitly restates this
caveat) and the realistic reading is. Per the issue's own framing, *"a
positive result obtained by... measuring the pad's literal 0.62×1.00 µm
via-landing shape as if it were a real bond pad, is not"* a valid outcome
— so the literal-geometry row is reported for completeness and cross-
validation, but the **graded, honest verdict is the realistic-bond-pad
row: no intersection.**

This is a materially different finding than DR-0005's original framing
anticipated. DR-0005 frames the tension as *"larger ESD diodes buy more
HBM/CDM margin at the cost of capacitance that closes the eye"* — i.e. a
clamp-sizing trade-off. §3 shows the clamp side of that trade-off is not
actually tight: even the most conservative HBM-density assumption in this
document's range costs under 0.85 pF, leaving over 1 pF of the 2 pF budget
unused by the clamp alone. **The budget is closed by the pad's own
parasitic capacitance, not by clamp sizing** — a different problem than
the one DR-0005 poses, and one this document recommends the operator weigh
directly: DR-0005's ≤2 pF figure may need to be revisited against what a
real bond pad actually costs, independent of any ESD-clamp trade-off,
rather than as a clamp-vs-capacitance trade-off. That recommendation is
offered here as input; per the guardrail, this document does not act on it.

## 6. `klt` coverage limitations relevant to this result

Restated here per the issue's requirement that a verdict's blind spots
travel with it, not be left to the reader:

- **`klt drc --deck gf180mcu` implements none of the `ESD.*` rules**
  (`spec/pad-ring-esd-survey.md` §5) — the curated deck's own module
  docstring describes itself as covering poly2/comp/contact/metal1
  (extended to metal2/3/5/metaltop and the MiM stack) plus one Nwell and
  one BJT rule, explicitly not Pplus/Nplus implant rules, LVPWELL/DNWELL,
  or any 5V/6V/dualgate/ESD-implant variant. A "DRC-clean" result against
  this deck for an ESD-implant-based device (not applicable to the clamp
  actually in use, which carries no ESD implant at all — §1a) would not
  mean clean against the PDK's real ESD design rules.
- **`klt extract --deck gf180mcu` has no diode device class**
  (`spec/pad-ring-esd-survey.md` §7 item 2,
  [2AMLogic/klayout-tools#541](https://github.com/2AMLogic/klayout-tools/issues/541)) —
  irrelevant to this document's GGNMOS clamp directly, but is *why* the
  clamp is a GGNMOS rather than DR-0005's originally named diode
  primitives in the first place, so it is load-bearing context for every
  number in this document.
- **`klt extract --parasitics` (§4a) is a first-order lumped-RC estimate**
  (one series R + one ground C per net, from a curated sheet-resistance/
  capacitance table), not a full field solve — appropriate for the
  order-of-magnitude cross-check this document uses it for, but not a
  signoff-grade parasitic extraction. It also only ever measures geometry
  that is actually drawn; it cannot answer the §4b realistic-bond-pad
  question directly, which is why that number is analytic instead (and
  explicitly marked as such).
- **No PDK/tool source in this repository's reach characterizes ESD
  failure current density, breakdown voltage, or snapback/trigger
  behavior for any device family** (§2a) — every number in §2 is either a
  PDK-geometry citation or an explicitly external, not-PDK-sourced
  literature assumption. No new `2AMLogic/klayout-tools` issue is filed
  for this: it is a PDK/model-content gap, not a `klt` tool gap, and
  `spec/pad-ring-esd-survey.md` §8 already documents it as a PDK-content
  finding rather than something upstream tooling work would fix.

## 7. Links

- Design doc: this file.
- Sizing/HBM inputs: `spec/pad-ring-esd-survey.md` §1–§3, §8; `spec/tmds-
  tx.md` DR-0002, DR-0005, DR-0006.
- Real pad cell: `layout/gds/gf180_tmds_pad_min.gds`,
  `layout/scripts/gen_pad_min.py`, `layout/lvs/gf180_tmds_pad_min.ref.spice`.
- Clamp capacitance testbench: `sim/esd-clamp-cv/testbench/esd_clamp_cv.spice`,
  `sim/esd-clamp-cv/testbench/tb.json`.
- Clamp capacitance record: `sim/esd-clamp-cv/records/20260814-193222-dd48630.md`.
- Eye-margin precedent (cited, not re-derived): `design/cml-driver-
  sizing.md` §5/§7/§8, `sim/cml-driver-eye/records/20260810-041436-a2c358b.md`.
- Model-card mapping precedent: `design/netlist/cml_driver.spice`.
- Friction-protocol citations: `2AMLogic/klayout-tools#541` (diode device
  class), `2AMLogic/klayout-tools#217` (parasitics capability this
  document uses and which corrects the issue's inherited "not available"
  framing).

## 8. Guardrail compliance

**No file under `spec/` is touched by this change.** The verdict in §5 is
a "no intersection under a realistic pad-size assumption" result, reported
with its full evidence per the operator's 2026-08-14 guardrail ruling on
issue #12. This document does not revise DR-0005, does not open a new
decision-record issue on its own authority, and explicitly recommends (§5)
that the pad-vs-clamp trade-off this finding implies be routed back to the
operator as input, not decided here.
