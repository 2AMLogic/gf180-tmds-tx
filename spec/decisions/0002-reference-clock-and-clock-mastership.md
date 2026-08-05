# 0002 — 27 MHz reference; the transmitter is clock master

**Status:** Accepted 2026-08-05.

## Context

A TMDS transmitter needs a bit clock coherent with the pixel clock. There
are two ways to get one, and they levy very different requirements on the
sibling PLL block:

- **Slave**: the video source supplies the pixel clock; the PLL locks to it
  and multiplies ×10 (or ×5 for a half-rate clock). This is what commercial
  transmitter chips do, because they must accept whatever a graphics
  controller hands them. It requires a PLL with a wide capture range —
  25 MHz to 165 MHz of reference — that must stay locked as the reference
  moves.
- **Master**: the block runs from a fixed crystal reference, generates the
  pixel clock, and the video source is slaved to it. The PLL becomes a
  fixed-ratio synthesizer.

The PLL is out of scope here (repo `CLAUDE.md`), so this decision is
primarily a decision about *what to ask another team for*. A wide-capture
tracking PLL is a substantially harder block than a fixed integer-N
synthesizer, and asking for one is a real cost imposed outside this repo.

27.000 MHz is the conventional video reference. From it,
[0001](0001-resolution-ladder.md)'s three pixel clocks are exact integer
ratios (`×1`, `×11/4`, `×11/2`), so the whole ladder is reachable with
integer-N synthesis and no fractional divider.

The video source for this canary is a testbench and, at silicon, an
FPGA — both of which can be slaved to an external pixel clock trivially.

## Decision

1. **Reference: 27.000 MHz ±50 ppm**, single-ended CMOS at 3.3 V, duty
   40–60%. The reference feeds the PLL, not this block directly.
2. **This block is the clock master.** It divides the PLL's half-rate serial
   clock by 5 to produce `pix_clk_o`, drives it out, and the video source is
   synchronous to it.
3. **The PLL is a fixed-ratio synthesizer**, selected by a 2-bit mode code
   this block drives (`pll_mode_o`). It is not required to track a moving
   reference.
4. **Fractional-N is out of scope.** Only exact integer ratios of 27.000 MHz
   are supported — which is the mechanism behind
   [0001](0001-resolution-ladder.md)'s exclusion of the `÷1.001` variants and
   of 640×480p60.

## Alternatives considered

- **Slave to an incoming pixel clock (PLL locks to 25–165 MHz).** Rejected:
  it converts the sibling PLL from a fixed-ratio synthesizer into a
  wide-capture tracking PLL, and moves the reference-jitter problem from a
  crystal (well-characterized, ~0 ps) to whatever the source supplies
  (unknown, and now inside our jitter budget). The cost is borne by another
  repo, for flexibility this canary does not need. This is the alternative to
  revisit first if the block is ever productized.
- **Second reference oscillator at 25.175 MHz to cover the DVI failsafe
  mode.** Rejected: two crystals, a reference mux inside the PLL, and a
  second lock sequence, for a mode [0001](0001-resolution-ladder.md) already
  declined.
- **Fractional-N from 27 MHz.** Rejected: fractional spurs land directly in
  the jitter budget ([0005](0005-pll-interface-and-jitter-budget.md) allows
  only 18 ps pk-pk, i.e. −40 dBc, for *all* spurs), and delta-sigma noise
  shaping raises the in-band phase noise the budget is already tight on. Not
  worth it for modes we do not need.
- **Generate the pixel clock in the video source and the bit clock here, both
  from the same crystal, unlocked.** Rejected: two independent dividers with
  no phase relationship means a FIFO and an elastic buffer, which is a video
  problem, not a transmitter problem.

## Consequences

- **The block cannot accept an externally-timed video stream.** The source
  must accept `pix_clk_o`. This is the single largest functional limitation
  of the block and is stated in `tmds-tx.md` §8 rather than left implicit.
- The requirement levied on the sibling PLL block is bounded and
  conventional: fixed reference, three fixed output frequencies, integer
  ratios.
- The pixel clock is phase-coherent with the serializer by construction (it
  is a ÷5 of the same clock), so there is no clock-domain crossing between
  the encoder and the serializer — a whole class of metastability and FIFO
  work does not exist in this block.
- `pix_clk_o` is a 74.25 MHz output that must be driven off-chip at silicon,
  so the pad list in `tmds-tx.md` §8 owes it a pad. That is #2's to finalize.
