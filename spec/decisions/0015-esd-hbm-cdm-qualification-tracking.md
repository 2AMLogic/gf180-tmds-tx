# DR-0015: HBM/CDM ESD qualification (DR-0013 row 11) is a permanent pre-silicon limitation, not schedulable work

**Status: Accepted.** Changes how DR-0013 row 11 is *tracked*; does not
weaken what it *requires*. HBM >= 2 kV (JEDEC JS-001) / CDM >= 500 V
(JEDEC JS-002) remain ratified and unrelaxed.

## Context

Issue #145 asked a routing question, not an engineering question: is "HBM
>= 2 kV / CDM >= 500 V ESD qualification" (DR-0013 row 11,
`spec/decisions/0013-operating-conditions.md:119`) open, schedulable work,
or a permanent pre-silicon limitation that should be recorded as an
accepted, non-closing caveat? The underlying evidence was already
established and undisputed before this record — issue #145 exists because
no prior document had turned that evidence into a tracker disposition.

`design/esd-capacitance-budget.md` §2a states the finding this record turns
on: **no source in the installed gf180mcu PDK characterizes ESD failure
current density, breakdown voltage, or snapback/trigger behavior for any
device family.** Neither `libs.tech/klayout/tech/drc/rule_decks/esd.drc`
(real, checkable geometry rules — implant width/area, gate length,
overlaps — but nothing about failure current or breakdown voltage) nor
`libs.tech/ngspice/sm141064.ngspice` (zero ESD-specific device models;
no drain-junction avalanche/secondary-breakdown current-density data, no
TLP I-V data, no parasitic-BJT snapback/holding-voltage parameters)
supplies it. Consequences, already honestly stated before this record:

- **HBM** (§2b): the 222/444/667 µm clamp-width figures are first-order
  estimates (`I_pk = V_HBM / R`) sized against a **2–6 mA/µm HBM
  failure-current density drawn from general ESD-design literature**
  (Amerasekera & Duvvury; Voldman), explicitly marked as not PDK-sourced —
  the PDK supplies no failure-current-density number of its own to check
  that estimate against.
- **CDM** (§2d): reported as "the source is silent" — CDM robustness turns
  on trigger voltage and turn-on delay, which need TLP characterization or
  mixed-mode TCAD data neither the PDK nor this repository's tooling
  provides. No CDM-driven width number exists.
- This repository has no tester and no fabricated parts;
  `measurements/` stays empty by design until tape-out (CLAUDE.md). Real
  HBM/CDM qualification — a measured pass/fail against a physical DUT and a
  physical ESD tester — cannot happen before silicon exists, independent of
  anything this repository's tooling or PDK data could supply in the
  interim.

That last point is the one this record turns into a disposition: the gap is
not a missing simulation this repository could still run, and not a
missing PDK dataset a future `klt` deck update could plausibly supply
(`spec/pad-ring-esd-survey.md` §8 and `design/esd-capacitance-budget.md`
§2a both independently confirm the open gf180mcu PDK carries no
electrical ESD-device data at all, only DRC geometry) — it is a structural
absence that only two things can close: **real silicon** (a fabricated
part and a physical HBM/CDM tester), or **a PDK-sourced ESD electrical
dataset** that does not exist today. Per the operator's 2026-09-15 comment
on issue #145 (citing the standing ratification-via-PR mechanism,
2AMLogic/2am#357 and its #372 mechanism), a tracker-treatment question that
presents options like this is not itself an operator-authority call — it
is resolved by drafting the decision and letting the existing two-key
review mechanism evaluate it, which is what this record does.

## Decision

**DR-0013 row 11 is recorded as an accepted, non-closing, pre-silicon
limitation (issue #145's option 1) — not schedulable work (option 2), and
not held open/blocked (option 3).**

- The row's **requirement is unchanged and unrelaxed**: HBM >= 2 kV (JEDEC
  JS-001), CDM >= 500 V (JEDEC JS-002), MM not targeted — carried forward
  from DR-0005/DR-0011 exactly as ratified. This record does not touch what
  DR-0013 row 11 requires; per CLAUDE.md ("agents do not relax the
  ratified spec to make results pass"), only a `spec/` decision record
  changing the requirement itself could do that, and none is proposed
  here.
- What changes is **how the row is tracked**: it no longer counts as open
  engineering work blocking this block's T1/bronze tier (see
  "Consequences" below). It is instead an accepted design-margin estimate
  — the existing HBM sizing (§2b's 222/444/667 µm clamp widths, already
  measured against the >=2 pF capacitance budget across the full window
  per `measurements/characterization.md`'s DR-0005 table) stands as the
  best available pre-silicon evidence, explicitly not presented as a
  qualification.
- **Option 2 (a narrower "bounded, cited ESD design-margin analysis" as a
  separate closable deliverable) is rejected as redundant, not wrong.**
  §2 of `design/esd-capacitance-budget.md` already *is* that analysis —
  bounded (HBM current-density range with two literature citations, CDM
  reported as "source silent" rather than guessed at), cited (every number
  traced to a PDK file/line or explicitly marked as external literature),
  and already landed. Opening a second issue to re-produce work already on
  file would not add evidence, only tracker overhead.
- **Option 3 (hold the row open/blocked on external data or silicon) is
  rejected as misleading.** "Blocked" in this repository's tracker
  vocabulary means an issue that becomes actionable once a specific,
  anticipated dependency resolves (`loom:blocked`, per
  `.loom/docs/label-state-machine.md`). Real HBM/CDM qualification is not
  waiting on a resolvable dependency this program controls or can forecast
  — it is waiting on tape-out itself, an event with no scheduled date in
  this repository's scope. Marking it "blocked" would imply near-term
  actionability that does not exist and would leave a permanently-open
  tracker item with no path to closure short of a fab run.

## Alternatives considered

- **Option 2, schedulable narrower deliverable** — considered and rejected
  above; the deliverable it would produce already exists in
  `design/esd-capacitance-budget.md` §2.
- **Option 3, genuinely blocked** — considered and rejected above; no
  resolvable near-term dependency exists to block on.
- **Leave the row's tracking ambiguous** (the state issue #145 was filed
  to resolve) — rejected because it is the status quo this record exists
  to fix: `measurements/characterization.md`'s own T1/bronze gap note
  already named this specific ambiguity as the individually-dispatchable
  remainder blocking a full tier re-read, and leaving it unresolved would
  only recur at the next T1 pass.

## Consequences

- **DR-0013 row 11's Basis column** (`spec/decisions/0013-operating-conditions.md:119`)
  is updated to cite this record alongside DR-0005/DR-0011, and its
  Existing-evidence column is updated to state the row's disposition
  (accepted pre-silicon limitation, not open work) instead of "future
  verification work."
- **`measurements/characterization.md`'s ESD-qualification row** (DR-0005
  table, §1) and its "Gap to T1 sim-validated (bronze)" note both cite this
  record and state explicitly that row 11 **does not block** this block's
  T1/bronze tier — the tier's remaining open item, per issue #145's own
  framing, is closed by this record's disposition, not by new simulation.
- **This record re-opens** if either of the two things that can actually
  close the underlying gap arrives: (a) real silicon and a physical
  HBM/CDM ESD test, or (b) a PDK-sourced electrical ESD dataset (failure
  current density, breakdown voltage, or snapback/trigger parameters) that
  did not exist at the time of this record. Either would let a future
  decision record supersede this one with a real qualification result
  instead of a design-margin estimate.
- No other spec row, measurement, or evidence record is touched. The
  capacitance-budget side of DR-0005/DR-0011 row 10 (`<= 2 pF/pad`) is
  already independently measured and passing (`measurements/characterization.md`'s
  DR-0005 table, landed-block-assembly row) and is unaffected by this
  record.

## Status

**Accepted.**
