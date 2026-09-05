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
- `tmds_final_mux.sch` / `tmds_final_mux.sym` — the DR-0003 custom final 2:1
  (DDR) multiplexer, one lane (issue #159): a resistively-loaded,
  self-biased CML 2:1 selector, clock-steered by DR-0012 Decision 1's
  internally-derived half-rate clock, driving the CML driver's `INP`/`INN`
  gates directly. Every active device is `nfet_03v3`, every resistor
  `ppolyf_u`, per DR-0002/DR-0003. `netlist/tmds_final_mux.spice` is the
  xschem-generated netlist. Sizing derivation:
  `tmds-final-mux-sizing.md`. PVT-swept verification:
  `sim/tmds-final-mux-eye/` (this cell's own output) and
  `sim/cml-driver-eye-realmux/` (the driver's own rows, re-measured with
  this cell's real output substituted for the ideal source
  `cml-driver-sizing.md` originally assumed).

The pad/ESD network is a follow-on cell (separate issue) — not yet designed
here. The 10:1→2:1 reduction stage (`rtl/tmds_serializer.v`) is a
synthesized-domain RTL module, not an xschem schematic — see DR-0014
(`spec/decisions/0014-serializer-rate-ceiling-and-microarchitecture.md`)
for why it is also the executable reference model this cell's `D0`/`D1`
custom-domain neighbour must reproduce at the 720p60 operating point.
