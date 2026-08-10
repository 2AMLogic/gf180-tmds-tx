# CML output driver sizing derivation

Sizing record for `design/cml_driver.sch` / `design/cml_driver.sym`
(issue #11). Every width, finger count and bias value below is traced to an
input number with its source, per the issue's requirement. Verification
evidence (the full PVT × bit-rate matrix this derivation is checked against)
lives in `sim/cml-driver-eye/` — see §7, which is the actual pass/fail
authority; everything before it is the derivation that produced the sizes
the record verifies.

## 0. Interface and topology

Ports, per `design/cml_driver.sym`:

| Pin | Direction | Function |
|---|---|---|
| `INP` / `INN` | in | Differential full-rate data from the DR-0003 custom 2:1 final multiplexer. **Not yet designed** — that mux is a separate cell and a follow-on issue. This cell is driven from an ideal differential source with the swing/edge-rate assumption stated in §4, and this cell's results are conditional on that assumption. |
| `OUTP` / `OUTN` | out | Open-drain outputs. The receiver's 50 Ω/leg termination to its own 3.3 V rail (`AVCC` below) is **outside this cell** (DR-0002) — it is the load this cell drives, not something this cell owns. |
| `IBIAS` | inout | Bias *current* input, nominal 500 µA sunk into this pin, mirrored 1:20 onto the tail device inside the cell (§2). The reference that generates 500 µA is a follow-on cell (the bias-generator issue) — modeled here by an ideal DC current source, per the issue's cell-boundary instruction ("bias reference itself is a follow-on, model ideally"). |
| `VSS` | inout | Cell ground; bulk tie for every device (this device family's bulk is grounded — no isolated well is used or needed for an NMOS-only cell). |

There is deliberately **no `VDD` port**: the stage is open-drain current-mode
(DR-0002), so the only rails that ever touch this cell are `VSS` and the
receiver-side termination rail — which is a load-side rail, not a supply
this cell owns.

Topology: two `nfet_03v3` switching devices (`M1`/`M2`) with commoned
sources at a `TAIL` node, sunk by an `nfet_03v3` tail device (`MT`) whose
gate is set by a diode-connected `nfet_03v3` reference device (`MB`) at
20× smaller width — a standard 1:20 current mirror. **Every device in the
cell is `nfet_03v3`**, gf180mcu's 3.3 V core NMOS, satisfying DR-0002; the
committed netlist (`design/netlist/cml_driver.spice`) shows this directly
(four `nfet_03v3` instances, `XM1`/`XM2`/`XMT`/`XMB`, no other device model
appears).

## 1. Inputs and their sources

### 1.1 Spec targets (DR-0002, §1)

- 50 Ω/leg termination to the receiver's 3.3 V rail, ~10 mA tail current.
- Single-ended swing target ~500 mV, working range 400–600 mV.
- Common-mode target 2.8–3.3 V.
- Device family: `nfet_03v3`/`pfet_03v3` (3.3 V core devices) — this design
  uses only the NMOS half of that family; an open-drain NMOS pull-down into
  an external pull-up resistor needs no PMOS.

### 1.2 PDK-published electrical data (`nfet_03v3`)

Per [GF180MCU PDK Electrical Specifications §1.0, Low Voltage Devices
(3.3V)](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_1.html)
(fetched 2026-08-10):

| Parameter | Device | W/L tested | min | typ | max | units |
|---|---|---|---|---|---|---|
| `VT0` (linear threshold) | NCH (NE2) | 10/0.28 | 0.53 | 0.63 | 0.73 | V |
| `Idsat` (\|Vds\|=\|Vgs\|=3.3 V) | NCH (NE2) | 10/0.28 | 430 | 510 | 590 | µA/µm |
| `BVDSS` (punch-through) | NCH (NE2) | 10/0.28 | 7 | 9 | — | V |

The vendored PDK's own `sm141064.ngspice` model card carries the same
threshold spread across its process-corner variants (`nfet_03v3_vth0_0`
through `_15`, ≈ 0.648–0.754 V — confirmed by direct inspection of the
installed `sm141064.ngspice`, gf180mcuD, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`), consistent with the table's
0.53–0.73 V window (the model's per-corner spread is narrower than the
table's absolute min/max because it is a *simulation* corner set, not a
silicon-lot spread).

**Device rated limit used for stress checking (§6)**: no separate
absolute-maximum-ratings table ships with the volare distribution for this
device family. This design adopts **3.63 V (nominal + 10 %)** as the rated
operating ceiling for `Vgs`/`Vgd`/`Vds` — the same envelope this repo's own
mandated PVT matrix already treats as the supply extreme
(`sim/harness/corners.py`'s `DEFAULT_SUPPLY_TOLERANCE`), and the standard
reliability convention for a device family whose own PDK-published
characterization bias is `Vgs=Vds=3.3 V` nominal (the `Idsat` row above).
This is a conservative *rated-operating-margin* choice, not a
proximity-to-breakdown one: the same table's punch-through voltage `BVDSS`
is 7–9 V, more than 3× the adopted 3.63 V ceiling, so there is a large
additional guard-band between "rated" and "hard failure."

### 1.3 Mirror ratio and tail current

DR-0002's ~10 mA target is realized as a 1:20 current mirror from a 500 µA
reference:

```
I_tail = 20 x I_ref = 20 x 500 uA = 10.0 mA   (nominal, ideal-mirror)
```

Realized in `design/cml_driver.sch` as `MB` (`W=20u nf=10 L=0.5u m=1`,
diode-connected, total width 20 µm) and `MT` (`W=20u nf=10 L=0.5u m=20`,
total width 400 µm) — same unit cell (`W=20u`/`nf=10`/`L=0.5u`, 2 µm/finger),
scaled only by `m`, so the two devices share identical `L`, finger geometry
and (to first order) `Vth`/mobility; only mismatch and finite output
impedance (`lambda`) distinguish them. `L=0.5u` (well above the process
minimum) is chosen specifically to keep `lambda` — and therefore the
mirror's `Vds`-mismatch-driven current error — small; this is a direct
design response to §2's tail-current-tolerance requirement, not an
arbitrary choice.

## 2. Tail current / swing arithmetic and tail-current tolerance

**Arithmetic** (DR-0002's headline derivation):

```
V_swing,se = I_tail x R_leg = 10 mA x 50 ohm = 500 mV
```

— centered in the 400–600 mV window with 100 mV (20 %) of headroom on each
side. Since `R_leg` is the *receiver's* termination (external to this chip,
not a swept process parameter here — the same modeling convention
`sim/smoke-cml-pair` established), the entire budget for staying inside
400–600 mV is a **tail-current tolerance**: `I_tail` must stay within
`10 mA x [0.8, 1.2]` = **8–12 mA** at every PVT point, at both operating
rates.

**This is the row DR-0002 flagged as "most likely to bind," and it binds
through the bias network** — the mirror's own accuracy plus the 500 µA
reference's own accuracy, added together, must clear the ±20 % budget. This
section quantifies the mirror's own share, which is what this cell can
control; the reference's share is what this section levies on the follow-on
bias-generator cell.

**Measured (`sim/cml-driver-eye`, full PVT matrix, `itail_dc`, an ideal
500 µA reference — no PVT compensation of its own)**:

| | value | corner |
|---|---|---|
| Minimum | 9.822 mA | `ss_125c_2.97v` |
| Maximum | 10.327 mA | `ff_-40c_3.63v` |
| Nominal (mirror-ideal) | 10.000 mA | — |

Deviation from the 20×-ideal target: **−1.78 % / +3.27 %** across the full
mandated PVT matrix (both rates — `itail_dc` is a DC/op-point measurement,
rate-independent, confirmed identical across the two rate columns in the
record). This is the mirror's *own* PVT sensitivity with a **perfectly
constant 500 µA reference** — it isolates exactly what the matched-device
mirror topology buys over a naive fixed-`Vgs` bias (which would show the
device family's full `Idsat` process spread directly, ≈ ±14 % from the
§1.2 table alone before adding temperature — a current mirror cancels
`Vth`/mobility to first order because `MB` and `MT` share the same `.lib`
corner section in every simulated point; only the `Vds` mismatch between the
diode-connected reference (`Vds≈Vgs≈1.1–1.3 V`) and the tail's own operating
point (similar range, confirmed in the record) remains, which is why `L`
was set well above minimum in §1.3).

**Tail-current tolerance this cell requires of the follow-on bias-generator
cell** (its own accepted-issue requirement, not just a note): using
worst-case-additive combination (conservative — no assumption that the two
error sources are independent/uncorrelated) against the total ±20 % budget
and this cell's own measured worst-case +3.27 % contribution:

```
tolerance_bias_generator <= 20% - 3.27% ~= 16.7%
```

**The 500 uA `IBIAS` reference must be held within roughly ±16.7 % across
the full PVT matrix** for the combined chain (reference + this cell's
mirror) to guarantee `I_tail` stays inside the 8–12 mA / 400–600 mV window.
This is a comfortable target for a bandgap-referenced or PTAT/CTAT-corrected
current generator (order ±1–5 % is typical for such a reference), so this
requirement is not expected to be the binding constraint on the follow-on
bias-generator cell's own design — but it is the number that design must be
checked against, not assumed.

## 3. Headroom inequality

For both the tail device and the ON switching device to remain in
saturation (out of triode, where current would drop below the mirrored
target and the output would sag toward the rail rather than the intended
swing), each device's terminal `Vds` must exceed its own `Vdsat`:

```
Vds_tail  > Vdsat_tail     (tail device stays saturated)
Vds_sw,on > Vdsat_sw,on    (ON switch device stays saturated)
```

with `Vds_tail + Vds_sw,on = V(TAIL-referenced-node) ... AVCC - I_tail*R_leg`
(the ON leg's settled low level) as the total headroom available between
the pulled-down output node and ground.

**Worst case** — lowest supply, highest temperature (both reduce headroom:
low `AVCC` compresses the available voltage, high `T` raises `Vdsat` via
reduced mobility) — is `ss`/125 °C/`AVCC`=2.97 V (also the PVT matrix's
lowest-swing corner, §2). A dedicated op-point probe at this exact corner
(same device geometry as the committed schematic; reproducible from
`design/netlist/cml_driver.spice` plus the bias conditions below) measured:

| Device | `Vds` (actual) | `Vdsat` | Margin |
|---|---|---|---|
| Tail (`MT`) | 0.893 V | 0.499 V | **+0.395 V** (79 % over `Vdsat`) |
| Switch, ON (`M1`) | 1.591 V | 0.628 V | **+0.963 V** (153 % over `Vdsat`) |

Both devices clear their own saturation boundary with substantial margin at
the worst PVT/rail point in the mandated matrix — the headroom inequality
passes with room to spare, not marginally.

## 4. Switch-pair sizing (from available gate overdrive)

### 4.1 Input swing assumption (levied on the DR-0003 mux)

The DR-0003 final multiplexer is a follow-on cell; this cell's results are
conditional on the input it is assumed to deliver, stated explicitly (see
`sim/cml-driver-eye/testbench/cml_driver_eye.spice`'s header for the same
numbers in testbench form):

- Single-ended levels `vih = 0.85 x VDD`, `vil = 0.55 x VDD` (2.805 V /
  1.815 V at the nominal 3.3 V digital rail) — i.e. a differential input
  swing of `0.30 x VDD` (≈ 0.99 V at nominal, ≈ 0.891 V at the digital
  rail's −10 % extreme), common mode `0.70 x VDD`.
- An 80 ps linear edge, at **both** bit rates (the mux is designed for the
  742.5 Mbps target and is not assumed to slow at the 270 Mbps fallback).
- Zero source impedance, zero jitter (every picosecond measured at this
  cell's output is this cell's own contribution, not inherited).

### 4.2 Steering-completeness derivation

A differential pair only delivers the full mirrored tail current to one
leg — the condition this design's whole swing/common-mode arithmetic
assumes — once the differential input exceeds the device's own
full-commutation threshold. A DC sweep of differential control voltage
against three switch-width candidates (all `L=0.28u`, minimum length — a
full-rate switch has no reason to use a longer channel, unlike the tail
device in §1.3), same `I_tail=10 mA` load, `typical`/27 °C:

| Candidate | `W` | Differential input needed for >99.9 % commutation |
|---|---|---|
| `W=40u` (`nf=20`) | 40 µm | ≈ 1.8 V |
| `W=64u` (`nf=32`) | 64 µm | ≈ 1.6 V |
| **`W=128u` (`nf=64`, chosen)** | **128 µm** | **≈ 0.8 V** |

The mux's assumed available differential swing (§4.1) is ≈ 0.891–0.99 V
across the digital rail's own ±10 % range — inside the `W=128u` candidate's
≈ 0.8 V full-commutation point with margin, but *not* reachable by either
narrower candidate (which need 1.6–1.8 V, 60–100 % more than this design
provides). **`W=128u`/`nf=64`/`L=0.28u` is therefore the derived minimum
practical width for full current steering at the mux's realistic reduced
swing** — a minimum-size device would leave the tail current only partially
steered, which (besides failing the swing target directly) would produce a
physically invalid split current path against this device family's grounded
bulk, the same failure mode `sim/smoke-cml-pair`'s own header comment
documents.

### 4.3 Full-tail-current steering within the bit period

At 742.5 Mbps the bit period is 1.347 ns; the assumed 80 ps input edge
(§4.1) is 5.9 % of the UI, so the switch pair's own steering time must not
add materially to that. The measured 10–90 % output rise/fall time at 0 pF
pad load (§7, the closest measurement to the switch pair's own intrinsic
speed, unburdened by external capacitance) is 40.5–59.3 ps across the full
PVT matrix at both rates — i.e. **comparable to, not larger than, the input
edge itself**, confirming the `W=128u` switch pair does not become the
bottleneck: the pair steers the full tail current well within a fraction of
the bit period at both 742.5 Mbps and 270 Mbps.

## 5. Bandwidth / dominant-pole analysis at 0, 1 and 2 pF pad load

The dominant pole at each output node is set by `R_leg` (50 Ω, and — per
§7's measured `ro_leg`, 11.0–56.8 kOhm, always ≥ 200× `R_leg` — the cell's own
output impedance is never a meaningful loading term) against the total
capacitance at that node: the cell's own intrinsic drain/junction
parasitics, plus the pad capacitance parameter DR-0005's ESD budget levies
(swept 0/1/2 pF, per this issue's own instruction and directly feeding
issue #12's ESD characterization work).

**Measured 10–90 % rise/fall time** (`sim/cml-driver-eye`, full PVT matrix,
both rates — values are ranges across the whole grid, not a single point):

| Pad cap | `trise`/`tfall` 10–90 % | Implied `f_-3dB` (`0.35/tr`, single-pole approximation) |
|---|---|---|
| 0 pF | 40.5–59.3 ps | 5.9–8.6 GHz |
| 1 pF | 105.0–139.3 ps | 2.5–3.3 GHz |
| 2 pF (DR-0005's full budget) | 205.9–251.6 ps | 1.4–1.7 GHz |

**Cross-check against the `R x C` estimate**: treating the 0 pF point as
revealing the cell's own intrinsic output capacitance,
`C_intrinsic = tr/(2.2 x R_leg)` gives ≈ 0.37–0.54 pF (best/worst corner).
Adding that to the swept pad capacitance and re-applying the same formula to
the 1 pF and 2 pF rows predicts `tr` in the ≈ 48–115 ps (1 pF) and ≈ 87–177 ps
(2 pF) range — the same order of magnitude as the directly measured values
above, with the single-pole approximation's usual optimism (a two-terminal
switch + tail network is not a clean single pole, so this is a sanity
cross-check, not a substitute for the direct measurement it's checked
against).

**Even at DR-0005's full 2 pF budget, the implied bandwidth (≥ 1.4 GHz) sits
comfortably above the signal's own relevant frequency content at 742.5 Mbps**
(fundamental ≈ 371 MHz at max-transition-density, out to a few harmonics
still well under 1.4 GHz) — consistent with §6's near-zero measured
data-dependent jitter at every pad-cap point. This is the trade curve issue
#12's ESD characterization work needs from the driver side (per this issue's
own framing): more ESD diode area buys HBM/CDM margin at the cost of pad
capacitance that erodes this bandwidth margin, and the 2 pF budget point
still leaves comfortable headroom against the 742.5 Mbps signal.

## 6. Jitter contribution against §2's <= 0.15 UI allocation

**Measurement method**: `sim/cml-driver-eye/testbench/cml_driver_eye.spice`
drives the cell with a 16-bit pattern (`1111111110101010`, MSB first) — nine
settled bits (full DC settling) followed by seven bits of maximum-transition-
density alternation — and measures the propagation delay of two different
output edges deep in the alternating section (a rising and a falling edge,
each several UI after the settled run) relative to the *input's* own ideal
timing for those same edges. The peak-to-peak spread between those two
edges' delay deviation, normalized by the measured UI, is `dj_ui_*` — this
isolates **deterministic jitter (ISI + rise/fall asymmetry)** the driver
itself contributes; the input is jitter-free by construction (§4.1), so the
entire spread is this stage's own. Random jitter is not a transient-
simulation quantity and is not included (same caveat `sim/README.md`'s
stimulus convention states for this class of measurement).

**Measured, full PVT matrix, both rates, matched pad-cap legs**:

| Pad cap | `dj_ui` max | vs. <= 0.15 UI allocation |
|---|---|---|
| 0 pF | 2.97 x 10^-6 UI | **PASS**, ~50,000x margin |
| 1 pF | 4.46 x 10^-6 UI | **PASS**, ~34,000x margin |
| 2 pF | 3.56 x 10^-5 UI | **PASS**, ~4,200x margin |

**Deliberate leg-to-leg pad-capacitance mismatch** (2 pF on `OUTP`, 1 pF on
`OUTN` — half of DR-0005's whole budget as imbalance, a jitter-sensitivity
probe rather than a nominal configuration): `dj_ui_cmis` max = 1.337 x 10^-3
UI — still **PASS** against the 0.15 UI allocation, ~112x margin, though
visibly larger than the matched-leg rows (as expected: a matched differential
pair's ISI is antisymmetric and partially cancels at the differential zero
crossing; a mismatched load breaks that cancellation). This is the concrete
number issue #12's pad-ring work should treat as a matching requirement,
not an assumption.

The driver's own contribution is negligible against the §2 budget at every
measured point, at both rates, with or without pad-cap mismatch — the
bandwidth margin established in §5 is the direct cause (edges settle fully
within each UI even at the full 2 pF budget, so essentially no
pattern-dependent delay difference is measurable).

## 7. Verification — `sim/cml-driver-eye/`

Full PVT (5-corner `mos` set x -40/27/125 C x 2.97/3.30/3.63 V) x bit-rate
(742.5 and 270 Mbps/lane) matrix, 90 points, against the DR-0002 load (50
ohm/leg to the receiver's own 3.3 V rail) at 0/1/2 pF pad capacitance, per
`sim/README.md`'s evidence-record convention.

**Result summary** (see the linked record for the full per-corner table):

| Row | 742.5 Mbps (720p60 target) | 270 Mbps (480p fallback) | Spec target |
|---|---|---|---|
| Swing, 0 pF (`swing_c0`) | 482.0–518.9 mV (`ss_125c_2.97v` / `ff_-40c_3.63v`) | 481.3–516.6 mV (same binding corners) | 400–600 mV |
| Swing, 1 pF (`swing_c1`) | 481.7–518.6 mV | 481.3–516.7 mV | 400–600 mV |
| Swing, 2 pF (`swing_c2`) | 481.2–516.8 mV | 481.3–516.7 mV | 400–600 mV |
| Common mode, 0/1/2 pF (`vcm_c0/c1/c2`) | 3.041–3.054 V | 3.042–3.054 V | 2.8–3.3 V |
| DJ, 0/1/2 pF (`dj_ui_c0/c1/c2`) | <= 3.56e-5 UI | <= 8.1e-6 UI | <= 0.15 UI |
| Vgs/Vgd/Vds stress (worst of all rows) | 2.761 V (`vds_sw_max`, `ss_-40c_2.97v`) | 2.761 V (same) | <= 3.63 V rated, positive margin |
| Tail current (`itail_dc`) | 9.822–10.327 mA | 9.822–10.327 mA (rate-independent) | 8–12 mA (this cell's own derived tolerance, §2) |

**480p fallback is reported here as a fallback result only** — it is not
folded into, or used to relax, the 720p60 target row above; both are named
and passed independently, per the acceptance criteria's explicit
requirement.

**Overall: PASS**, all rows, both rates, all three pad-cap points, full PVT
matrix — but that matrix sweeps process/temperature/pad-capacitance at
**nominal AVCC = 3.3 V** only; it does not by itself say anything about the
±10 % supply-corner sweep reported in §8. Once §8's AVCC ±10 % sensitivity
data is checked against DR-0002's common-mode target, the target as
originally stated (a flat 2.8–3.3 V window with no supply qualifier) is
crossed at both supply extremes. **A `spec/` change was needed**: see
**DR-0006** in `spec/tmds-tx.md` §4, which ratifies the 2.8–3.3 V
common-mode window as a nominal-AVCC-3.3 V figure with an explicit
supply-tracking tolerance across the ±10 % sweep. Against DR-0006's
qualified requirement, every row in this table (nominal-supply,
`vcm_c0`/`vcm_c1`/`vcm_c2`) and every row in §8's AVCC-sensitivity data
still PASS — the earlier "no `spec/` change was needed" framing addressed
only the nominal-supply sweep in this table, not §8's supply-corner data,
and has been corrected here.

Record: [`sim/cml-driver-eye/records/20260810-041436-a2c358b.md`](../sim/cml-driver-eye/records/20260810-041436-a2c358b.md) (see that file for the
complete 90-row per-corner table, the append-only evidence trail, and the
full Environment/provenance section — testbench, DUT netlist, and PDK/tool
versions). Testbench: `sim/cml-driver-eye/testbench/cml_driver_eye.spice`,
`sim/cml-driver-eye/testbench/tb.json`. DUT netlist (derived from
`design/netlist/cml_driver.spice`, see that file's own header for the
regeneration recipe): `sim/cml-driver-eye/testbench/cml_driver_dut.spice`.

## 8. Additional characterization (not spec-bound except where noted, reported per issue #9)

Per this issue's instruction to report rows the ratified spec does not yet
bound (since issue #9 proposes some of them as DR-0009), so a future
decision record can cite evidence rather than a textbook. One row below —
the `AVCC` common-mode sensitivity — is no longer "not spec-bound": DR-0006
(`spec/tmds-tx.md` §4) now governs it directly, per issue #19.

- **10–90 % rise/fall**: §5's table (40.5–59.3 ps at 0 pF, up to 205.9–251.6
  ps at 2 pF).
- **Tail/supply current draw**: `itail_dc` 9.822–10.327 mA (§2);
  `icell_dc` (whole-cell current, includes the reference branch) 10.32–10.83
  mA across the same grid.
- **Single-ended output impedance looking back into each leg** (`ro_leg`,
  two-point DC extraction at the cell's own operating levels, independent of
  the external 50 ohm termination): 11.0–56.8 kOhm across the full PVT
  matrix — always >= 220x the 50 ohm external termination, confirming the
  cell's own output impedance never meaningfully loads the DR-0002 termination
  or shifts the dominant pole computed in §5.
- **Termination-rail (`AVCC`) sensitivity — spec-bound, per DR-0006**
  (previously reported here as "not spec-bound"; corrected per issue #19):
  swing and common-mode at `AVCC` -10 %/+10 % (`swing_avcclo`/
  `swing_avcchi`, `vcm_avcclo`/`vcm_avcchi`), reported in the record.
  Common mode tracks `AVCC` essentially 1:1 (`vcm = AVCC - I_tail x R_leg /
  2`, as DR-0002's own topology note predicts) — measured **2.711–2.725 V**
  at `AVCC` = 2.97 V and **3.370–3.384 V** at `AVCC` = 3.63 V across the
  full PVT matrix (re-extracted `min`/`max` of `vcm_avcclo`/`vcm_avcchi`).
  Per DR-0006, DR-0002's 2.8–3.3 V common-mode window is a
  nominal-`AVCC`=3.3 V figure with this measured tracking as the explicit
  supply-tolerance qualifier — **PASS** against DR-0006's qualified
  requirement (this data crosses DR-0002's original flat-window reading,
  which is exactly why DR-0006 was needed; see §7). Swing stays within the
  400–600 mV window across the same +/-10 % sweep, unaffected — swing
  tracks `I_tail x R_leg`, not `AVCC`, per DR-0002's unchanged swing
  clause.

## 9. Non-goals (explicit, per this issue's scope)

- **No PLL.** Out of scope per `CLAUDE.md`; this cell's clocking is not
  addressed here (it has none — it is a purely combinational current-steering
  stage between the DR-0003 mux and the pad).
- **No ESD network design.** Pad capacitance is a swept load parameter only
  (§5/§7); the clamp network itself is issue #12's subject.
- **No 1080p60 headroom.** Every design choice above is checked against
  720p60 (742.5 Mbps) as the target and 480p (270 Mbps) as the fallback
  only — no sizing decision here was made to accommodate the 1.485 Gbps
  stretch rate.
