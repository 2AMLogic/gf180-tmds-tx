# 0005 — PLL interface and the jitter budget levied on it

**Status:** Accepted 2026-08-05.

## Context

The PLL is designed in a sibling canary, not here (repo `CLAUDE.md`). What
this repo owes that block is a requirement it can design and verify against —
which means every line has to be a number, and the numbers have to be
derived, not asserted. A jitter budget invented to sound reasonable is worse
than none: it either over-constrains a block in another repo or, more likely,
under-constrains it and the failure shows up as a closed eye in silicon.

TMDS eye closure is what jitter buys, so the budget is derived from the eye.
At 720p60 the UI is 1/742.5 MHz = **1346.8 ps**.

The transmitter's total-jitter allowance at the source connector is taken as
**0.25 UI pk-pk at BER 1e-9**. This is the commonly-applied DVI 1.0 source
limit. **It could not be checked against the DVI 1.0 document, which is not
available in this environment** — recorded as `tmds-tx.md` §10 O-1. The
budget below is linear in this number, so if it turns out to be tighter,
every allocation scales by the same factor.

The block does not control the package, board, or connector, so some of the
0.25 UI must be reserved for them.

Total jitter converts from its components as TJ = DJ + 2·Q·RJ_rms, with
Q = 6.0 at BER 1e-9, i.e. TJ = DJ + 12.0·RJ_rms. Deterministic terms add
linearly (conservative); random terms combine root-sum-square.

Two block-specific facts feed in:

- The final 2:1 mux is **DDR** ([0003](0003-serializer-partition.md)): one
  data edge per clock edge. Clock duty-cycle error therefore transfers 1:1
  into output jitter. This makes duty cycle a first-class PLL requirement,
  not an afterthought — and, as it turns out, the single largest line in the
  budget.
- The link is **forwarded-clock**: the TMDS clock lane travels alongside the
  data, so jitter below the sink's clock-recovery tracking bandwidth is
  common to both and largely cancels.

## Decision

### Frequencies and electrical interface

| Item | Requirement |
|---|---|
| Reference | 27.000 MHz ±50 ppm, CMOS 3.3 V, duty 40–60% ([0002](0002-reference-clock-and-clock-mastership.md)) |
| Output, 480p | 135.00 MHz |
| Output, **720p60 (target)** | **371.25 MHz** |
| Output, 1080p60 (stretch) | 742.50 MHz |
| Output format | Differential, DC-coupled, CML-compatible; 300–500 mV single-ended swing; V_CM = 2.50 V ±0.20 V |
| Mode select / status | 2-bit mode input from this block; `lock` output to this block |
| Lock time | ≤ 100 µs from reference-valid or mode change |
| Frequency error | Exact integer ratio to the reference; no error beyond the reference's own |

The PLL's topology is its own choice. Integer-N with N ∈ {40, 55} (VCO
1080 / 1485 MHz) and a ÷2/÷4/÷8 post-divider is offered only as proof the
requirement is satisfiable.

### Budget

| Level | Allowance |
|---|---|
| Source TJ at the connector, BER 1e-9 | 0.25 UI = 336.7 ps pk-pk |
| Reserved for package / board / connector | 0.05 UI = 67.3 ps |
| **TJ at the pad — this block** | **0.20 UI = 269.4 ps pk-pk** |

Deterministic, ≤ 150 ps pk-pk:

| Source | ps | Derivation |
|---|---|---|
| PLL duty-cycle distortion | 54 | 50% ±1.0% of the 2.694 ns half-rate period = ±26.9 ps |
| PLL reference spurs | 18 | ≤ −40 dBc ⇒ θ_pk = 2·10^(−40/20) = 0.0200 rad ⇒ Δt_pp = θ_pk/(π·371.25 MHz) = 17.2 ps |
| Serializer path (mux select skew, clock distribution mismatch, data-dependent delay) | 45 | This block |
| Driver and pad (asymmetry, supply-noise-induced) | 30 | This block; C_PAD-driven ISI is <1 ps (`tmds-tx.md` §7) |
| **Sum** | **147** | |

Random, ≤ 9.9 ps rms (RSS):

| Source | rms |
|---|---|
| **PLL** | **≤ 7.0 ps** |
| Clock distribution, CML mux, driver supply sensitivity | ≤ 7.0 ps |
| RSS | 9.9 ps ⇒ ×12.0 = 118.8 ps pk-pk |

**TJ = 147 + 118.8 = 265.8 ps = 0.197 UI ≤ 0.20 UI.** With the reserve:
333 ps = 0.247 UI ≤ 0.25 UI.

### The requirement on the sibling PLL, in four numbers

| Form | Value |
|---|---|
| RMS jitter | **≤ 7.0 ps rms**, integrated 10 kHz – 200 MHz, at 371.25 MHz |
| Integrated SSB phase noise (equivalent) | **≤ −38.7 dBc**, 10 kHz – 200 MHz. σ_φ = 2π·371.25 MHz·7.0 ps = 16.33 mrad; ∫L·df = σ_φ²/2 = 1.333e-4 |
| Discrete spurs | **≤ −40 dBc**, any spur, any offset |
| Duty cycle | **50% ± 1.0%** over PVT |

The 10 kHz lower limit is conservative for a forwarded-clock link. That
observation may not be used to relax the number without a decision record in
this repo.

### 1080p60 is not levied

At 1485 Mbps, 0.20 UI = 134.7 ps. Random jitter is fixed in picoseconds, so
an unchanged 7.0 ps rms PLL alone consumes 118.8 ps of it, leaving 16 ps for
every deterministic source combined. 1080p60 would need roughly **≤ 3.5 ps
rms and ≤ 0.5% duty error**. Per [0001](0001-resolution-ladder.md), **that
requirement is not levied.** The ask on the sibling block is the table above
and nothing else.

## Alternatives considered

- **Levy the 1080p60-capable number (≈3.5 ps rms) so the stretch mode stays
  open.** Rejected: it roughly doubles the difficulty of a block in another
  repo for a mode this one does not promise. This is the specific failure
  [0001](0001-resolution-ladder.md) exists to prevent, and it is where that
  decision would have been violated first.
- **State the budget only as total jitter, letting the PLL block split it.**
  Rejected: total jitter is not additively decomposable across blocks —
  without a DJ/RJ split and a stated Q, two blocks each "meeting the budget"
  can combine to miss it. Splitting DJ (linear) from RJ (RSS) makes the
  arithmetic composable.
- **Specify jitter only as phase noise, or only as ps rms.** Rejected as a
  false economy: the PLL block may measure either, and the conversion is
  where sign and factor-of-two errors live. Both forms are stated, with the
  conversion shown, so a mismatch is visible rather than latent.
- **Integrate from the sink's clock-recovery bandwidth instead of 10 kHz**,
  which is the physically correct band for a forwarded-clock link and would
  relax the PLL number. Rejected: it makes this repo's requirement depend on
  an unknown property of an arbitrary sink. The conservative fixed band is
  verifiable by the PLL block on its own; the physics is recorded so the
  margin is understood rather than accidental.
- **Give the PLL a duty-cycle requirement looser than ±1% and correct it here
  with a duty-cycle corrector.** Rejected for now: a DCC at 371.25 MHz is a
  custom analog circuit with its own supply sensitivity, added to a block
  whose custom content is already the schedule risk. Worth revisiting if the
  PLL block reports ±1% is the binding constraint on its design — that would
  be a new decision record, not an edit to this one.

## Consequences

- The sibling PLL block has a bounded, verifiable requirement it can close
  against: four numbers plus three frequencies and a reference.
- **Duty cycle, not phase noise, is the largest single jitter line (54 of
  265.8 ps).** Anyone tempted to spend effort on the PLL's phase noise should
  look at its output divider first.
- The block's own 45 ps and 30 ps deterministic allocations are budgets, not
  results (`tmds-tx.md` §10, O-4). If either is exceeded, the overrun comes
  out of the block's own margin — it does not get pushed back onto the PLL.
- The 0.25 UI premise (O-1) is the budget's single point of failure. Every
  number here scales linearly with it, so verifying it against DVI 1.0 is the
  highest-value open item in the spec.
- Eye-diagram verification of the driver must inject this budget, not assume
  an ideal clock — a driver eye simulated from a jitter-free source proves
  nothing about the link.
