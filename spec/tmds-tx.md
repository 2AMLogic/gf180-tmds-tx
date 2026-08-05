# gf180-tmds-tx — block specification

**Status: RATIFIED 2026-08-05.**
Supersedes the DRAFT table that previously lived in the repo `README.md`
(commit `fc8c465`). Every number below is binding. Changing one requires a
new decision record under [`decisions/`](decisions/) — see
[`spec/README.md`](README.md) for the convention. Agents do not relax this
document to make a result pass.

A **DVI-mode TMDS transmitter**: three data lanes plus a clock lane, DVI 1.0
8b/10b encoding, 10:1 serialization, and a current-mode line driver with a
custom pad and ESD structure, on the gf180mcu open PDK.

- PDK of record: **gf180mcu**, variant **`gf180mcuD`**, open_pdks
  `c6d73a35f524070e85faff4a6a9eef49553ebc2b`. All PDK citations below are
  relative to `$PDK_ROOT/gf180mcuD/`.
- Out of scope: **the PLL**. It comes from a sibling canary. §6 states what
  this block requires from it, numerically, and nothing more.

---

## 1. Resolution ladder

Ratified by [0001](decisions/0001-resolution-ladder.md) and
[0002](decisions/0002-reference-clock-and-clock-mastership.md).

| Mode | Standing | Format | Pixel clock | Bit rate / lane | UI | Half-rate serial clock |
|---|---|---|---|---|---|---|
| **480p** | Guaranteed fallback | 720×480p59.94 (CEA-861 fmt 2/3) | 27.000 MHz | 270.0 Mbps | 3703.7 ps | 135.00 MHz |
| **720p60** | **Target** | 1280×720p60 (CEA-861 fmt 4) | 74.250 MHz | 742.5 Mbps | 1346.8 ps | 371.25 MHz |
| **1080p60** | Stretch — see below | 1920×1080p60 (CEA-861 fmt 16) | 148.500 MHz | 1485.0 Mbps | 673.4 ps | 742.50 MHz |

All three pixel clocks are exact integer ratios of the 27.000 MHz reference
(`×1`, `×11/4`, `×11/2`). Modes needing a `÷1.001` factor — 720p59.94
(74.1758 MHz), 480p60 (27.027 MHz) — are **not supported**; they require
fractional-N synthesis, which [0002](decisions/0002-reference-clock-and-clock-mastership.md)
places out of scope. 640×480p60 (25.175 MHz), the DVI failsafe mode, is
likewise **not supported**; this block therefore does not claim DVI failsafe
conformance.

**1080p60 does not get a vote on architecture.** It is a stretch mode only.
The rule this document ratifies: no architectural choice may be made
*because* of 1080p60 while 720p60 is unclosed, and no 1080p60 requirement may
appear in any signoff gate. It is an acceptable outcome for this block to
tape out with 1080p60 failing. The partition in §4 happens to scale to
1080p60 without restructuring — that is a free property, not a commitment.

## 2. Signal-level specification (per lane, at the pad)

Ratified by [0004](decisions/0004-driver-topology-and-supplies.md).

| Parameter | Symbol | Min | Typ | Max | Unit | Notes |
|---|---|---|---|---|---|---|
| Lanes | — | — | 3 data + 1 clock | — | — | Lane 0 = blue + HSYNC/VSYNC, 1 = green, 2 = red (DVI 1.0 §3.2) |
| Coupling | — | — | DC | — | — | No series capacitor |
| Sink-side termination | R_T | 45 | 50 | 55 | Ω | To the sink's AV_CC; off-chip, not supplied by this block |
| Sink-side termination supply | AV_CC | 3.135 | 3.300 | 3.465 | V | ±5%; sets V_OH, which this block does not control |
| Tail current per lane | I_TAIL | 9.0 | 10.0 | 11.0 | mA | Over PVT, §5 corners; set by external R_REF, §3 |
| Single-ended output swing | V_SWING | 400 | 500 | 600 | mV | = I_TAIL × R_T; the 400–600 window is the DVI 1.0 requirement |
| Differential swing, pk-pk | V_DIFF | 800 | 1000 | 1200 | mV | 2 × V_SWING |
| Output high level | V_OH | AV_CC − 10 mV | AV_CC | AV_CC + 10 mV | V | Set by the sink's termination; driver leakage must not violate it |
| Output low level | V_OL | AV_CC − 600 mV | AV_CC − 500 mV | AV_CC − 400 mV | V | |
| Output common mode | V_CM | AV_CC − 300 mV | AV_CC − 250 mV | AV_CC − 200 mV | V | = AV_CC − V_SWING/2 |
| Pad voltage tolerance (driver off) | — | — | — | 3.465 | V | Pad idles at the sink's AV_CC max — drives the cascode requirement, [0004](decisions/0004-driver-topology-and-supplies.md) |
| Pad-node capacitance | C_PAD | 0.8 | — | 2.0 | pF | Both bounds binding — see §7 |
| Output rise/fall, 10–90% | t_R, t_F | 75 | — | 539 | ps | 539 ps = 0.4 UI at 720p60 |
| Total jitter at the pad, BER 1e-9 | TJ | — | — | 0.20 | UI | §6; 0.05 UI reserved for package/board |
| Intra-pair skew (P vs N) | — | — | — | 40 | ps | Layout-matched by construction |
| Lane-to-lane skew at the pads | — | — | — | 0.20 | UI | Clock lane uses an identical serializer instance, §4 |

**Where the drive current comes from.** The driver is a current *sink*. Its
DC current is supplied by the sink's AV_CC through the sink's 50 Ω
termination and returns to this block's AVSS_TMDS. It is not drawn from this
block's AVDD_TMDS. This block nonetheless dissipates it: 10 mA × ≈2.8 V ≈
28 mW per lane, ≈112 mW for four lanes, all on-die. Budget accordingly.

| Power (preliminary target, TT / 3.30 V / 25 °C, 720p60) | Budget |
|---|---|
| Output drivers (4 lanes, sunk from sink AV_CC) | ≤ 120 mW |
| CML pre-drivers, final mux, bias | ≤ 70 mW |
| Synthesized encoder + custom low-rate serializer | ≤ 60 mW |
| **Block total** | **≤ 250 mW** |

## 3. Bias reference

Ratified by [0004](decisions/0004-driver-topology-and-supplies.md).

| Item | Value |
|---|---|
| External reference resistor | R_REF = 1.00 kΩ ±1%, on dedicated pad `IREF_EXT` |
| Resulting I_TAIL accuracy | ±10% over the §5 corner set |
| Trim | 4-bit, `itrim_i[3:0]`, monotonic, ≥ ±20% range, ≤ 3% steps |

The reference must hold I_TAIL inside ±10% because R_T is itself allowed
±10% and V_SWING = I_TAIL × R_T must stay inside the 400–600 mV window: with
R_T at either extreme, I_TAIL error above ±10% pushes the swing out of
compliance. An on-chip poly resistor (±20% process spread, see
`libs.tech/ngspice/sm141064.ngspice` `res` section) cannot meet this alone,
which is why the reference resistor is external. The trim exists for
characterization and margining, not to rescue a reference that misses ±10%.

## 4. Architecture and the standard-cell / custom / CML boundary

Ratified by [0003](decisions/0003-serializer-partition.md).
Serialization ratio: **10:1**, in three stages.

| Stage | Clock domain (720p60) | Implementation | Devices |
|---|---|---|---|
| DVI 1.0 8b/10b encoder ×3 lanes, control-period coding, 10-bit word assembly | 74.25 MHz (pixel) | **Synthesized** — Yosys + OpenROAD, `gf180mcu_fd_sc_mcu9t5v0` | 6 V (`nfet_06v0`/`pfet_06v0`), 3.3 V rail |
| 10:2 gearbox (10-bit word → 2 bits/clock) | 371.25 MHz | **Custom** CMOS, hand-drawn | 3.3 V (`nfet_03v3`/`pfet_03v3`) |
| ÷5 clock divider (371.25 → 74.25 MHz) and clock distribution | 371.25 MHz | **Custom** CMOS | 3.3 V |
| Final 2:1 DDR mux + retiming latch | 371.25 MHz, both edges | **Custom CML** | 3.3 V |
| Current-steering output driver + pad | 742.5 Mbps | **Custom CML** | 3.3 V switches, 6 V cascode |

**The boundary is at 74.25 MHz.** Standard cells own the pixel-clock domain
and nothing faster. Everything at 371.25 MHz and above is custom.

The reason is measured, not stylistic. `gf180mcu_fd_sc_mcu9t5v0__dffq_1` —
the fastest flop in the library — carries a `minimum_period` constraint in
its own liberty, *before* any logic, routing, or clock skew is added:

| Corner (`libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib/`) | `minimum_period` | Implied ceiling |
|---|---|---|
| `ss_125C_3v00` (slow, 3.3 V −9%, 125 °C) | 2.357 ns | 424 MHz |
| `ss_n40C_3v00` | 1.606 ns | 623 MHz |
| `tt_025C_3v30` | 1.179 ns | 848 MHz |
| `ff_125C_3v60` | 0.991 ns | 1009 MHz |

At the slow corner a 371.25 MHz domain (2.694 ns) would leave 337 ps for
clk→Q, mux, setup, and clock skew across the whole block. That does not
close. At 74.25 MHz (13.468 ns) there is 5.7× margin on the same constraint.
The library is built from 6 V devices at L = 0.6 µm (see
`libs.ref/gf180mcu_fd_sc_mcu9t5v0/spice/gf180mcu_fd_sc_mcu9t5v0.spice`,
every device `nfet_06v0 … L=0.600000U`) — the ceiling is a property of the
*library's device flavor*, not of the process. The custom stages use the
3.3 V flavor (`nfet_03v3`, L_min = 0.28 µm, `libs.tech/ngspice/sm141064.ngspice`),
which is why the same node supports the 371.25 MHz and 742.5 Mbps stages
that standard cells cannot reach.

**Clock lane.** The clock lane is a fourth *identical* serializer and driver
instance, fed the constant 10-bit word `1111100000`. This produces the
required 74.25 MHz, 50%-duty TMDS clock while making lane-to-lane skew a
matter of layout matching rather than of two different circuits agreeing.

**Bit order.** LSB first (`D[0]` on the wire first), per DVI 1.0 §3.2.2.

## 5. Corners, supplies, and environment

| Domain | Pads | Nominal | Corner set | Rationale |
|---|---|---|---|---|
| Digital core | `DVDD` / `DVSS` | 3.30 V | 3.00 / 3.30 / 3.60 V | Matches the characterized liberty corners `*_3v00`, `*_3v30`, `*_3v60` — STA runs on data that exists |
| TMDS driver, CML, bias | `AVDD_TMDS` / `AVSS_TMDS` | 3.30 V | 3.135 / 3.300 / 3.465 V | ±5%, matching the DVI AV_CC tolerance the driver must interoperate with |
| Sink termination supply | off-chip | 3.30 V | 3.135 / 3.300 / 3.465 V | Not supplied by this block; the pad must tolerate its maximum |

- Temperature: **−40 / 25 / 125 °C** (the temperatures at which the PDK
  characterizes both the liberty corners and the SPICE models).
- Process corners, 3.3 V devices: **`typical`, `ff`, `ss`, `fs`, `sf`**
  (`libs.tech/ngspice/sm141064.ngspice` `.LIB` sections at lines 105, 140,
  175, 210, 245).
- **PDK limitation, recorded not worked around:** those five corner sections
  skew only the 3.3 V devices. Each one pulls in `nfet_06v0_t`,
  `pfet_06v0_t`, and `nfet_06v0_nvt_t` — the *typical* 6 V models — so the
  open PDK provides **no process skew for 6 V devices in ngspice**. Any
  analog result that depends on a 6 V device's process corner cannot be
  produced with the models available. This is a direct input to
  [0004](decisions/0004-driver-topology-and-supplies.md): the block keeps
  6 V devices out of every current- and speed-determining role, and the one
  place a 6 V device remains (the output cascode) must be shown by
  sensitivity analysis to be second-order before that result is recorded.
  Digital STA is unaffected — the standard-cell liberty does ship ss/tt/ff.

Analog signoff runs the full cross product {5 process} × {3 temperature} ×
{3 supply} = 45 corners unless a recorded result justifies a subset.

## 6. PLL interface — what this block requires from the sibling block

Ratified by [0005](decisions/0005-pll-interface-and-jitter-budget.md).
**This block does not design a PLL.** This section is the complete,
numeric interface contract; anything not stated here is the PLL block's
choice.

### 6.1 Frequencies

| Item | Requirement |
|---|---|
| Reference input | **27.000 MHz ±50 ppm**, single-ended CMOS 3.3 V, duty 40–60% |
| Output — 480p fallback | **135.00 MHz** |
| Output — **720p60 target** | **371.25 MHz** |
| Output — 1080p60 stretch | **742.50 MHz** (see §6.5) |
| Output format | Differential, DC-coupled, CML-compatible: 300–500 mV single-ended swing, V_CM = 2.50 V ±0.20 V |
| Mode select | 2-bit input from this block (`pll_mode_o[1:0]`); PLL asserts `pll_lock_i` |
| Lock time | ≤ 100 µs from reference-valid or mode change |
| Frequency accuracy | Exact integer ratio to the reference; no ppm error beyond the reference's own |

One implementation that satisfies this: integer-N with N ∈ {40, 55} (VCO
1080 / 1485 MHz) and a ÷2/÷4/÷8 post-divider. It is offered as an existence
proof that the requirement is buildable, **not** as a constraint — the PLL
block owns its topology.

### 6.2 Duty cycle

**50% ± 1.0%**, at the PLL output, over all PVT.

This is not a stylistic preference. The final 2:1 mux (§4) is DDR: it places
one data edge on each clock edge, so clock duty-cycle error transfers 1:1
into output duty-cycle distortion. At 371.25 MHz (period 2.694 ns), ±1.0% is
±26.9 ps, i.e. **53.9 ps pk-pk of deterministic jitter** — already the
largest single line in the budget below.

### 6.3 Jitter budget

UI at 720p60 = **1346.8 ps**. Working backwards from the DVI source
allowance:

| Level | Allowance | Owner |
|---|---|---|
| Source total jitter at the connector | 0.25 UI = 336.7 ps pk-pk | — |
| Reserved for package, board, connector | 0.05 UI = 67.3 ps | Not this block |
| **Total jitter at the pad, BER 1e-9** | **0.20 UI = 269.4 ps pk-pk** | **This block** |

Split as TJ = DJ + 12.0 × RJ_rms (BER 1e-9, Q = 6.0):

**Deterministic, ≤ 150 ps pk-pk total (added linearly — conservative):**

| Source | Allocation | Derivation |
|---|---|---|
| PLL duty-cycle distortion | 54 ps | 50% ±1.0% of 2.694 ns, §6.2 |
| PLL reference spurs | 18 ps | ≤ −40 dBc → θ_pk = 2×10^(−40/20) = 0.020 rad → Δt_pp = θ_pk/(π·371.25 MHz) = 17.2 ps |
| Serializer path: mux select skew, clock distribution mismatch, data-dependent delay | 45 ps | This block |
| Driver and pad | 30 ps | This block; ISI from C_PAD ≤ 2 pF into 50 Ω is <1 ps (§7), so this is dominated by driver asymmetry and supply noise |
| **Sum** | **147 ps** | |

**Random, ≤ 9.9 ps rms total (root-sum-square):**

| Source | Allocation |
|---|---|
| **PLL** | **≤ 7.0 ps rms**, integrated 10 kHz – 200 MHz, at the PLL output frequency |
| Clock distribution, CML mux, driver supply-noise-induced | ≤ 7.0 ps rms |
| RSS | 9.9 ps rms → 12.0 × 9.9 = **118.8 ps pk-pk** |

**Total: 147 + 118.8 = 265.8 ps = 0.197 UI ≤ 0.20 UI.** Adding the 67.3 ps
package/board reserve gives 333 ps = 0.247 UI ≤ 0.25 UI.

### 6.4 The PLL requirement, stated in three equivalent forms

So the PLL block can verify against whichever it measures:

| Form | Value |
|---|---|
| RMS jitter | **≤ 7.0 ps rms**, 10 kHz – 200 MHz, at 371.25 MHz |
| Integrated SSB phase noise | **≤ −38.7 dBc**, 10 kHz – 200 MHz (σ_φ = 2π·371.25 MHz·7.0 ps = 16.33 mrad; ∫L df = σ_φ²/2 = 1.333e-4) |
| Discrete spurs | **≤ −40 dBc**, any single spur, any offset |
| Duty cycle | **50% ± 1.0%** over PVT |

The 10 kHz lower integration limit is deliberately conservative. Because
this is a forwarded-clock link — the TMDS clock lane travels with the data —
jitter below the sink's clock-recovery tracking bandwidth is common to both
and largely cancels. Meeting the bound from 10 kHz is therefore sufficient
but stricter than strictly necessary; the PLL block may not use that
observation to relax the number without a decision record here.

### 6.5 What 1080p60 would cost, and why it is not levied

At 1485 Mbps the UI is 673.4 ps, so 0.20 UI is 134.7 ps. Random jitter does
not scale with UI: an unchanged 7.0 ps rms PLL would consume 118.8 ps of a
134.7 ps budget, leaving 16 ps for all deterministic sources. 1080p60 would
therefore require roughly **≤ 3.5 ps rms and ≤ 0.5% duty error** — a
materially harder PLL.

**This block does not levy that.** The requirement on the sibling PLL is
§6.4 and only §6.4. If the PLL happens to deliver better, 1080p60 becomes
reachable; if it does not, 1080p60 fails and 720p60 is unaffected. This is
the concrete meaning of "1080p60 does not drive architecture."

## 7. Pad cell and ESD

Ratified by [0006](decisions/0006-pad-cell-and-esd-strategy.md). The
*factual* PDK pad-ring and ESD survey is owned by **#2** and must be cited
from there, not re-derived here.

| Item | Ratified value |
|---|---|
| Approach | **Adapt** `gf180mcu_fd_io__asig_5p0`, not draw from scratch |
| Footprint | 75.000 × 350.000 µm, `SITE GF_IO_Site`, `CLASS PAD INOUT` — unchanged from the source cell |
| ESD topology | Dual-diode to rails + shared rail clamp, as in the source cell |
| ESD reference rails | **AVDD_TMDS / AVSS_TMDS** (3.3 V), re-referenced from the source cell's 5 V DVDD/DVSS |
| ESD target | **2 kV HBM (JEDEC JS-001 Class 2)** and **500 V CDM (JS-002 Class C3)**, all pads |
| Pad-node capacitance | **0.8 pF ≤ C_PAD ≤ 2.0 pF** — both bounds binding |

The source cell's ESD structure, from
`libs.ref/gf180mcu_fd_io/spice/gf180mcu_fd_io.spice`:

```
.SUBCKT gf180mcu_fd_io__asig_5p0 ASIG5V DVDD DVSS VDD VSS
D0 DVSS DVDD diode_nd2ps_06v0 m=4.0 area=40e-12  pj=82e-6
X1 DVDD DVSS cap_nmos_06v0 m=36.0 c_length=15e-6 c_width=15e-6
D2 DVSS ASIG5V diode_nd2ps_06v0 m=4.0 area=150e-12 pj=106e-6
D3 ASIG5V DVDD diode_pd2nw_06v0 m=4.0 area=150e-12 pj=106e-6
.ENDS
```

**Why the capacitance has a floor as well as a ceiling.** The pad node is a
single pole against the sink's 50 Ω: τ = 50 Ω × C_PAD, and the 10–90% edge is
2.2τ.

| C_PAD | τ | 10–90% edge | Against the 75–539 ps window (§2) |
|---|---|---|---|
| 0.8 pF | 40 ps | 88 ps | Just above the 75 ps EMI floor |
| 2.0 pF | 100 ps | 220 ps | Comfortably inside |
| 3.0 pF | 150 ps | 330 ps | Inside at 720p60; 0.49 UI at 1080p60 — fails |

Removing ESD capacitance is therefore not free: below ≈0.8 pF the edges
become *too fast* for the DVI minimum rise time. Data-dependent jitter is
negligible either way — at 2.0 pF the channel settles in 13.5τ per UI at
720p60 and 6.7τ at 1080p60 — which is why §6.3 allocates the driver-and-pad
30 ps to asymmetry and supply noise rather than to ISI.

The ESD diodes as shipped are estimated at **≈0.95 pF** at the TMDS operating
bias, computed from the model parameters in
`libs.tech/ngspice/sm141064.ngspice`:

| Diode | Zero-bias | At operating bias | Note |
|---|---|---|---|
| `D2` `diode_nd2ps_06v0`, m=4 | 626 fF | **392 fF** | Reverse-biased by ≈3 V (cjo 0.95 fF/µm², cjp 0.133 fF/µm, pb 0.606, mj 0.296) |
| `D3` `diode_pd2nw_06v0`, m=4 | 609 fF | **560 fF** | Reverse-biased by only ≈0.25 V — the pad idles at AV_CC, so this diode barely depletes (cjo 0.912 fF/µm², cjsw 0.1465 fF/µm, pb 0.768, mj 0.327) |
| **Total** | 1235 fF | **≈952 fF** | Leaves ≈1.05 pF for pad metal, cascode drain, and routing |

That asymmetry is a design fact worth carrying forward: the pad-to-AVDD
diode dominates the capacitance precisely *because* a DC-coupled TMDS pad
idles at the positive rail. Any later attempt to reduce C_PAD should reduce
`D3` first.

**These are hand calculations from model cards, not extractions.** #2 owns
the extracted value. §7 of [0006](decisions/0006-pad-cell-and-esd-strategy.md)
states the ratified contingency if the extraction exceeds 2.0 pF.

## 8. Interfaces

Preliminary and informative except where §1–§7 make a value binding; the pad
list is finalized by #2.

**Video side** (synchronous to `pix_clk_o`, which this block drives — see
[0002](decisions/0002-reference-clock-and-clock-mastership.md)):

| Port | Dir | Width | Notes |
|---|---|---|---|
| `pix_clk_o` | out | 1 | 27.00 / 74.25 / 148.50 MHz per mode. **The video source is slaved to this block.** |
| `d_r_i`, `d_g_i`, `d_b_i` | in | 8 each | Lane 2 / 1 / 0 respectively |
| `hsync_i`, `vsync_i` | in | 1 each | Encoded into lane 0 during control periods |
| `de_i` | in | 1 | High = video period, low = control period |
| `mode_i` | in | 2 | 480p / 720p60 / 1080p60 |
| `rst_n_i` | in | 1 | Async assert, sync deassert |

**PLL side** (on-die, to the sibling block — not pads):

| Port | Dir | Notes |
|---|---|---|
| `sclk_p_i` / `sclk_n_i` | in | Differential half-rate serial clock, §6.1 |
| `pll_lock_i` | in | Serializer holds reset until asserted |
| `pll_mode_o` | out, 2 | Selects the PLL output frequency |

**Pads:**

| Pad | Count | Notes |
|---|---|---|
| `TX0_P/N`, `TX1_P/N`, `TX2_P/N`, `TXC_P/N` | 8 | Adapted `asig_5p0`, §7 |
| `AVSS_TMDS` | ≥ 4 | Flanking each differential pair; carries the full 10 mA/lane return |
| `AVDD_TMDS` | ≥ 2 | |
| `DVDD` / `DVSS` | ≥ 2 each | Separately bonded from the analog rails |
| `IREF_EXT` | 1 | External 1.00 kΩ ±1%, §3 |
| `itrim_i[3:0]` | 4 | May be merged into a serial config port by #2 |

## 9. Signoff gates

The maturity ladder in the repo README, made testable. **No claim without a
testbench**; every analog result carries its corner set (§5); recorded
results are append-only.

| Gate | Evidence required |
|---|---|
| Spec ratified | This document, merged. ✔ |
| Encoder verified | cocotb regression vs. an independent DVI 1.0 §3.2.2 encoder model: exhaustive over all 256 input bytes × both running-disparity states, plus all four control codes, plus a randomized video/control-period stream. DC balance and transition count asserted, not assumed. |
| Serializer verified | cocotb regression on the synthesized 10:2 path; post-synthesis STA closing 74.25 MHz at `ss_125C_3v00`. Custom stages: SPICE, §5 corners. |
| Driver simulated across PVT | §2 table verified over all 45 corners of §5, with the 6 V-corner limitation of §5 explicitly addressed by sensitivity analysis. Eye diagram with the §6.3 jitter injected. |
| Pad cell DRC-clean | `klt drc` clean on the adapted pad, and C_PAD extracted against the §7 window. Owned by #2. |
| Assembled and LVS-clean | `klt lvs` clean, full block including the pad ring. |
| Shuttle seat | All of the above, plus a recorded decision that 720p60 closed. 1080p60 is not a gate. |

## 10. Open items

Recorded rather than buried. Each is a known gap in the evidence behind a
ratified number, not a licence to change one.

| # | Item | Effect if wrong |
|---|---|---|
| O-1 | The **0.25 UI** source jitter allowance (§6.3) and the **75 ps** minimum rise time and **400–600 mV** swing window (§2) are taken from the commonly-applied DVI 1.0 electrical requirements but were **not** checked against the DVI 1.0 document, which is not available in this environment. | The §6.3 budget scales linearly with the UI allowance. If the true figure is tighter, every allocation shrinks proportionally and §6.4's PLL number tightens with it. Verify before tape-out; a change requires a decision record. |
| O-2 | C_PAD (§7) is hand-computed from model cards, not extracted. | If the extraction exceeds 2.0 pF, [0006](decisions/0006-pad-cell-and-esd-strategy.md) §7's ratified contingency applies — and still requires a new decision record to invoke. |
| O-3 | The 6 V devices have no ngspice process corners (§5). | Any result depending on a 6 V device's process spread is unprovable with the open PDK. Mitigated by keeping 6 V devices out of current- and speed-determining roles; the residual is the output cascode. |
| O-4 | The 45 ps serializer-path and 30 ps driver-path DJ allocations (§6.3) are budgets, not simulated results. | They are targets for the driver and serializer issues to meet. If either is exceeded, the overrun comes out of margin, not out of the PLL requirement. |
| O-5 | HBM/CDM levels cannot be verified by `klt drc` or `klt lvs`. | The ESD claim in §7 rests on reusing the PDK's own qualified structure, which is why [0006](decisions/0006-pad-cell-and-esd-strategy.md) adapts rather than redraws. No ESD simulation capability is claimed. |
