// -----------------------------------------------------------------------
// tmds_serializer_broken.v -- NEGATIVE CONTROL. Deliberately wrong.
//
// Leg 3 of verification/README.md's three-leg plan: runner.py runs the
// UNMODIFIED test suite in test_tmds_serializer.py against this file and
// asserts it FAILS. A bench that has only ever been run against a correct
// DUT is not known to be able to fail.
//
// The single injected defect: the two bits of every emitted word are
// swapped, so `ser[0]` carries the LATER bit of each pair instead of the
// earlier one. This is exactly the class of error the DDR multiplexer
// cannot tolerate (it emits `ser[0]` on the half-rate clock's high half),
// and it is deliberately a defect that leaves the output stream
// self-consistent -- every bit is still present, exactly once, in a
// plausible order -- so only a check that pairs the stream against the
// encoder's own bit indices can catch it. That is the check
// `test_ser_word_pairs_are_lsb_first` exists for.
//
// Nothing else differs from rtl/tmds_serializer.v. Regenerate by applying
// that one substitution to the real RTL if the source changes.
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
      ser_q  <= {sh[0], sh[1]};  // NEGATIVE CONTROL: bit pair swapped
    end
  end

  assign ser = ser_q;

endmodule
