# rtl

Synthesized-domain sources for the DVI-mode TMDS transmitter. This is a
DVI-mode TMDS transmitter component, not an HDMI part -- see `CLAUDE.md`,
"On HDMI, and what may be said".

## What's here

- `tmds_encoder.v` -- one lane's TMDS encoder: transition-minimizing
  XOR/XNOR selection (stage 1) followed by DC-balancing against a
  running-disparity accumulator (stage 2), plus the four fixed control
  characters emitted during blanking. Registered output, one 10-bit TMDS
  character per pixel clock, at a **four-clock-cycle** latency from
  `data`/`de`/`ctrl` to `tmds` (a four-stage pipeline -- `spec/tmds-tx.md`
  DR-0009, superseding DR-0008's two-stage contract; `rst` itself keeps a
  one-cycle latency, see those decision records). Algorithm and
  control-character citation, the four stages' cut points, and the full
  interface/behavior description, are in the file's own header.

- `tmds_serializer.v` -- the 10:1->2:1 half-rate reduction (DR-0012, DR-0014);
  verified by `verification/tmds_serializer/`.
- `tmds_tx_lane.v` -- one TMDS lane (DR-0018): `tmds_encoder`, a registered
  2:1 character-source select, and `tmds_serializer`. Per lane it admits an
  external 10-bit character `ext_tmds` and a select `ext_sel` (parameter
  `SEL_MODE`: 2 runtime select, default; 0 encoder only; 1 external only).
  The external port's contract is the encoder's own: one registered character
  per `clk_pix`, bit 0 first. Every character comes wholly from one source;
  `ext_sel` may change at any `clk_pix` boundary; the mux register adds one
  `clk_pix` of latency to both paths (encoder to serializer input: 5 cycles).
  Three-lane use: instantiate it three times sharing `clk_bit`, `clk_pix`,
  `rst`. **Boundary**: this is the digital per-lane module only. It contains
  no HDMI-defined content (no TERC4, guard bands, preambles or packets -- that
  is the consumer's layer, DR-0016) and no claim of HDMI compliance.
  Physical/custom-domain integration and 720p60 timing closure are separate
  work under DR-0014; simulation here shows function, not timing closure.

Verified by `verification/tmds_encoder/` -- see `verification/README.md`
for the verification conventions this repo follows (three-leg plan,
cold-start invocation, pinned toolchain, negative-control rule).

## What's not here yet

- **A ratified full block-level top** (pad ring, custom domain, 720p60
  integration). `tmds_tx_lane.v` is the digital per-lane piece only.
- **Synthesis recipes.** Those live in `flow/` (Yosys/OpenROAD, via `klt`),
  which is currently empty pending this directory having something to
  synthesize.

## The synthesized/custom boundary (DR-0003)

Per `spec/tmds-tx.md` DR-0003, this directory (`rtl/`) is the
**synthesized** side of the synthesized/custom boundary: the TMDS encoder
and a first-stage 10:1->2:1 parallel-to-serial reduction target
`gf180mcu_fd_sc_mcu9t5v0` standard cells at its 3.3 V corner. Everything
past that 2:1 reduction -- the final multiplexer and the custom CML output
driver -- is hand-drawn analog/custom work under `design/` and `layout/`,
not RTL.

DR-0003 also flagged its own open item: whether
`gf180mcu_fd_sc_mcu9t5v0` actually closes timing at the pixel-domain-
derived intermediate rate (5x pixel clock = 371.25 MHz @ 720p60) is
explicitly **unverified**, pending RTL/synthesis work existing to ask the
question of. This encoder is the first RTL in the repository, which makes
asking that question possible -- but answering it (running synthesis under
`flow/` and checking the resulting timing report against 371.25 MHz) is
deliberately out of scope for the encoder itself; it is a follow-on issue
against `flow/`, once the serializer exists to synthesize alongside the
encoder.

No spec changes were made or needed while implementing the encoder: the
DVI 1.0 encoding algorithm did not contradict anything DR-0003 already
decided.
