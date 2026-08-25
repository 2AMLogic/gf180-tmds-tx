# layout

GDS, generator scripts, and DRC/LVS signoff reports.

**Which `klt` build, and why it matters (issue #127 finding):** the `klt`
binary a stock `pip install klayout-tools` / `uv tool install
klayout-tools` (no `--from <checkout>` override) resolves to reports the
same `klt --version` (`0.2.0`) as a build from the current `klayout-tools`
git checkout, but its bundled `gf180mcu` deck is a different, older
snapshot (`content_hash sha256:1256c45b…` vs. the checkout build's
`sha256:79e71a1e…`) that **has no diode device recognition at all** —
`diode_nd2ps_06v0`/`diode_pd2nw_06v0` are entirely absent from
`device_classes`, and a real diode structure silently extracts as
`device_count: 0` rather than erroring. Every diode-bearing cell below
(`gf180_tmds_pad_diode_draft`, `gf180_tmds_pad_v2`,
`gf180_tmds_pad_ring_assembly`) needs a `klt` built from a current
`klayout-tools` checkout (`uv tool install --from <checkout path>
klayout-tools --force`) to regenerate correctly — the same requirement
`cml_driver_core`'s own "Toolchain note" below already states for
`gate_contact`, now known to be necessary for a second, unrelated reason.
Filed generically at
[klayout-tools#1209](https://github.com/2AMLogic/klayout-tools/issues/1209).

## Every LVS signoff is a pair, and the pair is enforced

Each drawn cell below is signed off with **two** `klt lvs` runs: the intact
cell, which must report `status: match`, and a deliberately-shorted twin
(`<cell>_shorted.gds`), which must report `status: mismatch`. The second run
is the negative control — the only evidence that the first run's `match`
means anything at all, rather than `klt lvs` having quietly lost the ability
to tell a short from an intact cell.

That invariant is checked mechanically, not just written down here:

```bash
python3 layout/scripts/check_lvs_signoff.py --list
```

It reads the committed reports only (stdlib, no PDK, no `klt`, no KLayout),
and runs on every PR as step 6/6 of `.github/scripts/lint.sh`. A `_shorted`
report that says `match`, a `.json`/`.txt` pair from two runs that disagreed,
or an intact cell's unexplained `mismatch` all fail the build. Issue #129 is
why: an upstream extraction-deck drift silently flipped one negative control
to `match` — a defeated control, reported by the tool as good news — and
nothing in this repo noticed. The full episode is written up in the
`gf180_tmds_pad_v2` section below.

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

**Known regression (flagged, not fixed here — issue #9/DR-0011, 2026-08-19):**
re-running `klt drc --deck gf180mcu` against this committed GDS under the
currently-installed `klt` (built from a much newer `klayout-tools` checkout
than existed at this cell's original signoff) reports **8 violations** —
`pad.enclosing.metal5.1` (x4, a >=2.0 um Metal5-overlap-of-pad-opening rule
that did not exist in the deck at signoff time) and `via{1,2,3,4}.width.1`
(x1 each, a >=0.26 um via-size floor). The committed
`drc_reports/gf180_tmds_pad_min.drc.json` above still (correctly, for its
own time) reports `status: clean` — this is the deck gaining coverage after
the fact, not a defect introduced by this file. Left as a known finding for
whichever issue next redraws this cell (most likely #87's capacitance-budget
redesign, which must redraw the pad regardless); see
`spec/decisions/0011-pad-esd-strategy.md` for the full account.

**Re-signed-off against `gf180mcuD` (issue #127, DR-0010's amendment):** this
generator takes no `--pdk` argument at all (pure `klayout.db` drawing, no PDK
dependency), so its GDS is geometry-invariant by construction between
`gf180mcuC`/`gf180mcuD` — confirmed by `klt stats` reporting an identical
bbox/area/polygon/vertex count before and after regeneration (only the GDS
library header's wall-clock timestamp changed). Re-running `klt drc`/`klt
extract`/`klt lvs` reproduces the same **8-violation** known-regression
finding above, unchanged (same 4×`pad.enclosing.metal5.1` + 4×
`via{1,2,3,4}.width.1` set) — the deck-coverage gap is orthogonal to the C/D
question and remains open, not silently resolved or reintroduced.

## `gf180_tmds_pad_diode_draft` — diode-clamp verification draft (issue #9, DR-0011)

A `diode_nd2ps_06v0`-clamped counterpart to `gf180_tmds_pad_min` above,
drawn specifically to verify `2AMLogic/klayout-tools#542`'s diode-device
recognition (closed 2026-08-05) actually works end to end — the tool gap
that forced `gf180_tmds_pad_min`'s GGNMOS redraw in the first place. Not a
candidate final pad cell (no substrate tap, no ring continuity — see
DR-0011's own caveats); its only job is proving `klt drc`/`klt extract`/
`klt lvs` succeed against a real diode-clamp structure.

```
scripts/gen_pad_diode_draft.py          generator (klayout.db, no PDK-PCell dependency)
gds/gf180_tmds_pad_diode_draft.gds      the diode-clamp draft cell
gds/gf180_tmds_pad_diode_draft.spice    klt extract's schematic-equivalent netlist
drc_reports/gf180_tmds_pad_diode_draft.{drc,extract}.json  klt drc/extract reports
lvs_reports/gf180_tmds_pad_diode_draft.lvs.{json,txt}      klt lvs report
lvs/gf180_tmds_pad_diode_draft.ref.spice    hand-written reference netlist for LVS
lvs/pad_diode_draft.lvs_request.json        klt lvs request document
```

Regenerate and re-run signoff:

```bash
cd layout
python3 scripts/gen_pad_diode_draft.py -o gds/gf180_tmds_pad_diode_draft.gds
klt drc --deck gf180mcu gds/gf180_tmds_pad_diode_draft.gds
klt extract --deck gf180mcu gds/gf180_tmds_pad_diode_draft.gds -o gds/gf180_tmds_pad_diode_draft.spice
klt lvs lvs/pad_diode_draft.lvs_request.json
```

Signoff status: **DRC-clean** (0 violations, sized above every currently-
checked rule with margin, including the `pad.enclosing.metal5.1`/
`via*.width.1` rules the regression above surfaced), **extraction finds a
real device** (`device_counts: {diode_nd2ps_06v0: 1}`, vs. `device_count: 0`
the original survey measured against the pre-#542 deck), and **LVS-clean**
(`status: match` against a hand-written `D1 vsubs PAD diode_nd2ps_06v0`
reference). See `spec/decisions/0011-pad-esd-strategy.md` for the full
decision this verification supports.

**Re-signed-off against `gf180mcuD` (issue #127, DR-0010's amendment):** same
as `gf180_tmds_pad_min` above, this generator takes no `--pdk` argument
(geometry-invariant by construction) — `klt stats` confirms an identical
bbox/area/polygon/vertex count, and DRC/extract/LVS results are unchanged
(still DRC-clean, `device_counts: {diode_nd2ps_06v0: 1}`, LVS `status:
match`).

## `gf180_tmds_pad_v2` — realistic-pad-size, diode-clamped pad redesign (issue #87)

Redesign of `gf180_tmds_pad_min` against the DR-0005/DR-0011 ≤2 pF
pad-capacitance budget (`design/esd-capacitance-budget.md` Sec.9). Three
changes relative to `gf180_tmds_pad_min`/`gf180_tmds_pad_diode_draft`: a
real 25×25 µm Metal5 bond pad (the `gf180mcu_fd_io` I/O library's own
established bond-pad-opening size — both prior cells drew a tiny
via-landing or placeholder-sized pad only), a DR-0011-ratified
`diode_nd2ps_06v0` clamp drawn as a 20-finger array (cathodes tied together
on `PAD`, anodes on the deck's substrate global), and a real substrate tap
(`Pplus`-covered `Comp` outside every `Nwell`, tied to a real `VSS` net) —
closing DR-0011's flagged `device.body_unverified` gap: `klt extract`'s net
list for this cell is `PAD`/`VSS`, both real pins, no anonymous `vsubs`.

```
scripts/gen_pad_v2.py                   generator (klayout.db, no PDK-PCell dependency)
gds/gf180_tmds_pad_v2.gds               the redesigned pad cell
gds/gf180_tmds_pad_v2_shorted.gds       LVS negative control (PAD shorted to VSS)
gds/gf180_tmds_pad_v2.spice             klt extract's schematic-equivalent netlist
drc_reports/gf180_tmds_pad_v2{,_shorted}.drc.{json,txt}   klt drc reports
drc_reports/gf180_tmds_pad_v2.extract.json                klt extract report
drc_reports/gf180_tmds_pad_v2.parasitics.json              klt extract --parasitics report
lvs_reports/gf180_tmds_pad_v2{,_shorted}.lvs.{json,txt}    klt lvs reports
lvs/gf180_tmds_pad_v2.ref.spice             hand-written reference netlist for LVS
lvs/gf180_tmds_pad_v2.lvs_request{,_shorted}.json          klt lvs request documents
```

Regenerate and re-run signoff:

```bash
cd layout
python3 scripts/gen_pad_v2.py -o gds/gf180_tmds_pad_v2.gds
python3 scripts/gen_pad_v2.py -o gds/gf180_tmds_pad_v2_shorted.gds --shorted
klt drc --deck gf180mcu gds/gf180_tmds_pad_v2.gds
klt extract --deck gf180mcu gds/gf180_tmds_pad_v2.gds -o gds/gf180_tmds_pad_v2.spice
klt extract --deck gf180mcu --parasitics --pdk gf180mcuD gds/gf180_tmds_pad_v2.gds --format json
klt lvs lvs/gf180_tmds_pad_v2.lvs_request.json --format json > lvs_reports/gf180_tmds_pad_v2.lvs.json
klt lvs lvs/gf180_tmds_pad_v2.lvs_request.json --format text > lvs_reports/gf180_tmds_pad_v2.lvs.txt
# expect status: mismatch (negative control) from both of the next two:
klt lvs lvs/gf180_tmds_pad_v2.lvs_request_shorted.json --format json > lvs_reports/gf180_tmds_pad_v2_shorted.lvs.json
klt lvs lvs/gf180_tmds_pad_v2.lvs_request_shorted.json --format text > lvs_reports/gf180_tmds_pad_v2_shorted.lvs.txt
python3 scripts/check_lvs_signoff.py --list   # verdicts must still be match / mismatch
```

Signoff status: **DRC-clean** (0 violations, including the
`pad.enclosing.metal5.1`/`via*.width.1` rules DR-0011 flagged as a
regression on the older `gf180_tmds_pad_min` cell — this cell is sized to
clear both from the start), **extraction finds 20 real
`diode_nd2ps_06v0` devices** on 2 real nets (`PAD`, `VSS` — no
`body_unverified` warning), and **LVS-clean** (`status: match`, via
`options.combine_devices` folding the 20-finger array back to one combined
`D1 VSS PAD diode_nd2ps_06v0 A=40P P=120U` reference card, same convention
`cml_driver_core.ref.spice` already established for folded MOS fingers).
The `_shorted` negative control correctly reports `status: mismatch`
(4 error-severity findings: the merged `PAD|VSS` net, both reference nets
left with no layout counterpart, and the unmatched combined `D` card).
`klt extract --parasitics` measures the real
`PAD`-net parasitic capacitance at **12.185 fF** (byte-identical between
`--pdk gf180mcuC`/`gf180mcuD`, confirming DR-0010) — see
`design/esd-capacitance-budget.md` Sec.9 for the full capacitance-budget
verdict (clamp capacitance swept separately in SPICE,
`sim/esd-diode-clamp-cv`, and summed with this real pad/interconnect
figure).

**Re-signed-off against `gf180mcuD` (issue #127, DR-0010's amendment):** this
generator takes no `--pdk` argument (geometry-invariant by construction,
like the two draft cells above) — GDS/DRC/extract were regenerated and are
unchanged (still DRC-clean, `device_counts: {diode_nd2ps_06v0: 20}`). The
`--pdk gf180mcuD` `extract --parasitics` invocation above reproduces the
same **12.185 fF** figure the byte-identical cross-check already
established. The LVS reports below were already re-signed-off against the
current (post-#1196-fix) deck by issue #129/#130 and are unchanged here.

**Deck-drift episode: this cell's negative control was silently defeated,
and is now re-verified (issue #129, 2026-08-19).** The `PAD`/`VSS`
extraction claim above is not a claim that has held continuously — it broke
and was restored upstream, and the episode is recorded here rather than
quietly overwritten, because the way it broke is the interesting part.

For a window of klayout-tools commits, the gf180mcu extraction deck bound
`diode_nd2ps_06v0`'s anode to the deck's synthesized `substrate_net` global
(`vsubs`) with no path for this cell's *drawn* `Pplus`/`Comp` substrate tap
to join that same global. The anode therefore resolved to `vsubs` and this
cell's real, labeled `VSS` tie was discarded — precisely the
`device.body_unverified` gap the tap was drawn to close. Filed generically
(tool-side, no design detail) at
[klayout-tools#1196](https://github.com/2AMLogic/klayout-tools/issues/1196).

The damage was not that LVS started failing. It is that LVS *stopped*
failing where it had to: with the anode moved onto `vsubs`, the shorted
cell extracted as two nets (`PAD|VSS`, `vsubs`) against the reference's two
(`PAD`, `VSS`), a coincidental size match — so `klt lvs` reported
`status: match` on a cell whose drawn geometry still shorts `PAD` to `VSS`.
The negative control had been defeated, and it reported that as good news.
The intact cell also passed, on three nets against the reference's two.

Reproduced exactly, against the **unmodified** committed GDS, reference
netlist, and request document — the deck is the only variable:

| | broken | restored (current) |
|---|---|---|
| klayout-tools commit | `74a1bb0` (`e5763f3~1`) | `e5763f3` and later |
| deck `content_hash` | `sha256:e2726af8…` | `sha256:79e71a1e…` |
| intact cell | `match`, 3 nets/3 pins, `PAD`/`vsubs`/`VSS` | `match`, 2 nets/2 pins, `PAD`/`VSS` |
| `_shorted` control | **`match`** (0 error findings) | `mismatch`, 4 error findings |

The upstream fix is klayout-tools `e5763f3` (PR #1113, issue #1084), which
derives the well/substrate tap from the `Nplus`/`Pplus` implants and ties it
into the same `substrate_net` global, so a drawn tap's real net once again
carries the anode. **No workaround was applied in this repo**: the reference
netlist still names the anode `VSS`, because `VSS` is what the cell draws.
Renaming it to `vsubs` to match the broken deck would have encoded a tool
bug into the golden reference and broken the intact cell's own signoff once
the deck was fixed. The committed reports above were re-run against the
restored deck (`sha256:79e71a1e…`), and the broken report pair is kept as
evidence under `tests/fixtures/klayout_tools_1196/`.

Two things changed here as a result, both structural:

- `scripts/check_lvs_signoff.py` (wired into `.github/scripts/lint.sh` step
  6/6, so every PR runs it) asserts that **every** `_shorted` report is
  still a `mismatch` carrying at least one error-severity finding, that
  every intact report is a `match` unless explicitly allowlisted with a
  rationale, and that each report's `.json`/`.txt` pair agrees. A committed
  report that says a negative control passed is now a red build, not a green
  one.
- `tests/test_check_lvs_signoff.py` runs that guard against the captured
  broken report pair and requires it to be rejected — so the guard itself
  has a negative control.

Neither is a substitute for re-running signoff; both exist so that the next
deck drift has to announce itself.

**Re-verifying a committed LVS report** against the currently-installed
`klt` (cheap mode: re-hashes the layout, reference, and deck and diffs
against what the report recorded — exit 3 on drift):

```bash
cd layout/lvs      # report paths are relative to the request document
klt lvs --check ../lvs_reports/gf180_tmds_pad_v2.lvs.json
klt lvs --check ../lvs_reports/gf180_tmds_pad_v2_shorted.lvs.json
```

**Do not add `--rerun`** (full mode: re-run the compare and diff the
verdict) to either command above — it does not work for this cell in either
direction, and its failure mode on the intact cell is misleading rather than
loud. Full mode reconstructs the request from the report's own echoed
fields, which record a single `top` and no `options`:

- on the `_shorted` control, that one `top` is applied to both sides, so it
  exits 1 with `top cell/subcircuit 'gf180_tmds_pad_v2_shorted' not found in
  reference netlist` — every negative control in this repo compares a
  `…_shorted` layout against the *intact* cell's reference netlist, so this
  is structural, not a quirk of this cell;
- on the intact cell, the dropped `options.combine_devices` makes it compare
  all 20 un-folded fingers against the one combined `D1` reference card and
  report `status: drifted` with 27 fresh mismatches — a confident,
  detailed drift verdict about a compare nobody asked for, on evidence that
  has not drifted at all (cheap mode on the same report says `[OK]` on all
  three hashes).

Filed generically at
[klayout-tools#1205](https://github.com/2AMLogic/klayout-tools/issues/1205).
Until it lands, `scripts/check_lvs_signoff.py` plus cheap-mode `--check` are
the machine re-verification this repo relies on.

**Scope**: this cell answers the capacitance-budget question at a real pad
size with a real DR-0011-ratified clamp; it does not draw pad-ring
continuity straps (DVDD/DVSS at DR-0011's 350/75 µm pitch) or a second
(P-toward-VDD) clamp leg — both are block-level pad-ring assembly concerns
(issue #86's scope, coordinated with, not duplicated, here).

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

**Scope**: core driver cell only — ESD/pad-ring integration was explicitly
out of scope for this cell when it was drawn (downstream work, per the
issue). That downstream work now exists: see
`gf180_tmds_pad_ring_assembly` below (issue #86), which imports this GDS
directly and integrates it with a drawn ESD/pad-ring structure.

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

**Re-signed-off against `gf180mcuD` (issue #127, DR-0010's amendment):**
`DEFAULT_PDK` in `scripts/gen_cml_driver_core.py` now reads `"gf180mcuD"`
(previously `"gf180mcuC"`), and the committed GDS was actually regenerated
against that new default, not just the constant flipped in place. This is
the one cell in this repo whose generator *does* resolve real PDK-checkout
paths per variant (`klt gen mos_array --pdk`), so the flip was verified, not
assumed: a full per-layer `Region` XOR between a `--pdk gf180mcuC` build and
a `--pdk gf180mcuD` build of this cell is empty on every layer, and `klt
stats` reports an identical bbox/area/polygon/vertex count either way —
expected, since `mos_array` here draws only diffusion/poly/contact/metal1/
metal2 geometry, none of which is on the Metal5 layer DR-0010's survey found
actually differs between the two variants. DRC/extract/LVS re-signoff above
is unchanged (still DRC-clean, LVS `status: match`/`mismatch` as documented).

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

## `gf180_tmds_pad_ring_assembly` — block-level layout with pad-ring/ESD integration (issue #86)

The analog partition's first block-level assembly: `cml_driver_core.gds`
(above) imported as a flattened GDS instance and integrated with a drawn
ESD/pad-ring structure for its two differential outputs (`OUTP`/`OUTN`) —
the gap `cml_driver_core`'s own "ESD/pad-ring integration is explicitly out
of scope for this cell" disclosure (and `gf180_tmds_pad_min`'s "not the
final TMDS driver pad" disclosure, still accurate for that specific
minimal verification cell, which this assembly does not use) both flagged,
and #65's item 2 checklist re-read FAILed on for exactly that reason.

Structure, per DR-0011 (`spec/decisions/0011-pad-esd-strategy.md`):

- **Two integrated, diode-clamped bond pads** (`diode_nd2ps_06v0`, pad
  cathode / VSS anode), one per driver output, placed at DR-0011's ratified
  **350 um pad pitch**. Each pad reuses `gen_pad_diode_draft.py`'s own
  DRC/LVS-verified cathode + via-stack + bond-pad geometry (issue #9/
  DR-0011), translated and relabelled per pad rather than re-derived.
- **DVDD/DVSS ring continuity**: Metal3/Metal4/Metal5 supply straps drawn
  continuously across the full two-pad span (not stopping at either pad's
  own footprint) and via-stitched every 50 um so the three metal levels
  form one electrically continuous conductor per net — the requirement
  DR-0011 flagged as not yet exercised by any previously-committed cell.
- **A substrate tap on a real net**: an explicit Pplus/Comp region outside
  every Nwell, contacted and wired directly into the DVSS strap. Per
  `klayout_tools/decks/gf180mcu.py`'s issue-#1084 `tap_pplus` derivation,
  this ties the deck's synthesized `vsubs` global into the real, drawn VSS
  net — confirmed by `klt extract`'s own output, where every driver NMOS's
  body terminal reports `VSS` directly (no separate `vsubs` net exists in
  the extracted netlist at all), closing the `device.body_unverified`-class
  gap DR-0011 left open for "the eventual driver-integrated pad."

**Scope, deliberately bounded** (see `scripts/gen_pad_ring_assembly.py`'s
own module docstring for the full reasoning): two pads only (this driver's
own outputs), not a full multi-lane TMDS ring — three data lanes plus clock,
each needing its own differential pair, is a follow-up increment once this
pattern is proven. Clamp topology is `diode_nd2ps_06v0` (pad-to-VSS) only;
DR-0011's symmetric `diode_pd2nw_06v0` VDD-side leg is not drawn (this
driver has no VDD pin to begin with — the DVDD strap is still drawn for
ring-continuity's own sake, but carries no clamp leg or other connection in
this increment, and `klt extract` correctly reports it as disconnected
"dead metal", not a missing connection: see the Signoff section below).
`INP`/`INN`/`IBIAS` (driver inputs) are not routed to pads — out of scope
for the *output* pad-ring integration this issue targets. Pad-opening size
(2x2 um, matching the verified diode draft) is DRC-legal but not a
production wire-bond target; sizing the pad opening for a real bond process,
and the VDD clamp leg, and the multi-lane ring, are follow-up work (#87's
capacitance-budget redesign is the most likely owner for the pad-sizing
question specifically).

**Update (issue #143): the production pad geometry does fit, and this cell
still does not carry it.** The `pad_pitch_fit_*` study below answers the
pad-sizing question this paragraph left open — `gf180_tmds_pad_v2`'s
production 25×25 µm pad **fits DR-0011's ratified 350 µm pitch**, drawn and
DRC-clean, across the whole HBM clamp-sizing window. Folding that geometry
into *this* generator could not land in the same pass: the block-level LVS
signoff below no longer reproduces under the currently-installed `klt`
(see "The block-level LVS signoff no longer reproduces" below), so replacing
this cell's GDS would have meant committing a signoff pair in which **both**
halves report `mismatch` — a defeated negative control, which is exactly the
failure mode `check_lvs_signoff.py` exists to prevent. The redraw is
therefore filed as its own implementation issue (#149), blocked on the
upstream fix, rather than forced through here.

```
scripts/gen_pad_ring_assembly.py                     generator (klayout.db; imports gds/cml_driver_core.gds)
gds/gf180_tmds_pad_ring_assembly.gds                  the assembled block
gds/gf180_tmds_pad_ring_assembly_shorted.gds          LVS negative control (OUTP shorted to VSS)
gds/gf180_tmds_pad_ring_assembly.spice                klt extract's schematic-equivalent netlist
gds/gf180_tmds_pad_ring_assembly_shorted.spice        klt extract's schematic-equivalent netlist (shorted variant)
drc_reports/gf180_tmds_pad_ring_assembly*.{drc,extract}.json(.txt)  klt drc/extract reports, both cells
lvs_reports/gf180_tmds_pad_ring_assembly*.lvs.{json,txt}            klt lvs reports, both cells
lvs/gf180_tmds_pad_ring_assembly*.ref.spice           hand-written reference netlists for LVS
lvs/gf180_tmds_pad_ring_assembly*.lvs_request.json    klt lvs request documents
```

Regenerate and re-run signoff:

```bash
cd layout
python3 scripts/gen_pad_ring_assembly.py -o gds/gf180_tmds_pad_ring_assembly.gds --driver-gds gds/cml_driver_core.gds
python3 scripts/gen_pad_ring_assembly.py -o gds/gf180_tmds_pad_ring_assembly_shorted.gds --driver-gds gds/cml_driver_core.gds --shorted
klt drc --deck gf180mcu gds/gf180_tmds_pad_ring_assembly.gds
klt extract --deck gf180mcu gds/gf180_tmds_pad_ring_assembly.gds --top gf180_tmds_pad_ring_assembly -o gds/gf180_tmds_pad_ring_assembly.spice
klt lvs lvs/gf180_tmds_pad_ring_assembly.lvs_request.json                   # expect status: match
klt lvs lvs/gf180_tmds_pad_ring_assembly_shorted.lvs_request.json           # expect status: mismatch (negative control)
```

**Current signoff status**: **DRC-clean** (0 violations, both the clean
assembly and its `_shorted` negative control) and **LVS `status: match`** (2
`severity: warning` `topology` findings only — the same "unused device
class" informational notes every other cell's own clean LVS run already
carries) against a hand-written schematic-equivalent reference
(`lvs/gf180_tmds_pad_ring_assembly.ref.spice`, `design/netlist/cml_driver.spice`
plus two `diode_nd2ps_06v0` `D` cards). The `_shorted` negative control
(OUTP bridged directly to VSS) correctly reports `status: mismatch`
(`net.merged`/`net.split` findings, plus cascading device mismatches) against
the same reference, confirming the LVS check actually distinguishes
connected from disconnected. `klt extract`'s own report additionally flags
the DVDD strap's three 700x4um (~2800 um² each) Metal3/Metal4/Metal5
rectangles (plus its via3/via4 stitches) as
disclosed, expected "dead metal" — connected to no device or labelled net in
this single-driver-instance increment, exactly as the Scope note above
states.

**Tool gap, friction protocol (nondeterministic LVS)**: re-running the
*identical* `klt lvs` invocation against the unshorted assembly repeatedly
(same GDS/reference content hash every time) intermittently — roughly 1-in-5
runs, observed directly — flips `status` from `match` to `mismatch`, driven
by an internal KLayout `Netlist.combine_devices()` consistency error
(`"Internal error: Terminal still connected after removing device in device
combination"`) that partially folds one multi-finger device before
aborting, cascading into spurious `device.property`/`device.unmatched`
findings against an unchanged reference. Filed generically (no design-
specific detail) at
[klayout-tools#1185](https://github.com/2AMLogic/klayout-tools/issues/1185).

`klt lvs` emits one format per invocation (`--format text` or `--format
json`, no combined mode), so the committed `.txt`/`.json` pair for a cell is
necessarily produced by **two** separate `klt lvs` runs — and under this bug
those two runs can land on *different* outcomes, leaving a committed pair
that contradicts itself. The pair committed here
(`lvs_reports/gf180_tmds_pad_ring_assembly.lvs.{json,txt}`) was therefore
regenerated by looping both invocations until a single round produced
`status: match` from **both** formats, and the two files were then checked
against each other before committing: both report `status: match`, `2`
findings, both `severity: warning` `topology`, `nets 7/7 matched 7`, `devices
6/6 matched 6`, `pins layout=7 reference=6 matched=7`. **Anyone regenerating
these two files must re-do that agreement check** — do not commit a `.txt`
and a `.json` from rounds that disagree. Re-running either command above is
expected to reproduce `match` most of the time but not always, until that
issue is resolved upstream; a lone `mismatch` re-run carrying
`device.combine_incomplete` is this bug, not a real LVS failure (a real
failure looks like the `_shorted` control's `net.merged`/`net.split`).

Note also that `scripts/gen_pad_ring_assembly.py` writes GDSII, whose header
carries a modification timestamp, so a regenerated GDS has a different
`sha256` (and hence a different `environment.layout_sha256` in the report)
even when the geometry is byte-for-byte equivalent — the committed report's
`layout_sha256` matches the committed GDS as of this commit, but do not read
a hash difference after a regen as a geometry change on its own.

The `_shorted` negative control's `mismatch`
result is unaffected by this flakiness in practice (observed stable across
five repeated runs) since its `net.merged`/`net.split` findings alone
already force `status: mismatch` regardless of how `combine_devices`
resolves.

Also re-verified while assembling this block, per DR-0011's own flagged
regression: `klt drc --deck gf180mcu` against the already-committed
`gf180_tmds_pad_min.gds` still reports the same **8 violations**
(`pad.enclosing.metal5.1` x4, `via{1,2,3,4}.width.1` x1 each) under the
currently-installed `klt` build — unchanged from DR-0011's own finding, and
still out of scope to fix here since this assembly does not build on that
cell (it uses the diode-clamped pad structure above instead, which is
DRC-clean under the same current deck).

**Re-signed-off against `gf180mcuD` (issue #127, DR-0010's amendment):** this
generator takes no `--pdk` argument and imports `cml_driver_core.gds`
(itself re-verified geometry-invariant between variants, see that section
above), so this assembly's own geometry is unaffected by the C/D question.
Regenerated GDS/DRC/extract/LVS above against the current, post-#1196-fix
deck (`content_hash sha256:79e71a1e…`, the same "restored" deck
`gf180_tmds_pad_v2`'s own episode section documents) — `status: match`/
`mismatch` reproduced as documented, with the diode anode correctly binding
to the drawn `VSS` net rather than a synthesized `vsubs` global (five
repeated `klt lvs` re-runs against the intact cell all agreed `match`, no
`#1185` flakiness observed this round).

### The block-level LVS signoff no longer reproduces (issue #143 finding)

Under `klt 0.3.0+g634e074ff484` (git commit `634e074f`, KLayout 0.30.10, the
build installed as of 2026-08-24), the committed `status: match` above
**does not reproduce**. This is a regression in the tool, not in the layout —
it is measured against the *unchanged, committed* GDS, and it is stated here
rather than left for the next reader to rediscover:

- `klt lvs` against `lvs/gf180_tmds_pad_ring_assembly.lvs_request.json`
  returned `status: mismatch` on **40 of 40** consecutive runs. Every run
  carries `device.combine_incomplete`, i.e. klayout-tools#1185's
  `Netlist.combine_devices()` internal-consistency error, cascading into
  spurious `device.property`/`device.unmatched` findings against an unchanged
  reference. `klt lvs` already retries that call five times against
  independent `Netlist.dup()` copies, so 40 invocations is ~200 sampled
  attempts, all failing. The ~1-in-5 flake this README documented above has
  become deterministic for this netlist.
- `klt lvs --rerun --check lvs_reports/gf180_tmds_pad_ring_assembly.lvs.json`
  agrees: the layout/reference/deck hashes are all `[OK]` (nothing about the
  inputs drifted) while the fresh compare returns 362 mismatches / 360 errors
  against the committed report's 2 warnings / 0 errors.
- It is **not** the ESD diodes. Removing every `diode_nd2ps_06v0` device from
  the extracted netlist before combining still fails; so does rebinding the
  NMOS body terminals off the drawn `VSS` tap onto a separate net; so does
  keeping `cml_driver_core` as an unflattened subcircuit instance. Each of
  the two constituent cells combines cleanly on its own — `cml_driver_core`
  (338 `nfet`) and `gf180_tmds_pad_v2` (20 `diode_nd2ps_06v0`) both still
  report `status: match` under this same build — and their extracted `nfet`
  parameter multisets are identical inside and outside the assembly, so the
  trigger is purely a connectivity/ordering property of the combined
  block-level netlist.

Filed generically (tool gap only, no design detail) at
[klayout-tools#1370](https://github.com/2AMLogic/klayout-tools/issues/1370).
The committed report pair is left exactly as it is: it is internally
consistent, and it was produced by a build that did reproduce it. Replacing
it with a fresh pair would defeat the negative control outright — under this
build the `_shorted` twin still reports `mismatch` (correctly, on
`net.merged`/`net.split`, checked 3/3) but so now does the intact cell, so a
fresh pair would say `mismatch` on **both** halves and prove nothing about
`klt lvs`'s ability to tell a short from an intact cell. That is the precise
failure `scripts/check_lvs_signoff.py` (issue #129) exists to catch. This is also why
issue #143's pad redraw is filed as follow-up work (#149) rather than landed
against this cell; see the next section.

## `pad_pitch_fit_*` — does the production pad fit DR-0011's 350 µm pitch? (issue #143)

**The question, and why it needed drawing rather than estimating.**
`design/esd-capacitance-budget.md` §9 established that a production 25×25 µm
bond pad plus DR-0011's ratified `diode_nd2ps_06v0` clamp fits DR-0005's
≤ 2 pF budget — but it established it against `gf180_tmds_pad_v2`, a
*standalone* cell that deliberately draws no ring straps, no substrate tap in
a ring context, and no second pad at pitch (§9.2's own scope note). The
block-level ring above still carries a 2×2 µm placeholder opening. So the
load-bearing question — *does that validated geometry survive being tiled at
DR-0011's ratified 350 µm pitch / 75 µm depth, next to the DVDD/DVSS straps
and an HBM-sized clamp array?* — had never been checked. CLAUDE.md's framing
("the pad ring is the point, and the risk") makes an estimate the wrong
answer here, so it was drawn.

```
scripts/pad_pitch_fit_study.py                     generator (klayout.db; no PDK-PCell dependency)
gds/pad_pitch_fit_n{20,111,222,334}.gds            two-slot ring tile, one per clamp size
gds/pad_pitch_fit_n334_wide_bus.gds                the same top-of-window tile with a 4 µm gather bus
drc_reports/pad_pitch_fit_*.fit.json               computed fit report (x/y margins, fold, clearances)
drc_reports/pad_pitch_fit_*.drc.{json,txt}         klt drc reports
drc_reports/pad_pitch_fit_*.parasitics.json        klt extract --parasitics reports
drc_reports/pad_pitch_fit_n{20,334}.parasitics_critical_net.json  the same, with lateral coupling enabled on both pad nets
drc_reports/pad_pitch_fit_n{20,334}.components.json  klt components ring-continuity reports
```

No separate `*.extract.json` is committed for these tiles, and no extracted
`*.spice`: `klt extract --parasitics`'s report is a strict superset of the
plain `klt extract` report (same `device_counts`/`devices`/`nets`, plus the
`parasitics` block), and the netlist itself is re-derivable with `-o` and is
cited by nothing here. At 668 diodes per tile the duplicates are ~1 MB of
committed JSON that no claim in this section rests on.

```
```

Reproduce (from `layout/`, `klt` built from a current `klayout-tools`
checkout — see this file's opening note on which build):

```bash
for n in 20 111 222 334; do
  python3 scripts/pad_pitch_fit_study.py -o gds/pad_pitch_fit_n$n.gds \
      --clamp-fingers $n --report drc_reports/pad_pitch_fit_n$n.fit.json
  klt drc --deck gf180mcu gds/pad_pitch_fit_n$n.gds --format json > drc_reports/pad_pitch_fit_n$n.drc.json
  klt drc --deck gf180mcu gds/pad_pitch_fit_n$n.gds --format text > drc_reports/pad_pitch_fit_n$n.drc.txt
  klt extract --deck gf180mcu --parasitics --pdk gf180mcuD gds/pad_pitch_fit_n$n.gds \
      --top gf180_tmds_pad_pitch_fit --format json > drc_reports/pad_pitch_fit_n$n.parasitics.json
done

# The top-of-window tile again with an 8.3x wider Metal1 gather bus.
python3 scripts/pad_pitch_fit_study.py -o gds/pad_pitch_fit_n334_wide_bus.gds \
    --clamp-fingers 334 --bus-width 4.0 --report drc_reports/pad_pitch_fit_n334_wide_bus.fit.json

# Ring continuity, and the lateral-coupling cross-check (see below).
for n in 20 334; do
  klt components gds/pad_pitch_fit_n$n.gds --top gf180_tmds_pad_pitch_fit \
      --conductors '[{"name":"m3","layer":[42,0]},{"name":"m4","layer":[46,0]},{"name":"m5","layer":[81,0]}]' \
      --vias '[{"name":"via3","layer":[40,0],"between":["m3","m4"]},{"name":"via4","layer":[41,0],"between":["m4","m5"]}]' \
      --format json > drc_reports/pad_pitch_fit_n$n.components.json
  klt extract --deck gf180mcu --parasitics --pdk gf180mcuD --critical-net OUTP --critical-net OUTN \
      gds/pad_pitch_fit_n$n.gds --top gf180_tmds_pad_pitch_fit --format json \
      > drc_reports/pad_pitch_fit_n$n.parasitics_critical_net.json
done
```

The fit report itself needs no `klt` and no KLayout — `pad_pitch_fit_study.py`
without `-o` prints it from stdlib arithmetic alone, and
`layout/tests/test_pad_pitch_fit_study.py` re-derives every committed
`*.fit.json` in CI's PDK-free job.

Each finger contributes 2.0 µm of clamp width, so 111 / 222 / 334 fingers are
the 222 / 444 / 667 µm points `design/esd-capacitance-budget.md` §2b/§9.4
grades the HBM sizing window at (334 fingers is 668 µm — the nearest integer
above 667, i.e. very slightly conservative), and 20 is `gf180_tmds_pad_v2`'s
own as-drawn array.

### The answer: **yes, with two required changes**

| Clamp | Rows | Structure width in the 350 µm slot | Slot margin | Metal5 plate | DVDD-strap clearance | `klt drc` |
|---|---|---|---|---|---|---|
| 20 fingers (40 µm) | 1 | 65.4 µm | 284.6 µm (142.3 each side) | y 18.0–43.0 | 2.0 µm | `clean`, 0 |
| 111 fingers (222 µm) | 1 | 302.0 µm | 48.0 µm (24.0 each side) | y 18.0–43.0 | 2.0 µm | `clean`, 0 |
| 222 fingers (444 µm) | 2 | 325.4 µm | 24.6 µm (12.3 each side) | y 18.8–43.8 | 2.8 µm | `clean`, 0 |
| 334 fingers (668 µm) | 3 | 325.4 µm | 24.6 µm (12.3 each side) | y 19.6–44.6 | 3.6 µm | `clean`, 0 |

The two changes are not optional, and neither was visible before drawing:

1. **The clamp array must fold into rows above ~125 fingers.** A single row
   of `n` 2.0 µm fingers on a 2.6 µm pitch spans `(n-1)·2.6 + 2.0` µm, and the
   structure needs a further 14.0 µm of x past the last finger for the via
   stack and the Metal5 plate centred on it. At the top of the HBM window
   (334 fingers) a single row is **881.8 µm — 2.5× DR-0011's ratified
   pitch**. `pad_pitch_fit_study.py` folds at 120 fingers/row, which holds
   every point in the window to 325.4 µm with 24.6 µm of slot margin. The
   study raises `ValueError` rather than silently overrunning if a clamp
   cannot be folded to fit: DR-0011 is ratified, so the fold widens, never
   the pitch.
2. **The pad structure must sit higher in the ring depth than the current
   assembly places it.** The 25 µm-tall Metal5 plate is centred on the clamp
   array; at the pre-#143 y-origin its lower edge would land at y = 13.0 µm,
   straight through the DVDD strap band (y 12–16). Moving the array origin to
   y = 30 µm puts the plate at y 18.0–43.0, clearing the strap by 2.0 µm
   (7× `metal5.space.1`'s 0.28 µm floor) and leaving 30–32 µm of the 75 µm
   ring depth still unused at every clamp size.

**Ring continuity is intact, checked mechanically not by eye.** `klt
components` over the M3/M4/M5 conductor stack with via3/via4 declared reports
exactly **four** components on the largest tile
(`drc_reports/pad_pitch_fit_n334.components.json`): the DVSS strap as one
connected component spanning the full two-slot span (`bbox` x 0→700, y 2→6),
the DVDD strap likewise (x 0→700, y 12→16), and the two 25×25 µm pad plates
as their own separate components. The production-size pads neither bridge the
two supply straps nor interrupt either one — DR-0011's ring-continuity
requirement survives the larger pad. The same check on the tightest-clearance
tile (`n20`, 2.0 µm plate-to-DVDD gap) gives the same four-component answer.

**No spec change is needed, and none is made.** DR-0011's ratified 350 µm
pitch / 75 µm depth and its ring-continuity and substrate-tap requirements
are all met by the production geometry as drawn. This study checks against
DR-0011; it does not amend it.

### Block-level capacitance, measured for the first time

`klt extract --parasitics --pdk gf180mcuD` against these tiles gives the
pad-node interconnect capacitance the block-level ring has never had a number
for (per pad; `OUTP` and `OUTN` are symmetric and measure identically):

| Clamp | Pad-node C (pad plate + via stack + gather bus) | Pad-node R | Clamp C, `ss_125c_2.97v`, operating bias (§9.4) | Total | vs. 2 pF |
|---|---|---|---|---|---|
| 20 fingers (40 µm) | 12.185 fF | 10.4 Ω | 45.03 fF | 57.2 fF | fits (not HBM-sized) |
| 111 fingers (222 µm) | 34.251 fF | 54.7 Ω | 213.14 fF | 247.4 fF (0.247 pF) | **fits, 88 % headroom** |
| 222 fingers (444 µm) | 65.752 fF | 117.6 Ω | 425.94 fF | 491.7 fF (0.492 pF) | **fits, 75 % headroom** |
| 334 fingers (668 µm) | 95.071 fF | 176.0 Ω | 640.0 fF (extrapolated) | 735.1 fF (0.735 pF) | **fits, 63 % headroom** |
| 334 fingers, 4 µm gather bus | 195.627 fF | 21.6 Ω | 640.0 fF (extrapolated) | 835.6 fF (0.836 pF) | **fits, 58 % headroom** |

Two things worth reading off that table rather than skipping:

- **The 20-finger row reproduces §9.3's cell-level 12.185 fF exactly.** The
  same geometry measures the same capacitance placed in a 350 µm ring slot
  beside the straps as it does standing alone — a useful cross-check of §9.3,
  and a bounded one. It was checked rather than assumed: re-running with
  lateral coupling explicitly enabled on both pad nets
  (`--critical-net OUTP --critical-net OUTN`,
  `drc_reports/pad_pitch_fit_n{20,334}.parasitics_critical_net.json`) returns
  `cc_count: 0`, `total_coupling_capacitance_ff: 0.0` and identical per-net
  figures. The reason is geometric: the Metal5 pad plate and the Metal5
  supply straps are 2.0 µm apart, far outside the layer's own
  minimum-spacing lookback that `klt`'s lateral-coupling pass uses, and they
  nowhere vertically overlap (the unconditional coupling case). So the straps
  contribute no coupling term *under this extractor's model at this
  separation* — which is a statement about a 2.0 µm gap and a quasi-static
  per-net model, not a claim that a physical ring has no pad-to-strap
  coupling. §6's `klt` coverage limitations apply unchanged.
- **The wide-bus row closes §9.3's open caveat with a measurement.** §9.3
  said an HBM-sized clamp "would need a somewhat longer/wider Metal1 bus …
  which would add some additional routing capacitance beyond this figure …
  not literally re-measured at every clamp size". It now is: an 8.3× wider
  (4.0 µm) gather bus at the top of the window costs **+100.6 fF** of pad-node
  capacitance and buys an **8.1× lower** gather-bus resistance (176.0 → 21.6 Ω).
  Both endpoints fit the budget with ≥ 58 % headroom, so the bus-width choice
  is an ESD-current-density decision, not a capacitance-budget one. Note the
  0.48 µm default bus is `gf180_tmds_pad_v2`'s own and its 176 Ω is **not** a
  defensible HBM current path — sizing it is part of the clamp design that
  `design/esd-capacitance-budget.md` §2a still flags as literature-bounded,
  not PDK-bounded.

### What this study is not

It draws no CML driver, no driver→pad routing, and no LVS negative control —
it answers a geometric-fit and parasitic-capacitance question, not "is this
the final integrated block". There is therefore **no `klt lvs` signoff for
these tiles and none is claimed**; `check_lvs_signoff.py` correctly sees no
report pair for them. Folding this geometry into
`gen_pad_ring_assembly.py` — where it *would* need an LVS pair — is
**#149**, blocked on the `klt lvs` regression documented in the previous
section.

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
flow/gen_pnr_netlist.py                 routed DEF -> post-P&R gate-level netlist
flow/tmds_encoder/netlist/tmds_encoder.synth.v  pre-P&R synthesized netlist (P&R's input)
flow/tmds_encoder/netlist/tmds_encoder.pnr.v    post-P&R netlist (the LVS reference's input)
layout/gds/tmds_encoder.gds             the merged block-level GDS
layout/gds/tmds_encoder.spice           klt extract's plain (transistor-level) netlist
layout/gds/tmds_encoder.lvs_extracted.spice   klt extract --abstract-cells netlist (LVS side)
layout/lvs/tmds_encoder.ref.spice       LVS reference, mechanically derived from the
                                         post-P&R netlist (layout/scripts/gen_tmds_encoder_ref.py)
layout/lvs/tmds_encoder_negctl.ref.spice      the same reference with one deliberate
                                         break -- the LVS negative control
layout/lvs/tmds_encoder.lvs_request.json      klt lvs request document
layout/lvs/tmds_encoder.lvs_request_negctl.json  negative-control request document
layout/scripts/gen_tmds_encoder_ref.py  reference-netlist generator (+ --negative-control)
layout/scripts/filter_pnr_utility_cells.py    optional utility-cell filter (not used in the
                                         primary flow below -- see its own docstring)
drc_reports/tmds_encoder.drc.{json,txt}       klt drc reports
lvs_reports/tmds_encoder.lvs.{json,txt}       klt lvs reports
lvs_reports/tmds_encoder_negctl.lvs.{json,txt}   negative-control reports
```

Regenerate (requires OpenROAD on `PATH`, run via the pinned `openroad/orfs`
Docker image -- see `flow/README.md`'s "Pinned toolchain" -- plus the
`klayout` PyPI package for the GDS merge step):

```bash
python3 flow/pnr_tmds_encoder.py
klt drc --deck gf180mcu layout/gds/tmds_encoder.gds --format json > layout/drc_reports/tmds_encoder.drc.json
klt extract --deck gf180mcu layout/gds/tmds_encoder.gds --top tmds_encoder \
  --abstract-cells 'gf180mcu_fd_sc_mcu9t5v0__*' -o layout/gds/tmds_encoder.lvs_extracted.spice

# Post-P&R netlist, derived from the committed routed DEF -- no P&R re-run.
python3 flow/gen_pnr_netlist.py

python3 layout/scripts/gen_tmds_encoder_ref.py \
  --netlist flow/tmds_encoder/netlist/tmds_encoder.pnr.v --from-pnr \
  --subckt-headers-from layout/gds/tmds_encoder.lvs_extracted.spice \
  -o layout/lvs/tmds_encoder.ref.spice
python3 layout/scripts/gen_tmds_encoder_ref.py \
  --netlist flow/tmds_encoder/netlist/tmds_encoder.pnr.v --from-pnr --negative-control \
  --subckt-headers-from layout/gds/tmds_encoder.lvs_extracted.spice \
  -o layout/lvs/tmds_encoder_negctl.ref.spice

klt lvs layout/lvs/tmds_encoder.lvs_request.json --format json > layout/lvs_reports/tmds_encoder.lvs.json
klt lvs layout/lvs/tmds_encoder.lvs_request.json --format text > layout/lvs_reports/tmds_encoder.lvs.txt
klt lvs layout/lvs/tmds_encoder.lvs_request_negctl.json --format json > layout/lvs_reports/tmds_encoder_negctl.lvs.json
klt lvs layout/lvs/tmds_encoder.lvs_request_negctl.json --format text > layout/lvs_reports/tmds_encoder_negctl.lvs.txt
```

> **Do not regenerate `tmds_encoder.lvs_extracted.spice` with `klt` 0.3.0.**
> The committed artifact was produced by `klt` 0.2.0 and is clean.
> Re-extracting the identical GDS under 0.3.0 mis-binds abstracted cell pins
> to nets — 26 instances get a ground pin bound to the power net and 100 get
> an output bound to one of their own inputs, neither of which is physically
> realizable, and neither of which the 0.2.0 artifact contains. Same
> `.SUBCKT` headers, same instance set, 147 of 1339 bindings changed. Filed
> upstream as
> [klayout-tools#1366](https://github.com/2AMLogic/klayout-tools/issues/1366).
> The `klt lvs` *comparison* (netlist vs netlist, no extraction) is
> unaffected, which is why the reports above are 0.3.0-produced against the
> 0.2.0-produced layout netlist.

**Scope**: place-and-route only, per issue #84 (issue #100 added
clock-tree synthesis and hold repair to this same driver; issue #115 added a
two-corner timing view and a `repair_timing -setup` pass for the four-stage
(DR-0009) netlist) -- no timing-closure *claim* is made here either way
(issue #83/#110/#115 own static timing analysis). This does not integrate
with the analog pad ring (#86's scope, separate for the analog partition).

**Current signoff status** (regenerated for issue #115's four-stage (DR-0009)
GDS -- superseding the DR-0008 numbers this section used to cite, same
`klt` version, 0.2.0, and deck): **DRC clean** (0 violations -- unchanged
from the DR-0008 GDS; the `mim.space.1` false positives this section used to
report before that, 188 of them, remain absent, consistent with
[klayout-tools#1033](https://github.com/2AMLogic/klayout-tools/issues/1033)
having been addressed upstream) and **LVS match** (`status: match`, 0
mismatches; nets 384/384, pins 25/25), with a negative control that
correctly fails.

**LVS was a disclosed 18-mismatch FAIL until issue #142; here is what
changed.** The mismatches were never a layout defect — they were an
artifact of comparing a *routed* layout against a **pre**-P&R reference
netlist. `gen_tmds_encoder_ref.py` derived the reference from
`tmds_encoder.synth.v`, which by construction contains none of the cells
place-and-route inserts: fill, tap/endcap, CTS buffers, hold-repair delay
cells and inverters, and setup-repair resized gates. Every one of those
showed up as a layout-only cell type with no counterpart.

The fix is to compare against the netlist the layout was actually built
from. `flow/gen_pnr_netlist.py` reads the committed routed DEF — the same
DEF `layout/gds/tmds_encoder.gds` was streamed from — and writes
`tmds_encoder.pnr.v`, the post-P&R gate-level netlist, which does contain
all 1339 instances. `gen_tmds_encoder_ref.py --from-pnr` then derives the
reference from that. No layout, no netlist, and no P&R setting changed;
only which netlist the layout is graded against.

**What this LVS run does and does not prove.** It proves the DEF -> GDS
merge and the extraction preserved connectivity: every one of the 1339
instances and 384 nets in the routed DEF is present, with the same
topology, in the extracted layout. That is not a vacuous check — this exact
step has had two real, found-and-fixed DBU-mismatch defects (below) that
silently dropped via geometry. It does **not** prove that place-and-route
preserved the *synthesized* netlist's intent; that is a different question,
answered separately by the SDF-back-annotated post-route gate-level
re-simulation (`flow/gate_level_sim_tmds_encoder.py`, 3/3 tests pass
against the unmodified RTL bench) and by
`flow/sta_tmds_encoder.py`'s `assert_def_matches_netlist`. Neither question
subsumes the other, and neither is being claimed here as the other.

**Negative control** (`layout/README.md`'s "Every LVS signoff is a pair"
invariant, enforced by `layout/scripts/check_lvs_signoff.py`):
`tmds_encoder_negctl` compares the **unchanged** committed layout netlist
against a reference with exactly one deliberate fault — the `ctrl[0]`
top-level input merged into `data[3]` — and correctly reports `status:
mismatch` with 3 error-severity findings, the first being
`net.unmatched: CTRL[0]`. Unlike every other cell in this repo, this
control breaks the *reference* rather than shipping a `_shorted` GDS twin,
because the layout-side twin cannot currently be extracted cleanly:
klayout-tools#1366 (above) corrupts `--abstract-cells` extraction on this
design under the installed `klt` 0.3.0, and a control whose failure might
be the tool's rather than the injected fault's is not a control. Restoring
a layout-side `_shorted` twin is tracked as its own follow-up, blocked on
that upstream issue.

For the record, the 18 mismatches that used to be reported here — 17
standard-cell *types* present in the layout that the pre-P&R reference had
no counterpart for, plus one top-level rollup (17 + 1 = 18). Diffed
directly against the reference netlist's own `.subckt` set, not assumed.
All are now matched, since the post-P&R reference contains them:
  - **13 P&R-inserted utility/clock-tree/timing-repair types** that carry no
    logic or that no netlist instance names --
    `gf180mcu_fd_sc_mcu9t5v0__fill_{1,2,4,8,16,32,64}`, `__filltie`,
    `__endcap`, `__clkbuf_12` and `__clkbuf_16` from clock-tree synthesis,
    `__dlyc_1` and `__clkinv_2` from hold repair. Same root cause as the
    DR-0008 GDS's 12 (see `layout/scripts/filter_pnr_utility_cells.py`'s
    docstring); the specific CTS/hold-repair cells differ because issue
    #115 names an explicit CTS root/tree buffer instead of taking
    TritonCTS's default.
  - **2 hold-repair inverter types** (`__inv_3`, `__inv_4`) — the same
    class as the DR-0008 GDS's `__inv_2`, at the sizes this layout's hold
    repair chose.
  - **2 setup-repair *resized* types** (`__oai21_2`, `__oai31_2`). These are
    the three instances `repair_timing -setup` upsized (`_278_`, `_322_`,
    `_339_`), enumerated by name in issue #115's own STA evidence record.
    The reference netlist derives from the pre-P&R synthesized netlist,
    which names the `_1`-strength originals, so the `_2` variants appear
    here as layout-only types. This is the same disclosed netlist-vs-layout
    difference `flow/sta_tmds_encoder.py`'s `assert_def_matches_netlist`
    accepts and enumerates — a drive-strength change, never a function
    change — surfacing in a second place rather than a new one.

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

**PDK-variant sensitivity, explicitly checked, not assumed (issue #127,
DR-0010's amendment):** unlike the analog cells above, this cell's own PDK
resolution goes through `sim/harness/pdk.py` (`flow/pnr_tmds_encoder.py`'s
own docstring, "same PDK-pinning convention as `sim/`"), which has cited
`gf180mcuD` in every `flow/tmds_encoder/records/*.md` evidence record from
the start — this flow was never actually run against `gf180mcuC`, so there
is nothing to flip here (unlike `cml_driver_core`'s `DEFAULT_PDK`). DR-0010's
own survey found the standard-cell library's LEF/liberty (P&R's only
PDK-derived inputs — floorplan, placement, routing, and timing all read
these, not raw PDK geometry) are byte-identical between `gf180mcuC`/
`gf180mcuD`; only the library's `.gds`/`.mag` differ, and only on Metal5,
which standard cells do not route on. Re-running `python3
flow/pnr_tmds_encoder.py` (P&R stage) reproduces a **byte-identical** routed
DEF (`flow/tmds_encoder/pnr/tmds_encoder.def`, diffed directly against the
committed file — zero bytes changed), confirming determinism and
`gf180mcuD`-invariance directly rather than by inference alone. The DRC/LVS
reports above were regenerated against `layout/gds/tmds_encoder.gds`
unchanged (the GDS itself needs no regeneration, since P&R -- its only
variant-sensitive stage -- reproduces byte-identically) under the klt deck
current at the time (0.2.0), reproducing the same DRC-clean / 18-mismatch
LVS status this section documented then. The 18 mismatches were closed by
issue #142 by re-pointing the reference netlist at the post-P&R netlist (see
above); that change touched no layout artifact, so this determinism finding
is unaffected by it. The DEF -> GDS merge step itself (`merge_gds`, above) requires the
pinned `openroad/orfs` Docker image's bundled KLayout tech file
(`/OpenROAD-flow-scripts/flow/platforms/gf180/KLayout/gf180mcu_5LM_1TM_9K_9t.lyt`)
and was not re-run in this pass (the image was not pullable in this
environment) — not needed for this confirmation, since that step reads
ORFS's own bundled, PDK-variant-agnostic tech file plus the (Metal5-free,
byte-identical) standard-cell GDS library, and the DEF it would consume is
itself confirmed unchanged.
