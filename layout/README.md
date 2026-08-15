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

## `cml_driver_core` — CML output driver core cell (issue #22)

The differential switch pair (M1/M2) + tail current source (MT) + 1:20
bias-mirror reference device (MB) from the sized schematic
(`design/cml_driver.sch` / `design/netlist/cml_driver.spice`, issue #11),
laid out via `klt gen`'s `mos_array` generator (one folded multi-finger NMOS
per schematic device — `gate_contact=True` on a single-unit (`rows=1,
cols=1`) call for a real strapped source-rail/drain-rail/gate-comb device,
not the bare uncontactable stripes the generator's pre-strapping default
draws) composed
into one circuit with `klt gen-compose`. Unlike `gf180_tmds_pad_min` (which
predates `klt gen`'s generator family and draws every shape by hand), this
is the first cell in this repo built through that generator machinery — see
`scripts/gen_cml_driver_core.py`'s module docstring for the full device
mapping and a floorplan hazard the bring-up found (filed generically at
[klayout-tools#999](https://github.com/2AMLogic/klayout-tools/issues/999):
`klt gen-compose`'s same-facing-port obstacle check tests the route's
centerline against block bboxes, not the drawn path's actual
`routing.width_um`-inflated footprint, which let one route's drawn metal
silently clip back into its own origin block and short two of that block's
internal rails together — worked around here with an explicit
`waypoints_um` detour, not a design defect).

**Scope**: core driver cell only — ESD/pad-ring integration is explicitly
out of scope for this cell (downstream work, per the issue).

**Toolchain note**: `mos_array`'s `gate_contact` param this generator relies
on landed in klayout-tools after the `v0.2.0` PyPI tag (klayout-tools#497) —
a `klt` built only from the released `v0.2.0` package (`klt gen mos_array
--list` shows no `gate_contact` param) cannot regenerate this cell.
Reproducing the commands below needs a `klt` built from a post-`v0.2.0`
klayout-tools checkout (`uv tool install --from <checkout path>
klayout-tools --force` against a `klayout-tools` clone at or after that
commit) until the next PyPI release picks it up.

```
scripts/gen_cml_driver_core.py          generator (klt gen + klt gen-compose, subprocess-driven)
gds/cml_driver_core.gds                 the driver core cell
gds/cml_driver_core_shorted.gds         LVS negative control (OUTP shorted to VSS)
gds/cml_driver_core.spice               klt extract's schematic-equivalent netlist
gds/cml_driver_core_shorted.spice       klt extract's schematic-equivalent netlist (shorted variant)
drc_reports/                            klt drc (+ klt extract) reports (text + json), both cells
lvs_reports/                            klt lvs reports (text + json), both cells
lvs/cml_driver_core.ref.spice           hand-written reference netlist for LVS
lvs/cml_driver_core.lvs_request*.json   klt lvs request documents
```

Regenerate and re-run signoff:

```bash
cd layout
python3 scripts/gen_cml_driver_core.py -o gds/cml_driver_core.gds
python3 scripts/gen_cml_driver_core.py -o gds/cml_driver_core_shorted.gds --shorted
klt drc gds/cml_driver_core.gds --deck gf180mcu
klt extract gds/cml_driver_core.gds --deck gf180mcu --top cml_driver_core -o gds/cml_driver_core.spice
klt lvs lvs/cml_driver_core.lvs_request.json          # options.combine_devices folds the per-finger
                                                       # extraction back into one device per schematic line
klt lvs lvs/cml_driver_core.lvs_request_shorted.json  # expect status: mismatch (negative control)
```

Current signoff status: **DRC-clean** and **LVS `status: match`** (3
`severity: warning` findings only — one `device.body_unverified`, the same
deck-synthesized-substrate-net finding `gf180_tmds_pad_min` already
documents, since gf180mcu has no distinct substrate-tap layer; two
unused-device-class `topology` notes) against
`design/netlist/cml_driver.spice`, checked via a hand-written
schematic-equivalent reference netlist
(`lvs/cml_driver_core.ref.spice` — see that file's own header for the two
required, documented translations: folded `nf`/`m` into a single per-device
`W`, and bulk = `vsubs` not `VSS`). The `_shorted` negative control (OUTP
wired directly to VSS instead of left independent) correctly reports
`status: mismatch` (a `net.merged` finding) against the same reference,
confirming the LVS check actually distinguishes connected from
disconnected.
