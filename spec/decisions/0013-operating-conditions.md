# DR-0013: Operating conditions and the verifiable spec rows

**Status: Accepted.**

**Numbering note**: see DR-0010's "Renumbering note" — this record was
issue #9's originally-drafted `DR-0009`, renumbered to avoid colliding with
the already-ratified, unrelated `DR-0009` (`tmds_encoder`'s four-stage
pipeline record). This is also the record `spec/tmds-tx.md`'s *existing*,
unrelated DR-0006 (common-mode supply-tracking) itself anticipated under the
name "DR-0009" in its own Consequences section — see this record's Status
below for how that forward reference is corrected, and see `sim/README.md`
and `design/cml-driver-sizing.md`, both of which independently anticipated
this same record under the name "DR-0009" for the same reason.

## Context

The T1 evidence rung (`2AMLogic/klayout-tools`,
`docs/design-evidence-tiers.md`) requires *"corner-matrix results covering
every spec row at its bound corners, with per-row pass/fail and the binding
corner recorded."* `spec/tmds-tx.md` states **no operating temperature
range, no supply tolerance, and no process-corner list** anywhere — so, per
`sim/README.md`'s own honest framing before this record, *"no PVT matrix is
derivable from the ratified spec today."* Every PVT-matrix result this
repository has actually recorded (`sim/harness/corners.py`,
`sim/cml-driver-eye/`, `sim/esd-clamp-cv/`, `sim/smoke-cml-pair/`, and the
digital-partition STA sweeps behind `spec/tmds-tx.md`'s existing DR-0007/
0008/0009) has been run against a **working default** matrix ported
verbatim from `2AMLogic/gf180-bandgap`, explicitly documented as *"a working
default pending ratification, not a spec-derived requirement"* — this
record is that ratification.

Relatedly, §1's parameter table gives little the corner matrix can grade
against on the analog side: DR-0002 supplies swing (400–600 mV) and
common-mode (2.8–3.3 V, now qualified by the existing DR-0006's supply-
tracking derating), and §2/DR-0004 supply the PLL-and-this-block's-own
jitter split — but there is no rise/fall-time bound, no statement of what
constitutes a passing eye, and no output-impedance/return-loss row, for a
transmission-line-driving block on a program whose rule is "no claim
without a testbench."

## Decision

### 1. The PVT matrix

**Ratifies the existing working default verbatim, unchanged.** This is a
tightening/formalizing move, not a new requirement — every analog record
this repository has already produced was run against exactly this matrix,
so ratifying it invalidates nothing:

| Axis | Value |
|---|---|
| Temperature | **−40 °C, 27 °C, 125 °C** |
| Supply tolerance | **±10 %** of nominal (i.e. 2.97 V / 3.30 V / 3.63 V for the 3.3 V domain) |
| Process corners (minimum, every recorded result) | **The 5 classic MOS corners**: `tt`, `ff`, `ss`, `fs` (fast-N/slow-P), `sf` (slow-N/fast-P) — `sim/harness/corners.py`'s `mos` corner set |
| Process corners (required in addition, for any claim depending on resistor or BJT device parameters) | `res_ff`, `res_ss` (resistor sheet-rho skew), `bjt_ff`, `bjt_ss` — `sim/harness/corners.py`'s `full` corner set |
| Bit-rate axis (this block's own adaptation, not part of the source harness) | **742.5 Mbps/lane (720p60 target) and 270 Mbps/lane (480p fallback)**, cross-producted with every axis above — a result at one rate is not evidence for the other |

**Binding corner, current-mode driver**: per the existing measured evidence
(`design/cml-driver-sizing.md` §7/§8), the worst-case corner for this
block's swing/common-mode/device-stress rows is consistently
`ss_-40c_2.97v` or `ss_125c_2.97v` — slow process, either temperature
extreme, **low** supply (2.97 V, −10 %). This is the expected binding corner
for a current-mode driver whose output swing is `I_tail x R_leg`: low supply
tightens headroom for the tail-current source and the switch pair
simultaneously, and slow process lowers available `g_m`/increases `V_ov`
requirements at fixed current. Future records should expect this corner to
bind unless a specific row's physics argues otherwise, and should still run
the full matrix rather than assume it in advance.

**Why this and not a fresh derivation**: `spec/tmds-tx.md` states no
supply/temperature/process bound to derive from, and CLAUDE.md instructs
following *"the program's existing matrix unless there is a reason not to."*
No such reason surfaced in this survey — every sibling block in this
program (`gf180-bandgap`, `gf180-gate-driver`) already uses this exact
temperature/supply spread, and this block's own working-default harness
already implements it. Adopting it as-is is the conservative, evidence-
consistent choice.

### 2. The supply spec

- **This block's own 3.3 V domain** (the driver's core devices, DR-0002; the
  synthesized digital domain, DR-0003): **nominal 3.3 V, ±10 % tolerance**
  (2.97–3.63 V) — matching the PVT matrix above. This is the *"gf180mcu 3.3 V
  flavor"* `sim/harness/corners.py` already names as its `DEFAULT_NOMINAL_
  SUPPLY_V` and `DEFAULT_SUPPLY_TOLERANCE`, now ratified into the spec
  itself rather than living only in harness code comments.
- **The receiver-side 3.3 V termination rail** (`AVCC` in
  `design/cml-driver-sizing.md`'s own notation — the rail DR-0002's 50 Ω/leg
  termination returns to, and the rail the existing DR-0006's common-mode
  supply-tracking derating is stated against): **nominal 3.3 V, ±10 %
  tolerance, by the same convention as this block's own domain** (`Proposed`
  — no external receiver specification is cited or assumed beyond "the same
  3.3 V flavor, same tolerance," since a real DVI/HDMI-class receiver's own
  rail tolerance is not established anywhere in this repository; this is
  the working assumption every `AVCC`-sensitivity measurement this repo has
  taken already uses). §1 never bounded this rail at all before this
  record — DR-0002 only ever *assumed* it exists.

### 3. The verifiable spec rows

Every row below is either an existing, already-cited spec target (pulled
into one table so the corner matrix has a single place to grade against) or
a new row this survey found the spec lacking, each carrying its own
citation or an explicit `Proposed` mark per CLAUDE.md's "no fabricated
target" instruction.

| # | Row | Target | Citation / status | Existing evidence (if any) |
|---|---|---|---|---|
| 1 | Single-ended output swing | 400–600 mV | DR-0002 (Accepted) | `sim/cml-driver-eye/records/20260810-041436-a2c358b.md`: **PASS**, 481.2–518.9 mV across the full matrix, both rates, 0/1/2 pF pad cap |
| 2 | Common-mode (nominal `AVCC` = 3.3 V) | 2.8–3.3 V | DR-0002 as qualified by the existing DR-0006 (Accepted) | Same record: **PASS**, 3.041–3.054 V at nominal supply; `design/cml-driver-sizing.md` §8: **PASS** against DR-0006's supply-tracking derating at `AVCC` ±10 % (2.711–2.725 V / 3.370–3.384 V measured, both consistent with `AVCC − I_tail x R_leg / 2`) |
| 3 | Total TMDS output jitter (informative, DVI-class) | <= 0.25 UI p-p | DR-0004 (Accepted, informative — not independently re-derived from a formal DVI 1.0 citation) | Not directly measured as a single end-to-end number in this repo (the PLL side does not exist yet); this block's own contribution is measured (row 4 below) |
| 4 | This block's own jitter contribution | <= 0.15 UI p-p | DR-0004 (Accepted) | Same eye record: **PASS**, deterministic-jitter contribution 2.97e-6–3.56e-5 UI matched-leg, 1.337e-3 UI worst deliberately-mismatched-leg probe — margin >=100x the allocation in every measured case |
| 5 | 10–90 % output rise/fall time | **<= 20 % of the operating UI** (≈ 269 ps @ 742.5 Mbps, ≈ 741 ps @ 270 Mbps) | `Proposed` — engineering judgement: a common serial-link rule of thumb bounding transition time to a fraction of the unit interval so eye opening is not consumed by transition slope, not derived from a formal DVI 1.0 rise/fall citation (none is cited anywhere in this repository) | `design/cml-driver-sizing.md` §5/§8: measured 40.5–59.3 ps (0 pF pad) rising to 205.9–251.6 ps (2 pF pad, DR-0005/0011's full capacitance budget) across the full matrix, both rates. **PASS at every measured point against the `Proposed` bound above** — worst case (251.6 ps @ 742.5 Mbps) is 93 % of the 269 ps bound, i.e. a real but narrow (~7 %) margin at the tightest pad-cap point and target rate; comfortably passing at 270 Mbps (741 ps bound) |
| 6 | Passing-eye criterion | `Proposed` — eye height >= 50 % of the row-1 swing floor (>= 200 mV, using the 400 mV DR-0002 minimum) **and** eye width >= (1 − row-3's 0.25 UI budget) = **>= 0.75 UI**, both measured simultaneously at the eye's widest opening, no fixed sampling instant assumed | `Proposed` — derived arithmetically from already-ratified rows 1 and 3 (not an independent citation; no formal DVI 1.0 eye-mask figure is cited anywhere in this repository) | No existing record in this repository constructs a full statistical eye (ISI + random-pattern) combining swing and jitter simultaneously — `sim/cml-driver-eye/` measures swing and deterministic jitter as separate quantities (rows 1 and 4), not a combined eye-mask pass/fail. This is a genuine gap flagged, not silently closed, by this record — a future eye-diagram testbench should grade against this row directly |
| 7 | Single-ended output impedance / return loss | **N/A by design, not `Proposed`** — see rationale below | Measured (`design/cml-driver-sizing.md` §8): `ro_leg` (single-ended small-signal output resistance looking back into each leg) = 11.0–56.8 kOhm across the full matrix, always **>= 220x** the 50 Ω external termination | See below |
| 8 | Device voltage stress (`Vgs`/`Vgd`/`Vds`) | <= 3.63 V rated (3.3 V core devices, +10 % supply corner), positive margin required | DR-0002 (device family), this record (rating basis) | `design/cml-driver-sizing.md` §7: **PASS**, worst measured 2.761 V (`vds_sw_max`, `ss_-40c_2.97v`) against the 3.63 V rating |
| 9 | Tail current | 8–12 mA (this cell's own derived tolerance around the ~10 mA nominal §1 states) | §1 (Accepted, nominal only) / `design/cml-driver-sizing.md` §2 (tolerance derivation) | Same eye record: **PASS**, 9.822–10.327 mA across the full matrix (rate-independent) |
| 10 | Pad capacitance budget | <= 2 pF per data/clock pad | DR-0005/0011 (Accepted, unrelaxed) | `design/esd-capacitance-budget.md`: clamp alone **PASS** (0.240–0.822 pF); full budget against a realistic 25x25 um bond pad **FAILS** (7.95 pF, ~4.0x over) — reported as a finding, not silently relaxed, per the operator's 2026-08-14 guardrail; #87's own redesign scope, unchanged by this record |
| 11 | ESD | HBM >= 2 kV, CDM >= 500 V | DR-0005/0011 (Accepted, unrelaxed) | Not yet independently HBM/CDM-simulated end to end in this repository — the clamp-device *class* is now signed off (DR-0011), the pulse-level ESD event itself is future verification work |

**Row 7's rationale**: DR-0002's topology is current-mode, open-drain,
intentionally **not** source-matched to the 50 Ω termination the way a
voltage-mode driver would be — the 50 Ω/leg termination lives on the
*receiver* side of the channel, and a good current-mode driver is supposed
to present a *high* output impedance so its delivered current (and hence
swing) is set by the tail current source, not by a matched-impedance
divider with the termination. The measured `ro_leg` (>= 220x the
termination) confirms this design intent is met, not violated. A
traditional "output impedance / return loss at the transmitter's own
reference plane" row, as would apply to a voltage-mode 50 Ω driver, is
therefore **not a meaningful pass/fail criterion for this topology** — it
is marked `N/A by design`, distinct from `Proposed` (which would imply a
number is simply missing and should eventually be supplied). Return loss
for this channel is instead governed by the *receiver's* own termination
quality (off-block, out of scope for this repository) and by the pad/board
parasitics already captured in row 5's bandwidth analysis.

## Alternatives considered

- **Derive a fresh PVT matrix from first principles** (rather than adopting
  the program's existing default) was considered and rejected — CLAUDE.md
  explicitly instructs following the existing matrix absent a stated reason
  not to, no such reason surfaced, and every analog result this repo has
  already recorded was taken against exactly this matrix; deriving a
  different one now would retroactively orphan that evidence.
- **Invent numeric values for rise/fall, eye-mask, and return loss** (rather
  than marking them `Proposed`/`N/A by design`) was considered and rejected
  outright — CLAUDE.md forbids "laundering a guess as a standard," and this
  repo's own convention (DR-0004's informative jitter figure) already
  established the pattern of stating a target's provenance honestly rather
  than presenting an unsourced number as authoritative.
- **Treat `ro_leg`'s high measured value as a `Proposed` return-loss row
  needing a numeric target** was considered and rejected in favour of the
  `N/A by design` framing — a current-mode driver's high output impedance
  is a design *feature*, and grading it against a voltage-mode-style
  return-loss target would be grading the wrong physics, not merely an
  unmeasured one.
- **Fold the receiver-side `AVCC` tolerance into DR-0002 directly** (rather
  than stating it here) was considered and rejected — DR-0002 is a driver-
  topology decision, and §1 never bounded any supply tolerance at all; this
  is exactly the operating-conditions gap this record exists to close, so
  it belongs here.

## Consequences

- `sim/harness/corners.py`'s `DEFAULT_TEMPERATURES_C`,
  `DEFAULT_SUPPLY_TOLERANCE`, `DEFAULT_NOMINAL_SUPPLY_V`, and the `mos`/
  `full` corner sets are now a **spec-derived requirement**, not a working
  default — `sim/README.md`'s own "working default, pending #9 ratification"
  framing is corrected accordingly (see the accompanying edit to that file).
- `design/cml-driver-sizing.md` §7's *"reported per issue #9"* framing for
  its §8 rows (rise/fall, `ro_leg`, `AVCC` sensitivity) is now resolved:
  rise/fall is row 5 above (spec-bound, `Proposed` target, existing evidence
  passes it), `ro_leg` is row 7 (`N/A by design`, not a missing target), and
  `AVCC` sensitivity is already governed by the existing DR-0006. This
  record does not edit `design/cml-driver-sizing.md`'s own text (out of
  scope for a spec-only issue) — a future touch of that document should
  update its own forward references to name this record directly.
- Row 6 (passing-eye criterion) is a genuine, flagged gap: no existing
  record in this repository measures a combined swing+jitter eye directly.
  A future eye-diagram testbench is the natural place to close it, grading
  against the arithmetic criterion this record derives from rows 1 and 3.
- No target in the ratified spec is relaxed by this record. Rows 1–4, 8–11
  restate already-accepted targets (tightening their citation, not their
  value); rows 5–7 are net-new, and row 7 is explicitly a "does not apply"
  finding rather than a softened requirement.

## Status

**Accepted.** Fixes the forward reference in `spec/tmds-tx.md`'s existing
DR-0006 (Consequences: *"If issue #9's proposed DR-0009 ... lands"*) — that
record landed as **this** record, DR-0013, not DR-0009 (see this record's
own "Numbering note" and DR-0010's "Renumbering note" for why); DR-0006's
Status line is updated with a pointer to this record rather than its
Consequences prose being rewritten, per the "Status lines only" edit
convention this issue's own acceptance criteria establishes.
