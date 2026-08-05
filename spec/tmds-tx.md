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
| Bit-rate clock output (720p60 target) | 742.5 MHz (= 27.000 MHz × 11/4) |
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
supply rail). The driver's output devices are gf180mcu's **3.3 V core
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

**Status**: Accepted, with the synthesized-domain frequency ceiling flagged
as unverified pending RTL/synthesis work.

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
