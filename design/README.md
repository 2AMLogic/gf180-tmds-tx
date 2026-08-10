# design

Schematics and their supporting xschem configuration land here. See the repo
README for scope.

- `xschemrc` — project-local xschem configuration. Resolves the gf180mcu PDK
  the same way `sim/harness/pdk.py` does and adds this repo's symbol/
  testbench directories to the xschem library path. `source sim/env.sh && cd
  design && xschem` (see `sim/harness/README.md`).
- `cml_driver.sch` / `cml_driver.sym` — one lane's DVI-mode TMDS CML output
  driver (issue #11): a DC-coupled, current-mode, open-drain NMOS
  differential pair with an in-cell 1:20 current-mirror tail, every device
  `nfet_03v3` per DR-0002. `netlist/cml_driver.spice` is the xschem-generated
  netlist. Sizing derivation: `cml-driver-sizing.md`. PVT-swept verification:
  `sim/cml-driver-eye/`.

The DR-0003 custom 2:1 final multiplexer and the pad/ESD network are
follow-on cells (separate issues) — not yet designed here.
