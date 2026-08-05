# gf180-tmds-tx — agent instructions

Open-source canary block: a TMDS transmitter on the gf180mcu PDK, designed
and verified by AI agents. **Mixed-signal** — a synthesized encoder and
serializer plus a custom CML driver — so both flows apply.

- **PDK**: gf180mcu (open PDK). Analog: xschem + ngspice. Digital: cocotb +
  Icarus, Yosys, OpenROAD. Layout, DRC, and LVS through klayout-tools
  (`klt`) in both cases.
- **The pad ring is the point, and the risk.** This is the program's first
  block requiring custom pad-ring work — the gf180mcu I/O library ships a
  general-purpose 5 V GPIO library and no high-speed cell, so the driver and
  its ESD structure must be drawn and must satisfy pad-pitch and ESD rules.
  Nothing in the fleet has done this. Expect the tools to be weakest here and
  file accordingly.
- **Scope discipline.** The PLL comes from a sibling canary. Do not design one
  here. Specify the interface to it — including the jitter budget this block
  requires — and stop.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and describe
  the gap, not the design.
- **Verification is the product**: no claim without a testbench. PVT corners
  on every recorded analog result; recorded results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not relax
  the ratified spec to make results pass.
- **720p60 is the target.** 480p is the fallback and 1080p60 is a stretch. Do
  not let 1080p requirements drive architecture before 720p closes.

## On HDMI, and what may be said

TMDS signaling itself is unencumbered — the DVI protocol underneath HDMI is
free, and the HDMI Adopter Agreement covers the connector and the trademark,
not the signaling. This block is therefore a **DVI-mode TMDS transmitter**.
Do not describe it as an HDMI block, do not use the HDMI trademark or logo in
this repo, and do not imply any HDMI certification or compliance.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
