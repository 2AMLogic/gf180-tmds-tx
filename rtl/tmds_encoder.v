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
// (synthesis, flow/synth_tmds_encoder.py).
//
// Interface and behavior
// -----------------------------------------------------------------------
//   - One TMDS lane, registered output, **four-clock-cycle latency** from
//     `data`/`de`/`ctrl` to the corresponding `tmds` output (per
//     spec/tmds-tx.md DR-0009, which supersedes DR-0008's two-clock
//     contract, which in turn superseded the original one-clock one). Four
//     pipeline stages sit between the input pins and `tmds` -- see
//     "Pipelining" below for what each one computes and why the cut points
//     are where they are.
//   - `de` (data-enable) asserted: encode `data` through the DVI 1.0
//     two-stage algorithm -- the transition-minimizing XOR/XNOR selection
//     (stage 1), then the DC-balancing stage (stage 2) driven by the
//     running-disparity accumulator `cnt`. `de`/`ctrl` are pipelined
//     alongside the datapath so they reach the output register already
//     aligned with the word they belong to.
//   - `de` deasserted (blanking): emit the fixed control character
//     selected by `ctrl` = {C1, C0}, and reset the running-disparity
//     accumulator to zero -- the standard's blanking behaviour, since
//     each blanking interval starts a fresh disparity run for the next
//     active-video period. Like the data path, this reset of `cnt`
//     happens four clocks after `de` is driven low (the pipelined `de` is
//     what the output stage actually observes).
//   - `rst`: synchronous, active-high. Clears the running-disparity
//     accumulator and forces the output to the C1=0/C0=0 control
//     character, on the *same* clock edge `rst` is sampled asserted --
//     `rst` is deliberately **not** pipelined through any of the pipeline
//     registers (DR-0008, carried forward unchanged by DR-0009), so its
//     one-cycle-to-effect latency is unchanged from the original
//     un-pipelined design even though `data`/`de`/`ctrl` now take four
//     clocks. This is an intentional asymmetry: a synchronous reset that
//     itself took four cycles to reach `tmds` would be a strictly worse
//     contract with no benefit to the setup-timing problem the pipeline
//     exists to fix. Every pipeline register below clears on that same
//     edge, so a reset also flushes the pipeline rather than letting
//     in-flight symbols emerge afterwards.
//
// Pipelining (spec/tmds-tx.md DR-0009, superseding DR-0008)
// -----------------------------------------------------------------------
// DR-0008 cut the original single combinational cone once, at the
// stage1/stage2 boundary. Post-layout multi-corner STA
// (`flow/tmds_encoder/records/20260817-012556-7d9130d.md`) measured that
// this was a real improvement but still left both remaining cones far too
// deep for 74.25 MHz at the two slow-process 3.3 V corners. DR-0009
// therefore cuts further, into four stages, *and* re-expresses two
// internal computations in equivalent but logarithmic-depth form. The
// encoding function is bit-for-bit unchanged -- only its temporal and
// structural decomposition is:
//
//   S1 (inputs -> `d_s1`, `use_xnor_s1`, `de_s1`, `ctrl_s1`)
//       Population count of `data` and the DVI 1.0 Figure 3-5 threshold
//       test that selects the XOR or the XNOR chain. `data` itself is
//       carried forward unmodified.
//
//   S2 (`d_s1`/`use_xnor_s1` -> `qm_s2`, ...)
//       The 9-bit transition-minimized intermediate word `qm`. Computed
//       from a **parallel-prefix XOR** of `data` rather than the serial
//       8-deep XOR/XNOR chain the DVI 1.0 figure draws: writing
//       `qm[i] = qm[i-1] ^ d[i] ^ use_xnor` and unrolling gives
//       `qm[i] = (d[0]^...^d[i]) ^ (i odd ? use_xnor : 0)`, so the chain
//       is exactly a prefix-XOR followed by one conditional inversion of
//       the odd bits. That is an algebraic identity, not an
//       approximation: it computes the same `qm` for every input, at
//       depth log2(8)+1 = 4 instead of 8. See `p` below.
//
//   S3 (`qm_s2` -> candidate words and candidate `cnt` deltas)
//       Everything in DVI 1.0's DC-balancing stage that depends only on
//       `qm` and **not** on the running-disparity accumulator: the
//       population count of `qm[7:0]`, the character's own disparity, the
//       two candidate output words (inverted / not inverted), and the two
//       candidate accumulator deltas. Splitting the stage this way is
//       what makes the final stage short: the DC-balancing decision is a
//       three-way conditional whose three outcomes reduce to just those
//       two candidates (the `cnt == 0 || disparity == 0` case picks
//       between the very same two, selected by `qm[8]` -- see
//       `use_invert` below).
//
//   S4 (`cnt`/S3 registers -> `tmds`, `cnt`)
//       The only stage that can *not* be pipelined further, because it
//       carries the algorithm's single sequential recurrence: the
//       accumulator feeds its own next value. It is deliberately reduced
//       to a sign/zero test on `cnt`, one 2:1 select, and one add -- both
//       candidate sums are computed in parallel with the select rather
//       than after it, so the recurrence is one adder deep, not an adder
//       plus the selection logic.
//
// Scope note (per issue #10 / DR-0003): this module is the encoder only.
// The 10:1->2:1 serializer, and DR-0003's synthesized-domain
// timing-ceiling question, are deliberate follow-ons.
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

  // Balanced 8-bit population count. Same value `count_ones` computed
  // with a serial accumulate loop before DR-0009; written as an explicit
  // adder tree so the depth is log-shaped in the RTL itself rather than
  // left to the synthesizer's restructuring to recover.
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

  // -----------------------------------------------------------------
  // Stage S1: DVI 1.0 Sec 3.3, Figure 3-5's XOR-vs-XNOR selection.
  // -----------------------------------------------------------------
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

  // -----------------------------------------------------------------
  // Stage S2: the transition-minimized intermediate word `qm`, via a
  // parallel-prefix XOR (Kogge-Stone shape) instead of the serial chain
  // DVI 1.0 Figure 3-5 draws. `p[i] = d[0] ^ d[1] ^ ... ^ d[i]`, and the
  // XNOR variant of the chain is exactly `p` with its odd bits inverted
  // -- see this file's "Pipelining" header for the unrolling that shows
  // these are the same function.
  // -----------------------------------------------------------------
  wire [7:0] pfx1;  // prefix level 1: span 1
  wire [7:0] pfx2;  // prefix level 2: span 2
  wire [7:0] p;     // prefix level 3: span 4 -- the full prefix XOR

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

  // The XNOR chain inverts every odd-indexed prefix bit; `qm[8]` is the
  // DVI 1.0 flag bit saying which chain was used (1 = XOR).
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

  // -----------------------------------------------------------------
  // Stage S3: everything in DVI 1.0 Sec 3.3.3's DC-balancing stage that
  // depends only on `qm`, not on the accumulator.
  //
  // The published stage has three branches. Their outputs are only ever
  // one of two 10-bit words -- "transmit `qm` as-is" and "transmit `qm`
  // with its data bits inverted" -- because the `cnt == 0 || disparity
  // == 0` branch's own output, `{~qm[8], qm[8], qm[8] ? qm : ~qm}`, is
  // literally the not-inverted word when `qm[8]` is 1 and the inverted
  // word when it is 0. The same collapse holds for that branch's
  // accumulator update. So this stage precomputes both candidates, and
  // S4 only has to pick one.
  // -----------------------------------------------------------------
  wire [3:0]        n1_qm     = popcount8(qm_s2[7:0]);
  wire signed [7:0] disparity = $signed({3'b000, n1_qm, 1'b0}) - 8'sd8;  // N1 - N0, in [-8,8]

  wire [9:0] word_keep_next   = {1'b0, qm_s2[8],  qm_s2[7:0]};
  wire [9:0] word_invert_next = {1'b1, qm_s2[8], ~qm_s2[7:0]};

  // Accumulator deltas for the two candidates, straight from DVI 1.0's
  // own two non-degenerate branches:
  //   keep:   cnt + disparity - (qm[8] ? 0 : 2)
  //   invert: cnt + (qm[8] ? 2 : 0) - disparity
  wire signed [7:0] delta_keep_next   = disparity - (qm_s2[8] ? 8'sd0 : 8'sd2);
  wire signed [7:0] delta_invert_next = (qm_s2[8] ? 8'sd2 : 8'sd0) - disparity;

  reg [9:0]        word_keep_s3;
  reg [9:0]        word_invert_s3;
  reg signed [7:0] delta_keep_s3;
  reg signed [7:0] delta_invert_s3;
  reg              disp_zero_s3;   // disparity == 0
  reg              disp_pos_s3;    // disparity  > 0
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

  // -----------------------------------------------------------------
  // Stage S4: the DC-balancing decision and the accumulator recurrence.
  // This is the one stage the algorithm forbids pipelining further --
  // `cnt` feeds its own next value.
  // -----------------------------------------------------------------
  wire cnt_zero = (cnt == 8'sd0);
  wire cnt_pos  = (cnt > 8'sd0);

  // DVI 1.0's branch 1 (`cnt == 0 || disparity == 0`) selects the
  // inverted word exactly when qm[8] is 0; its other two branches select
  // the inverted word exactly when `cnt` and `disparity` share a sign.
  wire same_sign  = (cnt_pos & disp_pos_s3) | (~cnt_pos & ~disp_pos_s3);
  wire use_invert = (cnt_zero | disp_zero_s3) ? ~qm8_s3 : same_sign;

  // Both candidate sums are computed in parallel with `use_invert`, so
  // the accumulator recurrence is one adder deep.
  wire signed [7:0] cnt_keep   = cnt + delta_keep_s3;
  wire signed [7:0] cnt_invert = cnt + delta_invert_s3;

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
      cnt  <= use_invert ? cnt_invert : cnt_keep;
    end else begin
      tmds <= ctrl_code;
      cnt  <= 8'sd0;
    end
  end

endmodule
