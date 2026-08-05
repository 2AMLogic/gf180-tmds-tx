# gf180-tmds-tx

A TMDS transmitter on the [gf180mcu](https://github.com/google/gf180mcu-pdk)
open PDK — serializer plus current-mode line driver — designed by AI agents
driving [klayout-tools](https://github.com/2AMLogic/klayout-tools), xschem +
ngspice on the analog side and Yosys/OpenROAD on the digital side.

**Status: just opened, specification phase.** Nothing is designed yet.

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

## Target specification (DRAFT — engineering to ratify, see issue #1)

| Parameter | Target | Stretch |
|---|---|---|
| Lanes | 3 data + 1 clock | — |
| Rate per lane | 742.5 Mbps (720p60) | 1.485 Gbps (1080p60) |
| Electrical | DC-coupled, 50 Ω to 3.3 V, ~10 mA sink | — |
| Serialization | 10:1, custom CML final stages | — |
| Signoff | DRC + LVS clean, pad ring included | — |

Maturity ladder: spec ratified → encoder verified → driver simulated across
PVT → pad cell DRC-clean → assembled and LVS-clean → shuttle seat → measured
silicon. **Current position: pre-spec.**

## Repo layout

```
spec/          ratified spec + decision records
rtl/           encoder and serializer sources
verification/  cocotb testbenches
design/        analog schematics (driver, CML stages)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports, including the pad cell
measurements/  silicon characterization (empty until tape-out)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
