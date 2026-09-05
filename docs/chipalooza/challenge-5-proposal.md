# Chipalooza Challenge #5 (GF180MCU / Wafer.Space) — TMDS transmitter proposal

Submission target: Open Circuit Design's Chipalooza Challenge #5 (GF180MCU
test chip fabricated through Wafer.Space), 3.3 V digital / 5.0 V analog rail
structure, same as Challenge #3 unless that challenge's own rules page states
otherwise. This repository has not observed a published, dated submission
deadline for Challenge #5 as of this document's writing — none is asserted
here; the operator submitting this proposal should confirm the current
deadline directly against the challenge's own rules page before emailing it.

**Source repository**: `2AMLogic/gf180-tmds-tx` (public, Apache-2.0 — see
§8). Every number in §5 is transcribed from this repository's own
append-only `sim/` evidence, with a dated citation to the record it came
from — nothing here is asserted without a re-runnable testbench, per
`CLAUDE.md`'s "no claim without a testbench."

This document is written to be emailed verbatim as the block's public
proposal. It contains no personal or institutional identifiers; a designer
CV and a test-equipment list, if needed, are separate attachments the
submitting operator supplies outside this repository. Per this repository's
own `CLAUDE.md`, this is a **DVI-mode TMDS transmitter**: TMDS/DVI signaling
is unencumbered, and nothing here is described as HDMI-branded, HDMI-
certified, or implies HDMI compliance.

**Maturity note, stated up front rather than left for a reader to
discover.** This repository has **two separately mature partitions that are
not yet joined**: the digital TMDS encoder is RTL-verified, synthesized,
placed-and-routed, and timing-closed at 720p60; the analog current-mode
(CML) output driver with its integrated diode-clamped ESD/pad-ring is
schematic-captured, PVT-swept, laid out, DRC/LVS-clean, and — as of this
proposal — has its first post-layout electrical/PVT record as an assembled
block (§5, §6). **The 10:1→2:1 serializer/final-multiplexer stage that
would join them does not exist yet** (DR-0003, DR-0012) — it is modelled in
every analog testbench as an ideal differential source, a stated,
conditional assumption, not a measured interface. This document reports
both partitions honestly at their real, current maturity and does not
imply the join has happened.

---

## 1. Type of IP block

A DVI-mode TMDS transmitter: a synthesized 8b/10b-style TMDS encoder
(transition-minimized, DC-balanced, `rtl/tmds_encoder.v`) feeding — once the
not-yet-designed 10:1→2:1 serializer closes that gap (§3, §7) — a custom
current-mode (CML), open-drain differential line driver
(`design/cml_driver.sch`) integrated with a drawn diode-clamped ESD/pad-ring
structure (`layout/gds/gf180_tmds_pad_ring_assembly.gds`, DR-0011). Target
spec: [`spec/tmds-tx.md`](../../spec/tmds-tx.md) (**RATIFIED**, unlike the
draft specs some sibling proposals cite). Architecture and sizing derivation
in [`design/cml-driver-sizing.md`](../../design/cml-driver-sizing.md) and
[`design/esd-capacitance-budget.md`](../../design/esd-capacitance-budget.md).

**Per this repository's own scope discipline (`CLAUDE.md`), the PLL is not
part of this block.** It is sourced from a sibling canary
(`2AMLogic/gf180-pll`, itself a Challenge #5 proposal); §7 states this
block's numeric interface requirement of it and stops there.

---

## 2. I/O list, including test ports

### 2.1 Rails: this design is 3.3 V-only; the Challenge's 5.0 V analog rail is not exercised

Per DR-0002, the CML driver's output devices are gf180mcu's **3.3 V core
devices** (`nfet_03v3`), chosen explicitly over the 6 V thick-oxide I/O
devices (`nfet_06v0`) because the 6 V devices carry more parasitic
capacitance — capacitance this design's 742.5 Mbps eye budget cannot
absorb (DR-0002's own "Alternatives considered"). The digital domain runs
at the same 3.3 V corner of `gf180mcu_fd_sc_mcu9t5v0` (DR-0003), so no
level shifter exists anywhere in this design. **This is the single most
load-bearing disclosure in this proposal, stated the same way the sibling
`gf180-pll` proposal states its own**: the Challenge #5 brief asks that
"analog blocks should operate across 3.3–5.0 V," and this design, as it
exists today, does not. §5's supplementary check found that running the
receiver-side termination rail (`AVCC`) at 5.0 V does not even reach a
converged transient solution within a generous timeout against the
extracted assembly — it is not simply untested, it is measured to behave
pathologically outside its characterized 3.3 V ± 10 % operating region, and
no row in §5 is stated as "met" against a 5.0 V condition.

### 2.2 Pad table, mapped to the Challenge #5 slot budget

The digital encoder's port list (`rtl/tmds_encoder.v`: `clk`, `rst`, `data
[7:0]`, `ctrl[1:0]`, `de` in; `tmds[9:0]` out) and the analog assembly's
pin list (`layout/gds/gf180_tmds_pad_ring_assembly.gds`,
`.SUBCKT gf180_tmds_pad_ring_assembly IBIAS INN INP OUTN OUTP TAIL VSS`) map
onto the Challenge #5 budget (per Epic #542: one bandgap-referenced bias
voltage, up to 2 bandgap-referenced current sources, up to 24 digital
control inputs, up to 12 digital test outputs, up to 4 shared analog lines,
up to 4 dedicated pads, SPI control documented in the harness) as follows.

| Signal(s) | Dir | Challenge slot | Count used | Notes |
|---|---|---|---|---|
| `clk` | in | digital control input (budget ≤ 24) | 1 of 24 | Pixel-rate clock, 74.25 MHz (720p60) / 27.000 MHz (480p) — the PLL's pixel-rate output per §7, DR-0004/DR-0012 |
| `rst` | in | digital control input | 1 of 24 | Synchronous, active-high |
| `data[7:0]` | in | digital control input | 8 of 24 | 8-bit active-video pixel data |
| `ctrl[1:0]` | in | digital control input | 2 of 24 | `{C1, C0}` control pair, sampled during blanking |
| `de` | in | digital control input | 1 of 24 | Data-enable: 1 = active video, 0 = blanking |
| `INP`, `INN` | in, **proposed as test pins** | shared analog line (budget ≤ 4) | 2 of 4 | Differential full-rate data input to the CML driver. In the finished chip these are internal nets from the not-yet-built serializer (§1, §3, §7) — mapped here as bring-up/DC-level test pins standing in for that stage, per the note below |
| `IBIAS` | in | bandgap-referenced current source (budget ≤ 2) | 1 of 2 | 500 µA nominal, mirrored 1:20 onto the driver's tail device (`design/cml-driver-sizing.md` §0/§2) — a fixed DC bias current is exactly the kind of resource this slot category describes, not a generic control input; whether the harness's own supplied magnitude matches 500 µA exactly, or needs an on-die mirror/scale stage, is a harness-integration detail this proposal does not resolve |
| `OUTP`, `OUTN` | out, **dedicated** | dedicated pad (budget ≤ 4) | 2 of 4 | The block's actual TMDS lane output. **Needs a low-resistance, low-capacitance dedicated path, not a shared mux line** — DR-0005's ≤ 2 pF/pad capacitance budget exists specifically to preserve the 742.5 Mbps eye (§5), and any added mux-line series R/C directly narrows that eye; a shared line is not electrically compatible with this signal at rate |
| `tmds[9:0]` | out, **proposed as test outputs** | digital test output (budget ≤ 12) | 10 of 12 | Encoder's registered 10-bit TMDS character, exposed as diagnostic taps so encoder-only correctness can be bench-verified independently of the not-yet-built serializer/driver chain (§3, §4) — proposed, not load-bearing; a minimal test plan could omit these and rely on the cited RTL-level verification evidence instead |
| `VSS` | supply | ground (rail, not a slot) | — (rail) | Driver/pad-ring ground; also the substrate-tap net (DR-0011) |
| digital 3.3 V rail (`vdd_val` in `sim/`) | supply | 3.3 V digital rail | — (rail) | Encoder + driver's core-device supply |
| `AVCC` | — | **not a pin of this block** | — | The receiver's own termination rail, off-block by design (DR-0002) — listed here only to disambiguate it from the digital rail above; see §2.1 and §5 |

**Totals against the Challenge #5 budget**: 0 of 1 bandgap-referenced bias
voltage (this block draws no bandgap-referenced voltage of its own — only a
current, via `IBIAS`), **1 of ≤ 2** bandgap-referenced current sources,
**13 of ≤ 24** digital control inputs, **10 of ≤ 12** digital test outputs
(proposed; 0 required at minimum), **2 of ≤ 4** shared analog lines
(`INP`/`INN`, test-only), **2 of ≤ 4** dedicated pads (`OUTP`/`OUTN` — the
load-bearing item this document's filing context specifically asked to
check). **Every category fits inside budget with headroom**, unlike some
sibling proposals' current-source shortfall — this design's single
bandgap-current need (`IBIAS`) is comfortably inside the harness's ≤ 2
supply.

### 2.3 What's dropped, multiplexed, substituted, or new relative to this repo's own port lists

- **Nothing is dropped.** Every pin either RTL module exposes
  (`tmds_encoder`) or the signed-off analog assembly exposes
  (`gf180_tmds_pad_ring_assembly`) is mapped to a slot above.
- **`INP`/`INN` are proposed, not committed, as Challenge test pins.** In
  the finished, integrated chip they are internal nets between the
  not-yet-built serializer and the driver (§1, §3) — this proposal exposes
  them at the block boundary specifically so the driver can be
  bench-characterized and brought up on the shared test chip *before* the
  serializer exists, using the harness's shared analog mux (§2.1's
  low-speed/DC framing: `sim/`'s own eye/jitter evidence, not a
  repeat bench measurement at rate through the mux, is what substantiates
  the 742.5 Mbps claims in §5).
- **`tmds[9:0]` are proposed, not committed, digital test outputs**, for the
  same encoder-standalone-bring-up reason — a genuinely new addition
  relative to what has been simulated (the RTL/gate-level verification
  evidence cited in §5 already exercises `tmds` as an internal register; no
  change to the RTL itself is implied by exposing it as a pin).
- **`TAIL`** (the driver's internal tail node, promoted to a pin only by
  `klt`'s parasitic extraction, §6) is internal — not exposed here.
- **`SPI control` does not apply to the configuration inputs.** This
  block's digital control inputs (`clk`/`rst`/`data`/`ctrl`/`de`) are a
  real-time, per-pixel-clock data bus, not a slow configuration register —
  nothing in `design/`/`rtl/` implies an SPI-addressable state to program.

---

## 3. Functional description

The digital partition (`rtl/tmds_encoder.v`) transition-minimizes and
DC-balances each 8-bit pixel word (or passes one of four fixed control
characters during blanking) into a registered 10-bit TMDS character,
`tmds[9:0]`, one per `clk`, with four-clock-cycle registered latency
(module header comment). This is the well-understood DVI/HDMI-class
TMDS 8b/10b-style coding — unencumbered signaling, per `CLAUDE.md`'s "On
HDMI, and what may be said."

The analog partition (`design/cml_driver.sch`) is a DC-coupled,
open-drain, current-mode differential pair: two `nfet_03v3` switching
devices with commoned sources at a `TAIL` node, sunk by a tail device
mirrored 1:20 from the 500 µA `IBIAS` reference (`design/cml-driver-sizing.md`
§0/§2), driving `OUTP`/`OUTN` into the receiver's own 50 Ω/leg termination
to its 3.3 V rail (`AVCC`, off-block). The assembly
(`layout/gds/gf180_tmds_pad_ring_assembly.gds`, DR-0011) integrates this
driver core with two 25×25 µm Metal5 bond pads, each with a 20-finger
`diode_nd2ps_06v0` ESD clamp array and a real drawn substrate tap wired
into the DVSS ring strap, at the 350 µm pad pitch / 75 µm ring depth
`gf180mcu_fd_io`'s own library establishes (DR-0011).

**The join between the two partitions — a 10:1→2:1 serializer / final
multiplexer stage — is not yet designed** (DR-0003, DR-0012). Every analog
testbench in `sim/` models it as an ideal differential source (single-ended
levels `0.85·vdd_val`/`0.55·vdd_val`, an 80 ps linear edge, zero source
impedance, zero jitter — `sim/cml-driver-eye/testbench/cml_driver_eye.spice`'s
own module header), a stated requirement levied on that future stage
(`design/cml-driver-sizing.md` §4.1), not a measured interface. This is
disclosed here exactly as it is disclosed in this repository's own
`README.md` and `spec/tmds-tx.md` — it is a known, tracked gap, not an
oversight discovered while writing this proposal.

---

## 4. Bench test plan

All measurements below use only the pads/lines in §2.2 — `clk`, `rst`,
`data[7:0]`, `ctrl[1:0]`, `de`, `INP`/`INN`, `IBIAS`, `OUTP`/`OUTN`, and
(optionally) `tmds[9:0]`.

1. **Digital bring-up / encoder-only functional check.** Drive `clk`/`rst`/
   `data`/`ctrl`/`de` per `verification/tmds_encoder/`'s own test vectors
   and compare `tmds[9:0]` against the golden model — independently of the
   analog stage, since the serializer does not yet exist (§3).
2. **Analog DC bring-up.** Power the digital 3.3 V rail and apply a static
   differential level on `INP`/`INN` through the shared analog mux; confirm
   `OUTP`/`OUTN`'s DC swing and common mode against §5's `swing_dc`/`vcm_dc`
   rows.
3. **AC eye/jitter characterization.** Drive `INP`/`INN` at rate (bypassing
   the mux, or using the mux only if its added parasitic loading is
   confirmed negligible at 742.5 Mbps — an open bench question, not
   resolved by this document) and measure `OUTP`/`OUTN`'s eye height/width,
   rise/fall time, and deterministic jitter against §5's PRBS7 eye-mask row
   and PVT-corner jitter rows. This is the one measurement most likely to
   need the daughterboard's own high-speed fixture rather than the
   harness's shared/multiplexed lines.
4. **Device-stress / reliability spot check.** With `AVCC` at its nominal
   3.3 V ± 10 %, confirm no anomalous current draw or thermal behavior
   consistent with the `vgs`/`vgd`/`vds` stress margins §5 reports;
   **do not** apply `AVCC` = 5.0 V to real silicon — §5's supplementary
   check found that condition does not even converge in simulation, a sign
   of operation well outside this design's characterized 3.3 V core-device
   region.
5. **ESD clamp sanity (non-destructive).** Confirm the clamp diodes'
   leakage/off-state behavior at the bench is consistent with
   `sim/esd-diode-clamp-cv`'s simulated capacitance-vs-bias curve; full
   HBM/CDM qualification (JEDEC JS-001/JS-002 pulse testing) is a
   dedicated-fixture measurement this document does not plan in detail —
   see §7's open item.
6. **Repeat steps 2–4 across the daughterboard's available supply/
   temperature range** and record any deviation from §5's simulated PVT
   grid as a genuine silicon finding requiring a new, dated `sim/` record —
   not folded silently into this document, per this repository's
   evidence-trail convention.

---

## 5. Target specification at the Challenge #5 rails (3.3 V; the 5.0 V rail is unexplored)

### 5.0 Citation convention

Every row cites a specific, dated `sim/` record or `flow/` record from this
repository, or `spec/tmds-tx.md`'s own ratified decision records (DR-NNNN).
`spec/tmds-tx.md` is **RATIFIED** (2026-08-05) — unlike a draft spec, no row
below is graded against a target still subject to change through an open
ratification issue. Min/typ/max are re-derived directly from the underlying
evidence, per `measurements/characterization.md`'s own rollup, which this
table summarizes rather than duplicates independently.

| Parameter | Spec target (DR) | Measured (3.3 V, full PVT unless noted) | Verdict | Source (dated) |
|---|---|---|---|---|
| Rate per lane | 742.5 Mbps target, 270 Mbps fallback | Both rates swept at every PVT point below | — | `spec/tmds-tx.md` §1 |
| Single-ended swing | 400–600 mV (DR-0002) | Schematic 481.2–518.9 mV; core-extracted 481.2–519.0 mV; **assembly-extracted 493.6–511.7 mV (§6, `tt` corner)** | **MET** | `sim/cml-driver-eye/records/20260810-041436-a2c358b.md`, `.../20260815-072956-34e5253.md`, `.../20260905-193624-231b75c.md` |
| Common mode at nominal AVCC | 2.8–3.3 V (DR-0002, nominal-supply reading per DR-0006) | 3.041–3.054 V (schematic and core-extracted, unchanged); **3.0434–3.0506 V (assembly-extracted, `tt` corner)** | **MET** | Same records |
| Common mode across ±10 % AVCC | Tracks AVCC ~1:1 (DR-0006's qualified reading) | 2.711 V / 3.384 V (schematic/core); **2.714–2.721 V / 3.373–3.380 V (assembly-extracted, `tt` corner)** at AVCC = 2.97 V / 3.63 V | **MET against DR-0006**, not against DR-0002's original unqualified window | Same records |
| Device stress (`vds`/`vgs`/`vgd`) vs. 3.3 V core-device ceiling | Positive margin to the adopted 3.63 V ceiling (DR-0002, deferred to driver design) | Worst 2.761 V (`vds_sw_max`, schematic); 2.757 V (core-extracted); **2.632 V (assembly-extracted, `tt` corner, `tt_-40c_2.97v_742p5mbps`)** | **MET** | Same records |
| Deterministic jitter (this stage's contribution to the ≤ 0.15 UI allocation) | ≤ 0.15 UI p-p (spec/tmds-tx.md §2, DR-0004) | ≤ 5.79×10⁻⁵ UI (core-extracted, worst corner); **≤ 9.58×10⁻⁵ UI (assembly-extracted, `tt` corner)** — several thousand times inside budget either way | **MET** | Same records |
| Combined swing+jitter eye mask (DR-0013 row 6) | Height ≥ 200 mV AND width ≥ 0.75 UI, simultaneously, no fixed sampling instant | Worst 0.871–1.033 V margin, ≥ 4× the floor, full PVT × both rates × 0/1/2 pF pad cap | **MET** (schematic-level; no post-layout eye-mask run yet) | `sim/cml-driver-eye-mask/records/20260825-040412-4b0c9f6.md` |
| Pad capacitance budget | ≤ 2 pF/pad, ESD diodes + pad parasitic combined (DR-0005/DR-0011) | **0.094 pF (`OUTP`) / 0.075 pF (`OUTN`)**, 95–96 % headroom, at the landed block assembly, 20-finger clamp | **MET** — closed, not relaxed; corrects an earlier self-reported ~4× "over budget" figure that was a units-label bug (§9 of `design/esd-capacitance-budget.md`), not a redesign | `design/esd-capacitance-budget.md` §10.5, backed by `layout/drc_reports/gf180_tmds_pad_ring_assembly.parasitics.json` |
| ESD HBM ≥ 2 kV / CDM ≥ 500 V | JEDEC JS-001/JS-002 | No PDK source characterizes ESD failure current density or breakdown/snapback behavior for any gf180mcu device family; sizing is literature-estimated, not PDK-sourced | **Not evidenced — structurally unaddressable pre-silicon**, not a design gap this repo can close by simulation alone | `design/esd-capacitance-budget.md` §2; open decision, issue #145 |
| DRC (assembly) | 0 violations (`spec/tmds-tx.md` §1 "Signoff") | 0 violations, re-confirmed 2026-09-05 for this proposal | **MET** | `klt drc --deck gf180mcu layout/gds/gf180_tmds_pad_ring_assembly.gds`, this proposal's re-run |
| LVS (assembly) | `status: match`, negative control correctly `mismatch` | `status: match` (2 warning-only findings), `_shorted` negative control `status: mismatch` (5 error-severity findings), re-confirmed 2026-09-05 | **MET** | Same re-run; `layout/scripts/check_lvs_signoff.py` enforces the pair |
| Post-layout PVT, driver core only | Device-level extraction, full PVT × rate | Matches schematic to < 5 % on every DC/timing row (§ above) | **MET**, core-cell scope only | `sim/cml-driver-eye/records/20260815-072956-34e5253.md` |
| **Post-layout PVT, full driver+pad-ring+ESD assembly** | **Electrical/PVT simulation of the assembled block — previously an open gap this proposal exists to close** | **See §6 — first record of its kind (18-point `tt`-corner grid: full temperature/supply/rate sweep, one process corner)** | **MET for the `tt` corner; `ff`/`ss`/`fs`/`sf` not yet run (tracked, issue #161)** — a disclosed subset, not a narrowed claim | `sim/cml-driver-eye/records/20260905-193624-231b75c.md` |
| Digital: RTL functional verification | Exhaustive golden-model equivalence + negative control | Real DUT passes, negative-control DUT correctly fails | **MET** | `verification/tmds_encoder/`, `verification/README.md` |
| Digital: synthesis, P&R, DRC, LVS | Gate-level netlist, routed GDS, clean signoff | 266 cells, 0 unmapped; `status: clean` DRC; `status: match` LVS with a correctly-failing negative control | **MET** | `flow/tmds_encoder/records/20260816-*.md` |
| Digital: setup timing, 720p60 (74.25 MHz) | Met at all corners | Worst-corner Fmax 75.83 MHz (`ss_125C_3v00`); margin +0.2799 ns, 2.1 % of the period — **closed, not comfortable** | **MET, narrow margin** | `flow/tmds_encoder/records/20260817-110611-37e197a.md` |
| Digital: hold timing | Met at all corners, both targets | Worst margin +0.2703 ns | **MET** | Same record |
| Analog rail, **5.0 V** | Challenge #5 asks analog blocks to operate across 3.3–5.0 V | No 5.0 V-class device (`nfet_06v0`) exists in this design; supplementary single-point check at `AVCC` = 5.0 V (not a full PVT record) — see below | **UNMET — measured, not merely asserted**: see the paragraph immediately below | This proposal, §2.1, §6 |

No row above is relaxed, narrowed, or omitted to make it pass — the 5.0 V
rail row, the digital timing row's narrow margin, and the ESD HBM/CDM row
are all reported exactly as the underlying evidence states, per
`CLAUDE.md`'s "agents do not relax the ratified spec to make results pass."

**The 5.0 V row, measured, not just asserted.** `AVCC` (the receiver
termination rail) sets this driver's output common mode by DR-0006's own
closed-form relationship, `vcm ≈ AVCC − I_tail·R_leg/2` — not a curve fit,
a property of the open-drain topology itself — measured as an offset of
0.246–0.259 V below `AVCC` at the ±10 % nominal-3.3 V corners above, across
the schematic, core-extracted, and assembly-extracted records alike.
Extrapolating that same closed-form relationship (not the measured device-
stress figures themselves, which were never swept above `AVCC` = 3.63 V in
any record and so are not safely extrapolated on their own), an `AVCC` =
5.0 V common-mode output would sit around 4.74–4.75 V — already more than
1 V above this design's own adopted 3.63 V device-stress ceiling before
even accounting for the additional swing on top of it. A single-point,
non-PVT supplementary check (`AVCC` = 5.0 V, `tt` corner, 27 °C, nominal
digital rail, 742.5 Mbps, against the same layout-extracted assembly DUT
§6 uses — reproducible by overriding `avcc_nom` in
`sim/cml-driver-eye/testbench/cml_driver_eye.spice` and re-running the
harness, then reverting the edit) went further than that extrapolation: the
transient **did not converge within a 600 s timeout** (against ≈137 s for
the identical deck at the nominal 3.3 V rail) — a genuinely measured, not
merely asserted, sign that this operating point sits well outside the
region the design and its models are characterized for, not just numerically
over a margin line. This is cited here as an informative, explicitly
non-record check (`--no-write`), not a formal PVT-graded `sim/`-evidence
row — the point was to honestly characterize the gap, not to mint evidence
for a condition this design was never intended to run at.

---

## 6. Layout, DRC/LVS, and post-layout PVT status

**DRC/LVS-clean GDS exists and was re-confirmed for this proposal**
(`layout/gds/gf180_tmds_pad_ring_assembly.gds`, §5). **This proposal adds
the assembled block's first electrical/PVT simulation** — until now, only
its bare driver-core sub-cell had post-layout electrical evidence
(`sim/cml-driver-eye/records/20260815-072956-34e5253.md`), and the assembly
itself (driver + real diode-clamped ESD pads + real interconnect parasitics)
had structural DRC/LVS signoff only
(`measurements/characterization.md` §3 item 2's stated gap).

`layout/scripts/gen_pad_ring_assembly_dut.py` derives a simulatable DUT
fragment from `klt extract --deck gf180mcu --parasitics`'s full
interconnect-RC extraction of the signed-off GDS (338 extracted per-finger
`nfet_03v3` devices, 40 `diode_nd2ps_06v0` ESD-clamp fingers, real drawn
metal R/C) — a strictly larger-coverage extraction than the core-only
record above, which carried no interconnect parasitics at all
(`measurements/characterization.md` §3 item 2's other named gap). The
generator's own translation is asserted device-by-device and net-by-net
against the LVS reference by `sim/tests/test_pad_ring_assembly_dut.py`
(25 tests: model binding, diode parameter renaming, folded-width/geometry
agreement with `layout/lvs/gf180_tmds_pad_ring_assembly.ref.spice`, no
transposed leg, correct substrate handling).

**Record**: [`sim/cml-driver-eye/records/20260905-193624-231b75c.md`](../../sim/cml-driver-eye/records/20260905-193624-231b75c.md)
— the same testbench, manifest, measurements and checks as the two existing
driver-core records, run instead against this assembly DUT: **18 points**
(3 temperatures × 3 supply points × both rates) at the `tt` (typical)
process corner, **18/18 PASS**. Every row that record reports is summarized
into §5 above. As with the core-only extraction, `klt extract --parasitics`
does not model skin effect, distributed transmission-line behavior,
package, board, or bond wire — the drawn on-die pad and its real
interconnect R/C are what is captured; anything beyond the die edge is not
(the record's own **Claim** field states this explicitly).

**Scope, disclosed rather than glossed over**: this record covers the `tt`
process corner only, not the full 5-corner (`tt`/`ff`/`ss`/`fs`/`sf`)
`mos` set this repository's own PVT-matrix convention (DR-0013) mandates
for a complete claim — the record's own **Corner matrix run** field states
this explicitly with a written justification (the run was minted on
contended shared hardware; a full 5-corner invocation risked an unbounded
multi-hour run). Extending to the remaining four corners is tracked as a
follow-up (issue #161) and needs no new tooling — the DUT and testbench
already exist. This is stated here, in §5's table, and in
`measurements/characterization.md`'s own coverage-honesty section, so no
reader has to infer the scope from silence.

---

## 7. PLL interface note (out of scope to design — per `CLAUDE.md`)

This block requires, of the sibling `gf180-pll` canary (DR-0004,
`spec/decisions/0012-pll-interface-completion.md`):

| Requirement | Value |
|---|---|
| Reference input | 27.000 MHz, single-ended CMOS, ±100 ppm |
| Bit-rate clock output (720p60 target / 480p fallback) | 742.5 MHz / 270 MHz, **differential, low-swing (CML-compatible)**, 300–800 mV differential p-p (`Proposed`), common mode compatible with this block's 3.3 V core-device family |
| Pixel-rate clock output | 74.25 MHz / 27.000 MHz, single-ended CMOS, 3.3 V, rail-to-rail |
| Duty cycle (both outputs) | 45–55 % (`Proposed`) |
| Clock relationship | Fixed, edge-aligned 10:1 pair, no cycle slips |
| **PLL-attributable jitter budget (this block's requirement of the PLL)** | **≤ 0.10 UI peak-to-peak on the bit-rate clock output** (≈ 135 ps @ 742.5 Mbps, ≈ 370 ps @ 270 Mbps) |
| Remaining budget (this block's own responsibility: serializer + driver + board) | ≤ 0.15 UI peak-to-peak — closed out empirically by §5's driver-stage jitter rows; the not-yet-built serializer's own contribution is unmeasured (§3) |
| Half-rate/synthesized-domain clocks (371.25 MHz / 135 MHz) | **Not levied on the PLL** — derived internally by a single ÷2 toggle-flip-flop divider from the bit-rate clock output (DR-0012 Decision 1), inheriting that clock's jitter with no additional budget line |
| Loading the PLL must drive | Bit-rate output: this block's internal ÷2 divider (negligible) plus the not-yet-designed final-mux/CML clock-input buffer (`Proposed` placeholder, low single-digit fF, pending that stage's own sizing). Pixel-rate output: one clock-tree-root buffer input |

This block does **not** design the PLL — its internal architecture (loop
filter, VCO topology, charge pump, etc.) is entirely out of scope for this
repository, per `CLAUDE.md`'s explicit scope discipline. See
`spec/tmds-tx.md` §2 and DR-0004/DR-0012 for the full derivation.

---

## 8. Open items before this proposal's evidence trail is considered complete

1. **The 5.0 V analog rail is unexplored and, per §5/§6, quantifiably
   incompatible with this design's current device family without a
   redesign** (an on-die 5.0 V→3.3 V regulation stage, thick-oxide output
   devices with a capacitance/bandwidth re-analysis, or a harness
   accommodation to draw the analog rail from the 3.3 V digital supply).
   Nothing here should be read as implying that redesign has started.
2. **The 10:1→2:1 serializer / final multiplexer does not exist** (§1, §3).
   Every analog eye/jitter/swing measurement in §5 is conditional on the
   ideal-source input model `design/cml-driver-sizing.md` §4.1 states as a
   requirement levied on that future stage, not a verified interface.
3. **ESD HBM ≥ 2 kV / CDM ≥ 500 V qualification is not evidenced** and, per
   `design/esd-capacitance-budget.md` §2, cannot be evidenced from PDK data
   alone pre-silicon — tracked as an open decision at issue #145 (is this
   schedulable work, or a permanent pre-silicon limitation).
4. **No post-layout eye-mask (DR-0013 row 6) run exists yet against the
   extracted assembly** — only the schematic-level PRBS7 record does
   (tracked as issue #160).
5. **The assembly's post-layout PVT record (§6) covers the `tt` process
   corner only** — 18 of the mandated 90-point `mos` corner-set × rate
   grid. `ff`/`ss`/`fs`/`sf` have no electrical/PVT evidence yet for the
   assembled block (tracked as issue #161); the DUT and testbench already
   exist, so closing this needs no new tooling, only additional
   `sim/run_corners.py` invocations on uncontended hardware.
6. **Digital setup-timing margin at 720p60 is narrow** (2.1 % of the
   period at the worst corner, §5) — closed, not comfortable; a process
   shift or a design change elsewhere in the clock path could re-open it.
7. **`INP`/`INN` as a shared-analog-mux test path at 742.5 Mbps is an open
   bench question** (§2.3, §4) — the mux's added parasitic loading at that
   rate has not been characterized against this block's own eye budget;
   §5's rate-accurate claims rest on `sim/` evidence taken with an ideal
   source, not a measurement through the Challenge harness's shared line.

None of the above items block *submitting* this proposal — consistent with
this program's stated goal for Chipalooza proposals, the aim is to state the
design honestly at its current maturity with every claim traceable to a
dated `sim/` record, not to have already closed every open item by the
submission date.

---

## 9. Licensing and EDA flow

- **License**: this entire repository — spec, decision records, RTL,
  schematics, testbenches, layout, and every evidence record cited above —
  is licensed [Apache-2.0](../../LICENSE), satisfying the Challenge's
  requirement for a standard open license with all modifiable sources
  public.
- **Flow**: fully open-source. Digital: [Icarus
  Verilog](https://github.com/steveicarus/iverilog) + [cocotb](https://www.cocotb.org/)
  for RTL verification, [Yosys](https://github.com/YosysHQ/yosys) for
  synthesis, [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD)
  for place-and-route. Analog: [xschem](https://xschem.sourceforge.io/) for
  schematic capture, [ngspice](https://ngspice.sourceforge.io/) for
  simulation. Layout, DRC, LVS, and parasitic extraction (both partitions)
  via [KLayout](https://www.klayout.de/) driven by
  [klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`). The
  gf180mcu PDK (`gf180mcuD` variant, DR-0010) resolved via the standard
  `PDK_ROOT`/`PDK` environment convention this repository uses throughout.
  Every cited `sim/`/`flow/` record's own provenance fields state the exact
  pinned toolchain versions that produced it, so any reviewer can re-run the
  cited evidence from a clean checkout (`sim/run_corners.py`, documented in
  `sim/README.md`; `flow/README.md` for the digital side).
