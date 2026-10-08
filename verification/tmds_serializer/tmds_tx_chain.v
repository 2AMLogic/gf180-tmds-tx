// -----------------------------------------------------------------------
// tmds_tx_chain.v -- VERIFICATION WRAPPER, not a design deliverable.
//
// Thin bench fixture around the design's per-lane module
// `rtl/tmds_tx_lane.v` (encoder -> registered source select -> serializer;
// spec/decisions/0018-*). It exists only to give the bench the legacy port
// names (`tmds` = the character presented to the serializer) and to pass
// SEL_MODE through, so the same test module elaborates every static
// configuration. The block-level top is still not ratified as a whole:
// physical/custom-domain integration and 720p60 timing closure remain
// separate work under DR-0014.
//
// Verilog-2005, no vendor extensions -- same rule as the RTL it wraps.
// -----------------------------------------------------------------------

module tmds_tx_chain #(
    parameter SEL_MODE = 2
) (
    input  wire       clk_bit,
    input  wire       clk_pix,
    input  wire       rst,
    input  wire [7:0] data,
    input  wire [1:0] ctrl,
    input  wire       de,
    input  wire [9:0] ext_tmds,
    input  wire       ext_sel,
    output wire [9:0] tmds_enc,  // the encoder's own output, observed by the bench
    output wire [9:0] tmds,      // character presented to the serializer
    output wire       clk_half,
    output wire [1:0] ser
);

  tmds_tx_lane #(
      .SEL_MODE(SEL_MODE)
  ) u_lane (
      .clk_bit  (clk_bit),
      .clk_pix  (clk_pix),
      .rst      (rst),
      .data     (data),
      .ctrl     (ctrl),
      .de       (de),
      .ext_tmds (ext_tmds),
      .ext_sel  (ext_sel),
      .tmds_enc (tmds_enc),
      .tmds_char(tmds),
      .clk_half (clk_half),
      .ser      (ser)
  );

endmodule
