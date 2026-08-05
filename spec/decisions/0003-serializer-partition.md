# 0003 — Where the standard-cell / custom / CML boundaries fall

**Status:** Accepted 2026-08-05.

## Context

The serialization ratio is not in question: **10:1**, because DVI 1.0 §3.2.2
encodes each 8-bit pixel component into a 10-bit TMDS character. The open
question the DRAFT table left ("10:1, custom CML final stages") is *where*
the boundary sits — which stages are synthesized and which are drawn by hand.

The answer is set by what the gf180mcu standard-cell library can actually do,
and that is measurable. `gf180mcu_fd_sc_mcu9t5v0__dffq_1` is the fastest flop
in the 9-track library; its liberty carries a `minimum_period` constraint —
the flop's own recovery limit, before any logic, routing, or clock skew:

| Corner (`libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib/`) | `minimum_period` | Ceiling |
|---|---|---|
| `ss_125C_3v00` | 2.357 ns | 424 MHz |
| `ss_n40C_3v00` | 1.606 ns | 623 MHz |
| `tt_025C_3v30` | 1.179 ns | 848 MHz |
| `ff_125C_3v60` | 0.991 ns | 1009 MHz |
| `ss_125C_4v50` (5 V rail) | 1.455 ns | 687 MHz |
| `tt_025C_5v00` (5 V rail) | 0.783 ns | 1277 MHz |

The reason the library is slow is visible in its own netlist: every device in
`libs.ref/gf180mcu_fd_sc_mcu9t5v0/spice/gf180mcu_fd_sc_mcu9t5v0.spice` is
`nfet_06v0` / `pfet_06v0` at `L=0.600000U`. gf180mcu ships **no 3.3 V
standard-cell library** — only 7-track and 9-track libraries built from the
6 V flavor. The 3.3 V devices exist in the PDK
(`libs.tech/ngspice/sm141064.ngspice`: `nfet_03v3`, `pfet_03v3`, L_min
0.28 µm) but only as primitives for custom design.

So the standard-cell speed ceiling is a property of the *library's device
flavor*, not of the process. 180 nm supports multi-gigabit custom logic; it
does not support a 371.25 MHz synthesized domain at the slow corner in a
6 V, 0.6 µm library.

The clocking arithmetic: at 720p60, 10 bits per 13.468 ns pixel period. A
parallel bus `k` bits wide runs at 742.5/`k` MHz — 74.25 MHz at `k`=10,
148.5 at `k`=5, 371.25 at `k`=2, 742.5 at `k`=1. Only ratios that divide the
half-rate clock (371.25 MHz) by an integer are available without a second
clock source; 148.5 MHz is *not* one of them (371.25/148.5 = 2.5).

## Decision

**The standard-cell boundary is at 74.25 MHz — the pixel clock. Standard
cells own that domain and nothing faster. Everything at 371.25 MHz and above
is custom.**

| Stage | Clock (720p60) | Implementation | Devices |
|---|---|---|---|
| DVI 1.0 8b/10b encoder ×3, control-period coding, 10-bit word assembly | 74.25 MHz | Synthesized, Yosys + OpenROAD, `gf180mcu_fd_sc_mcu9t5v0` | 6 V, 3.3 V rail |
| 10:2 gearbox | 371.25 MHz | Custom CMOS | 3.3 V |
| ÷5 divider, clock distribution | 371.25 MHz | Custom CMOS | 3.3 V |
| Final 2:1 DDR mux + retime latch | 371.25 MHz, both edges | Custom CML | 3.3 V |
| Current-steering driver + pad | 742.5 Mbps | Custom CML | 3.3 V switches, 6 V cascode ([0004](0004-driver-topology-and-supplies.md)) |

Supporting choices:

- **Digital core runs at 3.30 V**, not 5 V, with STA corners 3.00 / 3.30 /
  3.60 V (matching the shipped liberty).
- **Bit order LSB-first** on the wire, per DVI 1.0 §3.2.2.
- **The clock lane is a fourth identical serializer + driver instance**, fed
  the constant word `1111100000`.

## Alternatives considered

- **Synthesize down to a 148.5 MHz 10:5 gearbox, custom 5:1 above it.**
  Rejected on arithmetic before speed: 148.5 MHz is not an integer divisor of
  the 371.25 MHz half-rate clock (ratio 2.5), so it would need a second
  clock from the PLL or a ×2 multiplier in this block. The 2.86× margin at
  `ss_125C_3v00` was otherwise attractive; the clocking cost was not.
- **Synthesize the whole 10:1 at 371.25 MHz.** Rejected: 2.694 ns available
  against a 2.357 ns flop `minimum_period` at `ss_125C_3v00` leaves 337 ps
  for clk→Q, mux, setup, and skew across the block. That does not close.
- **Run the standard-cell serializer back-end at 5.0 V** to buy speed
  (`ss_125C_4v50` gives 1.455 ns / 687 MHz — 371.25 MHz would fit). Rejected
  on three counts: it needs a 5 V supply the block otherwise does not have;
  dynamic power scales with V², and this is the fastest, most-toggled digital
  in the block; and it puts a 5 V domain adjacent to a 3.3 V analog driver
  whose supply-noise sensitivity is already a jitter line item
  ([0005](0005-pll-interface-and-jitter-budget.md)).
- **Custom-design everything, including the encoder.** Rejected: the encoder
  at 74.25 MHz has 5.7× margin on the slow-corner flop constraint. Hand-
  drawing it would forfeit the synthesized-flow half of what this mixed-signal
  canary is meant to exercise, for no timing benefit.
- **Generate the clock lane from a divider rather than a serializer
  instance.** Rejected: it makes lane-to-lane skew depend on two different
  circuits tracking each other over PVT. An identical instance fed a constant
  word reduces that to a layout-matching problem, which is a problem the tools
  can actually check.

## Consequences

- The 10:2 gearbox, the ÷5 divider, the CML mux, and the driver are all
  hand-drawn: no synthesis, no place-and-route, no liberty. Their
  verification is SPICE across the `tmds-tx.md` §5 corner set, and their
  layout is manual. That is the bulk of the block's custom effort and should
  be scoped as such.
- The digital/custom seam is a 2-bit bus plus a clock at 371.25 MHz. It is
  the block's most timing-critical internal interface and needs an explicit
  timing contract (setup/hold at the gearbox input relative to the ÷5 pixel
  clock) before either side is built.
- The partition scales to 1080p60 by clocking the same structure faster
  (encoder 148.5 MHz — 2.86× margin at `ss_125C_3v00`; custom stages
  742.5 MHz). Per [0001](0001-resolution-ladder.md) this is an incidental
  property, not a commitment.
- Choosing 9-track over 7-track is deferred; the numbers above are 9-track,
  and a switch to 7-track would need its `minimum_period` re-checked against
  this record.
