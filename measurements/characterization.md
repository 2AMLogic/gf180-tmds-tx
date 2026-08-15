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
below cites a specific `sim/*/records/*.md` file. This document makes no
claim beyond what those records already state — it is a index and rollup,
not new measurement work. `measurements/` itself stays otherwise empty
until tape-out (see `measurements/README.md`), consistent with this being a
design/simulation-stage rollup, not a silicon characterization.

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
| Remaining (serializer+driver+board) jitter allocation, ≤ 0.15 UI p-p (spec/tmds-tx.md §2) | **PASS** | same record | Driver's own deterministic-jitter contribution measured ≤ 3.56×10⁻⁵ UI at 2 pF pad load (full PVT, both rates) — several thousand times inside the 0.15 UI budget. This measures the driver stage only, not the full serializer+driver+board chain the budget row nominally covers (the serializer/mux stage upstream of this driver has not itself been captured yet — see §2 below). |
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
§2 below — a post-layout label is worth nothing if the reader has to guess
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
  post-layout evidence, not parasitic-RC post-layout evidence** — see §2
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
  pins (same open_pdks revision). That discrepancy is the same one §2 item 1
  describes and is owned by issue #9 — it is not resolved by this record.

The record sets **Supersedes**: `20260810-041436-a2c358b`, which
`sim/README.md` designates for "a post-layout extracted re-run that reports a
schematic-vs-extracted delta against the schematic-level record". That is a
pointer for the delta, **not** a statement that the schematic record was
wrong: nothing in the schematic record is corrected here, and both remain
citable (the schematic record is the one that states `NRD`/`NRS`; this one is
the one taken against the drawn geometry).

### DR-0005 — pad cell and ESD strategy (clamp capacitance)

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| ESD clamp capacitance vs. size, at 0 V and at the DR-0002/DR-0006 operating bias, full PVT | **Measured, reported — no simple PASS/FAIL against the ≤ 2 pF budget** | [`sim/esd-clamp-cv/records/20260814-193222-dd48630.md`](../sim/esd-clamp-cv/records/20260814-193222-dd48630.md) | Full PVT (45 points, process × temp × supply). The record itself is a corner-matrix capacitance-vs-width sweep, not a spec pass/fail claim — its own **Claim** field cites DR-0005 without asserting a verdict. The verdict synthesis lives in `design/esd-capacitance-budget.md` (see next row), which combines this record with the pad's own parasitic capacitance. Taken against a dirty working tree (see the record's own **Netlist provenance** field); not citable as a clean-tree result on its own, but `sim/README.md`'s cold-start reproducibility audit (issue #25) re-ran this experiment from a clean checkout and got a bit-for-bit match — the underlying data is not in question. |
| DR-0005's ≤ 2 pF/pad budget (clamp + pad parasitic combined), against the real drawn pad cell | **Clamp alone: PASS, large margin. Full budget (clamp + realistic bond pad): FAILS, reported not revised** | `design/esd-capacitance-budget.md` §5, backed by the same clamp record plus a `klt`-extracted/analytic pad-parasitic figure | Clamp sized to the HBM 2 kV target (222–667 µm total width, per the document's §2b HBM-density estimate) costs 0.240–0.822 pF at the worst measured/extrapolated PVT corner (`ss_125c_2.97v`) — well inside the 2 pF budget on its own. Against the **literal as-drawn pad geometry** (`layout/gds/gf180_tmds_pad_min.gds`'s 0.62×1.00 µm via-landing shape, not a real bond pad), the combined total is 0.822 pF and fits with large margin. Against a **realistic 25×25 µm bond-pad** assumption (the gf180mcu_fd_io library's own established pad-opening size), the pad's own Metal5 parasitic alone costs 6.4–7.1 pF — the combined total (7.95 pF worst case) is 4.0× over the 2 pF budget. Per the operator's 2026-08-14 guardrail on issue #12, this shortfall is reported as a finding, not used to silently relax DR-0005. Backed by the same dirty-working-tree `esd-clamp-cv` record cited above; not citable as a clean-tree result on its own, but `sim/README.md`'s cold-start reproducibility audit (issue #25) confirms a bit-for-bit match from a clean checkout — the underlying data is not in question. |
| HBM ≥ 2 kV / CDM ≥ 500 V ESD qualification | **Not evidenced — design-margin estimate only, explicitly not a qualification** | `design/esd-capacitance-budget.md` §2 | No PDK source (SPICE models or DRC deck) characterizes ESD failure current density, breakdown voltage, or snapback/trigger behavior for any device family in gf180mcu (§2a of that document). The HBM sizing figures (222/444/667 µm clamp widths) are order-of-magnitude estimates from general ESD-design literature, explicitly marked as not PDK-sourced. CDM is reported as "the source is silent" — no CDM-driven width number exists. This repo has no tester and no fabricated parts (`measurements/` stays empty by design, per CLAUDE.md); real ESD qualification cannot happen until silicon exists. |

### Harness/machinery self-verification (not a spec-row claim)

| Sub-claim | Verdict | Evidence record | Notes |
|---|---|---|---|
| Analog sim harness transient/rate-axis machinery, at both #1 operating points | **PASS** | [`sim/smoke-cml-pair/records/20260808-032312-430859a.md`](../sim/smoke-cml-pair/records/20260808-032312-430859a.md) | Full PVT × both rates (90 points), on a bare 3.3 V NMOS differential pair with the DR-0002 load topology — explicitly **not** a CML driver design deliverable (`sim/README.md`'s own framing). This record's own **Claim** field states "None — harness self-verification"; it is listed here for completeness (it is the first evidence this repo produced) but substantiates no spec row on its own. Taken against a dirty working tree, so it is not citable as a clean-tree result even for its own harness-proof purpose. |

## 2. What is not yet covered (named explicitly)

Per the coverage-honesty requirement this document exists to meet, the
following gaps are stated by name rather than left as silent omissions:

1. **Item 5 — PVT-vs-ratified-spec, gated by #9.** `sim/README.md`'s own
   working PVT matrix (−40/27/125 °C, ±10 % supply, 5 process corners) is
   explicitly **not yet ratified** — it is "a working default pending
   ratification, not a spec-derived requirement" (`sim/README.md`, "The PVT
   matrix" section). Issue #9 owns ratifying this matrix as DR-0009, and
   also owns resolving a PDK-variant discrepancy between this repo's `sim/`
   evidence (pinned to `gf180mcuD`) and its `layout/` evidence (produced
   against `gf180mcuC`, per `sim/README.md`'s "PDK variant" section and
   issue #9's own body). Until #9 rules, every PASS verdict in §1 above is
   graded against a **working-default, not-yet-ratified** PVT matrix, and
   the `sim/`-vs-`layout/` PDK-variant mismatch is unresolved. This is an
   operator-only item per CLAUDE.md's "agents do not relax the ratified
   spec" instruction and this repo's own `loom:operator-only` gating on #9
   — not something this document, or any other agent-authored artifact, can
   close.
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
   clamp, no package, no board — and the layout it extracts was produced
   against `gf180mcuC` while the simulation uses `gf180mcuD` models (item 1
   above, issue #9). A parasitic-RC re-run, and a post-layout run of the
   driver *with* its pad/ESD structure once that cell exists, are both still
   outstanding and neither has an evidence record.
3. **Monte Carlo evidence.** No record in `sim/` today carries a
   **Statistical convention** field with a seed, sample count, and a
   deterministic negative control — every record in §1 is a corner-matrix
   claim (`Statistical convention: N/A`), not a distribution claim. The T1
   evidence ladder requires Monte Carlo mismatch evidence, combined with
   (not replacing) the existing process-corner sweep, for the driver's
   swing/common-mode. This is tracked separately by **issue #23** ("Add
   Monte Carlo mismatch evidence for the CML driver's swing/common-mode"),
   the sibling Monte Carlo issue in this same Epic #17 phase, and has not
   landed as of this document.

No other spec row beyond those listed in §1 has any recorded `sim/`
evidence at all — in particular, the encoder/serializer digital domain
(DR-0003) is verified by `verification/tmds_encoder/` (cocotb, not the
`sim/` analog harness this document indexes) and is out of scope for this
rollup; the PLL interface (§2 of `spec/tmds-tx.md`, DR-0004) is a
requirement levied on a sibling canary block and has no evidence to cite
here by design (DR-0001/CLAUDE.md scope discipline).

## 3. Links

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
- Epic tracking the gap to T1 sim-validated (bronze): #17
