# layout

GDS, generator scripts, and DRC/LVS signoff reports.

## `gf180_tmds_pad_min` — minimal custom pad cell (issue #2)

The program's first custom-drawn pad cell: a Metal5 bond pad wired down a
Metal1-Metal5 via stack to the drain of a grounded-gate NMOS (GGNMOS) ESD
clamp, gate and source tied to a separate VSS net. Not the final TMDS driver
pad — a deliberately minimal structure built to prove the `klt drc`/`klt
extract`/`klt lvs` flow actually works at the pad boundary before the real
driver exists. See `spec/pad-ring-esd-survey.md` for the full PDK survey,
the design rationale (including why this is an NMOS clamp rather than the
diode `gf180mcu_fd_io` itself uses), and the tool gaps this work surfaced.

```
scripts/gen_pad_min.py         generator (klayout.db, no PDK-PCell dependency)
gds/gf180_tmds_pad_min.gds             the pad cell
gds/gf180_tmds_pad_min_shorted.gds     LVS negative control (PAD shorted to VSS)
gds/gf180_tmds_pad_min.spice           klt extract's schematic-equivalent netlist
drc_reports/                   klt drc reports (text + json), both cells
lvs_reports/                   klt lvs reports (text + json), both cells
lvs/gf180_tmds_pad_min.ref.spice        hand-written reference netlist for LVS
lvs/lvs_request*.json          klt lvs request documents
```

Regenerate and re-run signoff:

```bash
cd layout
python3 scripts/gen_pad_min.py -o gds/gf180_tmds_pad_min.gds
python3 scripts/gen_pad_min.py -o gds/gf180_tmds_pad_min_shorted.gds --shorted
klt drc --deck gf180mcu gds/gf180_tmds_pad_min.gds
klt extract --deck gf180mcu gds/gf180_tmds_pad_min.gds -o gds/gf180_tmds_pad_min.spice
klt lvs lvs/lvs_request.json
klt lvs lvs/lvs_request_shorted.json   # expect status: mismatch (negative control)
```

Current signoff status: **DRC-clean** and **LVS-clean** (`status: match`)
against every rule/device class `klt`'s gf180mcu deck currently implements
— which, per the spec doc, is a real but curated subset (no ESD-implant
rules, no diode device recognition yet). Two tool gaps discovered along the
way are filed against klayout-tools:
[#539](https://github.com/2AMLogic/klayout-tools/issues/539) (device-less
circuits are dropped entirely by `klt extract`/`klt lvs`) and
[#541](https://github.com/2AMLogic/klayout-tools/issues/541) (no diode
device class, which is why this cell uses an NMOS clamp instead).
