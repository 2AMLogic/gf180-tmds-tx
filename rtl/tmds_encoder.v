// -----------------------------------------------------------------------
// tmds_encoder.v -- DVI-mode TMDS 8b/10b-style transition-minimized,
// DC-balanced encoder for one TMDS lane.
//
// This is a DVI-mode TMDS transmitter component, not an HDMI part -- see
// CLAUDE.md, "On HDMI, and what may be said". TMDS/DVI signaling is
// unencumbered; nothing here implies HDMI certification or branding.
//
// Algorithm and control-character citation
// -----------------------------------------------------------------------
// The two-stage encoding algorithm (transition-minimizing XOR/XNOR
// selection, then DC-balancing against a running-disparity accumulator)
// and the four fixed control characters are taken from:
//
//   Digital Display Working Group, "Digital Visual Interface (DVI),
//   Revision 1.0", 2 April 1999 -- Section 3.3 "TMDS Encoding"
//   (stage 1: transition minimization, Figure 3-5; stage 2: DC balancing)
//   and the control-token values transmitted during horizontal/vertical
//   blanking (Section 3, Table 3-5 / Table B-3 depending on printing).
//
// Cross-check (not the primary source, corroborating only): the same
// two-stage algorithm and control-token values are reproduced in the
// public "Transition-minimized differential signaling" article on
// Wikipedia (https://en.wikipedia.org/wiki/Transition-minimized_differential_signaling),
// which also states the well-known invariant that only 460 of the 1024
// possible 10-bit codes are valid TMDS *data* characters. This RTL's
// verification bench (verification/tmds_encoder/) independently
// enumerates the reachable output-code set over its exhaustive input
// space and re-derives that exact figure (see verification/README.md) --
// agreement with a figure this widely published is strong evidence this
// transcription of the algorithm is correct, though the DVI 1.0 text
// above remains the citation for the algorithm and character *values*.
//
// Verilog dialect
// -----------------------------------------------------------------------
// Verilog-2005, no vendor extensions (see verification/README.md,
// "Verilog dialect") -- this file is consumed unmodified by both Icarus
// Verilog (simulation, see verification/tmds_encoder/) and Yosys
// (synthesis smoke-check here; full synthesis is flow/'s job, out of
// scope for this issue per DR-0003's synthesized/custom boundary).
//
// Interface and behavior
// -----------------------------------------------------------------------
//   - One TMDS lane, registered output, **two-clock-cycle latency** from
//     `data`/`de`/`ctrl` to the corresponding `tmds` output (per
//     spec/tmds-tx.md DR-0008): a pipeline register sits at the
//     stage1->stage2 boundary (see "Pipelining" below), so a new 10-bit
//     TMDS character reaches `tmds` two clocks after the corresponding
//     input is presented, not one. This supersedes an earlier one-clock
//     contract this header used to state -- DR-0007 measured that the
//     un-pipelined single combinational cone from `data` through both
//     stages did not close 720p60 setup timing at 3 of 5 3.3V corners, and
//     DR-0008 is the ratified fix.
//   - `de` (data-enable) asserted: encode `data` through both stages --
//     the transition-minimizing XOR/XNOR selection (stage 1), then the
//     DC-balancing stage (stage 2) driven by the running-disparity
//     accumulator `cnt`. `de`/`ctrl` are pipelined alongside stage 1's
//     result so they reach stage 2 already aligned with it -- see
//     "Pipelining" below.
//   - `de` deasserted (blanking): emit the fixed control character
//     selected by `ctrl` = {C1, C0}, and reset the running-disparity
//     accumulator to zero -- the standard's blanking behaviour, since
//     each blanking interval starts a fresh disparity run for the next
//     active-video period. Like the data path, this reset of `cnt`
//     happens two clocks after `de` is driven low, not one (the
//     pipelined `de` is what stage 2 actually observes).
//   - `rst`: synchronous, active-high. Clears the running-disparity
//     accumulator and forces the output to the C1=0/C0=0 control
//     character, on the *same* clock edge `rst` is sampled asserted --
//     `rst` is deliberately **not** pipelined through the stage1/stage2
//     boundary register (DR-0008), so its one-cycle-to-effect latency is
//     unchanged from the pre-pipeline design even though `data`/`de`/
//     `ctrl` now take two clocks. This is an intentional asymmetry: a
//     synchronous reset that itself took two cycles to reach `tmds` would
//     be a strictly worse contract with no benefit to the setup-timing
//     problem the pipeline register exists to fix.
//
// Pipelining (spec/tmds-tx.md DR-0008)
// -----------------------------------------------------------------------
// `stage1`'s output (`qm`, the 9-bit transition-minimized intermediate
// word) and the `de`/`ctrl` control signals that must stay aligned with it
// are captured in a pipeline register (`qm_p1`/`de_p1`/`ctrl_p1`) before
// `stage2` consumes them. This splits the original single combinational
// cone (primary input -> stage1's serial 8-bit XOR/XNOR chain -> stage2's
// disparity arithmetic -> the `tmds`/`cnt` output register, measured by
// DR-0007 to miss 720p60 setup timing by more than 2x at the worst 3.3V
// corner) into two shallower cones. The two-stage TMDS-encoding algorithm
// itself (DVI 1.0 Sec 3.3) is unchanged by this -- only where the register
// boundary between two already-sequential combinational stages sits.
//
// Scope note (per issue #10 / DR-0003): this module is the encoder only.
// The 10:1->2:1 serializer, synthesis, and DR-0003's synthesized-domain
// timing-ceiling question are deliberate follow-ons.
// -----------------------------------------------------------------------

module tmds_encoder (
    input  wire       clk,
    input  wire       rst,   // synchronous, active-high
    input  wire [7:0] data,  // 8-bit pixel data (active video)
    input  wire [1:0] ctrl,  // {C1, C0} control pair, sampled during blanking
    input  wire       de,    // data-enable: 1 = active video, 0 = blanking
    output reg  [9:0] tmds   // registered TMDS character, one per clk
);

  // Fixed control characters (DVI 1.0), indexed by {C1, C0}. These four
  // 10-bit values are exactly what a decoder distinguishes control
  // (character-boundary-sync) periods from data periods by -- see
  // verification/README.md for the exhaustive check that no data
  // character this encoder can emit collides with any of these four.
  localparam [9:0] CTRL_00 = 10'b1101010100;  // C1=0, C0=0
  localparam [9:0] CTRL_01 = 10'b0010101011;  // C1=0, C0=1
  localparam [9:0] CTRL_10 = 10'b0101010100;  // C1=1, C0=0
  localparam [9:0] CTRL_11 = 10'b1010101011;  // C1=1, C0=1

  // Running-disparity accumulator. Reset to zero on `rst` and on every
  // blanking cycle. The reachable value set is empirically {-8, -6, -4,
  // -2, 0, 2, 4, 6, 8} (see verification/README.md, "reachable state
  // space" -- the exhaustive bench discovers and reports this set rather
  // than assuming it). 8 bits (signed, [-128,127]) gives generous
  // headroom without relying on that empirical figure for correctness.
  reg signed [7:0] cnt;

  // -----------------------------------------------------------------
  // Stage 1: transition-minimized XOR/XNOR encoding (DVI 1.0 Sec 3.3,
  // Figure 3-5).
  // -----------------------------------------------------------------
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

  // Returns {qm8, qm[7:0]}: the 9-bit stage-1 intermediate word. qm8=1
  // means the XOR chain was selected, qm8=0 means the XNOR chain was
  // selected (the DVI 1.0 convention: bit 8 flags which chain was used,
  // to be undone by the decoder before this encoder's stage-2 inversion
  // is undone).
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

  // -----------------------------------------------------------------
  // Stage 2: DC balancing against the running-disparity accumulator
  // (DVI 1.0 Sec 3.3.3).
  // -----------------------------------------------------------------
  // Returns {qout[9:0], next_cnt[7:0]}.
  function [17:0] stage2;
    input [8:0]         qm;
    input signed [7:0]  cur_cnt;
    reg  [3:0]           n1_qm;
    reg signed [7:0]      disparity;  // N1(qm[7:0]) - N0(qm[7:0]) in [-8,8]
    reg  [9:0]            qout;
    reg signed [7:0]      next_cnt;
    integer                i;
    begin
      n1_qm = 4'd0;
      for (i = 0; i < 8; i = i + 1)
        n1_qm = n1_qm + qm[i];
      disparity = (n1_qm * 2) - 8;

      if ((cur_cnt == 0) || (disparity == 0)) begin
        // Character with fewer/no transitions than needed to force a
        // choice -- pick the polarity that carries qm8 through directly,
        // and update cnt with the (possibly inverted) disparity.
        qout[9]   = ~qm[8];
        qout[8]   = qm[8];
        qout[7:0] = qm[8] ? qm[7:0] : ~qm[7:0];
        next_cnt  = cur_cnt + (qm[8] ? disparity : -disparity);
      end else if ((cur_cnt > 0 && disparity > 0) || (cur_cnt < 0 && disparity < 0)) begin
        // Accumulated disparity and this character's disparity have the
        // same sign -- invert the data bits to pull disparity back
        // toward zero.
        qout[9]   = 1'b1;
        qout[8]   = qm[8];
        qout[7:0] = ~qm[7:0];
        next_cnt  = cur_cnt + (qm[8] ? 8'sd2 : 8'sd0) - disparity;
      end else begin
        // Opposite signs (or cnt already trending the right way) --
        // transmit qm as-is.
        qout[9]   = 1'b0;
        qout[8]   = qm[8];
        qout[7:0] = qm[7:0];
        next_cnt  = cur_cnt + disparity - (qm[8] ? 8'sd0 : 8'sd2);
      end

      stage2 = {qout, next_cnt};
    end
  endfunction

  wire [8:0] qm = stage1(data);

  // -----------------------------------------------------------------
  // Pipeline register: stage1 -> stage2 boundary (spec/tmds-tx.md
  // DR-0008). Captures stage1's result and the control signals stage2
  // needs to stay aligned with it. Deliberately *not* gated by `rst`
  // being pipelined further -- both this register and the final
  // tmds/cnt register below clear on the same edge `rst` is sampled
  // asserted, so `rst` keeps its original one-cycle-to-effect latency
  // (see this file's "Interface and behavior" header).
  // -----------------------------------------------------------------
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
