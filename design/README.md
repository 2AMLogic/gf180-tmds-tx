# design

Schematics and their supporting xschem configuration land here. See the repo
README for scope.

- `xschemrc` — project-local xschem configuration. Resolves the gf180mcu PDK
  the same way `sim/harness/pdk.py` does and adds this repo's symbol/
  testbench directories to the xschem library path. `source sim/env.sh && cd
  design && xschem` (see `sim/harness/README.md`).

No schematics have landed yet — that is the actual design work of #9/#11,
not this issue (#8), which only bootstraps the sim harness and PDK
environment.
