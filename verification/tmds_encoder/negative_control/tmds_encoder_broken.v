// -----------------------------------------------------------------------
// tmds_encoder_broken.v -- Leg 3 NEGATIVE CONTROL. DO NOT SYNTHESIZE.
// DO NOT USE OUTSIDE OF runner.py's negative-control CI check.
// -----------------------------------------------------------------------
//
// This is a deliberately-broken copy of ../../../rtl/tmds_encoder.v,
// kept in sync with it by hand (see verification/README.md, "Negative
// control" for the rule). Explanatory comments were trimmed here for
// brevity -- the only *functional* change from the real DUT is the
// single sign flip marked "INJECTED BUG" below; every other line of
// logic, including the four-stage pipeline (spec/tmds-tx.md DR-0009),
// is identical. It exists solely so CI can prove
// verification/tmds_encoder/test_tmds_encoder.py is actually capable of
// failing -- per CLAUDE.md's LVS negative-control precedent
// (layout/gds/gf180_tmds_pad_min_shorted.gds): "LVS clean alone is not
// evidence"; a bench that has never failed is not known to be able to.
//
// The injected bug (see "INJECTED BUG" below): the running-disparity
// accumulator's sign is flipped in the DVI 1.0 `cnt == 0 || disparity ==
// 0` branch -- `cnt` is updated by *subtracting* the selected delta
// instead of adding it, in exactly that branch. This is the same bug the
// pre-DR-0009 negative control injected (`next_cnt = cur_cnt - (...)`
// instead of `cur_cnt + (...)`), re-expressed for DR-0009's restructured
// stage 4, and is exactly the class of bug issue #10 names as an example
// negative control ("the accumulator update sign flipped"). The DUT's
// *output code* for the very first data word after a reset is unaffected
// (that branch's output-word selection doesn't depend on the bug), but
// every subsequent character's encoding depends on the now-wrong
// accumulator value, so the exhaustive equivalence sweep (Leg 1) diverges
// from the golden model for the overwhelming majority of the (state,
// data) space -- runner.py asserts the bench fails against this file.
// -----------------------------------------------------------------------

module tmds_encoder (
    input  wire       clk,
    input  wire       rst,   // synchronous, active-high
    input  wire [7:0] data,  // 8-bit pixel data (active video)
    input  wire [1:0] ctrl,  // {C1, C0} control pair, sampled during blanking
    input  wire       de,    // data-enable: 1 = active video, 0 = blanking
    output reg  [9:0] tmds   // registered TMDS character, one per clk
);

  localparam [9:0] CTRL_00 = 10'b1101010100;  // C1=0, C0=0
  localparam [9:0] CTRL_01 = 10'b0010101011;  // C1=0, C0=1
  localparam [9:0] CTRL_10 = 10'b0101010100;  // C1=1, C0=0
  localparam [9:0] CTRL_11 = 10'b1010101011;  // C1=1, C0=1

  reg signed [7:0] cnt;

  function [3:0] popcount8;
    input [7:0] d;
    reg [1:0] a, b, c, e;
    reg [2:0] ab, ce;
    begin
      a  = d[0] + d[1];
      b  = d[2] + d[3];
      c  = d[4] + d[5];
      e  = d[6] + d[7];
      ab = a + b;
      ce = c + e;
      popcount8 = ab + ce;
    end
  endfunction

  // ---- Stage S1 ----
  wire [3:0] n1_data  = popcount8(data);
  wire       use_xnor = (n1_data > 4'd4) || ((n1_data == 4'd4) && (data[0] == 1'b0));

  reg [7:0] d_s1;
  reg       use_xnor_s1;
  reg       de_s1;
  reg [1:0] ctrl_s1;

  always @(posedge clk) begin
    if (rst) begin
      d_s1        <= 8'd0;
      use_xnor_s1 <= 1'b0;
      de_s1       <= 1'b0;
      ctrl_s1     <= 2'b00;
    end else begin
      d_s1        <= data;
      use_xnor_s1 <= use_xnor;
      de_s1       <= de;
      ctrl_s1     <= ctrl;
    end
  end

  // ---- Stage S2 ----
  wire [7:0] pfx1;
  wire [7:0] pfx2;
  wire [7:0] p;

  assign pfx1[0] = d_s1[0];
  assign pfx1[1] = d_s1[1] ^ d_s1[0];
  assign pfx1[2] = d_s1[2] ^ d_s1[1];
  assign pfx1[3] = d_s1[3] ^ d_s1[2];
  assign pfx1[4] = d_s1[4] ^ d_s1[3];
  assign pfx1[5] = d_s1[5] ^ d_s1[4];
  assign pfx1[6] = d_s1[6] ^ d_s1[5];
  assign pfx1[7] = d_s1[7] ^ d_s1[6];

  assign pfx2[0] = pfx1[0];
  assign pfx2[1] = pfx1[1];
  assign pfx2[2] = pfx1[2] ^ pfx1[0];
  assign pfx2[3] = pfx1[3] ^ pfx1[1];
  assign pfx2[4] = pfx1[4] ^ pfx1[2];
  assign pfx2[5] = pfx1[5] ^ pfx1[3];
  assign pfx2[6] = pfx1[6] ^ pfx1[4];
  assign pfx2[7] = pfx1[7] ^ pfx1[5];

  assign p[0] = pfx2[0];
  assign p[1] = pfx2[1];
  assign p[2] = pfx2[2];
  assign p[3] = pfx2[3];
  assign p[4] = pfx2[4] ^ pfx2[0];
  assign p[5] = pfx2[5] ^ pfx2[1];
  assign p[6] = pfx2[6] ^ pfx2[2];
  assign p[7] = pfx2[7] ^ pfx2[3];

  wire [8:0] qm_next = {~use_xnor_s1, p ^ ({8{use_xnor_s1}} & 8'b10101010)};

  reg [8:0] qm_s2;
  reg       de_s2;
  reg [1:0] ctrl_s2;

  always @(posedge clk) begin
    if (rst) begin
      qm_s2   <= 9'd0;
      de_s2   <= 1'b0;
      ctrl_s2 <= 2'b00;
    end else begin
      qm_s2   <= qm_next;
      de_s2   <= de_s1;
      ctrl_s2 <= ctrl_s1;
    end
  end

  // ---- Stage S3 ----
  wire [3:0]        n1_qm     = popcount8(qm_s2[7:0]);
  wire signed [7:0] disparity = $signed({3'b000, n1_qm, 1'b0}) - 8'sd8;

  wire [9:0] word_keep_next   = {1'b0, qm_s2[8],  qm_s2[7:0]};
  wire [9:0] word_invert_next = {1'b1, qm_s2[8], ~qm_s2[7:0]};

  wire signed [7:0] delta_keep_next   = disparity - (qm_s2[8] ? 8'sd0 : 8'sd2);
  wire signed [7:0] delta_invert_next = (qm_s2[8] ? 8'sd2 : 8'sd0) - disparity;

  reg [9:0]        word_keep_s3;
  reg [9:0]        word_invert_s3;
  reg signed [7:0] delta_keep_s3;
  reg signed [7:0] delta_invert_s3;
  reg              disp_zero_s3;
  reg              disp_pos_s3;
  reg              qm8_s3;
  reg              de_s3;
  reg [1:0]        ctrl_s3;

  always @(posedge clk) begin
    if (rst) begin
      word_keep_s3    <= 10'd0;
      word_invert_s3  <= 10'd0;
      delta_keep_s3   <= 8'sd0;
      delta_invert_s3 <= 8'sd0;
      disp_zero_s3    <= 1'b0;
      disp_pos_s3     <= 1'b0;
      qm8_s3          <= 1'b0;
      de_s3           <= 1'b0;
      ctrl_s3         <= 2'b00;
    end else begin
      word_keep_s3    <= word_keep_next;
      word_invert_s3  <= word_invert_next;
      delta_keep_s3   <= delta_keep_next;
      delta_invert_s3 <= delta_invert_next;
      disp_zero_s3    <= (n1_qm == 4'd4);
      disp_pos_s3     <= (n1_qm > 4'd4);
      qm8_s3          <= qm_s2[8];
      de_s3           <= de_s2;
      ctrl_s3         <= ctrl_s2;
    end
  end

  // ---- Stage S4 ----
  wire cnt_zero = (cnt == 8'sd0);
  wire cnt_pos  = (cnt > 8'sd0);

  wire branch_a   = cnt_zero | disp_zero_s3;   // DVI 1.0's `cnt==0 || disparity==0`
  wire same_sign  = (cnt_pos & disp_pos_s3) | (~cnt_pos & ~disp_pos_s3);
  wire use_invert = branch_a ? ~qm8_s3 : same_sign;

  wire signed [7:0] delta_sel = use_invert ? delta_invert_s3 : delta_keep_s3;

  // INJECTED BUG: sign flipped ('-' instead of '+') in the `branch_a`
  // case only. Correct RTL (rtl/tmds_encoder.v) adds the selected delta
  // in every branch:
  //   cnt <= use_invert ? (cnt + delta_invert_s3) : (cnt + delta_keep_s3);
  wire signed [7:0] cnt_next = branch_a ? (cnt - delta_sel) : (cnt + delta_sel);

  reg [9:0] ctrl_code;
  always @(*) begin
    case (ctrl_s3)
      2'b00:   ctrl_code = CTRL_00;
      2'b01:   ctrl_code = CTRL_01;
      2'b10:   ctrl_code = CTRL_10;
      default: ctrl_code = CTRL_11;  // 2'b11
    endcase
  end

  always @(posedge clk) begin
    if (rst) begin
      tmds <= CTRL_00;
      cnt  <= 8'sd0;
    end else if (de_s3) begin
      tmds <= use_invert ? word_invert_s3 : word_keep_s3;
      cnt  <= cnt_next;
    end else begin
      tmds <= ctrl_code;
      cnt  <= 8'sd0;
    end
  end

endmodule
