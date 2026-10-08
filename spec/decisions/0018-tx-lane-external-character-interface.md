# DR-0018: Per-lane external 10-bit character input and source select (DR-0016 Option A enabler)

**Status: Proposed.** Implements the interface requirement DR-0016 (Accepted,
Option A) levies on the block-level top; adds no parameter to
`spec/tmds-tx.md` §1 and relaxes nothing. Needs the usual ratification.

## Context

DR-0016 keeps this block a DVI-mode TMDS transmitter and places any packet or
character layer beyond the DVI baseline in the consumer's digital block. That
split needs this block to accept finished 10-bit characters from outside.
Issue [#186](https://github.com/2AMLogic/gf180-tmds-tx/issues/186) asks for the
per-lane port and a select between it and `rtl/tmds_encoder.v`'s output. No
ratified block-level top exists; DR-0014 leaves which domain implements the
10:1 -> 2:1 reduction rate-dependent. This record therefore defines a **digital
per-lane module**, `rtl/tmds_tx_lane.v`, not the physical/custom-domain top.

## Decision

1. **Module.** `tmds_tx_lane` instantiates `tmds_encoder`, one 10-bit register
   `tmds_q` fed by a 2:1 mux, and `tmds_serializer` (whose `tmds` input is
   `tmds_q`). Ports: `clk_bit`, `clk_pix`, `rst`, `data[7:0]`, `ctrl[1:0]`,
   `de`, **`ext_tmds[9:0]`**, **`ext_sel`**, observation outputs `tmds_enc`
   and `tmds_char`, and `clk_half`, `ser[1:0]`. Three lanes are three
   instances sharing clocks and reset.
2. **Runtime select, with static tie-offs.** `ext_sel` is a runtime input
   (default `SEL_MODE = 2`); parameter values `0` (encoder only) and `1`
   (external only) elaborate the static configurations, ignoring `ext_sel`.
   Reasoning: the consumer's character layer alternates sources at pixel
   granularity (it supplies some periods and the encoder supplies the rest);
   a build-time select would force the consumer to duplicate the encoder or
   mux outside this block. The static modes exist for blocks that need no
   switching, and elaborate to a smaller netlist.
3. **Sampling and permitted changes.** `ext_sel`, `ext_tmds` and the encoder
   character are sampled at the same `clk_pix` edge into `tmds_q`. Every
   character leaving `tmds_q` therefore comes wholly from one source, and
   `ext_sel` may change at any `clk_pix` boundary. `ext_sel` must meet
   `clk_pix` setup/hold (be driven from a `clk_pix` register); it is not
   synchronised here. The mux feeds only D inputs, so there is no glitch path.
4. **Timing contract at `ext_tmds`.** Same as `tmds_encoder`'s `tmds`
   ("registered TMDS character, one per clk"): one character per `clk_pix`
   cycle, bit 0 first, driven from a `clk_pix` register, stable for the cycle.
5. **Alignment and latency.** The wrapper does not delay-match sources. The
   encoder output at an edge is the character for the input presented four
   `clk_pix` earlier (DR-0009); the producer aligns `ext_tmds` to the slot it
   replaces. `tmds_q` adds **one `clk_pix` cycle to both paths**, so
   switching never changes latency and the three lanes stay aligned.
   `ext_tmds` -> serializer input: 1 `clk_pix`; `data`/`de`/`ctrl` ->
   serializer input: 5; the serializer's own 3 `clk_half` to first bit on
   `ser` is unchanged.
6. **Serializer capture.** `tmds_q` changes only on `clk_pix` edges and holds
   for a full pixel period, exactly like the encoder output it replaces, so
   the serializer's half-rate load on its detected pixel boundary is
   unchanged. `tmds_serializer.v` and `tmds_encoder.v` are not modified.
7. **Reset.** `rst` clears `tmds_q` to 0 (the serializer's reset value) and
   is passed to both children. 0 is not a valid TMDS character and appears
   only while reset is asserted and for the characters in flight; no source
   change produces it.
8. **Content boundary.** No HDMI-defined content (no TERC4, guard bands,
   preambles, packets). Nothing here claims HDMI compliance.

## Alternatives considered

- **Static-only select.** Rejected for the reason in Decision 2.
- **Combinational mux after the two registered words (no `tmds_q`).** Saves
  one `clk_pix` of latency but puts the mux and `ext_sel` fan-in on the path
  into the serializer's half-rate capture. Rejected; one cycle on both paths
  is cheap and keeps the capture window as it is.
- **Select applied inside `tmds_encoder`.** Rejected; the encoder is ratified
  and verified, and this wraps rather than alters it.

## Consequences

- New: `rtl/tmds_tx_lane.v`; `verification/tmds_serializer/` exercises all
  three `SEL_MODE` values with an independent per-cycle scoreboard (source
  selection, 0/all-ones/alternating words, consecutive characters, reset,
  select changes at adjacent boundaries) and the existing negative control.
- **Simulation shows function, not physical timing.** 720p60 timing closure
  and custom-domain integration stay separate work under DR-0014; at 720p60
  the serializer is the executable reference model for the custom stage.
- The 5-cycle encoder-to-serializer latency replaces the former 4; nothing
  ratified states a total lane latency.

## Status

**Proposed.**
