# gf180-tmds-tx

A TMDS transmitter on the [gf180mcu](https://github.com/google/gf180mcu-pdk)
open PDK — serializer plus current-mode line driver — designed by AI agents
driving [klayout-tools](https://github.com/2AMLogic/klayout-tools), xschem +
ngspice on the analog side and Yosys/OpenROAD on the digital side.

**Status: spec ratified, driver core cell assembled with its pad-ring/ESD
structure and signed off.** The TMDS encoder RTL is verified (`rtl/`,
`verification/`). The CML output driver's schematic is captured, sized, and
PVT-swept against the ratified spec's electrical targets (`design/`,
`sim/cml-driver-eye/`), and its core cell is laid out, DRC-clean, and
LVS-matched against that schematic (`layout/gds/cml_driver_core.gds`);
post-layout (extracted-netlist) simulation of that core cell against the
full PVT suite has landed. A minimal custom pad cell — proving the DRC/LVS
flow at the pad boundary, not the final driver pad — is DRC-clean and
LVS-matched, and its ESD-clamp capacitance has been measured against the
spec's budget (`layout/`, `sim/esd-clamp-cv/`). The driver core cell has
since been assembled with a diode-clamped pad-ring/ESD structure per
DR-0011 — the block-level `layout/gds/gf180_tmds_pad_ring_assembly.gds` —
which is itself DRC-clean and LVS-matched, though that assembled block has
no electrical/PVT simulation of its own yet (only structural DRC/LVS
signoff), and the pad-capacitance budget (≤ 2 pF) still FAILs at ~4× over
against a realistic 25×25 µm bond pad. See
`measurements/characterization.md` for the full, per-row accounting.

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
PVT → pad cell DRC-clean → assembled and LVS-clean → shuttle seat → measured
silicon. **Current position: spec ratified, encoder verified, and the CML
driver schematic and its layout both simulated across the full PVT matrix —
the pad-ring flow has separately been proven DRC-clean/LVS-matched on a
minimal proof-of-flow cell, and the driver core cell itself is laid out,
DRC-clean, and LVS-matched. The driver core cell is now assembled with the
pad cell/ESD structure, and that assembly (`gf180_tmds_pad_ring_assembly`)
is itself DRC-clean and LVS-matched — reaching the "assembled and
LVS-clean" rung. What remains open: the assembled block has no
electrical/PVT simulation of its own yet, the pad-capacitance budget still
FAILs against a realistic bond pad, and ESD HBM/CDM qualification is not
yet simulated (see `measurements/characterization.md`); the "shuttle seat"
rung and later remain open for the actual block.**

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
