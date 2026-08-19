# DR-0012: Completing the PLL interface contract (successor to DR-0004)

**Status: Accepted.** Extends, does not replace, `spec/tmds-tx.md` §2 and
DR-0004 — DR-0004's Status line is updated to point here; its own numeric
derivations (reference frequency choice, 0.25/0.10/0.15 UI jitter split) are
**unchanged**.

**Numbering note**: see DR-0010's "Renumbering note" — this record was
issue #9's originally-drafted `DR-0008`, renumbered to avoid colliding with
the already-ratified, unrelated `DR-0008` (`tmds_encoder`'s two-stage
pipeline record).

## Context

`spec/tmds-tx.md` §2 specifies four PLL outputs (bit-rate and pixel-rate
clocks at both operating points), a 10:1 edge-aligned relationship, and a
jitter budget. DR-0003 (serialization/clocking) then requires clocks §2
never asks for:

- *"The final 2:1 multiplexer and the CML output driver itself are custom,
  clocked directly from the PLL's full-rate (742.5 MHz / 270 MHz) **and
  half-rate phases**"* — §2 levies no half-rate output and states no phase
  relationship for one.
- The synthesized domain runs at *"the pixel-domain-derived intermediate
  rate (5x pixel clock = 371.25 MHz @ 720p60)"* — §2 states neither a
  371.25 MHz output nor that this block derives it internally.

§2 also specifies a signal type for the reference input (single-ended CMOS,
±100 ppm) and **no signal type, swing, common-mode, or duty-cycle bound for
any output**. A sibling PLL canary could satisfy §2 to the letter and still
be unable to drive this block, because the mux input stage, the load the
PLL must drive, and a real slice of the jitter §2's own 0.15 UI allocation
has to absorb all depend on facts §2 does not state.

## Decision

### 1. Half-rate phase clocks and the 371.25 MHz synthesized-domain clock: both derived internally, not levied on the PLL

**This block derives its half-rate DDR clock and its synthesized-domain
clock from the PLL's bit-rate clock output by internal ÷2 division — the
PLL is not asked for either as a separate output.**

- **742.5 MHz ÷ 2 = 371.25 MHz** (720p60) and **270 MHz ÷ 2 = 135 MHz**
  (480p) are both produced by **one** internal divide-by-2 stage (a single
  toggle flip-flop clocked by the PLL's bit-rate clock output) inside this
  block. That one divider output serves **both** roles DR-0003 names:
  - the **half-rate phase clock** the final 2:1 multiplexer/CML driver
    stage uses (DR-0003's *"half-rate phases"*) — the multiplexer's DDR
    stage samples data on both edges of this internally-derived clock,
    reconstructing the full 742.5/270 Mbps bit-rate output from the
    synthesized domain's 2-bit-wide word;
  - the **371.25 MHz / 135 MHz synthesized-domain clock**, i.e. the clock
    tree root for the 10:1→2:1 reduction logic DR-0003 assigns to the
    standard-cell library.

  These are not two independent numbers that happen to match at 720p60 —
  742.5 MHz ÷ 2 and *"the intermediate rate = 5x pixel clock"* are the same
  371.25 MHz by construction (742.5 MHz = 10 x 74.25 MHz, so 742.5 MHz / 2 =
  5 x 74.25 MHz exactly), and the same identity holds at 480p (270 MHz / 2 =
  135 MHz = 5 x 27.000 MHz). One divider satisfies both DR-0003 clauses.
- **Rationale for internal derivation over a levied PLL output**: (a) a
  divide-by-2 toggle-flip-flop stage clocked from an already-supplied,
  already-jitter-budgeted clock adds no new PLL-attributable jitter budget
  line — it inherits the bit-rate clock's own period jitter exactly, with
  no additional cross-domain skew/jitter term to specify or verify against
  the sibling canary's own spec; (b) it keeps the PLL interface's total
  output count at two (bit-rate, pixel-rate) rather than four, honoring
  CLAUDE.md's scope-discipline instruction to specify the *minimum*
  interface this block actually needs of the PLL; (c) a toggle-flip-flop
  divider's output duty cycle is exactly 50% **by construction** (a single
  rising-edge-triggered T-flip-flop's high and low half-periods are each
  exactly one input-clock period), independent of the bit-rate clock's own
  duty cycle — see "Duty-cycle tolerance" below.
- **This is a design decision this block owns, not an open question left to
  the PLL's spec.** A sibling PLL canary satisfying §2's now-completed
  bit-rate/pixel-rate contract needs to do nothing further to support the
  half-rate/synthesized-domain clocks — they do not appear in its own
  interface at all.

### 2. Signal type, swing, and common-mode for every output

| Output | Signal type | Swing | Common-mode |
|---|---|---|---|
| Reference input (unchanged from §2) | Single-ended CMOS | Rail-to-rail (VDD-referenced) | N/A |
| Bit-rate clock (742.5 MHz / 270 MHz) | **Differential, low-swing (CML-compatible)** | **300–800 mV differential peak-to-peak** (`Proposed`) | **Compatible with this block's 3.3 V core-device family (DR-0002); nominal VDD/2 ~= 1.65 V** (`Proposed`) |
| Pixel-rate clock (74.25 MHz / 27.000 MHz) | **Single-ended CMOS, 3.3 V** | Rail-to-rail (VDD-referenced) | N/A |
| Half-rate/synthesized clock (371.25 MHz / 135 MHz) | **Not a PLL output** — internally derived, see Decision 1 | N/A | N/A |

- **Bit-rate clock: differential, low-swing.** At 742.5 MHz, a rail-to-rail
  single-ended CMOS clock would need an extra level-shift/buffer stage
  before it could drive the custom CML final-mux stage anyway, and would
  fight duty-cycle distortion and EMI at that edge rate. Specifying it as
  differential and CML-compatible from the PLL directly avoids that
  conversion stage and mirrors DR-0002's own driver-topology device family
  (3.3 V core devices) so no level shifter is required at the PLL-to-block
  boundary — the same reasoning DR-0003 already applied to picking the
  standard-cell library's 3.3 V corner over its 5 V corner. The 300–800 mV
  differential swing window is `Proposed`: it brackets a typical CML clock-
  buffer range without over-constraining the sibling canary's specific
  circuit choice; it is not measured against any implementation in this
  repository (there is none yet on the PLL side) and should be tightened
  once a sibling PLL canary's own driver stage is specified.
- **Pixel-rate clock: single-ended CMOS, 3.3 V.** This clock roots the
  synthesized domain's clock tree, which DR-0003 already fixes at the
  standard-cell library's 3.3 V corner. A CMOS clock input at the same
  supply is the natural, minimal-cost choice — no differential receiver is
  needed for a comparatively low-edge-rate (74.25 MHz maximum) digital
  clock, and it matches the reference input's own signal type for
  consistency.
- **Half-rate/synthesized clock: not applicable** — it is not a PLL output
  (Decision 1).

### 3. Duty-cycle tolerance

- **Bit-rate and pixel-rate PLL outputs**: **45–55% duty cycle** (`Proposed`
  — a standard working range for rising-edge-triggered synchronous digital
  logic, not derived from a specific timing-closure measurement). Neither
  output is sampled on both edges by this block, so this is a generous
  margin, not a load-bearing DDR-class requirement.
- **The half-rate DDR clock actually driving the final 2:1 multiplexer's
  both-edges sampling is not a PLL output** (Decision 1) — its duty cycle
  is governed entirely by this block's own internal toggle-flip-flop
  divider, which is exactly 50% by construction (see Decision 1's
  rationale). **No PLL-attributable duty-cycle budget applies to the signal
  the DDR stage actually samples on both edges** — this is the concrete
  payoff of choosing internal derivation over a levied PLL output: it moves
  the one duty-cycle-critical clock in this design entirely out of the
  PLL's own spec and onto a trivially-correct-by-construction internal
  divider.

### 4. Loading the PLL must drive

- **Bit-rate clock output**: drives (a) this block's internal ÷2 divider's
  clock input (negligible — one flip-flop clock-input gate capacitance,
  sub-fF to low single-digit fF at this process node) and (b) the custom
  final-mux/CML-driver stage's own clock-input buffer. **(b) is not yet
  characterized** — the driver's clock-input stage sizing is deferred to
  the driver design work (issue #11/#22 and successors) — so this is stated
  as an explicit gap, not asserted: as an interim placeholder, budget a
  purely capacitive load in the low single-digit-fF range per clock-input
  pin (`Proposed`, to be tightened once the driver's clock-input devices
  are sized).
- **Pixel-rate clock output**: drives this block's own top-level clock-tree
  root buffer (a single clock-input pin), not the full synthesized-domain
  clock tree directly — the digital PnR flow's own clock-tree synthesis
  (`flow/pnr_tmds_encoder.py`, per the existing, unrelated DR-0009's
  measured evidence) already characterizes everything downstream of that
  one root buffer. The PLL therefore presents one clock-input pin's
  capacitance to this block's top-level pixel-clock port, not a full-tree
  load.

DR-0004's 0.10 UI PLL-attributable / 0.15 UI this-block's-own jitter split
is **unchanged by this record**. The half-rate/synthesized clock's jitter
(Decision 1) is inherited directly from the bit-rate clock's own jitter (no
new PLL-attributable term), so it does not create a fifth jitter line to
budget — it is fully covered by the existing 0.10 UI allocation on the
signal it is divided from.

## Alternatives considered

- **Levy the half-rate phase clocks and the 371.25 MHz synthesized clock as
  two additional PLL outputs** (matching a literal reading of DR-0003's
  *"the PLL's ... half-rate phases"* as PLL-generated signals) was
  considered and rejected: it would require the sibling PLL canary to
  generate and maintain phase lock across *four* simultaneous outputs
  instead of two, adds at least one more cross-domain jitter/skew budget
  line this record would then have to define and verify, and buys nothing
  a single internal ÷2 divider does not already provide exactly (by
  construction, with zero additional jitter budget). Internal derivation is
  strictly simpler and, per CLAUDE.md's own scope-discipline instruction,
  the interface this block should specify is the *minimum* it actually
  needs.
- **Single-ended CMOS for the bit-rate clock output too** (matching the
  reference input's own signal type, for interface uniformity) was
  considered and rejected — at 742.5 MHz a rail-to-rail CMOS clock is a
  worse jitter/EMI starting point than a differential low-swing signal, and
  would force an extra buffer/level-shift stage this block would then have
  to specify and budget for anyway before the custom CML stage could use
  it.
- **Leave loading unspecified until the driver design lands** (rather than
  stating an explicit, honestly-provisional placeholder) was considered and
  rejected — Defect 3 in issue #9's own framing specifically calls out
  "the load the PLL must drive" as part of what makes §2 an incomplete
  contract; stating a `Proposed` placeholder and naming exactly what would
  tighten it is more useful to a sibling canary author than silence,
  consistent with this repo's "a `Proposed` row is honest and a fabricated
  one is not" convention (DR-0009's own operating-conditions framing,
  carried forward explicitly by DR-0013).

## Consequences

- A sibling PLL canary built against `spec/tmds-tx.md` §2 plus this record
  now has: every clock this block requires (two, not four), at both
  operating points, with signal type, swing, common-mode, and duty-cycle
  bounds for each, and an explicit statement of what load it must drive
  (with one item flagged `Proposed` pending this block's own driver design).
  It does **not** need to generate half-rate or synthesized-domain clocks —
  those are this block's own internal responsibility.
- §2's existing four rows (reference input, bit-rate output x2 operating
  points, pixel-rate output x2 operating points, clock relationship, and
  the three jitter-budget rows) are **unchanged** by this record — it adds
  columns/rows, it does not edit any existing cell. DR-0004's 0.25/0.10/
  0.15 UI split stands exactly as ratified.
- This block's own RTL (the not-yet-written 10:1→2:1 serializer and final
  2:1 mux, per the existing, unrelated DR-0009's closing note that this
  stage "is still unwritten and still unmeasured") must implement the
  internal ÷2 divider this record specifies, and its own testbench must
  verify the resulting half-rate clock's phase alignment to the bit-rate
  clock and 50% duty cycle directly — this record fixes the *architecture*
  of that derivation, not its RTL, which remains future work.

## Status

**Accepted.** Successor to DR-0004 (whose own numeric derivations are
unchanged) — `spec/tmds-tx.md`'s DR-0004 Status line now points here.
