# Roadmap

gf180-tmds-tx is a DVI-mode TMDS transmitter (encoder, serializer, CML line
driver and custom pad ring with ESD) on the gf180mcu open PDK.

Status as of 2026-11-13, `main` @ `d848ee2`.

The graded verdict lives in [`signoff/signoff.json`](../signoff/signoff.json)
and the per-row evidence in
[`measurements/characterization.md`](../measurements/characterization.md);
this file points at them and does not restate their numbers.

## Where it stands

Verdict of record: **17 of 22 T1 items met, 1 not applicable, 4 unmet**
(`klt signoff`, pinned to `klayout-tools==0.8.0`; see
[`signoff/README.md`](../signoff/README.md)).

| T1 item | Analog (driver + pad ring) | Digital (`tmds_encoder`) |
| --- | --- | --- |
| 1 to 4 (sources, layout, DRC, LVS) | met | met |
| 5 Corner verification | **unmet**, `no_evidence` (#229) | met (#228, `flow/tmds_encoder/klt_sta.json`) |
| 6 Monte Carlo evidence | **unmet**, `no_evidence` (#229) | not applicable (#296) |
| 7 Post-layout verification | **unmet**, `no_evidence` (#222, #230) | **unmet**, `no_evidence` (#228) |
| 8 to 10 (characterization, testbenches, hygiene) | met | met |
| 11 Power delivery | met (#210) | met (#206) |

The three analog rows are mostly a grading gap: the corner, mismatch and
post-layout results exist as append-only Markdown records under
`sim/*/records/`, and the grader accepts only `klt sim`, `klt yield` and
`klt pex` envelopes. One part is an engineering gap: the post-layout eye
records predate the VDD-side clamp of #210 and have not been re-run (#222).

On the README's maturity ladder the block sits at "assembly PVT-verified" for
the pre-#210 assembly only; later rungs are open. Other state that matters:

- The custom final 2:1 multiplexer is laid out and DRC/LVS-matched
  (`layout/gds/tmds_final_mux.gds`), but all of its simulation evidence is
  schematic-level. No simulatable extracted DUT exists for it: `layout/sim/`
  holds DUTs for `cml_driver_core` and the pad-ring assembly only.
- The PVT harness has a batch backend (`sim/harness/batch.py`, PR #300) with
  stubbed tests. Its one-point live proof has not passed, so #299 stays open.
- DR-0017 (PLL sourcing, 135 MHz half-rate clock, 480p first), DR-0018 (lane
  external character interface) and DR-0019 (pad pitch/depth correction) are
  **Proposed**, not Accepted. `rtl/tmds_tx_lane.v` is functionally verified;
  its timing closure is open.
- `sim/esd-diode-clamp-cv` measures `diode_nd2ps_06v0` only; the
  `diode_pd2nw_06v0` leg added by #210 is a bounded estimate in
  `design/esd-capacitance-budget.md` §10.5a.

## Now

Each of these now has an issue, filed alongside this pass; none needs a
multi-corner run.

1. **Extracted DUT for the final mux (#311).** Add a generator that turns
   `layout/gds/tmds_final_mux.spice` into a simulatable fragment, following
   `layout/scripts/gen_cml_driver_core_dut.py`.
   Done when `layout/sim/tmds_final_mux_dut.spice` is committed, the generator
   has a `--check` mode run by the lint job, and a unit test covers it.
2. **pd2nw branches in the clamp C-V testbench (#312).** Extend
   `sim/esd-diode-clamp-cv/testbench/` with `diode_pd2nw_06v0` probes at the
   drawn geometry. This is the testbench half of #222; the measurement stays
   there. Done when `sim/run_corners.py esd-diode-clamp-cv --backend batch
   --dry-run` prints requests carrying the new measures and CI is green.
3. **Point stale references at their live targets (#313).** `signoff/README.md`
   still names klayout-tools#3740 (closed, not fixed) as the item 7 digital
   blocker; the live one is klayout-tools#5002. The README repo-layout tree
   omits `signoff/`, `docs/` and `manifests/`.
   Done when both are corrected and the `signoff` CI job still passes.

## Next

- **Batch backend live proof (#299).** Done when one `esd-clamp-cv` point at
  `tt_27c_3.30v` run through `--backend batch` agrees with record
  `sim/esd-clamp-cv/records/20260814-193222-dd48630.md`. Blocked: the batch
  run aborts with `could not find a valid modelname` while the same request
  passes locally (`sim/README.md`, "Known gap"). klayout-tools#5474 (report
  the batch PDK revision in the receipt) closed on 2026-11-13, after the
  0.8.0 pin was taken.
- **Post-clamp eye re-run and pd2nw C-V record (#222).** Done when new
  append-only records exist for the 5-corner eye matrix on the current
  assembly and for the pd2nw clamp, and §10.5a carries the measured value.
  Unblocked by #299 and Now item 2.
- **Analog item 7 (#230).** Done when a `klt pex` report on the post-#210
  assembly is committed and `7.analog` is cited. Blocked on #222.
- **Analog items 5 and 6 (#229).** Done when every analog spec row has a
  passing `klt sim` envelope or is a declared gap, and a `klt yield` report
  backs each statistical row. Blocked on the same batch failure as #299.
- **Digital item 7 (#228).** Done when `flow/tmds_encoder/klt_fv_sdf.json` is
  committed and cited as `7.digital`. Blocked on klayout-tools#5002 (SDF
  annotation aborts `vvp`) and a pin bump to a release that fixes it.
- **Final-mux post-layout re-simulation.** Done when `sim/tmds-final-mux-eye`
  and `sim/cml-driver-eye-realmux` have records against the extracted DUT.
  Unblocked by Now item 1 and #299. No issue yet.
- **First artifact-store evidence run (#254).** Done when a real
  `esd-clamp-cv` grid is stored and `klt artifact verify` exits 0. Unblocked
  by #299 or by the ruling the issue asks for.

## Later

- **Lane timing closure.** Which rate is the target? DR-0017 makes 480p at
  135 MHz the only live operating point and defers 720p60; until it is
  Accepted there is no clock constraint to close `tmds_tx_lane` against.
- **A 720p60 clock path.** DR-0017 leaves 720p60 with no clock source. A
  successor record must name one before any 720p60 integration work.
- **Reduction stage in the custom domain.** DR-0014 moves the 10:1→2:1
  reduction out of the synthesized domain at 720p60. Is it built at all while
  720p60 is deferred?
- **Full pad ring (three data lanes plus clock).** What must be re-derived
  from DR-0019's corrected pad dimensions before a ring floorplan is drawn?
- **Shuttle seat.** Which open items in §8 of the
  [Chipalooza proposal](chipalooza/challenge-5-proposal.md) must close first?

## Blocked and waiting

**Of the seven issues open at `d848ee2` (2026-11-13), none was
dispatchable.** All seven were blocked or waiting:

- #299 and #229: batch runs abort on model selection, and no numbered issue
  tracks the cause yet. #222 waits on #299, and #230 on #222.
- #228: klayout-tools#5002. #254: a ruling on where the first real run executes.
- #158: a maintainer digest issue, not design work.
- DR-0017, DR-0018, DR-0019: ratification. A Status line is not flipped by hand.

Issues filed after that snapshot are not covered by the list above, and some of
them are startable — the three `## Now` items (#311, #312, #313) among them.
For what is dispatchable right now, read the live queue, not this section.

## Not planned

- A PLL. It comes from [`gf180-pll`](https://github.com/2AMLogic/gf180-pll)
  (DR-0017, `reuse.lock.json`); this repo specifies the interface and stops.
- HDMI. This is a DVI-mode block (DR-0016); data islands sit outside it.
- 1080p60 as an architecture driver; it is a stretch until 720p closes.
- Pre-silicon HBM/CDM ESD qualification (DR-0015), or relaxing a ratified
  spec row to make a result pass.
