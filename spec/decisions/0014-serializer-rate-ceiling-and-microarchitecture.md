# DR-0014: Serializer rate ceiling and micro-architecture

**Status: Accepted.** Revises DR-0003's synthesized/custom boundary at the
720p60 operating point only; DR-0003 stands unmodified at 480p. Does not
touch DR-0012 (the clock derivation this stage consumes) or the PLL
interface it fixes.

## Context

DR-0003 assigned the TMDS encoder and "a first-stage 10:1→2:1
parallel-to-serial reduction" to the synthesized domain
(`gf180mcu_fd_sc_mcu9t5v0`, 3.3 V corner family), leaving one item
explicitly open: *"the actual achievable synthesized clock frequency has
not yet been characterized against this library's timing arcs"* at the
"pixel-domain-derived intermediate rate (5× pixel clock = 371.25 MHz @
720p60)". DR-0009's own Status line (the encoder's four-stage pipeline
record) closed the **encoder's** half of that question and restated the
remainder verbatim: *"the 371.25 MHz intermediate rate this record flags
belongs to the 10:1→2:1 serializer, which is still unwritten and still
unmeasured."*

Issue #159 writes that stage (`rtl/tmds_serializer.v`,
`verification/tmds_serializer/`) and, per this record, measures it — not
by re-running the encoder's full synthesis→P&R→STA flow (see "Alternatives
considered" for why that would not change the answer at 720p60), but from
two library timing arcs this repository has already measured or can
measure directly from the vendored liberty file, at the same worst-setup
corner (`ss_125C_3v00`) DR-0003's own synthesized-domain assignment is
checked against:

- **The register-to-register sequential floor**: `SEQUENTIAL_OVERHEAD_NS`
  (`flow/synth_tmds_encoder.py`) — 2.3452 ns clock-to-Q on
  `gf180mcu_fd_sc_mcu9t5v0__dffq_1`, 0.7707 ns library setup time at the
  capture flop, and 0.004 ns launch-vs-capture clock skew, 3.1199 ns in
  total (rounded up to 3.2 ns for the encoder's own ABC delay-target
  arithmetic) — measured by issue #115's post-route STA
  (`flow/tmds_encoder/records/20260817-110611-37e197a.md`), for the *same*
  library, corner and flip-flop cell this serializer's own registers would
  map to if synthesized. This is a **floor on every register-to-register
  path in this library at this corner**, independent of which design the
  registers belong to: it is the delay of a path with literally zero logic
  between two `dffq_1` instances, so no combinational network — regardless
  of complexity — can make a register-to-register period shorter than it.
- **The chosen micro-architecture's own logic depth**: one
  `gf180mcu_fd_sc_mcu9t5v0__mux2_2` level (`I0`→`Z`, `cell_fall`, the
  `ss_125C_3v00` liberty's own timing table at the (0.111 ns input
  transition, 0.02966 pF output load) grid point) = **1.192 ns** — see
  "Micro-architecture" below for why one mux level is the actual depth
  needed, and `flow/serializer_rate_feasibility.py` for the script that
  reads this value directly from the vendored liberty file rather than
  asserting it.

Both numbers are reproducible from files already in this repository
(`flow/synth_tmds_encoder.py`'s constant, the vendored
`gf180mcu_fd_sc_mcu9t5v0__ss_125C_3v00.lib`) — `flow/serializer_rate_feasibility.py`
does exactly that and renders the verdict below, so this record's claim is
checkable rather than asserted.

## Decision

### 1. Micro-architecture: loadable shift register, not a holding-register + 5:1 mux

Two structures reduce the encoder's 10-bit character to 2 bits per
`clk_half` cycle:

- **(a) Loadable shift register** (chosen): a 10-bit register that shifts
  right by two every cycle, with a parallel load on the character
  boundary. Every output bit passes through exactly one 2:1 multiplexer
  (the shift/load select) between one register and the next — one
  `mux2_2` level.
- **(b) Holding register + 5:1 output mux**: a 10-bit register loaded once
  per character, with a free-running modulo-5 phase counter selecting one
  of five 2-bit slices onto the output register. A 5:1 selection needs at
  least two 2:1-equivalent mux levels (a `mux4`-then-`mux2`, or three
  `mux2` stages), and the phase counter itself needs to be established by
  reset timing and re-derived or held stable indefinitely.

At a 3.1199–3.2 ns sequential floor against a 2.6936 ns (720p60) or
7.4074 ns (480p) period, **every additional logic level is a first-order
cost, not a second-order one** — (b) needs at least one more `mux2_2`-class
level than (a) for no functional benefit (the character boundary already
comes from a two-flop edge detector on `clk_pix`, so (a) needs no
counter-to-mux path to close either). (a) is therefore the ratified
micro-architecture, implemented as `rtl/tmds_serializer.v`.

### 2. Rate ceiling: infeasible in the synthesized domain at 720p60

At 720p60 the reduction stage's own clock (`clk_half`, DR-0012 Decision 1)
is 371.25 MHz, a 2.6936 ns period. The required register-to-register
budget for micro-architecture (a) is:

```
3.1199 ns (sequential floor, ss_125C_3v00)
+ 1.192  ns (one mux2_2 level, I0->Z, same corner)
= 4.3119 ns
```

**4.3119 ns > 2.6936 ns — a 1.6183 ns (60.1 %) deficit against the period,
at the worst 3.3 V corner DR-0003's own synthesized-domain assignment is
checked against.** This is not a margin-limited result the way DR-0009's
encoder closure was (2.1 % margin) — it is a floor violation: even the
minimal one-mux-level micro-architecture this record just chose cannot
close timing in this domain at this rate, and no synthesis effort could
recover 1.6 ns from a single already-minimal mux level.

**Consequently, at 720p60 the 10:1→2:1 reduction — and, because it shares
the same clock-tree root, the divide-by-two clock derivation DR-0012
Decision 1 specifies — moves to the custom (CML) domain**, revising
DR-0003's synthesized/custom boundary at this operating point only. The
custom final 2:1 multiplexer DR-0003 already assigns to the custom domain
(`design/tmds_final_mux.sch`) absorbs this stage directly: at 720p60 it
becomes a 10:1 (not 2:1) structure, or equivalently the reduction and the
final mux merge into one custom stage. That physical implementation is
follow-on work this record does not itself perform (see "Consequences").

### 3. Rate confirmed feasible in the synthesized domain at 480p

At 480p, `clk_half` is 135 MHz, a 7.4074 ns period. The same 4.3119 ns
requirement leaves **3.0955 ns (41.8 % of the period) of positive margin**
— comfortable, not razor-thin, and using the *same* worst corner and the
*same* minimal micro-architecture as the 720p60 calculation above, so
this is not an optimistic estimate. **DR-0003's synthesized-domain
assignment for the 10:1→2:1 reduction stands unmodified at 480p.**

### 4. `rtl/tmds_serializer.v` serves both operating points, in different roles

One RTL module, unchanged between rates:

- **At 480p**, it is a synthesizable implementation of DR-0003 as
  ratified — the actual gate-level netlist for this stage, subject to the
  same synthesis→P&R→STA flow the encoder already went through (not yet
  run; see "Consequences").
- **At 720p60**, per Decision 2, it cannot be synthesized to this library
  at this rate. It instead serves as the **executable reference model**
  the custom (CML) implementation of the merged reduction+mux stage must
  reproduce bit-for-bit: the LSB-first bit ordering, the character-boundary
  cadence (a two-flop edge detector on `clk_pix`, self-aligning after
  reset, three `clk_half` cycles of latency), and the 2-bit word framing
  `ser[0]`/`ser[1]` present to the custom multiplexer.

`verification/tmds_serializer/` verifies the RTL's function at **both**
operating points regardless of which domain implements it — the reduction
logic and the divide-by-two's phase alignment/duty cycle are checked
identically whether the eventual physical realization at 720p60 is a
literal synthesized netlist (it is not, per Decision 2) or a custom
circuit built to the same specification the RTL encodes.

## Alternatives considered

- **Run the encoder's full synthesis→P&R→STA flow against
  `rtl/tmds_serializer.v` before ruling on feasibility**, rather than the
  liberty-arc floor argument above, was considered and deferred, not
  rejected outright — it remains useful future work for the **480p** netlist
  specifically (Decision 3 shows positive margin exists, not what a real
  synthesized netlist's actual critical path is). It would **not** change
  the 720p60 verdict: Decision 2's floor argument is a lower bound on any
  register-to-register path in this library, so a full physical
  implementation could only ever confirm what the floor already rules
  out, at the cost of standing up a P&R/STA run this repository's sandboxed
  build environment could not complete this record (OpenROAD requires a
  Docker image this environment could not obtain permission to run). Stated
  as an explicit gap, not hidden: **no synthesized netlist, routed layout, or
  post-route STA record exists yet for `rtl/tmds_serializer.v` at 480p** —
  DR-0003's synthesized-domain assignment there rests on the same liberty-arc
  floor argument as the 720p60 ceiling, not on a project-specific measured
  Fmax the way the encoder's DR-0009 record has one.
- **Deepen the synthesized reduction below 2 bits/cycle** (e.g. keep more
  bits synthesized, narrowing the custom domain's job) was considered and
  rejected for the same reason DR-0003 itself gave when it chose 10:1→2:1
  over a deeper split: the floor argument above applies to *any*
  register-to-register path in this domain at 720p60, so a narrower
  per-cycle reduction (more bits synthesized, same 371.25 MHz clock) would
  still need at least the same 3.1199 ns floor and would need *more*
  logic, not less, to reach a narrower bit count per cycle — strictly
  worse, not better.
- **Slow the reduction-stage clock below 371.25 MHz** (e.g. a 3:1 or 4:1
  synthesized ratio feeding a wider custom mux) was considered and
  rejected as a scope expansion beyond this record: DR-0012 Decision 1
  already fixes `clk_half` at exactly half the bit-rate clock for a
  specific, load-bearing reason (it is simultaneously the DDR clock the
  custom multiplexer samples on both edges), so changing the reduction
  stage's clock ratio would reopen DR-0012, not just this stage's
  micro-architecture — out of scope for issue #159's mandate to consume,
  not redesign, DR-0012's fixed interface.

## Consequences

- `spec/tmds-tx.md` DR-0003's synthesized/custom boundary is **revised at
  720p60 only**: the 10:1→2:1 reduction and the divide-by-two clock
  derivation move to the custom domain, merging with the already-custom
  final 2:1 multiplexer. DR-0003 stands **unmodified at 480p**.
- `rtl/tmds_serializer.v` is not itself the 720p60 physical implementation
  — it is the reference model a custom circuit at that rate must match.
  Drawing that custom circuit (schematic, netlist, PVT-corner verification
  against the same bit-ordering/framing contract) is follow-on work this
  record does not perform; DR-0003's own "still unwritten and still
  unmeasured" framing is retired for the *function* (written, verified by
  `verification/tmds_serializer/`) but a 720p60 custom-domain
  implementation of the merged stage remains open.
- No synthesis, place-and-route, or STA run of `rtl/tmds_serializer.v`
  exists yet at 480p either. `flow/serializer_rate_feasibility.py`'s
  liberty-arc argument establishes that 480p sits inside the achievable
  envelope (§3), not that a specific netlist has been measured against it.
  Running the encoder's own flow (`flow/synth_tmds_encoder.py`-style
  timing-driven synthesis, P&R, multi-corner STA) against this RTL at 480p
  is the natural next measurement, deferred here because this repository's
  build environment could not reach OpenROAD when this record was written
  (see "Alternatives considered").
- `verification/tmds_serializer/` (issue #159) is unaffected by this
  record's domain assignment either way: it verifies the RTL's function at
  both operating points, and that function is what any eventual physical
  realization — synthesized (480p) or custom (720p60) — must reproduce.

## Status

**Accepted.** `spec/tmds-tx.md` DR-0003's Status line is updated to point
here for the serializer side of its own open item; DR-0009's Status line
(which last restated that same open item) is updated with a forward
pointer. Numbering note: DR-0013 is the last decision record ratified
before this one; DR-0014 is the next available number, not a renumbering of
any prior draft.
