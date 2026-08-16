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
scripts/gen_cml_driver_core_dut.py      extracted netlist -> simulatable DUT fragment (issue #34)
sim/cml_driver_core_dut.spice           the DUT fragment sim/cml-driver-eye's post-layout records use
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

### Post-layout simulation of this cell (issue #34)

`gds/cml_driver_core.spice` is an **LVS signoff artifact, not a simulatable
deck**: every device is an `M`-card naming klt's own extraction-deck class
label `nfet`, which is not a model any PDK ships (gf180mcu ships its
primitive MOS as a `.subckt nfet_03v3`), and the extracted cell boundary
carries an extra deck-synthesized body pin (`vsubs`) plus the promoted
internal node `TAIL`.

`scripts/gen_cml_driver_core_dut.py` mechanically derives a simulatable DUT
fragment from it — model binding, the `vsubs`→`VSS` body tie, and a wrapper
presenting the schematic cell boundary — so that `sim/cml-driver-eye`'s
testbench runs unchanged against either netlist:

```bash
python3 layout/scripts/gen_cml_driver_core_dut.py   # writes layout/sim/cml_driver_core_dut.spice
python3 layout/scripts/gen_cml_driver_core_dut.py --check   # CI: committed output is not stale
python3 sim/run_corners.py cml-driver-eye --dut layout/sim/cml_driver_core_dut.spice
```

Nothing in that fragment is hand-written: `sim/tests/test_extracted_dut.py`
re-derives it, and independently asserts the translated netlist against
`lvs/cml_driver_core.ref.spice` (folded per-finger widths, 1:20 mirror
ratio, matched differential pair, body net, wrapper pin order) — the class
of mistake that would otherwise converge in ngspice and produce
plausible-looking numbers.

**What that netlist does not model**: it is a *schematic-equivalent*
extraction — devices and connectivity, no interconnect parasitics
(`klt extract --parasitics` was not used for the committed netlist) and no
NRD/NRS diffusion sheet counts. The evidence record taken against it states
this explicitly; see `measurements/characterization.md`.

**Tool gap (friction protocol)**: `klt extract --pdk <variant>` performs the
same model binding itself, but the `klt` **0.2.0** this repo has installed
**drops the per-device `AS`/`AD`/`PS`/`PD`** that the deck-class `M`-card
form carries — verified on this cell, 2026-08-15:

```
# klt extract --deck gf180mcu                (committed as gds/cml_driver_core.spice)
M$1 TAIL IBIAS VSS vsubs nfet      L=0.5U W=2U AS=0.42P AD=0.42P PS=2.42U PD=2.42U
# klt extract --deck gf180mcu --pdk gf180mcuD
X$1 TAIL IBIAS VSS vsubs nfet_03v3 L=0.5U W=2U
```

`nfet_03v3` declares `as=0 ad=0 ps=0 pd=0` defaults, so a `--pdk` netlist
simulates with **no junction capacitance at all** — silently, since it
converges. This is already filed and fixed upstream
([klayout-tools#695](https://github.com/2AMLogic/klayout-tools/issues/695),
closed 2026-08-11), after the `v0.2.0` PyPI tag; no new filing was made.
Until this repo's `klt` moves past that tag, the generator here rewrites the
`AS`/`AD`/`PS`/`PD`-bearing form itself rather than using `--pdk`, and
`sim/tests/test_extracted_dut.py` asserts every simulated device carries
non-zero junction area and perimeter so the gap cannot silently reappear.

## `tmds_encoder` — digital block-level place-and-route (issue #84)

The digital partition's block-level layout: `flow/pnr_tmds_encoder.py`
place-and-routes the gate-level netlist issue #82 synthesized
(`flow/tmds_encoder/netlist/tmds_encoder.synth.v`) against the gf180mcu
`gf180mcu_fd_sc_mcu9t5v0` standard-cell library via OpenROAD (floorplan,
tap/endcap, power distribution network, placement, routing, filler), then
merges the routed DEF into a final GDS in-process via the `klayout` PyPI
package's `klayout.db` module. See that module's own docstring for the full
recipe, and `flow/tmds_encoder/records/*.md` for the append-only evidence
record convention (same as `flow/README.md`'s synthesis records).

```
flow/pnr_tmds_encoder.py                driver (OpenROAD P&R + in-process GDS merge)
flow/tmds_encoder/pnr/tmds_encoder.def  routed DEF
layout/gds/tmds_encoder.gds             the merged block-level GDS
layout/gds/tmds_encoder.spice           klt extract's plain (transistor-level) netlist
layout/gds/tmds_encoder.lvs_extracted.spice   klt extract --abstract-cells netlist (LVS side)
layout/lvs/tmds_encoder.ref.spice       LVS reference, mechanically derived from the
                                         synthesized netlist (layout/scripts/gen_tmds_encoder_ref.py)
layout/lvs/tmds_encoder.lvs_request.json      klt lvs request document
layout/scripts/gen_tmds_encoder_ref.py  reference-netlist generator
layout/scripts/filter_pnr_utility_cells.py    optional utility-cell filter (not used in the
                                         primary flow below -- see its own docstring)
drc_reports/tmds_encoder.drc.{json,txt}       klt drc reports
lvs_reports/tmds_encoder.lvs.{json,txt}       klt lvs reports
```

Regenerate (requires OpenROAD on `PATH`, run via the pinned `openroad/orfs`
Docker image -- see `flow/README.md`'s "Pinned toolchain" -- plus the
`klayout` PyPI package for the GDS merge step):

```bash
python3 flow/pnr_tmds_encoder.py
klt drc --deck gf180mcu layout/gds/tmds_encoder.gds --format json > layout/drc_reports/tmds_encoder.drc.json
klt extract --deck gf180mcu layout/gds/tmds_encoder.gds --top tmds_encoder \
  --abstract-cells 'gf180mcu_fd_sc_mcu9t5v0__*' -o layout/gds/tmds_encoder.lvs_extracted.spice
python3 layout/scripts/gen_tmds_encoder_ref.py \
  --netlist flow/tmds_encoder/netlist/tmds_encoder.synth.v \
  --subckt-headers-from layout/gds/tmds_encoder.lvs_extracted.spice \
  -o layout/lvs/tmds_encoder.ref.spice
klt lvs layout/lvs/tmds_encoder.lvs_request.json --format json > layout/lvs_reports/tmds_encoder.lvs.json
```

**Scope**: place-and-route only, per issue #84 -- no clock-tree synthesis
and no timing-closure claim (issue #83 owns static timing analysis). This
does not integrate with the analog pad ring (#86's scope, separate for the
analog partition).

**Current signoff status**: **DRC violations** (188, all `mim.space.1`) and
**LVS mismatch** (10 topology mismatches; nets/pins otherwise match fully)
-- both fully attributed and explained, not silently worked around:

- The DRC violations are consistent with
  [klayout-tools#1033](https://github.com/2AMLogic/klayout-tools/issues/1033):
  the curated gf180mcu deck's `mim.space.1` rule is a general
  Metal4-to-Metal4 spacing check (its own violation `description` says so)
  applied indiscriminately to ordinary Metal4 PDN/routing geometry, not just
  real MiM capacitor plates -- this design has zero capacitor devices.
- The LVS mismatches are the 9 P&R-inserted filler/tap/endcap standard-cell
  *types* (`gf180mcu_fd_sc_mcu9t5v0__fill_*`, `__filltie`, `__endcap`, plus
  one top-level rollup) that carry no logic and that the pre-P&R reference
  netlist has no counterpart for, by construction (see
  `layout/scripts/filter_pnr_utility_cells.py`'s docstring).

**Two real, upstream DEF->GDS-merge defects were found and fixed while
building this driver** (not worked around) -- a DBU mismatch between
OpenROAD-flow-scripts' bundled gf180 KLayout tech file and this design's own
tech LEF that silently dropped most via-cut geometry, and a second,
related DBU-mismatch corruption when merging the standard-cell GDS library
afterward. See `flow/pnr_tmds_encoder.py`'s "GDS streamout" docstring
section for the full root-cause finding and the klayout-tools issues filed
([#1029](https://github.com/2AMLogic/klayout-tools/issues/1029),
[#1031](https://github.com/2AMLogic/klayout-tools/issues/1031) (superseded),
[#1032](https://github.com/2AMLogic/klayout-tools/issues/1032)).
