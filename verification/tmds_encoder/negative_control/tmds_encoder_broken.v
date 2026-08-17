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
// logic, including the stage1->stage2 pipeline register
// (spec/tmds-tx.md DR-0008), is identical. It exists solely so CI can prove
// verification/tmds_encoder/test_tmds_encoder.py is actually capable of
// failing -- per CLAUDE.md's LVS negative-control precedent
// (layout/gds/gf180_tmds_pad_min_shorted.gds): "LVS clean alone is not
// evidence"; a bench that has never failed is not known to be able to.
//
// The injected bug (see "INJECTED BUG" below): the running-disparity
// accumulator's sign is flipped in stage 2's `cnt == 0 || disparity == 0`
// branch -- `next_cnt` is computed as `cur_cnt - (...)` instead of
// `cur_cnt + (...)`. This is exactly the class of bug issue #10 names as
// an example negative control ("the accumulator update sign flipped").
// The DUT's *output code* for the very first data word after a reset is
// unaffected (that branch's `qout` computation doesn't depend on the
// bug), but every subsequent character's encoding depends on the
// now-wrong accumulator value, so the exhaustive equivalence sweep
// (Leg 1) diverges from the golden model for the overwhelming majority
// of the (state, data) space -- runner.py asserts the bench fails
// against this file.
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

  function [3:0] count_ones;
    input [7:0] d;
    integer i;
    reg [3:0] n;
    begin
      n = 4'd0;
      for (i = 0; i < 8; i = i + 1)
        n = n + d[i];
      count_ones = n;
    end
  endfunction

  function [8:0] stage1;
    input [7:0] d;
    reg  [7:0] qm;
    reg        use_xnor;
    integer    i;
    begin
      use_xnor = (count_ones(d) > 4'd4)
               || ((count_ones(d) == 4'd4) && (d[0] == 1'b0));
      qm[0] = d[0];
      for (i = 1; i < 8; i = i + 1)
        qm[i] = use_xnor ? ~(qm[i-1] ^ d[i]) : (qm[i-1] ^ d[i]);
      stage1 = {~use_xnor, qm};
    end
  endfunction

  function [17:0] stage2;
    input [8:0]         qm;
    input signed [7:0]  cur_cnt;
    reg  [3:0]           n1_qm;
    reg signed [7:0]      disparity;
    reg  [9:0]            qout;
    reg signed [7:0]      next_cnt;
    integer                i;
    begin
      n1_qm = 4'd0;
      for (i = 0; i < 8; i = i + 1)
        n1_qm = n1_qm + qm[i];
      disparity = (n1_qm * 2) - 8;

      if ((cur_cnt == 0) || (disparity == 0)) begin
        qout[9]   = ~qm[8];
        qout[8]   = qm[8];
        qout[7:0] = qm[8] ? qm[7:0] : ~qm[7:0];
        // INJECTED BUG: sign flipped ('-' instead of '+'). Correct RTL
        // (rtl/tmds_encoder.v) reads:
        //   next_cnt = cur_cnt + (qm[8] ? disparity : -disparity);
        next_cnt  = cur_cnt - (qm[8] ? disparity : -disparity);
      end else if ((cur_cnt > 0 && disparity > 0) || (cur_cnt < 0 && disparity < 0)) begin
        qout[9]   = 1'b1;
        qout[8]   = qm[8];
        qout[7:0] = ~qm[7:0];
        next_cnt  = cur_cnt + (qm[8] ? 8'sd2 : 8'sd0) - disparity;
      end else begin
        qout[9]   = 1'b0;
        qout[8]   = qm[8];
        qout[7:0] = qm[7:0];
        next_cnt  = cur_cnt + disparity - (qm[8] ? 8'sd0 : 8'sd2);
      end

      stage2 = {qout, next_cnt};
    end
  endfunction

  wire [8:0] qm = stage1(data);

  // Pipeline register: stage1 -> stage2 boundary (spec/tmds-tx.md DR-0008).
  // Not part of the injected bug -- kept identical to rtl/tmds_encoder.v.
  reg [8:0] qm_p1;
  reg       de_p1;
  reg [1:0] ctrl_p1;

  always @(posedge clk) begin
    if (rst) begin
      qm_p1   <= 9'd0;
      de_p1   <= 1'b0;
      ctrl_p1 <= 2'b00;
    end else begin
      qm_p1   <= qm;
      de_p1   <= de;
      ctrl_p1 <= ctrl;
    end
  end

  wire [17:0] enc        = stage2(qm_p1, cnt);
  wire [9:0]  data_code  = enc[17:8];
  wire [7:0]  next_cnt_w = enc[7:0];

  reg [9:0] ctrl_code;
  always @(*) begin
    case (ctrl_p1)
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
    end else if (de_p1) begin
      tmds <= data_code;
      cnt  <= next_cnt_w;
    end else begin
      tmds <= ctrl_code;
      cnt  <= 8'sd0;
    end
  end

endmodule
