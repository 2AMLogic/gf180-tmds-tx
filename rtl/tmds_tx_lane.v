// -----------------------------------------------------------------------
// tmds_tx_lane.v -- one TMDS lane: encoder, character-source select,
// serializer. DVI-mode TMDS transmitter component, not an HDMI part -- see
// CLAUDE.md, "On HDMI, and what may be said".
//
// Implements the interface requirement DR-0016 (question 3) levies on the
// block-level top, as decided in spec/decisions/0018-*: per lane, an
// externally supplied 10-bit character per pixel clock and a select between
// it and tmds_encoder's own output, feeding tmds_serializer's `tmds` input.
// The module is a mux and a port list at a cut the design already has. It
// contains no HDMI-defined content (no TERC4, guard band, preamble or packet
// logic); what an external producer sends is that producer's business.
//
// Three-lane instantiation: instantiate this module three times (blue,
// green, red lanes), sharing clk_bit, clk_pix and rst. All lanes have the
// same latency, so lane-to-lane alignment is preserved whatever each lane
// selects. Each lane has its own ser/clk_half; the clk_half outputs are
// identical by construction (same clk_bit, same reset).
//
// Character timing contract at `ext_tmds` (same as tmds_encoder's `tmds`
// output, rtl/tmds_encoder.v "registered TMDS character, one per clk"):
//   - one 10-bit character per clk_pix cycle, bit 0 transmitted first;
//   - driven from a register clocked by clk_pix (synchronous to the edge
//     that samples it here), stable for the whole cycle, no combinational
//     decode between the producer's last flop and this port;
//   - the character presented at clk_pix edge N is the one that can be
//     selected at edge N.
//
// Select (`ext_sel`, only when SEL_MODE == 2): 1 = external character,
// 0 = encoder character. It is a clk_pix-synchronous input with the same
// registered-driver rule as ext_tmds. It is sampled at the same clk_pix edge
// as both 10-bit words, into the single output register below, so every
// character leaving the register comes wholly from one source. Any change of
// ext_sel at any clk_pix boundary is permitted; it takes effect on the
// character sampled at the next edge. There is no glitch path: the mux feeds
// only the register's D inputs.
//
// Alignment: the wrapper does not delay-match the sources. The encoder's
// `tmds` at edge N is the character for pixel N-4 of its data/de/ctrl input
// (DR-0009 four-stage pipeline); the producer is responsible for presenting
// ext_tmds in the slot it wants to replace. The wrapper adds one clk_pix
// cycle to BOTH paths (the `tmds_q` register), so switching sources never
// changes latency.
//
// Latency: data/de/ctrl -> tmds_enc: 4 clk_pix (encoder). ext_tmds ->
// serializer `tmds` input: 1 clk_pix. data/de/ctrl -> serializer input:
// 5 clk_pix. Serializer then adds its own 3 clk_half to first bit on ser.
// The serializer loads `tmds` in the clk_half domain on its detected pixel
// boundary; tmds_q only changes on clk_pix edges and is stable for a whole
// pixel period, the same as the encoder output it replaces, so the
// serializer's capture window is unchanged.
//
// Reset: `rst` is synchronous (clk_pix) for tmds_q, clearing it to 0 --
// the serializer's own reset value -- and is also passed to encoder and
// serializer unchanged. 0 is not a valid TMDS character; it appears only
// while rst is asserted and the first clk_pix edges after, never as a
// consequence of a select change.
//
// SEL_MODE (elaboration-time):
//   0 = encoder only      (ext_tmds and ext_sel ignored; may be tied off)
//   1 = external only     (ext_sel ignored)
//   2 = runtime select    (default)
//
// Verilog-2005, no vendor extensions -- same rule as the RTL it wraps.
// -----------------------------------------------------------------------

module tmds_tx_lane #(
    parameter SEL_MODE = 2
) (
    input  wire       clk_bit,   // PLL bit-rate clock
    input  wire       clk_pix,   // PLL pixel-rate clock
    input  wire       rst,       // synchronous, active-high
    input  wire [7:0] data,      // to tmds_encoder
    input  wire [1:0] ctrl,      // to tmds_encoder
    input  wire       de,        // to tmds_encoder
    input  wire [9:0] ext_tmds,  // external 10-bit character, registered, one per clk_pix
    input  wire       ext_sel,   // SEL_MODE==2: 1 = ext_tmds, 0 = encoder
    output wire [9:0] tmds_enc,  // encoder's own registered character (observation)
    output wire [9:0] tmds_char, // character presented to the serializer
    output wire       clk_half,
    output wire [1:0] ser
);

  wire [9:0] enc_tmds;
  reg  [9:0] tmds_q;

  tmds_encoder u_enc (
      .clk (clk_pix),
      .rst (rst),
      .data(data),
      .ctrl(ctrl),
      .de  (de),
      .tmds(enc_tmds)
  );

  wire use_ext = (SEL_MODE == 0) ? 1'b0 : (SEL_MODE == 1) ? 1'b1 : ext_sel;

  always @(posedge clk_pix) begin
    if (rst) tmds_q <= 10'd0;
    else tmds_q <= use_ext ? ext_tmds : enc_tmds;
  end

  assign tmds_enc  = enc_tmds;
  assign tmds_char = tmds_q;

  tmds_serializer u_ser (
      .clk_bit (clk_bit),
      .clk_pix (clk_pix),
      .rst     (rst),
      .tmds    (tmds_q),
      .clk_half(clk_half),
      .ser     (ser)
  );

endmodule
