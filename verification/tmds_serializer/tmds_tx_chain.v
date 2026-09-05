// -----------------------------------------------------------------------
// tmds_tx_chain.v -- VERIFICATION WRAPPER, not a design deliverable.
//
// Instantiates `rtl/tmds_encoder.v` and `rtl/tmds_serializer.v` together so
// the serializer's reduction can be checked against the encoder's REAL
// output rather than against hand-written stimulus. Issue #159's acceptance
// criterion is specifically "correct 10-bit-to-2-bit reduction against
// tmds_encoder's existing output", which requires both cells in one
// elaboration.
//
// This file lives under verification/ deliberately: it is a bench fixture.
// The block-level top that the digital flow synthesizes is a separate
// question (and, per spec/decisions/0014-*, one whose answer depends on
// which domain implements the reduction at 720p60), so nothing here should
// be mistaken for a ratified top-level netlist.
//
// Verilog-2005, no vendor extensions -- same rule as the RTL it wraps.
// -----------------------------------------------------------------------

module tmds_tx_chain (
    input  wire       clk_bit,
    input  wire       clk_pix,
    input  wire       rst,
    input  wire [7:0] data,
    input  wire [1:0] ctrl,
    input  wire       de,
    output wire [9:0] tmds,      // the encoder's own output, observed by the bench
    output wire       clk_half,
    output wire [1:0] ser
);

  tmds_encoder u_enc (
      .clk (clk_pix),
      .rst (rst),
      .data(data),
      .ctrl(ctrl),
      .de  (de),
      .tmds(tmds)
  );

  tmds_serializer u_ser (
      .clk_bit (clk_bit),
      .clk_pix (clk_pix),
      .rst     (rst),
      .tmds    (tmds),
      .clk_half(clk_half),
      .ser     (ser)
  );

endmodule
