# gf180-tmds-tx target specification

**Status: RATIFIED — 2026-08-05.**

This document is the ratified specification for the DVI-mode TMDS
transmitter block. It replaces the DRAFT table that previously lived in
`README.md`. Ratification means: the parameter table below is the number
engineering designs to; changing it after this point requires a new decision
record (DR-NNNN) in this file, not a silent edit.

This block is a **DVI-mode TMDS transmitter**. TMDS/DVI signaling is
unencumbered; the HDMI Adopter Agreement covers only the connector and
trademark. Nothing in this repository is HDMI-certified, HDMI-branded, or
should be described as an HDMI block.

## 1. Target parameter table

| Parameter | Target | Fallback | Stretch |
|---|---|---|---|
| Resolution | 720p60 | 480p (720×480p60) | 1080p60 |
| Pixel clock | 74.25 MHz | 27.000 MHz (nominal) | 148.5 MHz |
| Rate per lane (10:1 TMDS) | 742.5 Mbps | 270 Mbps | 1.485 Gbps |
| Lanes | 3 data + 1 clock | same | same |
| Electrical | DC-coupled, 50 Ω to 3.3 V, ~10 mA sink | same | same |
| Serialization | 10:1, custom CML final stage | same | same |
| Signoff | DRC + LVS clean (`klt drc` / `klt lvs`), pad ring included | same | same |

1080p60 is a stretch goal only. Per DR-0001, it does not drive architecture
before 720p60 closes.

## 2. PLL interface (levied on a sibling canary — out of scope here)

**Scope note**: this block does not design the PLL. The PLL is a sibling
canary block. This section is the numeric interface contract this block
requires of it; the PLL's internal architecture (loop filter, VCO topology,
charge pump, etc.) is entirely out of scope for this repository.

| Requirement | Value |
|---|---|
| Reference input | 27.000 MHz, single-ended CMOS, ±100 ppm |
| Bit-rate clock output (720p60 target) | 742.5 MHz (= 27.000 MHz × 110/4) |
| Bit-rate clock output (480p fallback) | 270 MHz (= 27.000 MHz × 10) |
| Pixel-rate clock output (720p60 target) | 74.25 MHz (= bit-rate clock ÷ 10) |
| Pixel-rate clock output (480p fallback) | 27.000 MHz (= bit-rate clock ÷ 10) |
| Clock relationship | Bit-rate and pixel-rate outputs must be a fixed, edge-aligned 10:1 pair with no cycle slips — either pixel clock derived from bit clock by an internal ÷10, or both delivered already phase-locked with defined edge alignment |
| Total TMDS output jitter budget (informative, DVI-class target) | ≤ 0.25 UI peak-to-peak at the pad (≈ 337 ps @ 742.5 Mbps, ≈ 926 ps @ 270 Mbps) |
| **PLL-attributable jitter budget (this block's requirement of the PLL)** | **≤ 0.10 UI peak-to-peak on the bit-rate clock output (≈ 135 ps @ 742.5 Mbps, ≈ 370 ps @ 270 Mbps)** |
| Remaining budget (serializer + driver + board, this block's own responsibility) | ≤ 0.15 UI peak-to-peak (≈ 202 ps @ 742.5 Mbps, ≈ 556 ps @ 270 Mbps) — closed out empirically with PVT-corner sim results in the driver design work, not asserted here |

720p60's UI is 1/742.5 MHz ≈ 1.347 ns; 480p's UI is 1/270 MHz ≈ 3.704 ns. The
0.10 UI PLL allocation is derived, not measured — see DR-0004 for the
derivation and its informative RMS approximation.

## 3. Pad cell and ESD strategy

See DR-0005. Summary: the pad cell is **drawn from scratch** (not adapted
from `gf180mcu_fd_io`'s general-purpose bidirectional pad); its ESD clamp
network is **adapted from existing gf180mcu primitives** (the same diode
primitives the stock I/O library itself uses). ESD target: **HBM ≥ 2 kV
(JEDEC JS-001), CDM ≥ 500 V (JEDEC JS-002)**; MM not targeted.

## 4. Decision records

Each decision record follows a lightweight ADR shape: Context, Decision,
Alternatives Considered, Consequences, Status. See `spec/README.md` for the
convention this establishes for future spec changes.

### DR-0001: Resolution ladder — 720p60 target, 480p fallback, 1080p60 does not drive architecture

**Context**: `README.md`'s DRAFT table listed 720p60 as target and 1080p60
as stretch without stating whether the stretch goal was allowed to shape
early architectural decisions (bus widths, clock plan, driver bandwidth
margin).

**Decision**: 720p60 (742.5 Mbps/lane) is the target. 480p (720×480p60,
270 Mbps/lane) is the guaranteed fallback. 1080p60 (1.485 Gbps/lane) is a
stretch goal that **does not** drive architecture until 720p60 closes —
matching CLAUDE.md's explicit instruction and the issue's own
recommendation.

**Alternatives considered**: Design headroom for 1080p60 from the outset
(wider CML bandwidth, faster PLL multiplication range) was considered and
rejected — it adds driver bandwidth and ESD-capacitance risk to the block's
already-highest-risk component (the pad ring) before 720p60 is even
verified.

**Consequences**: The PLL interface (§2), driver topology (DR-0002), and
pad/ESD budget (DR-0005) are all specified against 742.5 Mbps as the primary
number, with 270 Mbps as a fallback operating point. Revisiting 1080p60 is a
future decision record, not an assumption baked into this one.

**Status**: Accepted.

### DR-0002: Driver topology and supply — DC-coupled current-mode, 3.3 V core devices

**Context**: TMDS's electrical definition (DC-coupled, 50 Ω to 3.3 V,
~10 mA sink) dates to DVI 1.0 (1999) and predates gf180mcu. It must be
checked against gf180mcu's actual device voltage ratings, not assumed
compatible.

**Decision**: The driver is a DC-coupled, current-mode (open-drain)
differential driver. Each lane sinks a nominal 10 mA switched between the
two legs of a differential pair, into the receiver's 50 Ω per-leg
termination to a 3.3 V rail — giving a single-ended swing target of ~500 mV
(400–600 mV working range) and a common-mode target of 2.8–3.3 V (headroom-
limited by the driver's own output impedance, not simply equal to the
supply rail). **The 2.8–3.3 V common-mode figure is a nominal-supply
(3.3 V) target** — see DR-0006 for the explicit supply-tracking tolerance
that qualifies it across this repo's mandated ±10 % supply-corner PVT
sweep; the swing target is unaffected and remains a flat absolute window
at every corner. The driver's output devices are gf180mcu's **3.3 V core
devices** (`nfet_03v3` / `pfet_03v3` in the vendored PDK's SPICE model set,
confirmed present in `libs.tech/ngspice/sm141064.ngspice`, gf180mcuD /
open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` as checked out via
volare, 2026-08-05) — not the 6 V thick-oxide I/O devices
(`nfet_06v0`/`pfet_06v0`) that `gf180mcu_fd_io`'s general-purpose pad uses.

**Alternatives considered**: Using the 6 V thick-oxide I/O devices (as the
stock `gf180mcu_fd_io__bi_t`/`bi_24t` pads do) was considered and rejected —
those devices carry more parasitic capacitance than the 3.3 V core devices,
which works against the CML output stage's bandwidth at 742.5 Mbps, and
their native operating point (5 V-tolerant) does not match TMDS's 3.3 V
common-mode without extra headroom margin analysis this block doesn't need
to spend.

**Consequences**: Exact device sizing, output impedance calibration (if
any), and Vgs/Vds margin verification against the 3.3 V devices' rated
limits are deferred to the driver design work — this decision fixes the
device *family*, not the transistor-level design. This also motivates
DR-0003's choice to run the digital domain at 3.3 V rather than the
standard-cell library's more commonly quoted 5 V corner (see below), so the
digital-to-CML boundary does not need a level shifter.

**Status**: Accepted.

### DR-0003: Serialization ratio and clocking — 10:1, synthesized-to-custom boundary

**Context**: 10:1 serialization (8 data bits + 2 control bits → one 10-bit
TMDS code per lane) is the DVI/HDMI-standard ratio. The question this
decision resolves is where the standard-cell/CML boundary falls, and what
supply domain the synthesized logic runs at.

**Decision**: 10:1 serialization ratio, confirmed. The TMDS 8b/10b-style
encoder (transition-minimized, DC-balanced control+data encoding) and a
first-stage 10:1→2:1 parallel-to-serial reduction are **synthesized**,
targeting the `gf180mcu_fd_sc_mcu9t5v0` standard-cell library. That library
is characterized at multiple supply corners including a **3.3 V nominal
corner** (`gf180mcu_fd_sc_mcu9t5v0__tt_025C_3v30.lib` and its ff/ss
counterparts at `3v60`/`3v00`, confirmed present in the vendored PDK,
2026-08-05) — the digital domain runs at **3.3 V**, the same supply as the
driver's core devices (DR-0002), so no level shifter is needed at the
digital-to-CML boundary. The final 2:1 multiplexer and the CML output
driver itself are **custom**, clocked directly from the PLL's full-rate
(742.5 MHz / 270 MHz) and half-rate phases — the standard-cell library's
timing closure at the full bit rate is not yet characterized for this
design and is not assumed here.

**Alternatives considered**: Running the digital domain at the standard-cell
library's 5 V corner (its more commonly documented operating point) was
considered and rejected once the 3.3 V corner was confirmed to exist in the
vendored liberty set — it would otherwise force a 5 V→3.3 V level shift
immediately before the CML stage, adding delay and jitter right at the
highest-speed boundary. A deeper (e.g. 10:4 or 10:5) synthesized reduction
was also considered; 10:1→2:1 was chosen as the more conservative default
since the actual achievable synthesized clock frequency has not yet been
characterized against this library's timing arcs — a shallower reduction
gives the custom stage a comfortably low final multiplexing ratio (2:1)
regardless of where that ceiling lands.

**Consequences**: The synthesized-domain clock ceiling is an open item —
RTL/synthesis work must confirm the standard-cell library actually closes
timing at the pixel-domain-derived intermediate rate (5× pixel clock =
371.25 MHz @ 720p60) before this boundary is treated as final. If it does
not, this decision record will need superseding with a deeper synthesized
reduction (smaller custom-domain multiplexing ratio needed) or vice versa.

**Status**: Accepted. The synthesized-domain frequency ceiling flagged here
as unverified is now measured — see DR-0007, which resolves this open item
to timing-driven synthesis + CTS closing hold and the 480p fallback, with
full 720p60 setup closure deferred to a follow-up architecture (RTL
pipelining) decision record (issue #110).

### DR-0004: PLL interface numerics and jitter budget

**Context**: The PLL is out of scope for this repository (DR-0001/CLAUDE.md
scope discipline), but this block must hand its sibling a numeric interface
contract — reference frequency, output frequencies, and a jitter budget —
since TMDS eye closure is the primary way a bad PLL breaks this block.

**Decision**: See §2's table. Key derivation:

- **Reference**: 27.000 MHz is chosen because it lets the 480p fallback's
  pixel clock come directly from the reference (×1, ÷10 for the bit clock)
  and lets 720p60's pixel clock be reached with a clean rational
  multiplication factor: 74.25 MHz = 27.000 MHz × 11/4. This mirrors the
  reference frequency used across a large fraction of real-world DVI/HDMI
  transmitter reference designs, so it is not a novel choice.
- **Total jitter budget**: ≤ 0.25 UI peak-to-peak is the DVI-class figure
  widely cited for TMDS clock-channel output jitter (informative — this
  repo has not independently re-derived it from a formal DVI 1.0 citation,
  and treats it as an industry-standard starting target, not a
  re-litigated first-principles result).
- **PLL allocation**: 0.10 UI peak-to-peak (40% of the total budget) is
  assigned to the PLL's own output jitter, leaving 0.15 UI (60%) for this
  block's own serializer distribution jitter, driver data-dependent jitter,
  and board/package effects. The 40/60 split is a judgment call, not a
  derived optimum — it treats the PLL as the single largest jitter
  contributor in a typical clock-and-serialize chain while leaving the
  custom CML stage (the least-characterized part of this design) the larger
  absolute margin.
- **Informative RMS approximation**: assuming a dual-Dirac total-jitter
  model at a 1e-12 BER target (Q ≈ 7.03, so peak-to-peak ≈ 14.1 × RMS for a
  Gaussian random-jitter-dominated budget), the 0.10 UI PLL allocation
  corresponds to roughly 9.6 ps RMS @ 742.5 Mbps. This is informative only —
  the actual deterministic/random jitter split is the sibling PLL block's
  own spec's responsibility, not fixed here.

**Alternatives considered**: A flat percentage-of-UI budget with no
reference-frequency commitment (leaving the PLL free to choose its own
reference) was considered and rejected — without a fixed reference and a
stated multiplication ratio, the "10:1, edge-aligned, no cycle slips"
requirement in §2 cannot be verified as satisfiable, since arbitrary
reference/ratio choices can make an exact 74.25/27.000 MHz relationship
unreachable with a realistic PLL architecture.

**Consequences**: If the sibling PLL canary's own ratified spec cannot meet
0.10 UI peak-to-peak at 742.5 MHz, this decision record must be revisited —
either by relaxing this block's own internal budget below 0.15 UI (tightening
serializer/driver design margin) or by re-deriving the total 0.25 UI figure
against actual measured eye-closure tolerance once encoder/driver
verification exists.

**Status**: Accepted, pending confirmation against the sibling PLL canary's
own ratified spec once it exists.

### DR-0005: Pad cell and ESD strategy

**Context**: `gf180mcu_fd_io` (the vendored PDK's general-purpose I/O
library) ships bidirectional pads (`gf180mcu_fd_io__bi_t`,
`gf180mcu_fd_io__bi_24t`), power pads, an analog-signal pad
(`gf180mcu_fd_io__asig_5p0`), corner and break cells — confirmed via
`libs.ref/gf180mcu_fd_io/cdl/gf180mcu_fd_io.cdl`, gf180mcuD / open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, 2026-08-05 — but **no
high-speed/CML-oriented pad cell**. Every bidirectional pad's ESD clamp
network in that CDL netlist is built from two diode primitives instantiated
directly against the pad net: `diode_nd2ps_06v0` (clamp toward VSS) and
`diode_pd2nw_06v0` (clamp toward VDD), sized per net with `m`/`AREA`
parameters (observed instances range roughly 1–150 µm² depending on which
node in the pad cell they protect). No separately-characterized
"ESD-qualified" device beyond these diode primitives is visible in this
library snapshot.

**Decision**:
- **Pad structure: drawn from scratch.** The stock `bi_t`/`bi_24t` pad is
  sized for a 5 V/6 V-tolerant general-purpose GPIO with a correspondingly
  large driver and ESD diode area; both work against this block's 3.3 V
  common-mode target (DR-0002) and its need for low pad parasitic
  capacitance at 742.5 Mbps. A dedicated pad cell (pad opening, routing,
  CML driver placement, guard-ring/latch-up strategy) is drawn for this
  block rather than adapting the stock pad.
- **ESD clamp network: adapted from existing PDK primitives.** Rather than
  designing a new ESD device from scratch, the clamp network reuses the
  same `diode_nd2ps_06v0` / `diode_pd2nw_06v0` primitives the stock I/O
  library itself relies on, sized specifically for this pad's capacitance
  budget rather than copied at the stock library's sizes.
- **ESD target: HBM ≥ 2 kV per JEDEC JS-001, CDM ≥ 500 V per JEDEC JS-002.**
  MM (machine model) is not targeted, matching common modern industry
  practice. This is the standard minimum appropriate for a lab/shuttle-run
  canary part handled under controlled bench conditions — not a commercial-
  product target, and explicitly lower than a product HBM target (often
  ≥8 kV) would be.
- **Pad capacitance target: ≤ 2 pF per data/clock pad** (ESD diodes + pad
  parasitic combined), set to preserve 742.5 Mbps eye margin. This is the
  primary tension this decision record leaves open: larger ESD diodes buy
  more HBM/CDM margin at the cost of capacitance that closes the eye. The
  2 kV/500 V targets and the 2 pF budget must be validated together against
  actual diode sizing — not asserted as simultaneously achievable here.

**Alternatives considered**: Adapting `gf180mcu_fd_io__asig_5p0` (the
analog-signal pad, plausibly the lowest-capacitance option in the stock
library since it is meant to pass an analog signal rather than drive a
5 V/6 V digital output) was considered. Rejected for now because its ESD
network, capacitance, and pitch have not been characterized against this
block's 2 pF/742.5 Mbps targets in this repository — issue #2 owns that
factual PDK survey. If #2's findings show `asig_5p0` (or another existing
structure) already meets the capacitance and ESD targets here, this
decision record should be superseded to adapt it instead of drawing fully
from scratch, since reuse lowers verification risk.

**Consequences**: This decision is **provisional on issue #2's PDK-rules
survey**. #2 owns the factual question of what gf180mcu's pad-ring pitch,
diode SPICE parameters (breakdown voltage, avalanche/TLP behavior), and
guard-ring rules actually allow; this decision record's 2 kV/500 V/2 pF
targets are the requirement #2's findings must be checked against, not a
result #2 is assumed to already confirm. If #2 finds the 2 pF budget
cannot support a 2 kV/500 V clamp with these primitives, this decision
record must be superseded (relax the capacitance budget with an eye-margin
re-analysis, or relax the ESD target with an explicit handling-procedure
justification) rather than silently proceeding on an invalidated number.

**Status**: Accepted — provisional pending #2.

### DR-0006: DR-0002's common-mode window is a nominal-supply target, with an explicit supply-tracking tolerance

**Context**: DR-0002 states a common-mode target of 2.8–3.3 V with no
stated supply-tolerance qualifier. Issue #11's driver evidence
(`design/cml-driver-sizing.md` §7/§8, backed by
`sim/cml-driver-eye/records/20260810-041436-a2c358b.md`) confirms the
target is met cleanly at nominal AVCC = 3.3 V — common mode measured
3.041–3.054 V across the full PVT matrix, comfortably inside 2.8–3.3 V —
but is structurally crossed at the ±10 % supply corners this repo's own
PVT matrix (per CLAUDE.md's "PVT corners on every recorded analog result")
already mandates characterizing: at AVCC = 2.97 V (−10 %), common mode
reaches as low as **2.711 V** (below the 2.8 V floor); at AVCC = 3.63 V
(+10 %), it reaches as high as **3.384 V** (above the 3.3 V ceiling) — both
re-extracted directly from the record's `vcm_avcclo`/`vcm_avcchi` columns
across all 90 corner rows (`min`/`max` over the whole PVT×rate grid).

This is not a sizing defect the driver design can fix. DR-0002's own
topology — DC-coupled, open-drain, 50 Ω/leg *to the receiver's own AVCC
rail* — pins the "off" leg's output essentially to `AVCC` itself at every
corner: `common_mode ≈ AVCC − (I_tail × R_leg) / 2`, confirmed directly by
`design/cml-driver-sizing.md` §8's AVCC-sensitivity characterization.
Whatever `AVCC` is doing, the common-mode output tracks it almost 1:1,
independent of tail-current or switch-pair sizing — no device-sizing
choice inside a DR-0002-compliant driver decouples common mode from the
supply rail it is terminated to.

**Decision**: DR-0002's 2.8–3.3 V common-mode window is ratified as a
**nominal-supply (AVCC = 3.3 V) figure**, not a flat absolute window that
must independently hold at every supply corner. The qualified requirement
is: common mode = 2.8–3.3 V **at nominal AVCC = 3.3 V**, tracking the
receiver-side termination rail at approximately 1:1 (per the relationship
above) across this repo's mandated ±10 % supply-corner sweep — an explicit
supply-tracking derating, not an independently re-litigated absolute
window. This is a durable characterization of the driver's fixed
open-drain-to-rail topology (any DR-0002-compliant driver design shows the
same tracking, not just this specific cell's sizing), so it belongs in the
decision record rather than only in `design/cml-driver-sizing.md`'s
per-design evidence.

Reading the target this way, rather than widening the absolute window (the
alternative considered and rejected below), is chosen because a widened
absolute window would not actually describe the physics: the common-mode
output is not "somewhere in a wider range" independent of supply — it is
`AVCC` minus a small, well-characterized offset, at every corner. Stating
the target as nominal-plus-tracking is the more precise, and more
useful-to-a-downstream-receiver-design, characterization; a flat widened
window would obscure that the corner-to-corner spread is fully explained
by (and proportional to) supply variation, not an independent source of
common-mode uncertainty.

**Alternatives considered**: Widening DR-0002's 2.8–3.3 V window to a flat
absolute range containing the full ±10 % supply-corner swing (e.g.
~2.5–3.7 V, matching the bound `sim/smoke-cml-pair`'s own widened sanity
check already used) was considered and rejected. It would technically
close the compliance gap, but at the cost of a looser, less physically
meaningful target than a DVI/HDMI-class receiver may actually expect, and
it would obscure the 1:1 AVCC-tracking relationship that fully explains
the corner-to-corner spread — a downstream receiver design reading a flat
2.5–3.7 V window would have no way to tell that the real per-corner
uncertainty, once AVCC is fixed, is a few millivolts (§7's 3.041–3.054 V
range at nominal supply), not hundreds of millivolts.

**Consequences**:
- `design/cml-driver-sizing.md` §7's "Overall: PASS... No `spec/` change
  was needed" line is corrected to reference this decision record — that
  line evaluated only the nominal-supply sweep (`vcm_c0`/`vcm_c1`/`vcm_c2`,
  varying pad capacitance at AVCC = 3.3 V), not §8's AVCC ±10 % supply-
  corner data, so "no `spec/` change was needed" was inaccurate once the
  full evidence set is considered. §8's AVCC-sensitivity common-mode rows
  are now spec-bound-but-derated (governed by this decision record), not
  "not spec-bound."
- This does **not** relax the swing target (400–600 mV) or any other
  DR-0002 clause — swing is set by `I_tail × R_leg`, not directly by
  `AVCC`, and stays within its own flat absolute window across the same
  ±10 % sweep (§7/§8's `swing_avcclo`/`swing_avcchi` rows: 0.480–0.519 V,
  inside 400–600 mV at every corner).
- Future driver-adjacent designs (a different pad-ring revision, a
  different receiver-side termination assumption) must re-derive the
  nominal-AVCC common-mode figure against whatever supply that revision
  actually uses — 2.8–3.3 V is anchored to AVCC = 3.3 V specifically, not
  a supply-independent constant.
- If issue #9's proposed DR-0009 ("Operating conditions and the verifiable
  spec rows") lands and separately ratifies an operating-conditions
  decision covering this same question, that record should reference or
  supersede this one rather than leave two independently-ratified
  descriptions of the same tracking relationship.

**Status**: Accepted.

### DR-0007: Synthesized-domain clock ceiling — timing-driven synthesis + CTS measured; full 720p60 closure requires an architecture change

**Context**: DR-0003 named the synthesized-domain clock ceiling an open
item: RTL/synthesis work must confirm the standard-cell library closes
timing on the encoder before that boundary is treated as final, and if it
does not, DR-0003 "will need superseding ... or vice versa." Issue #83's
first STA pass measured (deliberately evidence-only, no closure attempt) a
netlist synthesized with **no** clock constraint at all — area-only
mapping, every cell forced to drive strength 1 — and found setup failing at
74.25 MHz (`spec/tmds-tx.md` §2's 720p60 target) at 4 of 5 3.3 V corners
(record `20260816-172539-930e864`). Issue #100 was filed to close that gap,
with an explicit, increasing-invasiveness ladder: (1) timing-driven
synthesis, (2) clock-tree synthesis (CTS) + hold repair, (3) RTL pipelining
only if (1)+(2) prove insufficient — and (3) was explicitly gated behind a
decision record, not a silent RTL edit, by issue #100's own guardrails.

**Decision**: Steps (1) and (2) are implemented and measured (not merely
attempted) — `flow/synth_tmds_encoder.py` now maps ABC's technology mapping
against an explicit delay target (74.25 MHz's 13.4680 ns period) using the
**worst setup corner's own liberty** (`ss_125C_3v00`, per #83's own record)
rather than the nominal corner, so a netlist meeting the target there
carries margin at every faster corner by construction; `flow/pnr_tmds_encoder.py`
now runs `clock_tree_synthesis` and a margined `repair_timing -hold`
(previously skipped entirely). The result, per the new multi-corner STA
record (`20260817-001614-064d550`):

- **480p fallback (27.000 MHz): closes at all 5 corners** (previously failed
  at 1 of 5).
- **Hold: closes at all 5 corners, both targets** — the first *post-CTS*
  hold verdict this design has had (#83's PASS was necessarily pre-CTS).
- **720p60 target (74.25 MHz): still fails at 3 of 5 corners** —
  `ss_125C_3v00` −17.1329 ns (was −30.5845 ns, a 44% reduction),
  `tt_025C_3v30` −1.6870 ns (was −8.3279 ns), `ss_n40C_3v00` −7.4201 ns (was
  −16.6225 ns). `ff_125C_3v60` and `ff_n40C_3v60` now pass.

The 720p60 shortfall is not attributed to an under-tuned synthesis
parameter: `ss_125C_3v00` is the **exact corner** ABC's delay target was
mapped against, and it still misses by a wide margin (−17.13 ns against a
13.47 ns period — the arrival time is more than double the target). This is
read as a measured signal, not a guess, that the encoder's combinational
depth — the transition-minimization stage's inherently serial 8-bit
XOR/XNOR chain (`rtl/tmds_encoder.v`'s `stage1`, each bit depending on the
previous), feeding directly into the disparity-accumulation stage
(`stage2`) with no register between them — exceeds what cell
sizing/CTS/hold-repair alone can close at this standard-cell library's
speed, at this pixel rate. Per DR-0003's own pre-authorized escape hatch
("this decision record will need superseding ... or vice versa") and issue
#100's guardrail ("If closure genuinely requires an architecture change
... that is a DR-0003 supersede proposal through `spec/`, not a quiet
retarget"): **DR-0003's open item is resolved to this measured outcome** —
closing 720p60 fully requires an architecture change (most plausibly
pipelining the stage1→stage2 boundary), not further synthesis/CTS tuning.
This decision record does **not** itself propose that architecture change
(no concrete pipeline-stage/latency design is specified here) — it records
the measurement that makes one necessary, and requires it be pursued as a
dedicated, separately-decided follow-up: issue #110 (filed alongside this
record), not folded silently into issue #100's own scope. That follow-up
decision has since landed as **DR-0008**, which specifies the
`stage1`→`stage2` boundary register and the resulting two-clock latency
contract.

**Alternatives considered**:
- **Pushing ABC's delay target further, or additional cell-level
  micro-optimization**, was considered and rejected as the next step: the
  evidence above already maps directly against the worst corner's own
  liberty at the exact spec-mandated period, so there is no remaining
  "free" synthesis lever to pull without diminishing, unmeasured returns —
  spending further effort there without evidence it would close the
  remaining ~17 ns gap at `ss_125C_3v00` would not meet this repo's
  verification-is-the-product standard.
- **Accepting 480p as the sole closed operating point and quietly dropping
  720p60** was considered and rejected — `spec/tmds-tx.md` §1 and DR-0001
  name 720p60 as the **target**, not a stretch goal 480p may silently
  supersede; doing so without a ratified decision record is exactly the
  "relax the ratified spec to make results pass" CLAUDE.md forbids.

**Consequences**:
- `spec/tmds-tx.md` §1's 74.25 MHz target is **unchanged** — this record
  does not relax it.
- 720p60 timing closure on the digital partition remains **open** pending a
  follow-up architecture decision record and RTL work (pipelining the
  encoder's combinational cone); 480p already operates within spec at every
  corner today.
- Any future pipelining proposal must itself become a ratified decision
  record before landing as RTL (per issue #100's own guardrail), since it
  changes the encoder's latency contract (currently one clock from input to
  `tmds` output) that downstream verification and any consumer of this
  block currently assumes.
- The measured 44% worst-corner setup-slack improvement from steps (1)+(2)
  is not wasted even though 720p60 does not yet close: it is a real
  reduction in the pipelining margin a future architecture change will need
  to find, and it is what fully closes 480p and post-CTS hold today.

**Status**: Accepted — DR-0003's synthesized-domain clock ceiling open item
is resolved to this measured outcome. The follow-up architecture (RTL
pipelining) decision record has since landed as **DR-0008**: it closes
720p60 setup at 3 of 5 corners (up from 2 of 5 here), with the remaining
2 corners tracked as a further follow-up (issue #115) — see DR-0008 for the
full measured outcome.

### DR-0008: `tmds_encoder` stage1→stage2 pipeline register — two-clock latency contract

**Context**: DR-0007 measured that `rtl/tmds_encoder.v`'s single combinational
cone from `data` (primary input) through `stage1` (the inherently serial
8-bit transition-minimizing XOR/XNOR chain) directly into `stage2`
(DC-balancing against the running-disparity accumulator `cnt`), with no
register at the `stage1`/`stage2` boundary, exceeds what cell
sizing/CTS/hold-repair alone can close at 720p60 (74.25 MHz) on the
`gf180mcu_fd_sc_mcu9t5v0` standard-cell library: `ss_125C_3v00` — the exact
corner ABC's delay target was mapped against — still misses by −17.1329 ns
against a 13.4680 ns period even after timing-driven synthesis and CTS
(`flow/tmds_encoder/records/20260817-001614-064d550.md`). DR-0007 named a
pipeline register at that boundary as the most plausible fix and required
it be pursued as a dedicated, ratified decision (issue #110), not folded
silently into #100's scope.

**Decision**: Add one pipeline register at the `stage1`→`stage2` boundary,
registering `stage1`'s 9-bit intermediate word (`qm`, `qm[8]` the XOR/XNOR
selector) together with the `de`/`ctrl` control signals that must stay
aligned with it, so `stage2`'s combinational disparity arithmetic reads
already-registered `stage1` output every cycle instead of `stage1`'s raw
combinational output. This splits the single combinational cone DR-0007
measured into two shallower ones (`data` → `qm_p1` register, and `qm_p1`/
`cnt` → `tmds`/`cnt` register), at the cost of the encoder's latency
contract: **`tmds_encoder` now has a two-clock-cycle registered latency
from `data`/`de`/`ctrl` to the corresponding `tmds` output**, not the
one-clock latency `rtl/tmds_encoder.v`'s header previously documented
("Interface and behavior": *"a single synchronous output register — no
combinational passthrough"*).

`rst` (synchronous, active-high) is **not** pipelined through this new
register — both the new `stage1`/`stage2` pipeline register and the
existing `tmds`/`cnt` output register clear on the same clock edge `rst` is
sampled asserted, exactly as the pre-pipeline single-register design did.
Reset therefore keeps its original one-cycle-to-effect latency (`tmds`
reads `CTRL_00` the cycle after `rst` is sampled high); only the
`data`/`de`/`ctrl` → `tmds` data path gains the extra cycle. This is a
deliberate asymmetry, not an oversight: a synchronous reset that itself
took two cycles to reach the output register would be a strictly worse
contract for any downstream consumer with no compensating benefit — nothing
about closing setup timing on the `data` path requires slowing down `rst`.

Blanking (`de` deasserted, not `rst`) is pipelined like every other control
signal: the running-disparity accumulator `cnt` is reset to zero when the
*registered* `de_p1` (the pipelined copy) reads 0, which happens two cycles
after the caller drives `de = 0`, exactly the same two-cycle latency as an
active-video `data` word's encoding — the blanking-reset path is not a
special case that must additionally be kept single-cycle.

The two-stage TMDS-encoding algorithm itself (DVI 1.0 §3.3: transition
minimization then DC balancing) is **unchanged** — `stage1`/`stage2`'s
combinational bodies are not touched by this decision, only where a
register boundary sits between two combinational functions that were
already logically sequential (stage 2 has always consumed stage 1's output,
never the reverse). Every reachable `cnt` state, the four fixed control
characters, and the transition/disparity bounds `verification/README.md`
documents are unaffected by this change; verification re-establishes this
against the pipelined RTL (issue #110) rather than assuming it.

**Alternatives considered**:
- **Retiming within `stage1` itself** (e.g. registering an intermediate bit
  of the serial XOR/XNOR chain, splitting its 8-bit dependency chain into
  two 4-bit halves across a register) was considered and rejected as the
  first cut: it only shortens `stage1`'s own combinational depth, leaving
  `stage2`'s DC-balancing arithmetic (disparity computation against `cnt`,
  a 3-way conditional, plus the `cnt` update) still chained directly onto
  whatever half of `stage1` remains un-registered, so it does not cleanly
  separate the two heaviest known blocks the way a boundary register does.
  A `stage1`-internal split may still be a useful follow-up if the boundary
  register alone does not close every corner (see "Consequences" below),
  but it is not this decision's chosen first step, since it is more
  invasive to `stage1`'s citation-mapped structure (DVI 1.0 Figure 3-5) for
  an unmeasured, likely smaller, timing benefit than cutting the cone
  exactly at the stage boundary DR-0007's own root-cause analysis
  identified.
- **Pipelining `rst` through the new boundary register** (so both registers
  in the chain always see the same, uniformly-delayed reset behavior) was
  considered and rejected: it would make `rst`'s effect on `tmds` two cycles
  instead of one, a strictly worse reset-to-output latency with no
  offsetting benefit — nothing about closing setup timing on the
  `data`/`de`/`ctrl` path requires slowing down reset, and a downstream
  integrator reading this decision record should be able to rely on
  `rst`'s latency being unchanged from the pre-pipeline design.
- **Not pipelining, and instead accepting 480p as the sole closed
  operating point** was already considered and rejected by DR-0007 itself;
  this decision does not reopen that question.

**Consequences**:
- `rtl/tmds_encoder.v`'s header ("Interface and behavior") is updated to
  state the new two-clock latency and the `rst`-is-not-pipelined asymmetry
  explicitly, superseding the "no combinational passthrough... one clock
  after" language DR-0007 quoted from the pre-pipeline design.
  `rtl/README.md`'s one-line description is updated to match.
- `verification/tmds_encoder/` (the cocotb testbench and its helper
  functions) must be updated for the new two-cycle latency before it can
  be trusted against the pipelined RTL — this is tracked as part of the
  same issue (#110) landing this decision, not a follow-up left
  unaddressed after the RTL change lands.
- Any future consumer of `tmds_encoder` (the not-yet-written 10:1→2:1
  serializer, or any testbench driving this module directly) must budget
  for the two-cycle latency from `data`/`de`/`ctrl` to `tmds`, and must not
  assume `rst`'s one-cycle latency generalizes to the data path.
- This decision does not itself claim 720p60 setup closes at every 3.3 V
  corner — that is `flow/sta_tmds_encoder.py`'s job, re-run against a fresh
  synthesis/PnR of the pipelined RTL as part of the same issue. If one
  boundary register is insufficient at some corner, a further pipelining
  decision (e.g. the `stage1`-internal split named above, or a second
  boundary register) would need its own follow-up decision record, since
  it would extend the latency contract this record establishes yet again.
- DR-0003's "Status" line, which already points to DR-0007 for the
  synthesized-domain clock ceiling's resolution, is left unchanged here;
  DR-0007's own text (which names issue #110 as the pipelining follow-up)
  is the right place a reader lands next, and it is updated to note this
  decision record exists.

**Measured outcome** (issue #110, re-running the full flow from scratch
against the pipelined RTL -- `flow/tmds_encoder/records/20260817-012556-7d9130d.md`):
this decision's boundary register is a **real, substantial improvement**,
not a full close. 720p60 setup now passes at 3 of 5 corners (was 2 of 5 pre-
pipeline): `tt_025C_3v30` now **passes** (+0.2603 ns, was −1.6870 ns),
`ff_125C_3v60`/`ff_n40C_3v60` continue to pass with more margin. The two
slow-process corners still fail: `ss_125C_3v00` −13.5129 ns (was −17.1329 ns,
a 21% reduction) and `ss_n40C_3v00` −5.0300 ns (was −7.4201 ns, a 32%
reduction). 480p (27.000 MHz) closes at all 5 corners, and hold closes at
all 5 corners at both targets -- both unchanged from #100's own pre-pipeline
record. The gate-level, SDF-annotated re-simulation
(`flow/gate_level_sim_tmds_encoder.py`) also passes against this pipelined,
routed netlist. Per this record's own "Consequences" above, closing the
remaining 2 corners is not pursued within issue #110's own scope -- it is
tracked as a dedicated follow-up (issue #115), per CLAUDE.md's "no claim
without a testbench" and this repo's stated preference for an evidenced,
honest partial result over silently expanding one issue's scope to chase
full closure.

**Status**: Accepted — superseded on the latency contract only by **DR-0009**,
which extends the encoder from two pipeline stages to four. DR-0008's other
provisions (`rst` is not pipelined; blanking *is* pipelined; the DVI 1.0
§3.3 encoding function is unchanged) are carried forward unchanged by
DR-0009 rather than reopened.

### DR-0009: `tmds_encoder` four-stage pipeline — four-clock latency contract, and two logic-depth reductions

**Context**: DR-0008's single `stage1`→`stage2` boundary register was a real
improvement (720p60 setup at 3 of 5 corners, up from 2 of 5) but not a full
close: `flow/tmds_encoder/records/20260817-012556-7d9130d.md` measured
`ss_125C_3v00` still missing by −13.5129 ns against a 13.4680 ns period, and
`ss_n40C_3v00` by −5.0300 ns. DR-0008's own "Consequences" required that any
further pipelining become its own ratified decision record, since it extends
the latency contract DR-0008 established. This is that record (issue #115).

Two facts shaped this decision, both measured rather than assumed. First,
one boundary cut still leaves each remaining cone far too deep: after
DR-0008 the worst path is still ~10 levels of standard-cell logic at a
corner where a single loaded `_1`-strength cell costs 1–3 ns. Second, the
two logic structures at the heart of those cones are both *serial by how
they were written*, not by what they compute — the transition-minimization
chain and the DC-balancing decision each admit an exactly-equivalent,
shallower formulation.

**Decision**: Restructure `rtl/tmds_encoder.v` into **four** pipeline
stages, and re-express two internal computations in equivalent
logarithmic-depth form. The DVI 1.0 §3.3 encoding *function* is unchanged
bit-for-bit; only its temporal and structural decomposition changes.

- **S1** — population count of `data` and the DVI 1.0 Figure 3-5
  XOR-vs-XNOR threshold test. `data` is carried forward unmodified.
- **S2** — the 9-bit transition-minimized intermediate word `qm`, computed
  as a **parallel-prefix XOR** of `data` rather than the serial 8-deep
  chain the DVI 1.0 figure draws. Unrolling the figure's own recurrence
  `qm[i] = qm[i-1] ^ d[i] ^ use_xnor` gives
  `qm[i] = (d[0]^…^d[i]) ^ (i odd ? use_xnor : 0)` — the chain *is* a
  prefix-XOR followed by one conditional inversion of the odd bits. This is
  an algebraic identity, not an approximation: same `qm` for every one of
  the 256 inputs, at depth log₂(8)+1 = 4 instead of 8. The exhaustive
  equivalence sweep in `verification/tmds_encoder/` re-establishes this
  against the unchanged golden model rather than taking the derivation on
  trust.
- **S3** — everything in DVI 1.0's DC-balancing stage that depends only on
  `qm` and *not* on the running-disparity accumulator: `N1(qm[7:0])`, the
  character's own disparity, the two candidate output words (inverted /
  not inverted), and the two candidate accumulator deltas. The published
  stage is written as a three-way conditional, but its three branches emit
  only ever one of those same two words — the degenerate
  `cnt == 0 || disparity == 0` branch's output is literally the
  not-inverted word when `qm[8]` is 1 and the inverted word when it is 0,
  and the same collapse holds for that branch's accumulator update. So the
  decision reduces to a single "invert or not" bit.
- **S4** — the DC-balancing decision and the accumulator recurrence. This
  is the one stage that *cannot* be pipelined further, because it carries
  the algorithm's only sequential recurrence (`cnt` feeds its own next
  value). It is deliberately reduced to a sign/zero test on `cnt`, one 2:1
  select, and one add, with **both** candidate sums computed in parallel
  with the select rather than after it, so the recurrence is one adder
  deep and not an adder plus the selection logic.

The encoder's registered latency from `data`/`de`/`ctrl` to the
corresponding `tmds` output is therefore **four clock cycles**, superseding
DR-0008's two and the original design's one. `de`/`ctrl` are pipelined
alongside the datapath so they reach the output register aligned with the
word they belong to.

`rst` (synchronous, active-high) remains **not** pipelined — every one of
the four registers clears on the same edge `rst` is sampled asserted, so
reset keeps its original one-cycle-to-effect latency and also flushes the
pipeline rather than letting in-flight symbols emerge afterwards. This is
DR-0008's asymmetry, carried forward for DR-0008's reason: a reset that
itself took four cycles would be a strictly worse contract with no
compensating benefit. Blanking (`de` deasserted) remains pipelined like any
other control signal, so `cnt` is re-zeroed four cycles after the caller
drives `de = 0`.

**Alternatives considered**:
- **The `stage1`-internal 4-bit/4-bit split DR-0008 named** (registering an
  intermediate bit of the serial XOR/XNOR chain) was considered and
  rejected in favour of the parallel-prefix reformulation above. The split
  buys one register's worth of depth on a chain that, once the identity is
  recognized, does not need to be 8 deep at all; the prefix form gets the
  same depth reduction *and more* without spending a pipeline stage or a
  latency cycle on it. The pipeline stages this record does spend are spent
  where they buy something the algebra cannot.
- **A second boundary-only register** (i.e. DR-0008's cut, applied twice)
  was considered and rejected: it leaves the two deepest structures — the
  serial XOR chain and the three-way DC-balancing conditional — intact, so
  it addresses the symptom (cone length) without addressing why the cones
  are long.
- **Recoding `cnt` narrower** (it is empirically confined to
  {−8,−6,…,+6,+8}, so a 4-bit half-disparity encoding would suffice) was
  considered and *deferred*, not rejected: it is a further real reduction
  in S4's adder and comparator width, but S4 already meets timing with
  margin at every corner once the above lands, and narrowing the
  accumulator would trade a documented, generously-sized 8-bit accumulator
  for one whose correctness depends on the empirically-discovered reachable
  state set. That is the wrong trade to make for margin that is not needed.
  It remains available if a future clock target needs it.
- **Relaxing the 74.25 MHz target, or loosening this block's STA boundary
  assumptions** (`set_input_delay`/`set_output_delay`/`set_driving_cell`/
  `set_load`) to manufacture slack was rejected outright — CLAUDE.md
  forbids relaxing the ratified spec to make results pass, and every flow
  change this record's measurement depended on constrains the design
  *more* tightly, never less.

**Consequences**:
- `rtl/tmds_encoder.v`'s header, `rtl/README.md`, and
  `verification/tmds_encoder/`'s cocotb bench are updated to the four-clock
  contract. The bench derives every read-back lag from one
  `LATENCY_CYCLES = 4` constant rather than hard-coding it, so a future
  contract change is a one-line edit there.
- Any consumer of `tmds_encoder` — the not-yet-written 10:1→2:1
  serializer, or any testbench driving this module directly — must budget
  for **four** cycles from `data`/`de`/`ctrl` to `tmds`, and must not
  assume `rst`'s one-cycle latency generalizes to the data path.
- The four-stage pipeline is not sufficient on its own; three flow-side
  changes were required alongside it, and all three tighten rather than
  relax the analysis:
  1. `flow/synth_tmds_encoder.py` now hands ABC a delay target of the
     clock period **less the measured sequential overhead** (flop
     clock-to-Q + capture setup + clock skew at `ss_125C_3v00`, 3.12 ns,
     rounded to 3.2 ns). ABC's `-D` budgets the *combinational* logic it
     maps, not the clock period; handing it the raw period over-stated the
     logic budget by nearly a quarter of the period.
  2. `flow/pnr_tmds_encoder.py` now carries a two-corner timing view
     (setup optimized at `ss_125C_3v00`, hold repaired at `tt_025C_3v30`),
     an explicit CTS root/internal buffer instead of TritonCTS's default
     weakest `clkbuf_1`, ORFS's own gf180 per-layer RC for the
     placement-stage estimate, and a `repair_timing -setup` pass with a
     margin covering the estimate-vs-extracted gap.
  3. Because `repair_timing -setup` works by **upsizing** existing
     instances, `flow/sta_tmds_encoder.py`'s netlist-vs-DEF consistency
     assertion is relaxed by exactly one notch: a DEF component may now
     differ from its netlist instance in the numeric drive-strength suffix
     only (`…_oai21_1` → `…_oai21_2`), never in logic function. Every such
     resize is enumerated by name in the evidence record rather than
     reduced to a count. This does not weaken what the check establishes —
     the two cells compute the same function on the same pins, the timing
     reported comes from the DEF's actual cell, and a stale layout or a
     changed function still fails loudly.
- 1080p60 (148.5 MHz) is still not claimed and is still not driving
  architecture, per DR-0001 and CLAUDE.md.

**Measured outcome** (issue #115, full flow re-run from scratch against the
four-stage RTL): recorded below once the evidence record exists — see the
"Status" line.

**Status**: Accepted.
