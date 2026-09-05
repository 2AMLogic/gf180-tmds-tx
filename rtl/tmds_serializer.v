// -----------------------------------------------------------------------
// tmds_serializer.v -- DR-0003's synthesized 10:1 -> 2:1 parallel-to-serial
// reduction for one TMDS lane, plus DR-0012 Decision 1's internal
// divide-by-two clock derivation.
//
// This is a DVI-mode TMDS transmitter component, not an HDMI part -- see
// CLAUDE.md, "On HDMI, and what may be said".
//
// Where this sits
// -----------------------------------------------------------------------
// `rtl/tmds_encoder.v` produces one registered 10-bit TMDS character per
// pixel clock. The pad-side `cml_driver` (design/cml_driver.sch) wants a
// full-rate differential bit stream. Between them, spec/tmds-tx.md DR-0003
// puts two stages:
//
//   encoder --[10 bits @ pixel rate]--> THIS MODULE --[2 bits @ half rate]-->
//       custom final 2:1 DDR multiplexer (design/tmds_final_mux.sch)
//       --[1 bit @ bit rate]--> cml_driver
//
// and DR-0012 Decision 1 fixes the clocking: this block derives its own
// half-rate clock from the PLL's bit-rate clock with ONE internal
// divide-by-two toggle flip-flop, and that single divider output serves
// both as the half-rate DDR clock the custom multiplexer samples on both
// edges AND as the clock-tree root of this synthesized reduction. Both
// roles are the same net here: `clk_half`.
//
//   720p60: clk_bit 742.5 MHz -> clk_half 371.25 MHz (= 5 x 74.25 MHz)
//   480p:   clk_bit 270.0 MHz -> clk_half 135.00 MHz (= 5 x 27.000 MHz)
//
// READ THIS BEFORE USING THIS MODULE AT 720p60
// -----------------------------------------------------------------------
// `spec/decisions/0014-serializer-rate-ceiling-and-microarchitecture.md`
// records a measured result that constrains where this module can be used:
// on `gf180mcu_fd_sc_mcu9t5v0` at the 3.3 V corners DR-0003 selects, the
// register-to-register floor (launch clock-to-Q + capture setup, with ZERO
// logic between the flops) is 3.1199 ns at `ss_125C_3v00` -- measured, not
// estimated, by this repository's own post-route STA
// (`flow/tmds_encoder/records/20260817-110611-37e197a.md`, the numbers
// `flow/synth_tmds_encoder.py`'s `SEQUENTIAL_OVERHEAD_NS` is derived from).
// That floor is above the 2.6936 ns period 371.25 MHz needs and far above
// the 1.3468 ns period the divider's own 742.5 MHz clock needs. So:
//
//   - At **480p** (135 MHz reduction clock, 270 MHz divider clock) this
//     module is a synthesizable implementation of DR-0003 as ratified.
//   - At **720p60** it is NOT synthesizable on this library, and DR-0014
//     moves both the divider and the reduction into the custom (CML)
//     domain there. This RTL then serves as the executable REFERENCE MODEL
//     for that custom stage -- the bit ordering, the character boundary and
//     the 2-bit word cadence a CML implementation must reproduce exactly.
//
// Nothing about that is hidden in a comment: DR-0014 is the ratified
// record, `flow/serializer_rate_feasibility.py` is the reproducible
// measurement, and `verification/tmds_serializer/` verifies the function at
// both operating points regardless of which domain implements it.
//
// Micro-architecture (DR-0014): loadable shift register, not a tree mux
// -----------------------------------------------------------------------
// Two structures reduce 10 bits to 2 bits per cycle:
//
//   (a) a 10-bit shift register shifted right by two each cycle, with a
//       parallel load on the character boundary -- register-to-register
//       path is one 2:1 multiplexer deep;
//   (b) a 10-bit holding register plus a 5:1 output multiplexer selected by
//       a modulo-5 phase counter -- register-to-register path is one 5:1
//       multiplexer (a mux4 + mux2, or three mux2 levels) deep.
//
// (a) is chosen. On the library's own `ss_125C_3v00` arcs a
// `gf180mcu_fd_sc_mcu9t5v0__mux2_2` I0->Z delay is 1.192 ns against a
// 2.6936 ns period whose sequential overhead alone is 3.1199 ns -- every
// extra multiplexer level is a first-order loss, and (b) needs at least two
// more of them for no functional benefit. (a) also needs no phase counter
// in the datapath at all: the character boundary comes from the pixel clock
// directly (below), so there is no counter-to-mux path to close either.
//
// Character boundary: derived from `clk_pix`, not from a free-running count
// -----------------------------------------------------------------------
// `clk_half` is exactly 5x `clk_pix` and edge-aligned to it by construction
// (both descend from the same PLL bit-rate clock -- spec/tmds-tx.md #2's
// 10:1 edge-aligned relationship, DR-0012 Decision 1's divide-by-two), so a
// two-flop edge detector on `clk_pix` in the `clk_half` domain fires exactly
// once per character and self-aligns after reset. A free-running modulo-5
// counter would need its phase to be established by reset timing and would
// stay wrong forever if it ever slipped; this cannot slip, because the
// boundary is re-derived from `clk_pix` every character.
//
// The two-flop delay is also what makes the encoder-to-serializer handoff
// comfortable: `tmds` is sampled two `clk_half` cycles AFTER the pixel edge
// that produced it, not on that edge, so the path from the encoder's output
// register has two half-rate clock periods to settle rather than being a
// same-edge capture.
//
// Interface and behavior
// -----------------------------------------------------------------------
//   - `clk_bit`: the PLL's bit-rate clock (DR-0012 section 2). Clocks the
//     divide-by-two flip-flop and nothing else.
//   - `clk_pix`: the PLL's pixel-rate clock; also the encoder's clock. Used
//     here only as a character-boundary reference, sampled in the
//     `clk_half` domain.
//   - `rst`: active-high, applied in both domains, but NOT with the same
//     flavour in each -- see "Reset" below.
//
// Reset: synchronous on the divider, asynchronous-assert on the datapath
// -----------------------------------------------------------------------
// `rtl/tmds_encoder.v` uses a purely synchronous reset and this module
// deliberately does not, for a reason specific to a clock divider: `rst`
// holds `div_q` low, which HOLDS `clk_half` LOW. A synchronous reset in the
// `clk_half` domain would therefore never take effect -- the domain's own
// clock is stopped for exactly as long as the reset is asserted, and by the
// time `clk_half` edges resume, `rst` has already been released. The
// datapath registers would come out of reset holding whatever they held
// before it, which is precisely what a reset exists to prevent (and, in
// simulation, X).
//
// So the datapath uses the standard asynchronous-assert / synchronous-
// deassert form (`always @(posedge clk_half or posedge rst)`): assertion
// does not need a clock edge, deassertion is sampled by `clk_half` like any
// other synchronous release. The divider itself keeps the synchronous form,
// because `clk_bit` is free-running and never stops. This asymmetry is not
// stylistic drift from the encoder -- it is forced by the fact that this
// module gates the clock of one of its own domains.
//   - `tmds[9:0]`: the encoder's registered character.
//   - `clk_half`: the divide-by-two output. DR-0012 Decision 1's half-rate
//     DDR clock AND this module's own clock-tree root.
//   - `ser[1:0]`: the 2-bit word the custom multiplexer emits over one
//     `clk_half` period -- `ser[0]` on the high half, `ser[1]` on the low
//     half. TMDS transmits LSB first, so `ser[0]` carries the lower-indexed
//     bit of the pair.
//   - Latency from a `clk_pix` rising edge to the first bit of that
//     character appearing on `ser` is three `clk_half` cycles (two for the
//     edge detector, one for the output register).
//
// Verilog dialect
// -----------------------------------------------------------------------
// Verilog-2005, no vendor extensions -- same rule as `rtl/tmds_encoder.v`,
// so this file is consumed unmodified by both Icarus Verilog
// (verification/tmds_serializer/) and Yosys.
// -----------------------------------------------------------------------

module tmds_serializer (
    input  wire       clk_bit,  // PLL bit-rate clock (742.5 MHz / 270 MHz)
    input  wire       clk_pix,  // PLL pixel-rate clock (74.25 MHz / 27 MHz)
    input  wire       rst,      // synchronous, active-high, both domains
    input  wire [9:0] tmds,     // registered TMDS character from tmds_encoder
    output wire       clk_half, // internally derived half-rate DDR clock
    output wire [1:0] ser       // 2-bit word at the half rate, ser[0] first
);

  // -----------------------------------------------------------------
  // DR-0012 Decision 1: the one internal divide-by-two. A single
  // rising-edge toggle flip-flop, so its output's high and low half-periods
  // are each exactly one `clk_bit` period -- a 50% duty cycle by
  // construction, independent of `clk_bit`'s own duty cycle, which is
  // precisely the property DR-0012 relies on to keep the DDR stage's
  // duty-cycle requirement out of the PLL's spec.
  // -----------------------------------------------------------------
  reg div_q;

  always @(posedge clk_bit) begin
    if (rst) div_q <= 1'b0;
    else div_q <= ~div_q;
  end

  assign clk_half = div_q;

  // -----------------------------------------------------------------
  // Character boundary: `clk_pix` sampled in the `clk_half` domain.
  // -----------------------------------------------------------------
  reg pix_d;
  reg pix_dd;
  wire pix_edge = pix_d & ~pix_dd;

  // -----------------------------------------------------------------
  // The reduction itself: a 10-bit register that either loads a fresh
  // character or shifts right by two. Zeros are shifted in; they are never
  // observed, because the load happens every fifth cycle, exactly when the
  // fifth pair has been consumed.
  // -----------------------------------------------------------------
  reg [9:0] sh;
  reg [1:0] ser_q;

  always @(posedge clk_half or posedge rst) begin
    if (rst) begin
      pix_d  <= 1'b0;
      pix_dd <= 1'b0;
      sh     <= 10'd0;
      ser_q  <= 2'd0;
    end else begin
      pix_d  <= clk_pix;
      pix_dd <= pix_d;
      sh     <= pix_edge ? tmds : {2'b00, sh[9:2]};
      ser_q  <= sh[1:0];
    end
  end

  assign ser = ser_q;

endmodule
