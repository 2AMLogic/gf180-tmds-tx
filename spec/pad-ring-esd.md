# Pad ring and ESD: PDK facts, a minimal pad cell, and what's still open

Status: **partial**. This closes the PDK-facts survey and produces a
DRC-clean minimal pad cell; it does **not** close LVS signoff or land an
ESD-diode structure — both are blocked by real, filed gaps in the tooling
(see Sec. 6/8). Issue: `2AMLogic/gf180-tmds-tx#2`.

## 0. Why this document exists

CLAUDE.md calls the pad ring "the point, and the risk" of this block: the
gf180mcu I/O library ships a general-purpose 5V GPIO library and no
high-speed cell, so a TMDS driver needs a **custom pad** with its own ESD
structure, and no canary in the fleet has drawn one before. This document
records what the PDK actually provides (Sec. 1-4), what was drawn and
checked (Sec. 5-6), what blocked full signoff and where that friction was
filed (Sec. 6/8), and what the resulting geometry implies for the driver
(Sec. 7).

## 1. The gf180mcu I/O library ships

Source: `google/globalfoundries-pdk-libs-gf180mcu_fd_io` (Apache-2.0),
`docs/` (`features.rst`, `naming.rst`, `power.rst`), commit as installed by
this environment's `volare` PDK (`open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`,
resolved via `klt pdk find --pdk gf180mcuC`). Also cross-checked directly
against the installed PDK's own `libs.ref/gf180mcu_fd_io/{gds,cdl,lef,spice}`
under that same `volare` install.

**1.1 Technology options** (`docs/features.rst`): 5V I/O library available in
3LM/4LM/5LM metal-stack options; bond pad is **non-CUP** (no circuit under
pad) due to a design-manual restriction on the 3LM option; top-metal
thickness 6kA or 9kA; design grid 0.005um.

**1.2 Cell list** (`docs/specs/02_Cell_List.csv`):

| Cell | Description |
|---|---|
| `gf180mcu_fd_io__bi_t` | 5V WR bidirectional pad, 4/8/12/16mA programmable drive, tri-state, fast/slow slew, pull-up/down, CMOS/Schmitt select |
| `gf180mcu_fd_io__bi_24t` | 5V WR bidirectional pad, 24mA drive, tri-state, fast/slow slew, pull-up/down, CMOS/Schmitt select |
| `gf180mcu_fd_io__in_c` | 5V WR CMOS input-only pad, pull-up/down |
| `gf180mcu_fd_io__in_s` | 5V WR Schmitt-trigger input-only pad, pull-up/down |
| `gf180mcu_fd_io__asig_5p0` | 5V WR analogue-signal pad, double-diode protection, 10mA DC current capability |
| `gf180mcu_fd_io__dvdd` / `__dvss` | Power/ground supply cells, 60mA DC current capability each |
| `gf180mcu_fd_io__cor` | Corner cell |
| `gf180mcu_fd_io__fillnc` / `__fill1` / `__fill5` / `__fill10` | Fillers (<1um / 1um / 5um / 10um gap) |
| `gf180mcu_fd_io__brk2` / `__brk5` | 2um / 5um breaker cells with VSS |

**No high-speed/CML/LVDS cell exists in this list** — confirms CLAUDE.md's
framing directly from the library's own cell catalogue, not just the repo's
own prior assertion.

**1.3 Cell dimensions** (`docs/specs/03_Cell_Dimensions.csv`, cross-checked
against the installed PDK's own `libs.ref/gf180mcu_fd_io/lef/*.lef`):

| Cell | Height (um) | Width (um) |
|---|---|---|
| `bi_t`, `bi_24t`, `in_c`, `in_s`, `asig_5p0`, `dvdd`, `dvss` | 350 | 75 |
| `cor` (corner) | 355 | 355 |
| `fillnc` / `fill1` / `fill5` / `fill10` | 350 | 0.1 / 1 / 5 / 10 |
| `brk2` / `brk5` | 350 | 2 / 5 |

"The I/O cell height of 350um (est.) is inclusive of the bonding pad. The
bond pad opening is 60umx60um." (`docs/features.rst` Sec. 2.2). This 350um
row height and 75um base pitch is the abutment contract every ordinary
gf180mcu I/O cell in this library shares — confirmed directly from
`libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__asig_5p0.lef`: `SIZE 75.000 BY
350.000`, `SITE GF_IO_Site`.

**1.4 Operating conditions** (`docs/specs/15_Operating_Conditions.csv`): I/O
DC supply voltage 4.5-5.5V (typ 5V); junction temperature -40 to 125 degC.

**1.5 ESD targets** (`docs/specs/16_ESD_Protection.csv`, `docs/esd.rst`):

| ESD model | Target |
|---|---|
| Human Body Model (HBM) | 2000V |
| Machine Model (MM) | 200V |
| Charged Device Model (CDM) | 500V |

**1.6 Latch-up immunity** (`docs/specs/17_Latchup_Immunity.csv`,
`docs/latchup.rst`): Digital and analog I/O, tested to JESD78B, target
+/-100mA over 25-125 degC.

**1.7 Power-pad leakage** (`docs/power.rst`): each DVDD/DVSS pad has one ESD
protection circuit inside, max leakage 648nA (FF corner, 5.5V, 125C,
simulated); the corner cell has two such circuits (max 1296nA).

**1.8 The closest existing reference structure — the analogue-signal pad**
(`docs/analog.rst`, and the installed PDK's own
`libs.ref/gf180mcu_fd_io/cdl/gf180mcu_fd_io.cdl`): "The 5.0V analogue signal
pad is meant for analogue circuits that use the thick-gate transistors ...
The analogue signal pads contain only HBM protection diodes. If they are
connected to input gates, the designer needs to include CDM protection
network near to these gates ... If these analog signal pads are used with
internal circuit, the user must add their own secondary ESD protection
adjacent to the devices of the internal circuit being protected. The
perimeter of the CDM diode should be larger than 25um. The CDM resistor
should be larger than 50 [ohm] and should be realized using appropriate poly
resistor."

The `asig_5p0` cell's actual CDL subcircuit is a plain **dual-diode clamp**
plus a decoupling cap between the supply rails:

```
.SUBCKT gf180mcu_fd_io__asig_5p0 ASIG5V DVDD DVSS VDD VSS
D0 DVSS DVDD diode_nd2ps_06v0 m=4.0 AREA=40e-12 PJ=82e-6
C1 DVDD DVSS $[cap_nmos_06v0] m=36.0 l=15e-6 w=15e-6
D2 DVSS ASIG5V diode_nd2ps_06v0 m=4.0 AREA=150e-12 PJ=106e-6
D3 ASIG5V DVDD diode_pd2nw_06v0 m=4.0 AREA=150e-12 PJ=106e-6
.ENDS
```

This is directly relevant: a dual-diode clamp to the supply rails is the
lowest-capacitance standard ESD topology, which is exactly the property a
high-speed TMDS output needs (added pad capacitance eats directly into the
742.5Mbps/lane 720p60 target's rise/fall budget). It is also the *only* ESD
topology this PDK's own I/O library demonstrates anywhere in a shipped cell
— see Sec. 7 for what that means for the driver's own ESD network, and Sec.
6/8 for why this topology could not yet be carried into an LVS-checkable
custom pad cell here.

## 2. Bond pad rules (DRM Chapter 9)

Source: `google/gf180mcu-pdk` (Apache-2.0),
`docs/physical_verification/design_manual/drm_09*.rst` +
`tables_clear/29_BondPad1_70.csv` / `29_BondPad2_70.csv`.

"This mask defines the opening where the bond wires connect the circuit to
the lead frame ... Pad metal is connected to Metal1, Metal2, Metal3, Metal4
and/or Metal5 through Via1, Via2, Via3, Via4 and/or Via5, which are located
below the perimeter of the pad metal. Bond pad size and pitch are limited by
assembly house." (`drm_09.rst`)

| Rule | Description | Wedge (no CUP) | Ball (CUP) | Gold bump |
|---|---|---|---|---|
| PAD.1 | Pad opening (min, um) | 40 | 40 | 4 |
| PAD.2 | Pad opening to pad opening (um) | 9 | 9 | 9 |
| PAD.4 | Top-layer-metal overlap of pad opening (um) | -- | 2 | -- |
| PAD.5 / PAD.6 | MetalTop / MetalTop-1 overlap of Top_Via (um) | 0.5 | 0.5 | 0.5 |
| PAD.7-14 | Each metal's overlap of its via, Metal5..Metal1 (um) | 0.5 | 0.5 | -- (varies) |
| PAD.15 | Min pad-opening space to nearest guard ring (um) | 30 | 30 | 30 |
| PAD.16 | Max pad-opening space to nearest guard ring (um) | 200 | 200 | N/A |
| PAD.17 / PAD.18 | Pad-opening space to active COMP / Poly2 (um) | 15 | N/A | N/A |
| PAD.19a | Pad opening to non-pad Metal1-5 up to MetalTop-1 (um) | 6 | N/A | N/A |
| PAD.19b | Pad opening to non-pad MetalTop (um) | 6 | 6 | 6 |
| PAD.20 | Pad metal to pad metal space (um) | 5 | 5 | 5 |

"Active circuits are allowed when ball-type wire-bonding process is used ...
No circuit under pad is allowed when wedge-type wire-bonding process is
used." (`drm_09_3.rst`, Circuit-Under-Pad rules) — this PDK's own I/O
library ships **non-CUP** pads (Sec. 1), so no active circuitry sits
directly under the bond pad in the vendor library; a custom pad following
that convention keeps ESD/active devices adjacent to, not beneath, the pad
opening.

**These `PAD.*` rules are not modeled in `klt drc`'s curated gf180mcu deck at
all** (no `Pad`/passivation-opening layer, no `PAD.*` rule entries) — see
Sec. 6/8, filed as `2AMLogic/klayout-tools#544`.

## 3. gf180mcu layer numbers used here

From `klayout_tools/decks/gf180mcu.py`'s module docstring (itself verified
against `google/globalfoundries-pdk-libs-gf180mcu_fd_pv`'s `main.drc` layer
derivations, e.g. `metal5 = get_polygons(81, 0)`), reproduced here for this
document's own citations:

| Layer | (layer, datatype) | | Layer | (layer, datatype) |
|---|---|---|---|---|
| Nwell | 21/0 | | Metal3 | 42/0 |
| Comp | 22/0 | | Via3 | 40/0 |
| Poly2 | 30/0 | | Metal4 | 46/0 |
| Contact | 33/0 | | Via4 | 41/0 |
| Metal1 | 34/0 | | Metal5 | 81/0 |
| Via1 | 35/0 | | MetalTop | 53/0 |
| Metal2 | 36/0 | | FuseTop | 75/0 |
| Via2 | 38/0 | | | |

Metal-layer pin/label purpose is datatype 10 on the same layer number (e.g.
Metal5 label = 81/10), gf180mcu's convention per the same module.

## 4. What `klt` and the installed PDK actually give us today

Checked directly in this environment (`klt --version`; PDK resolved via
`klt pdk find --pdk gf180mcuC`):

- `klt drc --deck gf180mcu` and `klt extract --deck gf180mcu` /
  `klt lvs` exist and run fully headless (no GUI/Qt), confirmed working
  against real gf180mcu geometry (Sec. 5/6).
- `klt gen --list` (headless PCell-style generator library) has
  `mos_array`, `res_array`, `bjt_array`, `diff_pair`, `guard_ring` — **no
  bond-pad, ESD-diode, or pad-ring generator**. `guard_ring` (substrate/well
  tap ring) is the one directly useful primitive here and is what Sec. 5's
  pad cell uses.
- No interactive layout/schematic tool (`magic`, `klayout` GUI, `xschem`)
  is installed in this environment — only the PDK itself (via `volare`) and
  `klt`'s headless CLI. All layout in Sec. 5 was produced by a small script
  driving `klayout.db` directly (the same library `klt` itself is built on)
  plus `klt gen guard_ring`, not by hand-editing in a layout editor.

## 5. A minimal custom pad cell

`layout/pad_min/` — built by `layout/pad_min/build_pad_min.py`, output
`layout/pad_min/gf180_tmds_pad_min.gds`.

**What it is**: a first-cut, deliberately trivial stand-in for a custom pad's
geometry — not a reproduction of the vendor `gf180mcu_fd_io` bond pad (a
proprietary Cadence-PCell-generated structure with no available source), and
**not yet an ESD-protected pad** (see Sec. 6 for why the ESD diode is not
in it yet).

- A substrate/well tap **guard ring** (`klt gen guard_ring`, params
  `inner_width_um=64, inner_height_um=64, ring_width_um=2.0,
  contacts_per_side=14` — Nwell/Comp/Contact/Metal1 tap ring with a well
  tie, generated bbox `(-0.15,-0.15)-(68.15,68.15)` um). This is the
  substrate-contact structure a real ESD clamp's guard ring would enclose;
  see Sec. 7 for the driver-design implication.
- A bond-pad-equivalent solid **Metal2-Metal5 stack**, 60um x 60um
  (matching the gf180mcu_fd_io library's own documented pad-opening size,
  Sec. 1), centered in the ring's inner clear area, stitched together with
  a modest Via2/Via3/Via4 array (0.28um squares, 2um pitch, 3um inset from
  the pad edge).
- Net-name labels (`PAD` on the Metal5 label layer, `VSUB` on the Metal1
  label layer) for `klt extract` pin promotion — see Sec. 6 for why these
  did not end up producing a usable extracted netlist.

**DRC**: `klt drc gf180_tmds_pad_min.gds --deck gf180mcu` →
`layout/pad_min/drc_report.json` — **status: clean, 0 violations**. Real
output, not asserted: `coverage.layers_checked` is
`["21/0","22/0","33/0","34/0","36/0","41/0","42/0","46/0","81/0"]` — Nwell,
Comp, Contact, Metal1, Metal2, Metal3, Metal4, Metal5, and Via4 (only
because Via4 is also `mim.enclosing.via4.1`'s `other_layer`, which is why
it's tracked even though that specific rule was skipped, per
`coverage.rules_skipped`, for lacking any drawn FuseTop). Meanwhile
`coverage.layers_in_stream_without_rules` lists the Metal1/Metal5 label
layers (34/10, 81/10) and Via2/Via3 (38/0, 40/0) — those carry no rules in
this curated deck at all (see Sec. 6/8, `#544`), so "clean" here means clean
against the rules the deck actually checks, not a claim that Chapter 9's
`PAD.*` rules or full via geometry were verified (they weren't — the deck
has no rules for either).

**Regenerating it**:

```
klt gen guard_ring --params '{"inner_width_um": 64, "inner_height_um": 64,
    "ring_width_um": 2.0, "contacts_per_side": 14}' --pdk gf180mcuC \
    -o /tmp/ring_only.gds
<klt-venv-python> layout/pad_min/build_pad_min.py /tmp/ring_only.gds \
    layout/pad_min/gf180_tmds_pad_min.gds
klt drc layout/pad_min/gf180_tmds_pad_min.gds --deck gf180mcu --format json
```

(`<klt-venv-python>` is the python `klt` itself ships with, e.g.
`~/.local/share/uv/tools/klayout-tools/bin/python` in a `uv tool install`
setup — it carries the `klayout.db` bindings `build_pad_min.py` imports.)

## 6. LVS: attempted, not achieved — and why

`klt extract gf180_tmds_pad_min.gds --deck gf180mcu --top
gf180_tmds_pad_min -o gf180_tmds_pad_min.spice` (`layout/pad_min/extract_report.json`,
`layout/pad_min/gf180_tmds_pad_min.spice`) returns **`device_count: 0,
net_count: 0, pin_count: 0`** — an empty netlist, despite the `PAD`/`VSUB`
net-naming labels described in Sec. 5.

Root cause, isolated directly against `klayout.db` independent of `klt`
(full reproduction in the filed issue below): `klayout.db.Netlist`'s
`make_top_level_pins()` does not promote a named-but-deviceless net to a pin
despite its own docstring saying it turns "all named nets of top-level
circuits ... into pins", and the subsequent `purge()` call then discards the
net (and, since nothing is left, the whole circuit) as "floating" —
regardless of whether a pin was even attached. **Any layout with zero
recognised devices extracts to nothing today**, which is exactly the case a
bond pad or a guard/tap ring is (this cell has neither a transistor, a
bipolar, a MiM cap, nor a recognised resistor on it).

A `klt lvs` attempt against a hand-written golden reference netlist
(`layout/pad_min/reference.spice`, `layout/pad_min/lvs_request.json`) fails
cleanly for the same reason — there is no layout-side circuit to compare
against: `layout/pad_min/lvs_report.json` →
`"top cell/subcircuit 'gf180_tmds_pad_min' not found in layout netlist"`.

This is filed as `2AMLogic/klayout-tools#543` (deviceless circuits purged to
nothing, reproduced identically on both the gf180mcu and sky130 decks) —
until it's fixed (or `klt extract` grows an opt-in "keep deviceless nets"
mode), **no bond pad, guard ring, or other passive/interconnect-only
structure can be LVS-checked via `klt` at all**, regardless of which design
draws it.

Separately, even once that's fixed, the pad's *real* target ESD structure —
a dual-diode clamp, per Sec. 1's `asig_5p0` reference — still could not be
LVS-checked: `klt extract`'s device-recognition decks (both gf180mcu and
sky130) have no diode device class at all. Filed as
`2AMLogic/klayout-tools#542`.

**Net effect**: DRC-clean is real and verified (Sec. 5). LVS-clean is
**not** claimed — it is blocked by `#543` (and, once a diode is added to
the design, also by `#542`), not by anything left undone in this repo.

## 7. What this implies for the driver's design

- **Pitch/pin contract**: the gf180mcu I/O library's own ordinary cells all
  share a **350um row height** and abut on **75um-wide** cells (`SITE
  GF_IO_Site`), with power rails carried on Metal3/Metal4/Metal5 at the far
  left/right edges of each cell (confirmed directly from
  `gf180mcu_fd_io__asig_5p0.lef`'s `DVDD`/`DVSS` pin geometry: vertical
  rail segments at x=[0,1]um and x=[74,75]um spanning nearly the full
  350um height). A custom driver pad that needs to sit *inside* this
  library's pad ring (rather than forming its own, separate ring) should
  either match that 350um row height and an integer multiple of the 75um
  base pitch, or the ring assembly needs an explicit transition/breaker
  strategy at the seam — this is exactly the "core-to-pad seam" CLAUDE.md
  flags as untested ground. Not attempted here; Sec. 5's cell is
  deliberately smaller and does not yet target this pitch.
- **Bond-pad geometry to reuse**: 60um x 60um pad opening (Sec. 1/5), and
  DRM Chapter 9's keep-outs (Sec. 2) — in particular PAD.15's 30um minimum
  pad-opening-to-guard-ring spacing and PAD.17/18's 15um pad-opening-to-
  active-circuit spacing are real constraints on how tightly the ESD clamp
  can sit next to the pad in the real driver cell; Sec. 5's cell uses a much
  smaller ~4um clearance (deliberately, for a compact first exercise) and
  does not meet PAD.15 as drawn — a real driver pad needs to.
- **ESD topology**: the PDK's own library only ever demonstrates a
  dual-diode clamp (Sec. 1.8) — no rail-clamp/big-FET secondary network
  ships anywhere in this library. A dual-diode clamp to DVDD/DVSS is also
  the right first choice electrically (lowest added pad capacitance,
  important at 742.5Mbps/lane), so absent contrary data this is the
  starting-point topology for the driver's own ESD network — but it cannot
  be LVS-verified today (Sec. 6, `#542`) until that gap closes.
- **Guard ring**: Sec. 5's tap ring (Nwell/Comp/Contact/Metal1, well-tied)
  is the substrate-contact structure the real ESD clamp needs around it for
  latch-up immunity (JESD78B +/-100mA target, Sec. 1.6); reuse the same
  `klt gen guard_ring` primitive, sized to actually enclose the diode
  devices once `#542` is closed, rather than (as here) just the bond-pad
  metal stack.

## 8. Filed tool gaps (klayout-tools friction protocol)

Per CLAUDE.md's friction protocol, every gap below is filed generically
against the tool, not this design:

- **`2AMLogic/klayout-tools#542`** — no diode device-recognition class in
  `klt extract`'s gf180mcu/sky130 decks; blocks LVS of any diode-based ESD
  clamp (the standard topology, Sec. 1.8/7).
- **`2AMLogic/klayout-tools#543`** — `klt extract`/`klt lvs` purge any
  deviceless (pure-interconnect) circuit to nothing, even with named pins;
  blocks LVS of a bond pad, guard ring, or any passive/routing-only
  structure (Sec. 6). This is the gap that most directly blocked this
  issue's LVS acceptance criterion.
- **`2AMLogic/klayout-tools#544`** — no bond-pad (`PAD.*`, DRM Chapter 9,
  Sec. 2) rule coverage in the curated gf180mcu DRC deck, and Via1-4
  width/space rules are also absent (`layers_in_stream_without_rules` in
  Sec. 5's own DRC report).

## 9. Status / next steps

- [x] PDK pad-ring and ESD rules summarized with citations (Sec. 1-4).
- [x] A minimal custom pad cell is DRC-clean (Sec. 5, real `klt drc` output).
- [ ] The same pad cell is LVS-clean — **blocked**, not achieved (Sec. 6);
      re-attempt once `2AMLogic/klayout-tools#543` closes.
- [x] Tool gaps filed upstream and linked (Sec. 8).
- [x] Driver-design implications recorded (Sec. 7).

Follow-on work (not this issue): once `#543` (and, for the real ESD device,
`#542`) close, extend Sec. 5's cell with an actual dual-diode clamp sized
per Sec. 1.8's reference areas, re-run `klt extract`/`klt lvs` for a real
LVS-clean result, and re-draw at the Sec. 7 pitch/pin contract so the cell
can actually sit in a gf180mcu_fd_io-compatible pad ring.
