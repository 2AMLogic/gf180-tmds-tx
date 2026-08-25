# Block characterization report

This is the single aggregated, current summary of what this block's recorded
evidence actually substantiates against the ratified spec
(`spec/tmds-tx.md`), per spec row. It is written for Epic #17's T1
sim-validated (bronze) evidence-tier ladder: one artifact, citing every
evidence record against the specific spec row it verifies, and naming what
is not yet covered explicitly rather than leaving it to be inferred from
silence.

Per CLAUDE.md ("Verification is the product: no claim without a
testbench... recorded results are append-only evidence"), every verdict
below cites a specific evidence record — `sim/*/records/*.md` for the analog
CML-driver partition (§1), `flow/tmds_encoder/records/*.md` plus
`verification/tmds_encoder/` for the digital encoder partition (§2). This
document makes no claim beyond what those records already state — it is a
index and rollup, not new measurement work. `measurements/` itself stays
otherwise empty until tape-out (see `measurements/README.md`), consistent
with this being a design/simulation-stage rollup, not a silicon
characterization.

**Convention**: this document is not append-only in the `sim/` sense — it is
expected to be revised in place as evidence accumulates (a new record lands,
a coverage gap closes). Each cited record itself remains the append-only
source of truth; this document only ever needs to be re-pointed at the
latest one.

## 1. Spec-row coverage

`spec/tmds-tx.md` §1's target parameter table and its decision records
(DR-0001 through DR-0006) are the rows below. Only rows with a recorded
`sim/` evidence record are listed as "covered" — a row not listed here has
no simulation evidence at all yet.

### DR-0002 — driver topology and supply (swing, common mode, device stress)

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| Single-ended swing 400–600 mV into 50 Ω/leg, ~10 mA tail | **PASS** | [`sim/cml-driver-eye/records/20260810-041436-a2c358b.md`](../sim/cml-driver-eye/records/20260810-041436-a2c358b.md) | Full PVT × both rates (90 points). Measured 481.2–518.9 mV across every pad-cap point (0/1/2 pF) and both rates — see `design/cml-driver-sizing.md` §7's summary table. |
| Common mode 2.8–3.3 V at nominal AVCC = 3.3 V | **PASS** | same record | 3.041–3.054 V across the full PVT × rate × pad-cap grid at nominal supply. |
| Common mode across the ±10 % supply-corner sweep | **PASS, against DR-0006's qualified reading** | same record | At AVCC = 2.97 V/3.63 V, common mode reaches 2.711 V / 3.384 V — outside DR-0002's original flat 2.8–3.3 V window taken literally, but DR-0006 (`spec/tmds-tx.md` §4) ratifies the window as a nominal-AVCC-3.3 V figure with this measured 1:1 supply-tracking as the explicit qualifier. Graded against DR-0006, every row in this record PASSes; graded against DR-0002's original unqualified text, the supply-corner rows do not. Both readings are stated here, per DR-0006's own correction of `design/cml-driver-sizing.md`'s earlier framing. |
| `Vgs`/`Vgd`/`Vds` margin against the 3.3 V core devices' rated limit (deferred to driver design work by DR-0002) | **PASS** | same record | Worst measured stress 2.761 V (`vds_sw_max`, `ss_-40c_2.97v`) against the adopted 3.63 V rated ceiling — positive margin at every corner. |
| Remaining (serializer+driver+board) jitter allocation, ≤ 0.15 UI p-p (spec/tmds-tx.md §2) | **PASS** | same record | Driver's own deterministic-jitter contribution measured ≤ 3.56×10⁻⁵ UI at 2 pF pad load (full PVT, both rates) — several thousand times inside the 0.15 UI budget. This measures the driver stage only, not the full serializer+driver+board chain the budget row nominally covers (the serializer/mux stage upstream of this driver has not itself been captured yet — see §3 below). |
| Tail-current tolerance (this cell's own derived requirement, §2 of `design/cml-driver-sizing.md`, not a `spec/tmds-tx.md` row) | **PASS** (informative, not spec-bound) | same record | 9.822–10.327 mA across the full PVT matrix, inside the design's own derived 8–12 mA tolerance. |

#### DR-0002, post-layout (extracted) corroboration

[`sim/cml-driver-eye/records/20260815-072956-34e5253.md`](../sim/cml-driver-eye/records/20260815-072956-34e5253.md)
re-runs **the same testbench deck, manifest, measurements and checks** as the
schematic record above — same 90-point PVT × rate grid — against the
layout-extracted netlist of the DRC/LVS-signed-off cell
(`layout/gds/cml_driver_core.gds` → `layout/gds/cml_driver_core.spice` →
`layout/sim/cml_driver_core_dut.spice`, issue #22 / issue #34). Every row in
the schematic table above holds against the extracted netlist too:

| Sub-claim | Schematic record | Extracted record | Verdict |
|---|---|---|---|
| Single-ended swing, 400–600 mV | 481.2–518.9 mV | 481.2–519.0 mV | **PASS**, unchanged |
| Common mode at nominal AVCC | 3.041–3.054 V | 3.041–3.054 V | **PASS**, unchanged |
| Common mode at ±10 % supply | 2.711 V / 3.384 V | 2.711 V / 3.384 V | same DR-0006 qualified reading as above |
| Worst device stress vs. the 3.63 V ceiling | 2.761 V (`vds_sw_max`, `ss_-40c_2.97v`) | 2.757 V (`vds_sw_max`, `ss_-40c_2.97v`) | **PASS**, unchanged |
| Driver's own deterministic jitter, ≤ 0.15 UI p-p | ≤ 3.56×10⁻⁵ UI at 2 pF | ≤ 5.79×10⁻⁵ UI at 2 pF | **PASS**, unchanged |
| Tail current, 8–12 mA derived tolerance | 9.822–10.327 mA | 9.822–10.327 mA | **PASS**, unchanged |

**The measured deltas, and why they are what they are.** The corner-by-corner
comparison is computed, not transcribed —
`python3 sim/compare_records.py cml-driver-eye 20260810-041436-a2c358b 20260815-072956-34e5253`
reproduces the full 46-measurement table; **no corner changed verdict**. The
deltas fall into three groups:

1. **DC operating point: unchanged to within 0.01 %.** Swing ≤ +0.010 %,
   common mode ≤ 0.001 %, tail current ≤ 0.001 %, single-ended output
   resistance ≤ 0.11 %, worst-case device stress ≤ 0.73 % (`vgs_sw_max`) —
   all far below any corner-to-corner variation. This is the expected
   result and it is the useful one: the drawn cell's total device widths,
   channel lengths and the 1:20 mirror ratio come out of the layout equal
   to the sized schematic's, so the bias point the swing/common-mode claim
   rests on is a property of the drawn geometry, not of the schematic's
   idealisation of it.
2. **Edge rate at the unloaded pad point: +2 to +4.4 %, from junction
   capacitance.** `trise_c0`/`tfall_c0` (0 pF pad) move by up to +4.39 %
   (41.2 → 43.0 ps at `ff_-40c_3.30v_270mbps`), with `vpp_c0` following at
   up to +1.35 %. The same measurement at the 1 pF and 2 pF pad points moves
   by ≤ 0.58 %. That ratio is the signature of a small fixed capacitance
   added at the output node: fitting rise time against the swept pad
   capacitance gives an unloaded output-node capacitance of **≈ 404 fF
   (schematic) vs. ≈ 418 fF (extracted) — about +14 fF, ~3.5 %**. The cause
   is the difference between xschem's folded-device `AS`/`AD`/`PS`/`PD`
   estimate for `nf=64`/`m=20` devices and the extractor's per-finger
   measurement of the *drawn* diffusion shapes (338 separate finger
   devices, shared diffusions split between neighbours). It is a real
   post-layout effect, it is small, and it is bounded: at the ≥ 1 pF pad
   loading DR-0005's budget actually contemplates it is under 0.6 %.
3. **Deterministic jitter: at the measurement's own resolution floor.**
   The `dj_ui_*` relative deltas look enormous (up to +3700 %) purely
   because the baseline is near zero. In absolute terms the worst delta is
   **+4.23×10⁻⁵ UI** and the worst extracted value is 5.79×10⁻⁵ UI, against
   a 0.15 UI allocation — three to four orders of magnitude inside it. For
   scale, one `.tran` print step (10 ps) is 7.4×10⁻⁶ UI at 742.5 Mbps and
   2.7×10⁻⁶ UI at 270 Mbps, i.e. the deltas are a handful of print steps on
   a crossing-time difference. The same reasoning covers `ioff_dc`'s
   +5057 % worst relative delta: that is a sub-nanoamp leakage figure
   (2.1×10⁻¹⁰ A at the corner in question) and the worst *absolute* change
   anywhere on the grid is −1.5×10⁻⁷ A.

**What this post-layout run does and does not model** (stated here as well as
in the record's own **Claim** field, per the coverage-honesty requirement in
§3 below — a post-layout label is worth nothing if the reader has to guess
what was extracted):

- **Modelled**: the drawn device geometry of the real cell — 338 extracted
  per-finger `nfet` devices, each carrying its own drawn `W`/`L` and its own
  drawn source/drain junction area and perimeter (`AS`/`AD`/`PS`/`PD`), with
  shared diffusions split between neighbouring fingers — plus the drawn
  intra-cell connectivity, DRC-clean and LVS-matched against the sized
  schematic (issue #22's reports under `layout/drc_reports/`,
  `layout/lvs_reports/`).
- **Not modelled — interconnect parasitic R/C.** The source extraction is
  *schematic-equivalent* (devices + connectivity); `klt extract --parasitics`
  was **not** used. Intra-cell metal resistance, coupling capacitance and
  wiring capacitance to ground are absent. **This is therefore device-level
  post-layout evidence, not parasitic-RC post-layout evidence** — see §3
  item 2 for what remains open because of it.
- **Not modelled — diffusion sheet resistance.** The extraction carries no
  `NRD`/`NRS`, so `nfet_03v3`'s zero defaults apply; the schematic DUT states
  them (1.406 mΩ/sq-count on the switches, 9 mΩ on the mirror).
- **Not modelled — substrate resistance.** gf180mcu has no distinct
  substrate-tap layer, so `klt` ties every device body to a single
  deck-synthesized global net `vsubs` regardless of the drawn tap geometry
  (`klt lvs` reports this as its own `device.body_unverified` warning). The
  DUT wrapper ties `vsubs` to `VSS` — the sized schematic's own intended tie
  for this NMOS-only cell in the common p-substrate — so the *topology* is
  right but the resistance between taps is not represented.
- **Not modelled — anything outside the core cell.** No pad, no ESD clamp,
  no package and no board. Pad capacitance is still swept in-deck at
  0/1/2 pF and the 50 Ω/leg termination is still the testbench's ideal load,
  exactly as in the schematic record.
- **PDK-variant caveat.** The layout and its extraction were produced against
  `gf180mcuC`; this simulation uses the `gf180mcuD` models `sim/pdk.json`
  pins (same open_pdks revision). That discrepancy is the same one §3 item 1
  describes and is owned by issue #9 — it is not resolved by this record.

The record sets **Supersedes**: `20260810-041436-a2c358b`, which
`sim/README.md` designates for "a post-layout extracted re-run that reports a
schematic-vs-extracted delta against the schematic-level record". That is a
pointer for the delta, **not** a statement that the schematic record was
wrong: nothing in the schematic record is corrected here, and both remain
citable (the schematic record is the one that states `NRD`/`NRS`; this one is
the one taken against the drawn geometry).

#### DR-0002, Monte Carlo device-mismatch corroboration

[`sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md`](../sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md)
(issue #23, landed 2026-08-15) adds **statistical** evidence on top of the
deterministic corner sweep above: gf180mcu's own Pelgrom-law local
(intra-die) mismatch injection (`nfet_03v3_dss` with `sw_stat_mismatch=1`) on
all four transistors of the CML driver, **N = 30 independent samples per
process corner × 5 process corners = 150 statistical points**, plus one
`mismatch=0` reference per corner and one deterministic negative control
(156 ngspice invocations, all completed).

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| Single-ended swing 400–600 mV under local device mismatch | **PASS** | [`sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md`](../sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md) | Worst observed sample across all 150 points: **456.8 mV** (`ss`) to **485.3 mV** (`ff`) — inside the window at every sample, with 56.8 mV of margin to the 400 mV floor. Per-corner 1σ ≤ 1.32 mV. |
| Common mode 2.8–3.3 V under local device mismatch | **PASS** | same record | Worst observed sample: **3.0573 V** (`ff`) to **3.0716 V** (`ss`) — inside the window at every sample. Per-corner 1σ ≤ 0.66 mV. |

**How it is graded, and why that matters.** The PASS/FAIL roll-up uses the
**observed min/max across the N samples**, not a σ-projection from the
per-corner mean — so a heavy-tailed sample cannot be hidden behind a Gaussian
assumption. Per-corner σ is reported alongside, but is not what the verdict
rests on.

**Reproducibility.** Every sample's seed is derived deterministically —
base seed `20260814`, sample `i` at process-corner index `k` uses
`.option seed = 20260814 + k*1000 + i` — so any individual sample is
independently re-runnable, not just the aggregate.

**Negative control** (`tt_mcneg_27c_3.30v`, excluded from the statistics and
from the roll-up): the same unmodified vendor mismatch mechanism is driven
with `par_tail_val=0.0001` on the tail-mirror device, which scales only the
Pelgrom-law area term the mismatch σ is drawn against — not the transistor's
real electrical `w`/`l`/`nf`/`m`. Measured **swing 117.3 mV — FAILS** the
400–600 mV window (vcm 3.2414 V still passes). The pass/fail check therefore
demonstrably fires; the PASS above is not vacuous.

**What this record does not cover**, stated rather than left to be inferred:

- **Temperature and supply are held at nominal** (27 °C, 3.30 V); the swept
  axis is process corner × sample count. This is a deliberate subset of the
  DR-0013 PVT matrix, justified in the record's own **Corner matrix run**
  field: `sim/cml-driver-eye` already carries this driver's swing/common-mode
  claim deterministically across the full −40/27/125 °C × ±10 % supply ×
  process grid (90 points, both rates), and re-running that T×V grid × N=30
  is a 9× cost multiplier that adds no new axis. Read the two records
  together — statistical evidence **combined with**, not replacing, the
  corner sweep, which is exactly what the T1 ladder's Monte Carlo item asks
  for.
- **Schematic-level, not extracted.** No layout-extracted Monte Carlo run
  exists. The mismatch DUT's `nfet_03v3_dss` wrapper also adds small, real
  routing-resistance parasitics the un-wrapped `nfet_03v3` omits, so the
  `mismatch=0` reference rows are *comparable* to the `cml-driver-eye`
  deterministic rows but not numerically identical to them.
- **N = 30 per corner** is enough to bound the observed spread at the σ
  magnitudes measured here (σ ≈ 1 mV against a 200 mV-wide window), not to
  substantiate a parts-per-million tail claim. No yield number is claimed
  anywhere in this repository.
- **Swing and common mode only** — no statistical claim is made about jitter,
  device stress, or tail current, and none is made about any other spec row.

### DR-0013 row 6 — passing-eye criterion (combined swing+jitter eye mask)

[`sim/cml-driver-eye-mask/records/20260825-040412-4b0c9f6.md`](../sim/cml-driver-eye-mask/records/20260825-040412-4b0c9f6.md)
(issue #144) closes the gap §3 item 5 previously named: DR-0013 row 6
(`spec/decisions/0013-operating-conditions.md`) grades a single combined
criterion — eye height >= 200 mV **and** eye width >= 0.75 UI, measured
simultaneously at the eye's widest opening, no fixed sampling instant
assumed — and until this record, no testbench in this repository evaluated
it directly. This bench drives a genuine PRBS7 (ITU-T O.150, period 127)
pattern, long enough to develop real inter-symbol interference, unlike
`sim/cml-driver-eye`'s fixed single-transition measurements (rows 1 and 4
above).

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| DR-0013 row 6: eye height >= 200 mV AND eye width >= 0.75 UI, simultaneously, at the eye's widest opening | **PASS** | same record | Full PVT (5 process corners x 3 temperatures x 3 supply points) x both rates x 0/1/2 pF pad cap (90 points). Worst-case per-window (0.75 UI) minimum vertical opening ("eyemask_margin"): **0.871–1.033 V** at 2 pF pad (the tightest load), **0.958–1.033 V** at 1 pF, **0.962–1.033 V** at 0 pF — every measured point clears the 0.2 V floor by >= 4x. Worst single corner: `ss_125c_2.97v_742p5mbps` at 2 pF pad, 0.871 V (still 4.4x the floor). |

**Methodology, briefly** (full derivation in
`sim/cml-driver-eye-mask/gen_testbench.py`'s module docstring). Each of the
127 measured PRBS7 bits is preceded by a 20-bit rolling-history prefix (the
sequence's own tail) so no measured bit starts from an arbitrary settle-in
state. Each unit interval is tiled into 8 equal phase bins; per bin, the
worst-case vertical opening is (minimum sampled level over every measured
"1" bit at that phase) minus (maximum sampled level over every measured "0"
bit at that phase) — the standard worst-case-ISI eye-height construction. A
6-of-8-bin (0.75 UI) sliding window is then scanned across every start
offset, and the largest per-window minimum height is the eyemask margin:
the tallest box that fits the width floor somewhere in the open eye, which
is exactly DR-0013 row 6's test — no fixed sampling instant is assumed.

**What this does not cover**, stated rather than left to be inferred:

- **Schematic-level, not extracted.** Like `sim/cml-driver-eye`'s own
  schematic record, this bench uses `sim/cml-driver-eye/testbench/
  cml_driver_dut.spice` — no post-layout eye-mask run exists yet.
- **`mos` corner set only** (tt/ff/ss/fs/sf), matching `sim/cml-driver-eye`'s
  own precedent — row 6's claim does not depend on resistor/BJT device-
  family parameters, so the resistor/BJT skew corners are not required for
  this claim.
- **No statistical (Monte Carlo) eye-mask claim.** The driver's Monte Carlo
  evidence above (swing/common mode under local device mismatch) does not
  extend to a combined eye-mask construction; none is made here.
- **8 phase bins (12.5 % UI resolution)**, chosen for runtime rather than
  rigor — a finer grid did not double runtime when doubled, it took a
  single PVT point from ~4 s to over 180 s. Given every measured margin
  above clears the 0.2 V floor by >= 4x, a finer grid is very unlikely to
  change the verdict; see the generator's own docstring for the full
  reasoning.

### DR-0005 — pad cell and ESD strategy (clamp capacitance)

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| ESD clamp capacitance vs. size, at 0 V and at the DR-0002/DR-0006 operating bias, full PVT | **Measured, reported — no simple PASS/FAIL against the ≤ 2 pF budget** | [`sim/esd-clamp-cv/records/20260814-193222-dd48630.md`](../sim/esd-clamp-cv/records/20260814-193222-dd48630.md) | Full PVT (45 points, process × temp × supply). The record itself is a corner-matrix capacitance-vs-width sweep, not a spec pass/fail claim — its own **Claim** field cites DR-0005 without asserting a verdict. The verdict synthesis lives in `design/esd-capacitance-budget.md` (see next row), which combines this record with the pad's own parasitic capacitance. Taken against a dirty working tree (see the record's own **Netlist provenance** field); not citable as a clean-tree result on its own, but `sim/README.md`'s cold-start reproducibility audit (issue #25) re-ran this experiment from a clean checkout and got a bit-for-bit match — the underlying data is not in question. |
| DR-0005's ≤ 2 pF/pad budget (clamp + pad parasitic combined), against the real drawn pad cell | **PASS at a realistic 25×25 µm pad — 0.225–0.652 pF across the full HBM-sizing window (67–89 % headroom)** | [`design/esd-capacitance-budget.md` §9](../design/esd-capacitance-budget.md) (§9.3 pad/interconnect, §9.4 clamp PVT sweep, §9.5 verdict), backed by [`sim/esd-diode-clamp-cv/records/20260819-053140-72b44e8.md`](../sim/esd-diode-clamp-cv/records/20260819-053140-72b44e8.md) and `layout/drc_reports/gf180_tmds_pad_v2.parasitics.json` | **§9 supersedes §5; this row previously reported §5's "7.95 pF worst case, 4.0× over budget" FAIL and no longer does.** §5's verdict fell on two independent grounds, both established by issue #87 / PR #124 (2026-08-19): (a) §4b's analytic "realistic bond pad" figure carried a **1000× units-label bug** — the `aF` arithmetic was right but the result was divided by 1,000 (`aF`→`fF`) and then labelled `pF`, so the real bare-25×25 µm-Metal5-plate figure is **6.66 fF, not 6.66 pF** (§9.1, confirmed twice: re-derived arithmetic at 6.6629 fF and an independent `klt extract --parasitics` measurement at 6.66235 fF, 0.02 % agreement); and (b) rather than rest on that correction, §9 draws the pad for real — `gf180_tmds_pad_v2` (`layout/gds/gf180_tmds_pad_v2.gds`), a 25×25 µm Metal5 bond pad with DR-0011's ratified `diode_nd2ps_06v0` clamp and a real substrate tap, DRC-clean (0 violations) and LVS-matched with its `_shorted` negative control correctly mismatching. Measured: **12.185 fF** pad-plate + via-stack + Metal1 bus parasitic (§9.3, `klt extract --parasitics` against the drawn cell, byte-identical across `gf180mcuC`/`gf180mcuD`) plus a full-PVT diode-clamp CV sweep (§9.4, 45/45 points, binding corner `ss_125c_2.97v`, operating-bias-graded) over §2b's HBM-sizing window: **0.225 pF at 222 µm, 0.438 pF at 444 µm, 0.652 pF at 667 µm** (the last linearly extrapolated, §9.4). DR-0005 is met, not relaxed — the operator's 2026-08-14 guardrail on issue #12 is satisfied by correcting the measurement, not the budget. **Two caveats, stated rather than hidden**: the *capacitance* is measured but the *clamp width* it is graded at still comes from literature-sourced HBM current density, not PDK data (§2a — see the next row); and `gf180_tmds_pad_v2` is a standalone proof-of-concept cell, so this particular row's numbers are a cell-level result. The block-level half of that second caveat is now measured — see the next row. |
| DR-0005's ≤ 2 pF/pad budget **at block level**, at DR-0011's ratified 350 µm pad pitch | **PASS — 0.247–0.836 pF across the full HBM-sizing window (58–88 % headroom), drawn and DRC-clean at pitch** | [`design/esd-capacitance-budget.md` §10](../design/esd-capacitance-budget.md) (§10.2 fit, §10.3 budget), backed by `layout/drc_reports/pad_pitch_fit_*.{fit,drc,parasitics,components}.json` and, for the clamp term, the same [`sim/esd-diode-clamp-cv/records/20260819-053140-72b44e8.md`](../sim/esd-diode-clamp-cv/records/20260819-053140-72b44e8.md) §9.4 uses | Issue #143 answered the question §3 item 4 previously named as open: **`gf180_tmds_pad_v2`'s production 25×25 µm pad geometry does fit DR-0011's ratified 350 µm pitch / 75 µm ring depth**, tiled two-up alongside the DVDD/DVSS Metal3/4/5 straps, a real substrate tap and an HBM-sized clamp array — drawn, not estimated: `klt drc` `status: clean`, 0 violations, at every clamp size from the as-drawn 20-finger array up to 334 fingers (668 µm of clamp width, the top of §2b's HBM window). Ring continuity is checked mechanically, not by eye: `klt components` over the M3/M4/M5 stack reports each supply strap as **one** connected component spanning the full two-slot span, with the pad plates as separate components — the larger pads neither bridge nor interrupt either strap. Two changes are required and are recorded as such (§10.2): the clamp array must **fold into rows** above ~125 fingers (a single 334-finger row is 881.8 µm, 2.5× the ratified pitch), and the pad structure must sit ~5 µm higher in the ring depth so the 25 µm-tall Metal5 plate clears the DVDD strap band. Measured pad-node interconnect capacitance at block level: 12.185 fF (20 fingers — reproducing §9.3's cell-level figure exactly), 34.251 fF (222 µm), 65.752 fF (444 µm), 95.071 fF (668 µm), 195.627 fF (668 µm with an 8.3× wider Metal1 gather bus, which also closes §9.3's own open "an HBM-sized clamp needs a wider bus" caveat with a number: +100.6 fF for an 8.1× resistance reduction). Summed with §9.4's PVT-swept clamp term at its binding `ss_125c_2.97v` corner: **0.247 / 0.492 / 0.735 / 0.836 pF**, all inside 2 pF. **DR-0011 is met, not amended** — no decision record is opened or relaxed. **Three caveats, stated rather than hidden**: (a) the exact agreement with the cell-level figure was checked rather than assumed — re-running with lateral coupling explicitly enabled on both pad nets (`--critical-net OUTP --critical-net OUTN`) returns `cc_count: 0` and identical figures, because the Metal5 plate and the Metal5 straps are 2.0 µm apart (outside the layer's minimum-spacing lookback) and nowhere vertically overlap; that is a statement about this extractor's quasi-static per-net model at this separation, not a claim that a physical ring has no pad-to-strap coupling (`design/esd-capacitance-budget.md` §6's coverage limits apply unchanged); (b) the clamp *width* is still literature-sized, same as every row above; (c) these are dedicated fit-study tiles, **not** the block assembly itself — `layout/gds/gf180_tmds_pad_ring_assembly.gds` still carries the old 2×2 µm placeholder opening, and adopting the production geometry there is #149, blocked on a `klt lvs` regression (klayout-tools#1370). See §3 item 4. |
| HBM ≥ 2 kV / CDM ≥ 500 V ESD qualification | **Not evidenced — design-margin estimate only, explicitly not a qualification** | `design/esd-capacitance-budget.md` §2 | No PDK source (SPICE models or DRC deck) characterizes ESD failure current density, breakdown voltage, or snapback/trigger behavior for any device family in gf180mcu (§2a of that document). The HBM sizing figures (222/444/667 µm clamp widths) are order-of-magnitude estimates from general ESD-design literature, explicitly marked as not PDK-sourced. CDM is reported as "the source is silent" — no CDM-driven width number exists. This repo has no tester and no fabricated parts (`measurements/` stays empty by design, per CLAUDE.md); real ESD qualification cannot happen until silicon exists. |

### Harness/machinery self-verification (not a spec-row claim)

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| Analog sim harness transient/rate-axis machinery, at both #1 operating points | **PASS** | [`sim/smoke-cml-pair/records/20260808-032312-430859a.md`](../sim/smoke-cml-pair/records/20260808-032312-430859a.md) | Full PVT × both rates (90 points), on a bare 3.3 V NMOS differential pair with the DR-0002 load topology — explicitly **not** a CML driver design deliverable (`sim/README.md`'s own framing). This record's own **Claim** field states "None — harness self-verification"; it is listed here for completeness (it is the first evidence this repo produced) but substantiates no spec row on its own. Taken against a dirty working tree, so it is not citable as a clean-tree result even for its own harness-proof purpose. |

## 2. Digital partition

This section indexes the `tmds_encoder` synthesis/P&R/STA/verification
pipeline under `flow/tmds_encoder/` and `verification/tmds_encoder/` against
DR-0003 (`spec/tmds-tx.md`'s digital encoder/serializer row) and against the
`klayout-tools/docs/design-evidence-tiers.md` T1 checklist items each result
addresses. Every result below is now a PASS; item 5 (LVS) was a
**disclosed FAIL** until issue #142 and its row records what changed and
why, rather than quietly flipping. Per CLAUDE.md's "Verification is the
product" and this document's own coverage-honesty convention, each row also
states the *scope* of what it verifies, not just its verdict.

| # | Item | Verdict | Evidence record | Notes |
|---|---|---|---|---|
| 1 | RTL-level functional verification (three-leg plan: exhaustive golden-model equivalence, invariants, negative control) | **PASS** | [`verification/tmds_encoder/`](../verification/tmds_encoder/), convention documented in [`verification/README.md`](../verification/README.md) | Cold-start re-run (`pip install -r requirements.txt && python3 runner.py`) reproduces cleanly: real DUT passes, negative-control DUT correctly fails, per issue #65's 2026-08-15 T1 re-read (item 9, "fresh cold-start re-run ... reproduces cleanly"). This bench uses its own convention (`verification/README.md`), distinct from `sim/`'s analog evidence-record format, so it is cited by directory + convention doc rather than a single dated record file. |
| 2 | Synthesis (gate-level netlist) | **PASS** | [`flow/tmds_encoder/records/20260816-033153-e2d0580.md`](../flow/tmds_encoder/records/20260816-033153-e2d0580.md) | 266 cell instances (17 sequential, 249 combinational), 0 unmapped cells, `gf180mcu_fd_sc_mcu9t5v0` library at `tt_025C_3v30` (DR-0003's synthesized-domain corner). Area-oriented mapping only — no `.sdc`/clock-period constraint applied at this stage, every cell drive strength 1; this matters for reading the STA result below. |
| 3 | Place & route (block-level digital layout exists) | **PASS** | [`flow/tmds_encoder/records/20260816-063442-def7827.md`](../flow/tmds_encoder/records/20260816-063442-def7827.md) | `layout/gds/tmds_encoder.gds`, 266 instances placed and routed (11184 µm total wire length, 1684 vias), 35% target / 36.1% effective utilization. No CTS, no SDC — scope disclosed in the record itself. |
| 4 | DRC | **PASS** | same record (`layout/drc_reports/tmds_encoder.drc.json`) | `status: clean`, 0 violations. Historical note: an earlier read of this row reported a disclosed FAIL (188 violations, all rule `mim.space.1`, a Metal4-to-Metal4 spacing check the curated gf180mcu deck could not distinguish from a real MiM capacitor's bottom plate on a design with zero capacitor devices — filed generically upstream as [klayout-tools#1033](https://github.com/2AMLogic/klayout-tools/issues/1033)); that finding no longer reproduces as of the DRC report regenerated by PR #133 (issue #127), and upstream #1033 was closed 2026-08-16, three days before that regeneration. |
| 5 | LVS | **PASS** | same record (`layout/lvs_reports/tmds_encoder.lvs.json`), negative controls `layout/lvs_reports/tmds_encoder_negctl.lvs.json` and `layout/lvs_reports/tmds_encoder_shorted.lvs.json` | `status: match`, **0 mismatches**; nets `{layout: 384, reference: 384}`, pins `{layout: 25, reference: 25}`. **This row was a disclosed FAIL (18 topology mismatches) until issue #142.** The cause was never a layout defect: the reference netlist was derived from the *pre*-P&R synthesized netlist, which by construction contains none of the 17 cell types place-and-route inserts (`FILL_1/2/4/8/16/32/64`, `FILLTIE`, `ENDCAP`, CTS's `CLKBUF_12/16` and `CLKINV_2`, hold-repair's `DLYC_1`/`INV_3`/`INV_4`, and setup-repair's resized `OAI21_2`/`OAI31_2`), so each appeared as a layout-only type, plus one top-level rollup. The reference is now derived from the post-P&R netlist (`flow/gen_pnr_netlist.py` -> `tmds_encoder.pnr.v` -> `gen_tmds_encoder_ref.py --from-pnr`), read out of the same committed routed DEF the GDS was streamed from. No layout, netlist or P&R setting changed — only what the layout is graded against. **Scope of the claim, stated rather than inflated**: this verifies the DEF -> GDS -> extraction path preserved connectivity (a step with two real, found-and-fixed DBU defects in its history), *not* that P&R preserved the synthesized netlist's intent — that is item 6's SDF-back-annotated re-simulation and `flow/sta_tmds_encoder.py`'s `assert_def_matches_netlist`. **Two negative controls, kept side by side (issue #146)**: `tmds_encoder_negctl` compares the same unchanged layout netlist against a reference carrying one deliberate fault (`ctrl[0]` merged into `data[3]`) and correctly reports `status: mismatch`, 3 error-severity findings — but breaks the *reference*, not the layout, so it never runs `klt extract --abstract-cells`. `tmds_encoder_shorted` is the layout-side twin every other cell in this repo ships: a real Metal4 bridge shorting the same `ctrl[0]`/`data[3]` pair, drawn into the GDS by `layout/scripts/gen_tmds_encoder_shorted.py` (geometry derived from the routed DEF's own `PINS` block, not hardcoded) and extracted for real — `status: mismatch`, 2 error-severity findings (`net.merged`, `topology`). Restoring this twin was blocked on [klayout-tools#1366](https://github.com/2AMLogic/klayout-tools/issues/1366) (a `klt` 0.3.0 regression that mis-bound abstracted-cell pins on this design badly enough that a layout-side control built on top of it could not be trusted), now fixed upstream (PR #1374); the fixed build was re-verified to reproduce the previously-committed 0.2.0-era extraction byte-for-byte before either the intact `match` above or the new `_shorted` `mismatch` was trusted — see `layout/README.md`'s `tmds_encoder` section. |
| 6 | Post-layout verification (SDF-back-annotated gate-level re-simulation) | **PASS, scope-limited** | [`flow/tmds_encoder/records/20260816-080228-185a5d3.md`](../flow/tmds_encoder/records/20260816-080228-185a5d3.md) (SDF extraction), [`flow/tmds_encoder/records/20260816-080524-185a5d3.md`](../flow/tmds_encoder/records/20260816-080524-185a5d3.md) (re-simulation) | The unmodified `verification/tmds_encoder/test_tmds_encoder.py` bench, run against the SDF-annotated post-route netlist: 3/3 tests PASS. SDF extracted at a single corner (`tt_025C_3v30`, OpenRCX), no PVT sweep, no CTS/SDC. No formal setup/hold timing-closure verdict is made at this stage — that is item 7/8 below. |
| 7 | Static timing analysis — setup, 720p60 target (74.25 MHz) | **PASS** | [`flow/tmds_encoder/records/20260817-110611-37e197a.md`](../flow/tmds_encoder/records/20260817-110611-37e197a.md) | Setup **met at all 5** 3.3 V liberty corners (`tt_025C_3v30`, `ss_125C_3v00`, `ss_n40C_3v00`, `ff_125C_3v60`, `ff_n40C_3v60`). Measured Fmax: **75.83 MHz worst-corner** (`ss_125C_3v00`), 148.96 MHz typical. Setup at the 480p fallback (27.000 MHz) also PASSes at all 5 corners. **Supersedes** the earlier pre-timing-driven-synthesis/pre-CTS record ([`20260816-172539-930e864.md`](../flow/tmds_encoder/records/20260816-172539-930e864.md)), which reported setup FAIL at 4/5 corners and 22.70 MHz worst-corner Fmax against an unconstrained, CTS-free netlist — that gap is now closed by issue #100's timing-driven-synthesis/CTS/timing-repair machinery combined with issue #115's DR-0009 four-stage pipeline restructuring (S1 popcount/threshold, S2 parallel-prefix transition-minimized word, S3 accumulator-independent DC-balance candidates, S4 decision + accumulator recurrence). The worst-corner margin is narrow (+0.2799 ns, 2.1 % of the 13.4680 ns period, at `ss_125C_3v00`) — closed, not closed with headroom. |
| 8 | Static timing analysis — hold, all corners, both targets | **PASS** | same record | Hold met at every one of the 5 corners, at both the 720p60 and 480p targets (hold is clock-period-independent, so both targets give the same answer). Worst hold margin +0.2703 ns (`ff_n40C_3v60`). |

**What this means.** The digital partition's RTL-level functional
verification, synthesis, layout existence, DRC, post-layout gate-level
re-simulation, and setup/hold timing closure at the 720p60 target are clean
PASSes (items 1–4, 6–8 above). **LVS (item 5) is now a PASS too**: its 18
mismatches were an artifact of grading a routed layout against a pre-P&R
reference netlist that could not contain P&R-inserted cells
(fill/tap/endcap/CTS buffers/hold-repair/resized gates), and issue #142
closed it by deriving the reference from the post-P&R netlist read out of
the committed routed DEF instead. Read that row for what the resulting
`status: match` does and does not establish — it verifies the DEF -> GDS ->
extraction path, not P&R's fidelity to synthesis, which item 6 covers. It
ships with a negative control that correctly fails. DRC's
earlier disclosed FAIL (188 `mim.space.1` violations, a deck-level
klayout-tools false-positive — [#1033](https://github.com/2AMLogic/klayout-tools/issues/1033))
no longer reproduces against the current evidence record; that upstream
issue was closed 2026-08-16. Timing closure
was achieved by issue #100's timing-driven-synthesis/CTS/timing-repair
machinery plus issue #115's DR-0009 four-stage pipeline; this rollup's job
is to report the current, disclosed state, not to re-derive it. Per
CLAUDE.md's "720p60 is the target" scope discipline, this closes what was
previously the single most load-bearing fact in this section — 720p60
setup timing is now met at every corner — though the worst-corner margin
(2.1 % of the period) is narrow, not comfortable.

## 3. What is not yet covered (named explicitly)

Per the coverage-honesty requirement this document exists to meet, the
following gaps are stated by name rather than left as silent omissions:

1. **PVT matrix — now ratified.** `sim/README.md`'s own working PVT matrix
   (−40/27/125 °C, ±10 % supply tolerance, the 5 classic MOS process
   corners plus `res_ff`/`res_ss`/`bjt_ff`/`bjt_ss` for resistor/BJT-
   dependent claims, both bit-rate targets) is **ratified**:
   [`spec/decisions/0013-operating-conditions.md`](../spec/decisions/0013-operating-conditions.md)
   (**Accepted**, 2026-08-18) ratifies the existing working-default matrix
   verbatim and unchanged — a tightening/formalizing move, not a new
   requirement, so no existing evidence in §1 above is invalidated or needs
   re-running. Issue #9 (closed, merged via PR #122) is the issue that
   originally opened this question; DR-0013 is its resolution, landed under
   a renumbered decision-record slot (see that record's own "Numbering
   note"). Every PASS verdict in §1 above is now graded against a
   spec-derived requirement, not a working default. The PDK-variant
   discrepancy this item previously flagged (`sim/` pinned `gf180mcuD`,
   `layout/` produced against `gf180mcuC`) is likewise resolved: DR-0010
   (Accepted) ratifies `gf180mcuD`, and every `layout/` artifact has since
   been regenerated and re-signed off against it (#127, closed) — per
   DR-0010's own survey, no numeric result recorded in this repository
   changes value as a result. DR-0013 also ratifies an 11-row
   verifiable-spec-row table (its own §3); at ratification time two of
   those rows were genuine open gaps: row 6 (combined swing+jitter
   eye-mask criterion) had no testbench yet, and row 11 (ESD HBM/CDM
   qualification) is not yet independently simulated — and per §1's
   DR-0005 table, structurally cannot be, pre-silicon. Row 10
   (pad-capacitance budget, ≤ 2 pF) was listed here as a third gap,
   **FAILing at ~4× over budget** against a realistic 25×25 µm bond pad;
   **that is no longer the state** — the figure behind it was a
   units-label bug, and a real drawn pad now measures 0.225–0.652 pF
   against the 2 pF budget (§1's DR-0005 table above,
   `design/esd-capacitance-budget.md` §9). Row 10 is closed at cell
   level, and since issue #143 also at block level, at DR-0011's ratified
   350 µm pad pitch (0.247–0.836 pF, `design/esd-capacitance-budget.md`
   §10, §1's block-level DR-0005 row above); what remains for it is
   adopting that geometry in the block assembly itself, item 4 below.
   **Row 6 is likewise no longer a gap**: `sim/cml-driver-eye-mask/records/
   20260825-040412-4b0c9f6.md` (issue #144) grades it directly and
   **PASSes** across the full PVT matrix, both rates, 0/1/2 pF pad cap —
   see §1's new DR-0013 row 6 subsection above and item 5 below. **Row 11
   remains the one open gap** of the original two, tracked as issue #145.
   They were previously listed here as tracked by Epic #17's own T1
   checklist item 5; #17 closed COMPLETED on 2026-08-21, so that pointer no
   longer resolves to anything open and has been replaced by the two live
   issues — row 6's (#144) now resolved by this update, row 11's (#145)
   still open.
2. **Post-layout re-simulation — device-level done, parasitic RC not.**
   The DR-0002 rows in §1 now carry a **Netlist provenance: extracted**
   record as well as the schematic one
   ([`20260815-072956-34e5253`](../sim/cml-driver-eye/records/20260815-072956-34e5253.md),
   issue #34, on the layout landed by issue #22), so "no post-layout
   evidence at all" is no longer the gap. **The remaining gap is narrower
   and must not be read as closed**: that extraction is
   *schematic-equivalent* — devices, their drawn geometry, and connectivity
   — with **no interconnect parasitic R/C**, because
   `klt extract --parasitics` was not used. Nothing recorded in this repo
   yet bounds intra-cell metal resistance or wiring/coupling capacitance,
   and the +14 fF of extra output-node junction capacitance the device-level
   run does show (§1) is a lower bound on the post-layout capacitance story,
   not the whole of it. Two further scope limits are equally unclosed by
   that record: it covers **the core driver cell only** — no pad, no ESD
   clamp, no package, no board. The layout-vs-simulation PDK-variant
   question (item 1 above) is now resolved (DR-0010, `layout/` regenerated
   against `gf180mcuD`). The driver-plus-pad/ESD assembled cell itself now
   exists:
   [`layout/gds/gf180_tmds_pad_ring_assembly.gds`](../layout/gds/gf180_tmds_pad_ring_assembly.gds)
   (#86, landed 2026-08-19) integrates the driver core cell with two
   diode-clamped bond pads and DR-0011's pad-ring/ESD structure, and is
   itself DRC-clean (0 violations) and LVS-matched (`status: match`, 2
   warning-only findings) — so "no pad/ESD post-layout evidence because the
   cell doesn't exist yet" is no longer the gap. **What remains
   outstanding**: no electrical/PVT simulation of that assembled cell has
   been run — only its structural DRC/LVS signoff exists, not a
   `sim/`-style corner-matrix electrical record. A parasitic-RC re-run of
   the bare driver core, and a first post-layout electrical simulation of
   the assembled driver+pad+ESD cell, are both still outstanding and
   neither has an evidence record.
3. **Monte Carlo evidence — landed for the driver's swing/common mode;
   nothing else carries a distribution claim.** This item previously stated
   that *"no record in `sim/` today carries a **Statistical convention**
   field with a seed, sample count, and a deterministic negative control"*
   and that issue #23 *"has not landed as of this document"*. **Both were
   false**, and had been since 2026-08-15:
   [`sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md`](../sim/cml-driver-mismatch/records/20260815-044555-9e8a33a.md)
   (issue #23, closed COMPLETED 2026-08-15) carries exactly that field —
   base seed `20260814` with a per-sample derivation, N = 30 samples × 5
   process corners, and a deterministic negative control that correctly
   FAILs — and it is now indexed in §1 above under DR-0002, where it
   belongs. The T1 ladder's Monte Carlo item asks for mismatch evidence
   *combined with* (not replacing) the process-corner sweep for the driver's
   swing/common mode; that is what the two records together are, and that
   item is **met**. Lint step 7 (`sim/check_record_citations.py`) now fails
   the build if any tracked `sim/*/records/*.md` is missing from this
   document, so this particular class of omission cannot recur silently.

   **What is still not covered statistically** — the genuine remainder of
   this item, as distinct from the stale claim above: every *other* verdict
   in §1 and §2 is a corner-matrix claim (`Statistical convention: N/A`),
   not a distribution claim. There is no Monte Carlo evidence for jitter,
   device stress, tail current, the ESD clamp's capacitance, or anything in
   the digital partition; the mismatch run is schematic-level, with no
   extracted-netlist Monte Carlo counterpart; and it holds temperature and
   supply at nominal (see §1's own statement of that record's limits). No
   yield or parts-per-million claim is made anywhere in this repository, and
   none of the above is required by the T1 ladder — they are named here so
   the coverage boundary is explicit rather than inferred from the single
   PASS in §1.
4. **Pad-ring integration of the budget-passing pad geometry — measured,
   but not yet landed in the block assembly.** This item previously read
   "not done", and named two distinct gaps: (a) no capacitance-budget
   number had ever been measured against a block-level pad ring carrying
   production-sized pads, and (b) whether `gf180_tmds_pad_v2`'s 25×25 µm
   pad can be tiled at DR-0011's ratified 350 µm pitch with ring
   continuity intact was **unchecked**. Issue #143 closed both, by drawing
   rather than estimating — see §1's new block-level DR-0005 row and
   [`design/esd-capacitance-budget.md` §10](../design/esd-capacitance-budget.md):
   the production geometry fits at pitch (DRC-clean at every clamp size in
   §2b's HBM window, ring continuity confirmed mechanically by
   `klt components`), it needs a row fold above ~125 clamp fingers and a
   ~5 µm higher pad placement, and it measures 0.247–0.836 pF against the
   2 pF budget.

   **What remains open, precisely.** The measurement was taken against
   dedicated fit-study tiles
   (`layout/gds/pad_pitch_fit_*.gds`,
   `layout/scripts/pad_pitch_fit_study.py`), not against the block
   assembly this design would tape out.
   [`layout/gds/gf180_tmds_pad_ring_assembly.gds`](../layout/gds/gf180_tmds_pad_ring_assembly.gds)
   (#86) still carries `gen_pad_diode_draft.py`'s 2×2 µm pad opening,
   which `layout/README.md` itself calls "DRC-legal but not a production
   wire-bond target". Adopting the production geometry there is **#149**,
   and it is blocked, on the tool rather than on the design: under the
   currently-installed `klt` (`0.3.0+g634e074ff484`, KLayout 0.30.10) that
   cell's committed `klt lvs` `status: match` **no longer reproduces at
   all** — 40 of 40 fresh runs return `mismatch` carrying
   `device.combine_incomplete`, against the *unchanged, committed* GDS,
   with `klt lvs --rerun --check` confirming every input hash still `[OK]`.
   Landing a redraw under that condition would mean committing an LVS pair
   whose intact half and whose `_shorted` negative control both say
   `mismatch` — a defeated control, exactly what
   `layout/scripts/check_lvs_signoff.py` (§ "Every LVS signoff is a pair")
   exists to catch. Filed generically under CLAUDE.md's friction protocol
   as [klayout-tools#1370](https://github.com/2AMLogic/klayout-tools/issues/1370);
   full evidence in `layout/README.md` § "The block-level LVS signoff no
   longer reproduces". **No block-level `klt lvs` claim is made anywhere in
   this document on the strength of the #143 tiles** — they carry DRC,
   extract, parasitics and components evidence only.
5. **Eye-mask criterion (DR-0013 row 6) — now evidenced.** Item 1 above
   previously named this as one of DR-0013's two live gaps; it no longer
   is. `sim/cml-driver-eye-mask/records/20260825-040412-4b0c9f6.md`
   (issue #144) drives a genuine PRBS7 pattern, builds the eye by tiling
   each UI into phase bins and scanning every 0.75 UI window position for
   the worst-case vertical opening, and grades it directly against row 6's
   own wording (height >= 200 mV AND width >= 0.75 UI, simultaneously, no
   fixed sampling instant assumed): **PASS**, full PVT matrix, both rates,
   0/1/2 pF pad cap, worst-case margin 0.871 V (>= 4x the 0.2 V floor).
   See §1's new "DR-0013 row 6" subsection above for the full table and
   this record's own stated coverage limits. **What this does not cover**:
   schematic-level only (no post-layout eye-mask run yet), and no Monte
   Carlo/mismatch eye-mask claim (the driver's Monte Carlo evidence, item 3
   above, covers swing/common mode only, not a combined eye construction).
   Row 11 (ESD HBM/CDM qualification) remains DR-0013's one other open gap,
   unaffected by this record, tracked as issue #145.

No other spec row beyond those listed in §1 has any recorded `sim/`
evidence at all. The encoder/serializer digital domain (DR-0003) is verified
by a separate `flow/tmds_encoder/records/` and `verification/tmds_encoder/`
evidence trail (cocotb, Yosys, OpenROAD — not the `sim/` analog harness §1
indexes); that trail is already folded into this rollup, as §2 above, rather
than left out of it. The PLL interface (§2 of `spec/tmds-tx.md`, DR-0004) is
a requirement levied on a sibling canary block and has no evidence to cite
here by design (DR-0001/CLAUDE.md scope discipline).

## 4. Links

- Ratified spec: [`spec/tmds-tx.md`](../spec/tmds-tx.md)
- Evidence-record convention: [`sim/README.md`](../sim/README.md)
- Driver sizing derivation (cites `sim/cml-driver-eye`):
  [`design/cml-driver-sizing.md`](../design/cml-driver-sizing.md)
- ESD/capacitance measurement study (cites `sim/esd-clamp-cv`):
  [`design/esd-capacitance-budget.md`](../design/esd-capacitance-budget.md)
- Post-layout DUT derivation and its stated limits:
  [`layout/README.md`](../layout/README.md) § "Post-layout simulation of this
  cell", generated by `layout/scripts/gen_cml_driver_core_dut.py`
- Record-to-record delta tool used in §1: `sim/compare_records.py`
- Digital evidence-record convention: [`flow/README.md`](../flow/README.md)
- Digital verification convention (three-leg plan): [`verification/README.md`](../verification/README.md)
- Digital timing-closure follow-up (§2 items 7/8's disclosed setup FAIL): #100
- Coverage self-check for this document (lint step 7): `sim/check_record_citations.py`
- Gap to T1 sim-validated (bronze): originally Epic #17 (**closed COMPLETED
  2026-08-21**), continued by #142; the individually-dispatchable remainder
  is #149 (adopt the production pad geometry in the block assembly, §3
  item 4 — the investigation that scoped it, #143, is closed) and #145
  (whether ESD HBM/CDM qualification is schedulable work or a permanent
  pre-silicon limitation, §1's DR-0005 table). #146 (restore a layout-side
  `_shorted` LVS negative control for `tmds_encoder`, §2 item 5) is closed —
  klayout-tools#1366 was fixed upstream and the layout-side twin restored.
