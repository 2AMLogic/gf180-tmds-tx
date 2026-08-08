# verification

Digital verification conventions for this repository -- the digital
counterpart to what `sim/README.md` is for analog (ngspice + PVT corners).
This document is authoritative: every digital bench in this repo (cocotb +
Icarus Verilog, per `CLAUDE.md`) follows the layout, invocation, and
negative-control rule below.

## Layout

```
verification/
  README.md                      this file
  <bench-name>/
    <dut_model>.py                independent Python golden model(s)
    test_<bench-name>.py          cocotb testbench (the actual test cases)
    runner.py                     cold-start entry point (build + run + assert)
    requirements.txt              pinned Python-side toolchain (cocotb, ...)
    negative_control/
      <dut>_broken.v               deliberately-broken DUT variant (Leg 3)
```

Each `<bench-name>/` directory verifies exactly one RTL module (named after
it) and is self-contained: it can be run on its own from a clean checkout
without touching any other bench directory.

Currently: `verification/tmds_encoder/` verifies `rtl/tmds_encoder.v`.

## The three-leg verification plan

Every bench in this repo ships three independent legs. This is not
boilerplate -- each leg catches a different failure mode a single
"testbench vs. RTL" comparison cannot:

1. **Exhaustive equivalence against an independent golden model.** A
   from-scratch model, written in a different language (Python) from a
   separately-read pass over the same cited public standard, checked
   against the DUT over the *entire* reachable input space (not a sample,
   when the space is small enough to enumerate -- see "Exhaustiveness is a
   computed claim" below). This catches RTL coding bugs the model doesn't
   share.
2. **Invariants checked directly against the sweep, without reference to
   the model.** These catch the case Leg 1 cannot: the model and the RTL
   both being wrong the *same* way, because both authors misread the same
   sentence of the standard. Each invariant's check is derived independently
   from the DUT/model comparison, and its **observed** value is reported as
   data in the bench's log output, not merely asserted to hold silently.
3. **Negative control.** A deliberately broken DUT variant, run through the
   *exact same, unmodified* test suite, with an assertion that it fails.
   This is the same discipline #2 applied to LVS on the layout side
   (`layout/gds/gf180_tmds_pad_min_shorted.gds`, *"LVS clean alone is not
   evidence"*) -- a bench that has never failed is not known to be able to
   fail, and is wired into CI on every PR (`.github/workflows/ci.yml`).

### Exhaustiveness is a computed claim, not an assumed one

When a bench claims "exhaustive," it must **discover and report** the
covered space in its own log output -- a hardcoded comment asserting
exhaustiveness is not sufficient. `verification/tmds_encoder/`'s bench does
this by running a BFS over the golden model's own transition function to
discover the DUT's reachable internal-state space *before* sweeping it
(see `tmds_model.discover_reachable_states`), and logs the discovered count
and the resulting vector count actually checked
(`Leg 1 (exhaustive equivalence): checked 2304 of 2304 ...`).

## Cold-start invocation

From a clean checkout, to run the encoder bench (real DUT + negative
control):

```bash
cd verification/tmds_encoder
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
python3 runner.py
```

`runner.py` builds and simulates both DUT variants under Icarus Verilog via
cocotb's Python runner API (`cocotb_tools.runner`) and exits non-zero unless
**both** of the following hold:

- the real DUT (`rtl/tmds_encoder.v`) passes every test with zero failures.
- the negative-control DUT (`negative_control/tmds_encoder_broken.v`) fails
  the same, unmodified test suite.

Useful flags for local debugging: `python3 runner.py --good-only` (skip the
negative control), `python3 runner.py --broken-only` (only run the negative
control).

This is exactly what `.github/workflows/ci.yml` runs on every PR.

## Pinned toolchain

| Tool | Verified version | Pin mechanism |
|---|---|---|
| cocotb | 2.0.1 | `verification/tmds_encoder/requirements.txt` |
| Icarus Verilog | 13.0 (local); CI installs Ubuntu's `iverilog` apt package and prints `iverilog -V` in the job log | `.github/workflows/ci.yml` |
| Yosys | 0.68+ (local, `read_verilog`/`hierarchy`/`check` only -- see "Yosys smoke check" below); CI installs Ubuntu's `yosys` apt package and prints `yosys -V` | `.github/workflows/ci.yml` |
| Python | 3.11+ | CI: `actions/setup-python@v5` |

cocotb is the strict pin (an exact `==` version in `requirements.txt`,
since API changes across cocotb major versions are common and silently
change bench behavior -- e.g. `cocotb.runner` moved to
`cocotb_tools.runner` and `Clock(..., units=...)` was renamed to
`unit=...` between recent versions). Icarus and Yosys are pinned by
recording the exact version this bench was signed off against here, plus
printing the CI-resolved version in every run's log, rather than building
a specific simulator binary from source in CI -- if a CI apt-package bump
ever changes bench behavior, that log line is the first place to look.

## Verilog dialect

**Verilog-2005, no vendor extensions.** `rtl/` sources are consumed
unmodified by both Icarus Verilog (this directory's simulation benches)
and Yosys (`flow/`'s synthesis, and the smoke check below) -- a
SystemVerilog-only construct (`always_comb`, `logic`, interfaces, ...)
would silently work in one tool's frontend and not the other's. Concretely:
plain `module`/`endmodule`, `reg`/`wire`, `always @(...)` blocks, and
`function`/`endfunction` (including `signed` ports and `for` loops inside
them, both legal Verilog-2005) -- no `always_comb`/`always_ff`, no `logic`,
no SystemVerilog interfaces or packages.

### Yosys smoke check

Full synthesis is `flow/`'s job (out of scope here, and for DR-0003's
synthesized-domain timing-ceiling question -- a follow-on issue, not this
one). This directory's CI only asserts the RTL *elaborates* cleanly under
Yosys with no vendor extensions:

```bash
yosys -p "read_verilog rtl/tmds_encoder.v; hierarchy -check -top tmds_encoder; check"
```

## Negative control: the rule

**Every bench in this repo ships a negative control, and CI asserts it
fails.** Concretely:

- A deliberately broken copy of the DUT lives under
  `<bench-name>/negative_control/`, kept in sync with the real DUT by hand
  (small, hand-verified diffs -- not generated) so it stays a clear,
  reviewable single-bug diff against the real source.
- The broken copy declares the **same module name and port list**, so the
  *exact same, unmodified* test module runs against it -- proving the bench
  itself (not a copy of it) is capable of failing.
- The bug is documented in the broken file's header: what was changed, and
  why it's wrong -- so a reviewer doesn't have to diff two files to
  understand what's being tested.
- `runner.py` (or the bench's equivalent cold-start entry point) asserts
  the broken variant fails, and this assertion is part of the same CI job
  that runs the real bench -- not a separate, easily-forgotten job.

`verification/tmds_encoder/negative_control/tmds_encoder_broken.v` flips
the sign of the running-disparity accumulator's update in one of stage 2's
three branches (`next_cnt = cur_cnt - (...)` instead of `+`) -- exactly the
class of bug issue #10 named as an example ("the accumulator update sign
flipped"). Because every state but the post-reset one (`cnt == 0`) is
reached, in this DUT, through that same branch (see "Reachable state
space" below), this single-line bug is caught immediately by Leg 1
(exhaustive equivalence), not just by a long-run statistical leg -- a
sharper, faster-failing negative control than one that only shows up after
many cycles.

## `tmds_encoder`: bench-specific notes

### Algorithm and control-character citation

Digital Display Working Group, *"Digital Visual Interface (DVI), Revision
1.0"*, 2 April 1999 -- Section 3.3 "TMDS Encoding" (stage 1: transition
minimization, Figure 3-5; stage 2: DC balancing) and the four fixed
control-token values transmitted during horizontal/vertical blanking. The
same citation is repeated in `rtl/tmds_encoder.v`'s header and in
`verification/tmds_encoder/tmds_model.py`'s module docstring.

Cross-check (corroborating only, not the primary source): the same
algorithm and control-token values are reproduced in the public
"Transition-minimized differential signaling" Wikipedia article, which also
states the well-known invariant that exactly 460 of the 1024 possible
10-bit codes are valid TMDS *data* characters. The exhaustive bench
independently re-derives that same figure (`460 distinct reachable data
codes` in the Leg 2 log line) from this repository's own transcription of
the algorithm -- agreement with a figure this widely published is strong
corroborating evidence the transcription is correct.

### Reachable state space

The DUT's only internal state (besides the output register) is the
8-bit signed running-disparity accumulator `cnt`. The bench's Leg 1
BFS discovers its reachable set from `cnt == 0` (the post-reset /
post-blanking value) to be exactly:

```
{-8, -6, -4, -2, 0, 2, 4, 6, 8}   (9 states)
```

Every one of these 9 states is reachable from `cnt == 0` in exactly **one**
step (there is a data word that reaches each state directly from reset) --
so the exhaustive sweep re-establishes each state, for every one of the 256
data words tested against it, via a fresh reset plus a single witness data
word, rather than needing a longer replay sequence. Full space: 9 states x
256 data words = **2304 vectors**, all checked (not sampled) -- the number
the bench's log line reports.

### Leg 2 invariants and their derivations

- **Transition bound: <= 3.** The transition-minimization stage (stage 1)
  picks whichever of the XOR/XNOR chains has fewer bit-to-bit transitions
  among the 8 data-derived output bits. Since the two chains' transition
  counts always sum to exactly 7 (each of the 7 internal chain positions
  contributes a transition to exactly one of the two chains), the
  minimum of the pair is provably <= 3 for any 8-bit input (the pair sums
  to an odd number, 7, so the closest achievable split is 3 and 4). This is
  a closed-form combinatorial consequence of the cited algorithm, not a
  number taken from the citation directly -- the bench's exhaustive sweep
  confirms it is tight (observed max = 3, `Leg 2 (transition bound):
  observed max transitions = 3`).
- **Control/data distinguishability: exact.** Checked against the
  *enumerated* set of reachable data codes (460 of them, from the same
  exhaustive sweep), not a rule of thumb -- `0` collisions with the 4 fixed
  control codes, every run.
- **Round-trip decode: exact, 0 failures over the full 2304-vector sweep.**
  `tmds_model.decode` is a from-scratch inverse transcription (undoing
  stage 1's chain, then stage 2's optional full-byte inversion) -- notably
  stateless: unlike encoding, decoding a *data* character needs no running
  disparity, since bit 9 (whether the byte was inverted) and bit 8 (which
  chain encoded it) are both carried in the character itself.
- **Long-run cumulative disparity: reported, and sanity-bounded by a
  random-walk formula, not a fixed constant.** This is the one property
  where the naive expectation ("DC-balanced, so bounded by a small
  constant regardless of run length") turned out to be wrong, and is
  recorded here rather than quietly patched around: two of the four fixed
  control characters (`CTRL_10`, `CTRL_11`) carry nonzero bit-disparity
  (-2 and +2 respectively; `CTRL_00`/`CTRL_01` are exactly 0), and nothing
  in the encoder equalizes control-character *usage frequency* -- that's a
  property of the video timing signal driving `ctrl`, not of this encoder.
  A synthetic stream that selects among the 4 control codes uniformly at
  random (deliberately, to stress this rather than flatter it) is
  therefore a bounded-step random walk in cumulative disparity, whose
  magnitude grows roughly with sqrt(symbol count) -- not O(1). The bench
  asserts a `5 * sqrt(symbol count)` sanity bound (observed ~120 over 8180
  symbols against a ~452 bound at the time this was written) -- generous
  enough to tolerate that expected sqrt(n) growth, tight enough to still
  catch a genuine regression such as an accumulator that never corrects
  (which grows linearly in n and blows through the bound quickly; this is
  exactly what the negative control's sign-flip bug does further out than
  Leg 1 already catches it). A real DVI/TMDS link does not hit this
  synthetic worst case (control codes encode HSYNC/VSYNC, far from
  uniformly distributed over a real blanking interval), but the bench
  reports what it actually observes rather than assuming the friendlier
  real-world case.

### cocotb clocking gotchas (Icarus + cocotb 2.0.1)

Two footguns this bench's helpers (`start_clock`, `clock_edge` in
`test_tmds_encoder.py`) work around, recorded here so the next bench in
this repo doesn't have to rediscover them:

1. **Spurious edge at t=0.** `dut.clk` is `X` until the `Clock` coroutine
   drives its first value. Awaiting `RisingEdge(dut.clk)` immediately after
   `cocotb.start_soon(Clock(...).start())`, with no intervening trigger,
   can observe that initial `X`-to-known transition as if it were a real
   rising edge, silently shifting every subsequent cycle's accounting by
   one. Fix: `await Timer(1, unit="ns")` once, right after starting the
   clock, before the first `RisingEdge`.
2. **Registered outputs can read stale immediately after
   `await RisingEdge`.** On this Icarus + cocotb 2.0.1 combination, reading
   a register (`tmds`, `cnt`) right after `await RisingEdge(dut.clk)` can
   observe the *pre-edge* value, not the value that edge's non-blocking
   assignment just produced -- a real, reproducible one-edge race, not a
   misunderstanding of this bench's own timing (confirmed by an isolated
   monitor coroutine during development). cocotb's usual fix,
   `await ReadOnly()` after the edge, resolves the read but then forbids
   writing new stimulus until another trigger is awaited (`"Attempting
   settings a value during the ReadOnly phase"`), which breaks the
   set-inputs/read-outputs-next-call pattern this bench uses per vector.
   Fix used here instead: sample at the **following `FallingEdge`**
   (`await RisingEdge(dut.clk); await FallingEdge(dut.clk)`) -- by then the
   posedge's non-blocking assignments have safely settled, reads are
   reliable, and the coroutine is back in a normal (write-legal) phase for
   the next vector's stimulus.
