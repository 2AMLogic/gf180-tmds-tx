# DR-0011: Pad and ESD strategy after #2 (successor to DR-0005)

**Status: Accepted.** Successor to and full supersession of DR-0005
(`spec/tmds-tx.md`), which is not deleted — its Status line points here.

**Numbering note**: see DR-0010's "Renumbering note" — this record was
issue #9's originally-drafted `DR-0007`, renumbered to avoid colliding with
the already-ratified, unrelated `DR-0007` (`spec/tmds-tx.md`'s
synthesized-domain clock ceiling record).

## Context

DR-0005's Status was **"Accepted — provisional pending #2."** #2 closed and
produced `spec/pad-ring-esd-survey.md`, which contradicts or leaves open
three specific parts of DR-0005 that were never resolved back into the
spec:

1. **Clamp device.** DR-0005 decided the ESD clamp reuses gf180mcu's
   `diode_nd2ps_06v0`/`diode_pd2nw_06v0` diode primitives. The survey (§4,
   §5, §8) found `klt`'s gf180mcu extraction deck had **no diode device
   class at all** at the time (`device_count: 0` on a diode-based draft;
   filed as `2AMLogic/klayout-tools#541`, informally referenced by its issue
   number in the survey text as "#541"/"#542" depending on section), redrew
   the clamp as a grounded-gate NMOS (GGNMOS) for that reason, and is the
   *only* clamp this repository has actually signed off
   (`layout/gds/gf180_tmds_pad_min.gds`). So the ratified decision named a
   device the block's own signoff flow could not verify.
2. **Pad pitch and ring continuity.** The survey (§8) established 350 um
   pitch / 75 um depth from `gf180mcu_fd_io`'s LEF, but explicitly deferred
   the "should a custom TMDS pad target the same pitch" call to issue #1,
   which had already closed by the time the survey landed — an orphaned
   decision no document in `spec/` had picked up.
3. **Substrate tap.** The survey (§5) records `klt lvs` returning a
   `device.body_unverified` warning on the signed-off GGNMOS cell, because
   it draws no explicit substrate tap.

## The clamp-device contingency, resolved

The survey's *sole* stated reason for redrawing a GGNMOS instead of using
the diode DR-0005 decided on was a **tool gap**, not an electrical
preference (survey §8: *"prefer a GGNMOS ... clamp over a diode-based one
**if** `klt`-based LVS signoff is required before klayout-tools closes the
diode-device-class gap ... this is a tooling-driven constraint, not an
electrical one"*). That gap was filed as
[`2AMLogic/klayout-tools#541`](https://github.com/2AMLogic/klayout-tools/issues/541)
(the survey also references it as `#542` in one place — both numbers track
the same underlying diode-device-class gap in that tracker's history).
`2AMLogic/klayout-tools#542` **closed 2026-08-05**, landing junction-diode
device recognition
([klayout-tools PR #561](https://github.com/2AMLogic/klayout-tools/commit/2c2cd063d1862e994e210f65cae61b2b0d460ef3),
`feat(extract): recognise junction diodes via a new DiodeDevice deck
family`) — `ExtractionDeck.diodes`, wired to KLayout's native
`kdb.DeviceExtractorDiode`, recognising both `diode_nd2ps_06v0` (n+
diffusion in p-substrate) and `diode_pd2nw_06v0` (p+ diffusion in Nwell) —
see `docs/cli/extract.md` "Junction diodes (issue #542)" in the
`klayout-tools` checkout.

Per the operator ruling on issue #9 (2026-08-19), this is contingent on a
real verification: **a `klt drc`/`klt extract`/`klt lvs` run against a
diode-clamp draft, proving extraction now works in practice** — not merely
that the upstream issue is closed. That run is part of this decision
record's own evidence, not asserted on the tracker's say-so:

### Verification: a `diode_nd2ps_06v0` clamp draft, drawn and signed off

`layout/scripts/gen_pad_diode_draft.py` draws
`layout/gds/gf180_tmds_pad_diode_draft.gds`: a `diode_nd2ps_06v0` clamp (the
same flavour named first in DR-0005's own Decision, and the flavour
`gf180mcu_fd_io__asig_5p0`'s own CDL clamp toward `DVSS` uses) — a `Comp`
region marked `Nplus` + `Dualgate` + `diode_mk` (115/5), wired straight up a
Metal1–Metal5 via stack to a bond pad, with the p-substrate anode left
undrawn (gf180mcu draws no p-substrate mask; `klt` ties it to its
synthesized `substrate_net` global, `vsubs`).

Installed `klt` version: `0.2.0` CLI string, built from
`2AMLogic/klayout-tools` git commit `9c71bb6741f20be19bf94b847832803505042ec6`
(2026-08-18) — post-dates the diode-recognition landing commit `2c2cd06`
(2026-08-05) the operator ruling cites. Results, against `klt`'s `gf180mcu`
deck (content hash `sha256:6a323622d93c1b4716a7874c37ee3d825bd08398c3c030c85175e44e2cc229a3`,
which `klt deck resolve` does not find in its packaged-release history table
— i.e. this is an unreleased/dev-checkout deck build, consistent with the
above):

- **`klt drc --deck gf180mcu`**: `status: clean`, `violations: 0`
  (`layout/drc_reports/gf180_tmds_pad_diode_draft.drc.{json,txt}`).
- **`klt extract --deck gf180mcu`**: `status: extracted`, `devices: 1`,
  `device_counts: {diode_nd2ps_06v0: 1}`
  (`layout/drc_reports/gf180_tmds_pad_diode_draft.extract.json`). The
  extracted netlist is exactly the schematic-equivalent `D` card form
  `docs/cli/extract.md` documents:
  `D$1 vsubs PAD diode_nd2ps_06v0 A=1P P=4U`
  (`layout/gds/gf180_tmds_pad_diode_draft.spice`) — a real, non-zero device
  count, unlike the `device_count: 0` the survey measured against the old
  deck.
- **`klt lvs`** against a hand-written reference netlist
  (`layout/lvs/gf180_tmds_pad_diode_draft.ref.spice`,
  `D1 vsubs PAD diode_nd2ps_06v0`): **`status: match`**
  (`layout/lvs_reports/gf180_tmds_pad_diode_draft.lvs.{json,txt}`) — 2/2
  nets matched, 1/1 devices matched, 2/2 pins matched; the only reported
  mismatches are three benign `topology` warnings (device classes present
  in the deck's vocabulary but instantiated on neither side, e.g. `nfet`,
  `pfet`, `bjt` — the same class of informational warning
  `gf180_tmds_pad_min`'s own LVS match already carries for its unused
  device classes).

This is the contingency's evidence: **the tool gap that forced DR-0005's
GGNMOS redraw is closed, and diode-based LVS signoff is now real, not
theoretical.**

### A discovered, out-of-scope regression (flagged, not fixed here)

Re-running `klt drc --deck gf180mcu` against the *already-committed*
`layout/gds/gf180_tmds_pad_min.gds` (the signed-off GGNMOS cell) under this
same, newer `klt` build reports **8 violations** — `pad.enclosing.metal5.1`
(x4, a >=2.0 um Metal5-overlap-of-pad-opening rule) and `via{1,2,3,4}
.width.1` (x1 each, a >=0.26 um via-size floor) — where the cell's own
committed evidence record (`layout/drc_reports/gf180_tmds_pad_min.drc.json`)
still reports `status: clean`. `klt`'s curated gf180mcu deck has grown DRC
coverage since issue #2's original signoff (the `pad.enclosing.metal5.1`
rule in particular did not exist when the survey found "no minimum
pad-opening size ... anywhere in this open-sourced deck") — so this is a
**deck-coverage improvement surfacing a genuine regression in a
previously-clean cell**, not a defect in this decision record's own new
draft (which was sized to clear both rules and is DRC-clean under the same,
current deck). This is out of scope to fix here — DR-0011 rules on the
clamp *device*, not on re-drawing the already-committed `gf180_tmds_pad_min`
cell — and is left as a flagged finding for whichever issue next touches
that cell (most likely #87's redesign, since it must redraw the pad against
the capacitance budget regardless).

## Decision

- **Clamp device: diode-based, reaffirming DR-0005.** The verification
  above satisfies the operator's stated contingency — diode-clamp LVS
  signoff through `klt` is real. This block's ESD clamp network reuses
  `diode_nd2ps_06v0` (and, symmetrically, `diode_pd2nw_06v0` where a
  P-clamp-toward-VDD leg is needed, mirroring `gf180mcu_fd_io__asig_5p0`'s
  own two-diode topology), sized for this pad's own capacitance budget —
  DR-0005's language on that point is unchanged and carried forward.
  `gf180_tmds_pad_min.gds`'s GGNMOS clamp remains this repository's only
  full, integrated pad cell to date; it is **not** required to be redrawn as
  a diode by this decision record — that redesign (against the
  capacitance-budget numbers `design/esd-capacitance-budget.md` and #87
  own) is explicitly out of scope here, same as the issue body states for
  the 7.95 pF vs <=2 pF tension. This record clears the *device-class*
  question so that redesign is not blocked on it.
- **Pad pitch and ring depth: 350 um pitch / 75 um depth**, adopted from the
  survey's LEF reading (`gf180mcu_fd_io__bi_t.lef`: `SIZE 75.000 BY
  350.000`, shared by every cell in that library). No stated reason in this
  block's driver topology (DR-0002) or serialization plan (DR-0003) argues
  for a different pitch, so the survey's own recommended default is
  adopted rather than left orphaned. A future pad-ring assembly (#87 or
  whichever issue owns it) may still argue for a tighter custom pitch to
  fit four lanes' worth of pads plus `DVDD`/`DVSS` straps in a smaller
  span — that would be its own decision record, since it would depart from
  this one, not silently narrow it.
- **DVDD/DVSS ring continuity: required.** This block's pads must carry
  through `Metal3`/`Metal4`/`Metal5` `DVDD`/`DVSS` supply straps at the
  ring's established positions to stay electrically continuous with
  neighbouring stock `gf180mcu_fd_io` cells (or with each other, if this
  block's four lanes form their own standalone sub-ring) — not the stand-
  alone, non-ring-continuous structure `gf180_tmds_pad_min` and this
  record's diode draft both are today (deliberately, since both are
  minimal verification cells, not ring segments). A future integrated pad
  must exercise this requirement, not merely cite it.
- **Substrate tap: required on a real net.** A drawn, explicit substrate tap
  tied to a real ground net is required for the eventual driver-integrated
  pad, so that a future `klt lvs` `match` is obtained without a
  `device.body_unverified`-class warning still attached. This record's own
  diode draft does *not* draw one (its anode is deliberately left tied to
  `klt`'s synthesized `substrate_net`, matching `docs/cli/extract.md`'s
  documented "substrate-side anode inherits the NMOS-body limitation"
  behaviour) — that is acceptable for *this* verification draft, whose only
  job is proving diode extraction works, but is **not** acceptable for the
  production pad, which must draw a real tap.
- **ESD target and capacitance budget: carried forward unrelaxed.**
  **HBM >= 2 kV (JEDEC JS-001), CDM >= 500 V (JEDEC JS-002), MM not
  targeted; pad capacitance budget <= 2 pF per data/clock pad** (ESD diodes
  + pad parasitic combined) — all unchanged from DR-0005. These remain a
  requirement to be validated together, not a result; DR-0005's framing of
  this as *"the primary tension this decision record leaves open"* is
  unchanged. `design/esd-capacitance-budget.md`'s 7.95 pF measurement
  (~4.0x over budget at a realistic 25x25 um pad) is untouched by this
  record — that redesign is explicitly #87's scope, not this one's, per the
  issue body's own framing.

## Alternatives considered

- **Ratify the GGNMOS clamp instead**, matching the one cell this repo has
  actually signed off, was the operator's own stated fallback if the diode
  verification failed. It did not fail — the diode draft above is both
  DRC-clean and LVS-matched under the current `klt` build — so this
  alternative is not taken. If a future `klt` regression or a real
  electrical argument against diodes emerges, that is a fresh decision
  record with its own evidence, not a silent reversion.
- **Defer the clamp-device ruling until the production pad redesign (#87)
  lands**, rather than deciding it here against a minimal verification
  draft, was considered and rejected — #87 is explicitly blocked on this
  ruling landing first (per the cross-link on issue #9 from #81's
  decomposition), so deferring would only push the same tool-gap
  contingency check into #87's own scope without adding information; the
  verification is drawable today and was drawn.
- **Adopt a tighter or looser pad pitch than 350/75 um** without a stated
  reason was considered and rejected — the survey's own recommendation
  (adopt the stock library's pitch absent a driver-topology argument
  otherwise) is followed because no such argument exists yet in DR-0002/
  DR-0003.

## Consequences

- `spec/pad-ring-esd-survey.md`'s dangling *"the driver's final pad topology
  decision belongs to #1"* pointer is retired in favour of this record (see
  the header-note edit accompanying this decision).
- #87 (the analog pad/ESD redesign against the 7.95 pF vs 2 pF tension) and
  #86 (block-level layout assembly with pad-ring/ESD integration) both
  unblock against this record's clamp-device ruling — the redesign now
  proceeds against a ratified diode-based clamp (or may still choose to
  draw a GGNMOS on electrical grounds, but does not need to for tooling
  reasons).
- The `gf180_tmds_pad_min.gds` DRC regression noted above is left as a
  known, flagged issue for whichever future work next touches that cell —
  not silently absorbed into this record's "clean" claim, and not fixed
  here (out of scope for a decision-record-only issue).
- DR-0005 is superseded in full; its Status line points here.

## Status

**Accepted.**
