# gf180-tmds-tx

A TMDS transmitter on the [gf180mcu](https://github.com/google/gf180mcu-pdk)
open PDK — serializer plus current-mode line driver — designed by AI agents
driving [klayout-tools](https://github.com/2AMLogic/klayout-tools), xschem +
ngspice on the analog side and Yosys/OpenROAD on the digital side.

**Status: spec ratified, driver+pad-ring/ESD assembly signed off DRC/LVS-clean
and now electrically post-layout-verified for its first process corner, and
the serializer/final-mux stage joining the digital and analog partitions
designed and analog-verified at that same corner.**
The TMDS encoder RTL is
verified (`rtl/`, `verification/`), synthesized, placed-and-routed, and
timing-closed at 720p60 (`flow/`). The 10:1→2:1 serializer/reduction stage
(DR-0003, sized against timing by DR-0014) is written and verified against
the encoder's own real output (`rtl/tmds_serializer.v`,
`verification/tmds_serializer/`); DR-0014 found it cannot close timing in
the synthesized domain at 720p60 on this standard-cell library, so it moves
to the custom domain there and merges with the DR-0003 custom final 2:1
multiplexer, which is now captured as a schematic and sized
(`design/tmds_final_mux.sch`, `design/tmds-final-mux-sizing.md`) and
analog-verified — its own real output (`sim/tmds-final-mux-eye/`) and the
driver's own rows re-measured with it substituted for their prior
ideal-source assumption (`sim/cml-driver-eye-realmux/`) both PASS at the
nominal process corner across the full temperature/supply/rate matrix, with
the remaining process corners named as follow-up work
(`measurements/characterization.md`). The CML output driver's schematic is
captured, sized, and PVT-swept against the ratified spec's electrical
targets (`design/`, `sim/cml-driver-eye/`), and its core cell is laid out,
DRC-clean, and LVS-matched against that schematic
(`layout/gds/cml_driver_core.gds`); post-layout (extracted-netlist)
simulation of that core cell against the full PVT suite has landed. A
minimal custom pad cell — proving the DRC/LVS flow at the pad boundary, not
the final driver pad — is DRC-clean and LVS-matched, and its ESD-clamp
capacitance has been measured against the spec's budget (`layout/`,
`sim/esd-clamp-cv/`). The driver core cell has since been assembled with a
diode-clamped pad-ring/ESD structure per DR-0011, drawn at the production
25×25 µm pad geometry — the block-level
`layout/gds/gf180_tmds_pad_ring_assembly.gds` — which is DRC-clean and
LVS-matched, and its pad-capacitance budget (≤ 2 pF) **is met**: 0.094 pF
(`OUTP`) / 0.075 pF (`OUTN`), 95–96 % headroom (an earlier self-reported
~4× "over budget" figure was a units-label bug, corrected and re-measured
against the real drawn geometry, not a relaxed target). **The assembled
block now also has its first electrical/PVT simulation** — a full 5-corner
`mos` process-corner sweep (`tt`/`ff`/`ss`/`fs`/`sf`), each an 18-point full
temperature/supply/rate grid, 90/90 PASS, layout-extracted with real
interconnect parasitic R/C and the real diode-clamp ESD array in circuit
with the driver — closing the "no electrical/PVT simulation of its own
yet" gap across the full mandated corner-set (issues #154/#161). See
`measurements/characterization.md`
for the full, per-row accounting, and
[`docs/chipalooza/challenge-5-proposal.md`](docs/chipalooza/challenge-5-proposal.md)
for the brief-conformant proposal document.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using gf180mcu, not just this repo.

## Why this block, on this node

TMDS is the signaling underneath DVI and HDMI: three data lanes plus a clock,
DC-coupled, each lane terminated 50 Ω to a 3.3 V supply with the driver
sinking roughly 10 mA. That electrical definition dates from 1999 and was
written for the process nodes of that era, which makes gf180mcu's 3.3 V
devices a native fit rather than a retarget. 720p60 needs 742.5 Mbps per
lane — comfortable at 180 nm.

It is also the first block in this program to require a **pad ring**. Every
sibling canary is a core block, so the ESD structures, pad pitch, and the
core-to-pad seam are untested ground for the tools. That is a large part of
why this block exists.

## Scope

- **Target**: 720p60 (742.5 Mbps/lane). 480p is the guaranteed fallback.
- **Stretch, not promised**: 1080p60 (1.485 Gbps/lane).
- **In scope**: TMDS encoder, 10:1 serializer, current-mode driver, and the
  custom pad cell with its ESD structure.
- **Not in scope**: the PLL. It comes from a sibling canary; specify the
  interface to it, including the jitter budget, and stop.

The gf180mcu I/O library ships a general-purpose 5 V wide-range GPIO library
and no high-speed cell, so the driver and its ESD protection are custom
pad-ring work. Treat that as the block's central risk, not a detail.

## Target specification

The ratified spec — parameter table, numeric PLL interface (reference
frequency, output frequencies, jitter budget), and pad-cell/ESD decision
record — lives in [`spec/tmds-tx.md`](spec/tmds-tx.md). See
[`spec/README.md`](spec/README.md) for the decision-record convention. This
README does not keep its own copy of the numbers, to avoid a driftable
second source of truth.

Maturity ladder: spec ratified → encoder verified → driver simulated across
PVT → pad cell DRC-clean → assembled and LVS-clean → assembly PVT-verified
→ shuttle seat → measured silicon. **Current position: spec ratified,
encoder verified/synthesized/placed-and-routed/timing-closed, the CML
driver schematic and its core-cell layout both simulated across the full
PVT matrix, and the driver+pad-ring/ESD assembly
(`gf180_tmds_pad_ring_assembly`) DRC-clean, LVS-matched, and now
electrically PVT-verified post-layout — with real interconnect parasitics
and the real ESD clamp array in circuit — across the full mandated 5-corner
`mos` process-corner set (18 temperature/supply/rate points per corner,
90/90 PASS), reaching the "assembly PVT-verified" rung across the full
matrix. The pad-capacitance budget (≤ 2 pF) is met with 95–96 % headroom.
The 10:1→2:1 serializer/final-mux stage joining the digital and analog
partitions is now designed too — RTL verified against the encoder's own
output, and the custom final 2:1 multiplexer captured, sized, and
analog-verified across the full 5-corner (`tt`/`ff`/`ss`/`fs`/`sf`)
process grid and the full temperature/supply/rate matrix (DR-0014, issue
#163). What remains open: that same PVT sweep discloses genuine, narrow
`vswing_m`/`vswing_s` margin shortfalls at the `ss` and `sf` process
corners' low-supply extremes (issues #169, #171) — not observable at the
driver's own output, but an open design-margin question for the mux cell
itself; the custom final-mux cell has no layout and therefore no
post-layout run of its own yet; ESD HBM/CDM qualification is not simulated
(no PDK source
characterizes the needed device parameters pre-silicon — see
`measurements/characterization.md`), and no post-layout eye-mask run exists
yet against the extracted assembly (issue #160).
The "shuttle seat" rung and later remain open for the actual block; see
[`docs/chipalooza/challenge-5-proposal.md`](docs/chipalooza/challenge-5-proposal.md)
for the current brief-conformant proposal.**

## Chipalooza

This block is proposed against Open Circuit Design's
[Chipalooza](https://opencircuitdesign.com/chipalooza/) Challenge #5
(GF180MCU / Wafer.Space): see
[`docs/chipalooza/challenge-5-proposal.md`](docs/chipalooza/challenge-5-proposal.md)
for the brief-conformant proposal document — I/O mapped to the slot budget,
functional description, spec table re-derived from `sim/` at the brief's
rails, and bench test plan.

## Repo layout

```
spec/          ratified spec + decision records
rtl/           encoder and serializer sources
verification/  cocotb testbenches
flow/          synthesis and place-and-route recipes (Yosys, OpenROAD), via klt
design/        analog schematics (driver, CML stages)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports, including the pad cell
measurements/  silicon characterization (empty until tape-out)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
