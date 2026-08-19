# gf180mcu pad-ring / ESD survey, and a minimal custom pad signoff

Status: informational survey + first layout evidence, for issue #2. Not a
decision record. The driver's final pad topology decision was originally
pointed at #1 ("Ratify the target spec"), but #1 closed before this survey
landed — that pointer was dangling. It has been picked up instead by
**DR-0011** (`spec/decisions/0011-pad-esd-strategy.md`, issue #9), which
rules on the clamp device, pad pitch/ring depth, DVDD/DVSS ring continuity,
and substrate-tap questions this survey raises in §8, drawing directly on
the findings below.

This document does two things:

1. Summarizes what the gf180mcu PDK actually provides for pad-ring and ESD
   work (§1-§3), with citations to the installed PDK checkout.
2. Records what `klt` (klayout-tools) can and cannot check at the pad
   boundary today, established by actually driving `klt drc`/`klt
   extract`/`klt lvs` against a real, minimal custom pad cell (§4-§6) —
   including two tool gaps this issue's "friction protocol" requires filing
   upstream (§7).

All PDK citations are against the installed volare checkout used to produce
this document:

- PDK root: `~/.volare/gf180mcuC` (variant `gf180mcuC`)
- `open_pdks` commit: `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- Resolved via `klt pdk find --pdk gf180mcuC` (2AMLogic/klayout-tools v0.2.0)

All `klt` citations are against the installed `klayout-tools` checkout at
`~/GitHub/klayout-tools` (klt version `0.2.0`, klayout `0.30.10`).

## 1. What the PDK ships for I/O: `gf180mcu_fd_io`

The gf180mcu open PDK ships one I/O library, `gf180mcu_fd_io`
(`libs.ref/gf180mcu_fd_io/{gds,lef,cdl,lib,mag,spice}`) — a **5V wide-range
inline non-CUP GPIO library**, general-purpose MCU I/O. There is no
high-speed / differential / CML pad cell in it (confirmed by cell-name
inspection below) — this is the fact CLAUDE.md's "the pad ring is the point"
framing is built on, and this survey re-confirms it directly against the
installed library rather than taking it on faith.

Cell inventory (`klt cells .../gf180mcu_fd_io/gds/gf180mcu_fd_io.gds`, 15 top
cells): `asig_5p0`, `bi_24t`, `bi_t` (bidirectional I/O pads, two drive
strengths), `brk2`/`brk5` (ring breaker cells, 2um/5um), `cor` (ring corner
cell), `dvdd`/`dvss` (supply-rail cells), `fill1`/`fill5`/`fill10`/`fillnc`
(ring filler cells), `in_c`/`in_s` (input-only cells). No differential pair,
no CML/LVDS driver, no explicit ESD-only test-pad cell.

### Pad-ring pitch and geometry (from the LEF)

`libs.ref/gf180mcu_fd_io/lef/gf180mcu_fd_io__bi_t.lef`:

```
MACRO gf180mcu_fd_io__bi_t
  CLASS PAD INOUT ;
  SIZE 75.000 BY 350.000 ;
  SITE GF_IO_Site ;
```

i.e. the standard bidirectional pad cell is **75um deep (core-to-pad-edge)
by 350um wide (along the ring)** — 350um is this library's established
pad-to-pad pitch. `PAD` itself is a `Metal5` pin near one corner of the
cell (`RECT 25.000 20.000 50.000 45.000`, a 25x25um landing inside the
75x350um cell footprint) — i.e. the bond-pad opening is a small feature
within a much larger cell whose bulk is ESD/driver silicon and the supply
straps described next. Every cell in the library shares the same 75um depth
and either the full 350um pitch (`bi_t`, `bi_24t`, `asig_5p0`, `dvdd`,
`dvss`, `in_c`, `in_s`) or a pitch sub-multiple used for ring filling
(`brk2`=2um, `brk5`=5um, `fill1`/`fill5`/`fill10`=1/5/10um, `fillnc`=0.42um)
— i.e. the ring is built by tiling cells of the *same depth* and *variable,
summable width* along the ring, not a fixed-pitch grid the way a
digital standard-cell row is.

Every pad cell carries **`DVDD`/`DVSS`** (I/O-domain supply) in addition to
core `VDD`/`VSS` — 12+10 separate `Metal3`/`Metal4`/`Metal5` strap segments
each, running the full cell height. Any custom pad dropped into this ring
must bring its own `DVDD`/`DVSS` straps at the same pitch to stay
electrically continuous with its neighbours; a standalone pad (as built for
this issue, §4) does not exercise that ring-continuity requirement and is
explicitly not a claim that a full assembled ring would DRC-clean today.

### The bond-pad structure itself: `Bondpad_5LM`

Every pad cell's `PAD` metal region instantiates copies of a shared
sub-cell, `Bondpad_5LM` (visible via `klt cells`'s cell-hierarchy report on
the same GDS: e.g. `M5_M4_CDNS_4066195314556`, parent `Bondpad_5LM`) — a
5-layer-metal (Metal1 through Metal5) redundant via/fill lattice under the
landing pad, not a single flat Metal5 square. This is the PDK's own
reference pattern for "how to build a bond-pad opening safely" and the
closest thing to an official pad-stack precedent, though it ships only as
an opaque sub-cell inside `gf180mcu_fd_io.gds`, not as a separately
documented, reusable primitive.

### The pad-opening layer itself has almost no DRC coverage in the open PDK

The installed PDK's own KLayout DRC deck defines a `pad` layer
(`libs.tech/klayout/tech/drc/rule_decks/layers_def.drc:575`, `pad =
get_polygons(37, 0)`) but the **only** rules in that deck that reference it
(`libs.tech/klayout/tech/drc/rule_decks/geom.drc:549-552`) are generic
geometry hygiene — on-grid vertices and 45-degree-multiple angles. There is
**no minimum pad-opening size, no pad-to-pad spacing, and no
metal5-encloses-pad-opening rule** anywhere in this open-sourced deck. A
full pad-opening design-rule table (bond-pad minimum size, pad-to-seal-ring
keepout, etc.) would live in the closed-source foundry Design Rule Manual,
which is not part of the open PDK distribution.

## 2. ESD implant rules (`ESD.*`)

`libs.tech/klayout/tech/drc/rule_decks/esd.drc` (Apache-2.0, GlobalFoundries
PDK Authors) is a real, complete rule file covering the ESD implant layer
(GDS `24/0`), used to build higher-voltage-tolerant ESD-clamp devices:

| Rule | Description | Value |
|---|---|---|
| ESD.1 | Min ESD implant width | 0.6um |
| ESD.2 | Min space between two ESD implant areas | 0.6um |
| ESD.3a | Min space to NCOMP | 0.6um |
| ESD.3b | Min/max space to a butted PCOMP | (containment) |
| ESD.4a | Extension beyond NCOMP | 0.24um |
| ESD.4b | Min overlap of ESD implant edge to COMP | 0.45um |
| ESD.5a | Min ESD area | 0.49um² |
| ESD.5b | Min field area enclosed by ESD implant | 0.49um² |
| ESD.6 | Extension perpendicular to Poly2 gate | 0.45um |
| ESD.7 | No ESD implant inside PCOMP | (exclusion) |
| ESD.8 | Min space to Nplus/Pplus | 0.3um |
| ESD.pl | Min gate length of 5V/6V gate NMOS | 0.8um |
| ESD.9 | ESD implant must be overlapped by Dualgate | (containment) |
| ESD.10 | LVS_IO must cover I/O MOS active area | (containment) |

These are real, checkable rules **in the official PDK's own KLayout deck**
— but, per §5 below, `klt`'s own curated gf180mcu DRC deck does not
implement any of them yet.

## 3. ESD device options in the PDK

Two families of ESD-relevant devices are available:

**ESD diodes.** The I/O library's own CDL netlist
(`libs.ref/gf180mcu_fd_io/cdl/gf180mcu_fd_io.cdl`) uses two 6.0V-rated
diode primitives extensively as the actual clamp devices in every pad cell:
`diode_nd2ps_06v0` (N+/P-substrate, e.g. `D80 DVSS n21 diode_nd2ps_06v0`)
and `diode_pd2nw_06v0` (P+/N-well, e.g. `D3 ASIG5V DVDD
diode_pd2nw_06v0`). Both have a SPICE model
(`libs.tech/ngspice/sm141064.ngspice:38145`/`:38156`) and an official
KLayout PCell generator
(`libs.tech/klayout/tech/pymacros/cells/draw_diode.py`,
`draw_diode_nd2ps`/`draw_diode_pd2nw`) — **but that generator depends on
`gdsfactory`, which is not installed in this environment** (`pip index
versions gdsfactory` resolves fine, i.e. it is installable, but running the
PDK's own PCell was out of scope for standing up one dependency; see §7).
The generator's own geometry recipe (enclosure/spacing constants) was
instead read and hand-transcribed for a first draft of this pad (not the
final design — see §4).

**ESD-clamp transistors.** `ESD.pl`'s 0.8um minimum gate length (§2) is
specifically the rule for a "5V/6V gate NMOS" ESD device — i.e. a
grounded-gate NMOS (GGNMOS) clamp, built from the same primitive
NMOS/dualgate/ESD-implant layers as a normal 5V/6V transistor, is an
equally legitimate, PDK-anticipated ESD topology, not an invented one.
This is the option §4's actual signoff-clean cell uses, precisely because
it is extractable by `klt` today (§5) and a diode is not.

## 4. The minimal custom pad cell

`layout/gds/gf180_tmds_pad_min.gds` (generated by
`layout/scripts/gen_pad_min.py`, no PDK-PCell dependency — plain
`klayout.db` calls): a Metal5 bond pad (`PAD` net) wired straight down a
Metal1-Metal5 via stack to the drain of a grounded-gate NMOS clamp; the
transistor's gate and source both land on a separate `VSS` net via an
L-shaped Metal1 strap. `Comp`/`Poly2`/`Contact`/`Metal1-5` geometry is sized
generously above every rule `klt`'s gf180mcu deck checks (see the script's
comments for exact dimensions and the margin over each threshold) — this is
deliberately not a tight, real-DRM-minimum layout; the point of "minimal" is
proving the DRC/LVS flow at the pad boundary, not proving area efficiency.

A second cell, `layout/gds/gf180_tmds_pad_min_shorted.gds`, is identical
plus one extra Metal1 bridge directly shorting the `PAD` net to `VSS` — an
LVS negative control (§6).

### Why a GGNMOS clamp, not the diode `libs.ref` uses

The first draft of this cell used a hand-transcribed `diode_nd2ps_06v0`
(§3). It was DRC-clean against every rule `klt` checks, but **`klt
extract`'s gf180mcu deck has no diode device class at all** — confirmed by
reading `klayout_tools/decks/gf180mcu.py`'s `EXTRACTION_DECK` (only
`bipolars`, `capacitors`, `resistors` device families are wired up; the
module's own comment at line 714 lists `diode_mk` among the layers "not
modelled" even in the one place — the resistor exclusion set — where it is
mentioned at all) and by direct extraction: running `klt extract --deck
gf180mcu` against the diode-based draft returned `device_count: 0`. A
diode-based pad's ESD element is therefore real, DRC-legal geometry that
`klt lvs` cannot verify at all today (see the filed issue in §7). Redrawing
the same "PAD-to-clamp-to-VSS" topology as a grounded-gate NMOS instead —
electrically a legitimate ESD topology in its own right (§3) — sidesteps
that gap entirely, because `nfet` *is* one of `klt`'s recognised device
classes, and produces a signoff result that is actually meaningful rather
than a DRC-only pass on an unverifiable structure.

## 5. `klt`'s actual coverage at the pad boundary (measured, not assumed)

Both `klt drc --deck gf180mcu` and `klt extract --deck gf180mcu` self-report
exactly what they did and did not check (`coverage`/`ignored_layers` in
their JSON output) — quoted directly rather than inferred, against
`layout/gds/gf180_tmds_pad_min.gds`:

**DRC** (`layout/drc_reports/gf180_tmds_pad_min.drc.json`): `status: clean`,
`violation_count: 0`. Layers actually checked: `Comp(22/0)`, `Poly2(30/0)`,
`Contact(33/0)`, `Metal1(34/0)`, `Metal2(36/0)`, `Metal3(42/0)`,
`Metal4(46/0)`, `Metal5(81/0)`, plus `Via4(41/0)` (only as the "other layer"
of an enclosure check). Layers present in the stream but **not covered by
any rule**: `Nplus(32/0)`, the Metal1/Metal5 pin-label purposes
(`34/10`/`81/10`), `Via1/Via2/Via3(35/0, 38/0, 40/0)`, and the pad-opening
marker `(37/0)`. This matches `klayout_tools/decks/gf180mcu.py`'s own module
docstring, which describes itself as "a curated subset of the official rule
set" covering poly2/comp/contact/metal1 (extended to metal2/3/5/metaltop and
the MiM stack) plus one Nwell and one BJT rule — explicitly **not**
Pplus/Nplus implant rules, LVPWELL/DNWELL, or any 5V/6V/dualgate/ESD-implant
variant. None of §2's `ESD.*` rules, and none of a real ESD-implant-based
device's Pplus/Nplus/Dualgate/LVPWELL geometry, are checked by `klt` today
— "DRC-clean" against `klt drc --deck gf180mcu` for a structure touching
those layers means "clean against the currently-curated subset," not "clean
against the full GF180MCU signoff rule set."

**Extraction/LVS** (`layout/drc_reports/gf180_tmds_pad_min.extract.json`,
`layout/lvs_reports/*.lvs.{txt,json}`): `device_count: 1` (`nfet`,
`L=0.4U W=2U`), `net_count: 3` (`PAD`, `VSS`, and the deck-synthesized
substrate net `vsubs`), `pin_count: 3`. `klt lvs` against a hand-written
schematic-equivalent reference (`layout/lvs/gf180_tmds_pad_min.ref.spice`)
reports `status: match`, with two informational warnings: `topology`
(benign — other device classes have no counterpart on either side, since
this cell only uses one) and `device.body_unverified` (the NMOS body/bulk
terminal is compared against `klt`'s deck-synthesized global substrate net,
not a real drawn substrate-tap net, because this minimal cell draws no
explicit substrate tap — a real driver-integrated pad would need one).

## 6. Negative control: does the LVS check actually mean something?

Per `klt lvs`'s own documented methodology
(`docs/cli/lvs.md`, "Negative controls" — "LVS clean alone is not evidence
... a mis-wired invocation that silently compares nothing also passes"),
`layout/gds/gf180_tmds_pad_min_shorted.gds` (§4) is byte-identical to the
clean cell plus one extra Metal1 bridge shorting `PAD` to `VSS`. Run through
the *same* reference netlist:
`layout/lvs_reports/gf180_tmds_pad_min_shorted.lvs.txt` reports `status:
mismatch` (`net.unmatched` x5, `device.unmatched` x1) — confirming the
`match` result above is a real topological check, not a vacuous pass
against an extraction that dropped everything (which is exactly what would
have happened with the diode-based draft — see §7's first filed issue).

## 7. Friction filed upstream (2AMLogic/klayout-tools)

Both filed generically (tool-gap framing, no design-specific detail) per
CLAUDE.md's friction protocol:

1. **`klt extract`/`klt lvs` cannot represent a device-less,
   pure-interconnect circuit.** `Netlist.purge()` (called unconditionally at
   the end of `_extract_netlist`) drops the entire top circuit — and every
   labelled pin on it — whenever the circuit contains zero recognised
   devices, even when the layout has legitimately labelled, electrically
   distinct nets. Reproduced with a two-line, two-labelled-metal-island
   smoke test (no PDK-specific geometry at all) against **both** the
   `gf180mcu` and `sky130` curated decks: `klt extract` returns
   `device_count: 0, net_count: 0, pin_count: 0` for a layout with two
   clearly separate, correctly labelled nets; `klt lvs` against any
   reference netlist then hard-errors (`"layout netlist has no top
   circuit"`) rather than comparing (even trivially) or reporting a
   graceful zero-device/N-net result. This blocks LVS on any
   interconnect-only structure — bond pads, guard/seal rings, RDL, power
   straps — independent of PDK. Filed as
   [2AMLogic/klayout-tools#539](https://github.com/2AMLogic/klayout-tools/issues/539).
2. **`gf180mcu`'s extraction/LVS deck has no diode device class.**
   `klayout_tools/decks/gf180mcu.py`'s `EXTRACTION_DECK` recognises
   `nfet`/`pfet`/`bjt`/one MiM capacitor/one poly resistor, but no diode —
   even though `diode_mk`-marked diode devices are one of the PDK's two
   standard ESD-clamp primitives (§3) and the deck's own module comment
   already lists `diode_mk` among the layers it does not model (today only
   noted as a resistor-extraction exclusion, not as its own gap). Filed
   generically as a device-coverage gap (applicable to any PDK whose ESD
   library leans on diode clamps, not gf180mcu-specific) as
   [2AMLogic/klayout-tools#541](https://github.com/2AMLogic/klayout-tools/issues/541).

## 8. What this implies for the driver's pad geometry

- **Pad pitch**: the PDK's own `gf180mcu_fd_io` library establishes 350um
  as the standard pad-to-pad pitch (bi_t/bi_24t/asig_5p0/dvdd/dvss/in_c/
  in_s), with a 75um ring depth — a custom TMDS pad dropped into (or
  alongside) that ring should target the same 350um pitch and 75um depth
  unless #1's driver-topology decision explicitly argues for a different
  pitch (e.g. to fit four lanes' worth of custom pads plus their DVDD/DVSS
  straps in a tighter span). This survey does not make that call.
- **DVDD/DVSS ring continuity**: any custom pad must carry through
  `Metal3`/`Metal4`/`Metal5` supply straps at the ring's established
  positions to stay electrically continuous with neighbouring standard I/O
  cells — not exercised by this issue's standalone cell.
- **ESD topology**: prefer a GGNMOS (or other transistor-based) clamp over
  a diode-based one *if* `klt`-based LVS signoff is required before
  klayout-tools closes the diode-device-class gap (§7 item 2) — this is a
  tooling-driven constraint, not an electrical one; a diode clamp may still
  be electrically preferable for the real driver and should be decided on
  its own merits once the tool gap closes or a workaround (e.g. `klt sim`
  ngspice-level verification instead of layout LVS) is adopted.
- **Substrate tap**: `klt`'s `device.body_unverified` warning (§5) means a
  real driver-integrated pad needs an explicit, drawn substrate tap tied to
  a real ground net for a clean (warning-free) LVS result — this minimal
  cell intentionally omits one to keep the "minimal" footprint honest,
  documented as a known follow-on rather than silently absorbed into the
  `match` verdict.
- **Interconnect-only sub-structures are currently unverifiable by `klt
  lvs`** (§7 item 1) — a pure bond-pad-plus-via-stack piece (no device) of
  any future driver layout cannot get a real LVS check today; plan on
  including at least one recognised device (as this cell does) in whatever
  sub-block needs LVS signoff, or wait for the filed fix.
