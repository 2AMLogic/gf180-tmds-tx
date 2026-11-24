# Work Log

Chronological record of merged PRs and closed issues, newest first.
Maintained automatically by the Guide triage agent's document-maintenance
phase — see `.claude/skills/loom-guide/guide.md` for how entries are
selected.

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)
- [2026-08](work_log/WORK_LOG_2026-08.md)

### 2026-11-24

- **PR #403**: fix(sim): select GF180 MOS bins by finger width in batch requests
- **PR #397**: refactor(flow): drop never-interpolated params from render_record
- **Issue #396** (closed): flow: four never-referenced params remain in sibling render_record() signatures (sdf, synth, gate-level)

### 2026-11-23

- **PR #395**: test: keep testbench fixture files alive through assertions
- **PR #393**: docs: mark pad-to-strap lateral coupling unmeasured in the retained pad-pitch reports
- **PR #392**: refactor: drop unused params from pnr render_record
- **PR #391**: sim(pex): reject mixed card/expr measurement deps; check node rewrite on every emitted form
- **PR #390**: refactor: share ngspice version rendering between batch and MC report paths
- **PR #388**: fix(sim): regenerate pex eye requests with rise/fall UI measurements
- **PR #386**: test(signoff): guard analog target text and closes_with liveness; add digital-spec map guard
- **Issue #394** (closed): Share the temporary testbench fixture and keep its files alive through assertions
- **Issue #385** (closed): lint step 4 fails on main: sim/pex requests stale after #379's tb.json edits
- **Issue #383** (closed): Signoff spec maps: guard target text and closes_with liveness, and give digital-spec.json any guard at all
- **Issue #382** (closed): sim/pex/gen_requests.py: a measurement depending on both a raw .meas card and an expr result is emitted as an unreadable expr (no guard, no test)
- **Issue #381** (closed): Share ngspice version formatting between batch points and Monte Carlo reports
- **Issue #378** (closed): render_record in flow/pnr_tmds_encoder.py takes three parameters it never uses
- **Issue #326** (closed): Document unmeasured pad-to-strap lateral coupling in the retained pad-pitch reports

### 2026-11-22

- **PR #376**: flow: drop stale DRC/LVS verdicts from P&R record template
- **Issue #373** (closed): Remove obsolete DRC and LVS verdicts from new place-and-route records

### 2026-11-21

- **PR #380**: sim(pex): add generated klt pex requests, schematic assembly DUT, and extract-only report
- **PR #379**: feat(signoff): map DR-0013 rows to bench checks and grade row 5 rise/fall in UI units
- **Issue #372** (closed): T1 item 5 (analog) prep: commit the DR-0013 row-to-measure map and give row 5 (rise/fall) a graded check
- **Issue #371** (closed): T1 item 7 (analog) prep: klt pex-shaped testbench requests for the post-#210 pad-ring assembly, plus an extract-only body-bias report

### 2026-11-20

- **PR #375**: feat(sim): add --stage-models opt-in for batch model staging, record worker staging state

### 2026-11-18

- **PR #367**: test(sim): pin nominal seed=None in run_all request and samples
- **PR #365**: test(sim): pin MC seed-block corner order against a literal
- **PR #363**: test(sim): pin ids and seeds supplied by run_all
- **PR #360**: fix(sim): read MC provenance from klt sim reports
- **PR #361**: test(sim): cover run_mc's klt sim report-to-Sample mapping
- **PR #357**: feat(sim): run the mismatch Monte Carlo as klt sim monte_carlo requests
- **PR #356**: ci: run the append-only evidence gate on merge_group against the queue's recorded base
- **Issue #366** (closed): Pin the nominal request's seed=None in test_run_all_supplies_ids_and_seeds
- **Issue #364** (closed): The record's k-to-corner seed-block mapping ("k: 0=tt, 1=ff, ...") is not pinned by any test
- **Issue #362** (closed): run_all's sample label and seed lambdas are untested: four off-by-one mutations leave the suite green
- **Issue #358** (closed): run_mc.py re-derives provenance the klt sim report already states (ngspice version, per-sample seed/index)
- **Issue #359** (closed): No unit test for run_mc.py's klt sim report -> Sample mapping (_samples_from_report)
- **Issue #347** (closed): Retire run_mc.py's hand-rolled local ngspice pool in favour of klt sim monte_carlo
- **Issue #355** (closed): Merge queue: add the merge_group trigger to the required-check workflow(s)

### 2026-11-17

- **PR #354**: chore(loom): resync installed Loom to v0.19.1306

### 2026-11-16

- **PR #352**: chore(loom): resync installed Loom to v0.19.1302

### 2026-11-15

- **PR #351**: refactor: single-source DR-0011 pad constants in pad_ring_cells.py, dedupe their tests
- **PR #349**: Move cml-driver-mismatch MC logs to the artifact store, forward-only
- **PR #348**: test: pin provenance-extractor non-vacuity in the shared-composition guard
- **PR #346**: erc: commit the tmds_encoder well-tie negative-control report (51 KB findings-only shape)
- **PR #331**: fix: narrow sim/*/corners log negation to the un-migrated bench, drop stale committed-log comments
- **PR #343**: fix: rewrite negctl ERC spec comment to describe its own control
- **PR #344**: test: fold SPICE continuations in the shared DUT parser and convert the mux suite to it
- **PR #327**: refactor(verification): one cocotb pin file, one shared three-leg runner skeleton
- **PR #322**: feat: add extracted-DUT generator for tmds_final_mux
- **PR #338**: docs: add --findings-only --omit-antenna-tables to the tmds_encoder ERC recipe
- **PR #342**: docs: qualify harness log-location docstrings for manifest-forward storage
- **PR #339**: test: compare composer provenance comments in the shared-composition guard
- **PR #335**: layout: drop blanket noqa:F401 and six dead imports from layout/scripts
- **PR #336**: feat(sim/harness): drop ngspice's Reference value trace from corner logs
- **PR #315**: refactor(sim/harness): assemble both backends' netlists from one set of helpers
- **PR #323**: refactor(flow): source klt sta constants from their flow-family single source
- **PR #333**: chore: remove dead worktree:return npm script
- **PR #328**: refactor: single-source extracted-DUT test scaffolding into _dut_netlist
- **PR #330**: test: guard the klt sta request against the committed graded envelope
- **Issue #350** (closed): Single-source DR-0011 pad constants and drop duplicated ClampRows/DR0011 tests
- **Issue #345** (closed): Migrate sim/cml-driver-mismatch/run_mc.py to the artifact store and drop its .gitignore carve-out
- **Issue #340** (closed): sim/tests: the new provenance guard goes silently vacuous if _dut_lines renames its comment prefix
- **Issue #337** (closed): Commit the ERC negative-control reports now that the flagged recipe keeps them at ~51 KB (follow-on to #320)
- **Issue #314** (closed): Remove the dead sim/*/corners .gitignore negation and two comments that still claim logs are committed
- **Issue #341** (closed): layout/erc-supply-spec.json's own Run: block still shows the pre-flag klt erc recipe (follow-on to #320/#338)
- **Issue #329** (closed): Convert test_tmds_final_mux_dut.py onto sim/tests/_dut_netlist.py (landed with #328)
- **Issue #307** (closed): Collapse duplicated cocotb bench scaffolding in verification/: one pin file, one three-leg runner skeleton
- **Issue #311** (closed): Generate a simulatable extracted DUT for tmds_final_mux (layout/sim/tmds_final_mux_dut.spice)
- **Issue #320** (closed): Drop 2.53 MB of all-unchecked antenna scaffolding from tmds_encoder.erc.json: add --omit-antenna-tables to the klt erc recipe
- **Issue #332** (closed): Harness docstrings still claim raw logs are committed (report.py, corners.py, harness/README.md)
- **Issue #334** (closed): sim/tests: the composer drift guard does not compare the DUT provenance comment
- **Issue #309** (closed): Drop the blanket `# noqa: F401` in layout/scripts: it suppresses a linter CI never runs, and 6 imports have already rotted behind it
- **Issue #308** (closed): sim/harness: one netlist-assembly path for both backends — compose_body re-implements compose_deck line for line
- **Issue #319** (closed): flow/klt_sta_tmds_encoder.py retypes the cell library, corner list, and clock period the flow family already single-sources
- **Issue #321** (closed): Remove dead npm script worktree:return: its target was deleted by a Loom resync
- **Issue #318** (closed): Single-source the extracted-DUT test scaffolding: sim/tests duplicates 67 lines the generators already share
- **Issue #324** (closed): flow/ has no test suite, so nothing guards the klt sta request against the graded envelope it produced

### 2026-11-14

- **PR #310**: docs: roadmap as of 2026-11-13
- **PR #316**: feat(sim/harness): emit .options noinit from one shared options builder
- **PR #325**: sim: probe the VDD-side diode_pd2nw_06v0 clamp in esd-diode-clamp-cv
- **Issue #305** (closed): Suppress ngspice's initial-transient node table in harness logs: 76.8 MB of 92.7 MB no tool reads
- **Issue #312** (closed): sim/esd-diode-clamp-cv: add diode_pd2nw_06v0 probes to the testbench (testbench half of #222)

### 2026-11-12

- **PR #302**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-07

- **PR #300**: feat(sim): add klt batch backend to the PVT harness
- **PR #298**: Bump Repo Skills 0.25.1 -> 0.25.10

### 2026-11-06

- **PR #297**: feat(signoff): record not_applicable for item 6 digital partition
- **Issue #296** (closed): T1 item 6 (digital): record the not_applicable outcome for the tmds_encoder partition

### 2026-11-01

- **PR #256**: feat(sim): store raw run logs via klt artifact, commit only a manifest
- **PR #290**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-30

- **PR #287**: refactor: drop 35 unused re-exported imports from pad-ring generators
- **Issue #282** (closed): Trim 32 unused re-export imports from pad_pitch_fit_study.py and gen_pad_ring_assembly.py

### 2026-10-29

- **PR #281**: refactor: draw gen_pad_v2 pad and clamp via shared _draw_production_pad
- **PR #270**: docs: qualify post-layout verification claims against signoff item 7
- **Issue #277** (closed): Dedupe gen_pad_v2.py pad/clamp drawing onto pad_ring_cells._draw_production_pad
- **Issue #269** (closed): T1 status: correct README status-line claim 'electrically post-layout-verified' — item 7 is no_evidence on both partitions

### 2026-10-28

- **PR #279**: docs: add missing verb to README status serializer/final-mux clause
- **Issue #278** (closed): docs: README status line lost its verb after the signoff.json qualification
- **PR #276**: refactor: share DBU, CONTACT_SIZE and drawing closures in gf180_layers
- **Issue #274** (closed): Consolidate layout generators' duplicated drawing closures and DBU/CONTACT_SIZE constants
- **PR #273**: docs: qualify digital T1 row 6 against klt item 7 no_evidence
- **Issue #272** (closed): characterization.md digital T1 table: qualify local item 6 'PASS, scope-limited' against klt T1 item 7 (no_evidence)

### 2026-10-27

- **PR #267**: refactor: share the I/O-boundary timing constants across synth, pnr and sta drivers
- **PR #265**: chore: pin klayout-tools to the 0.8.0 release and regenerate the signoff record
- **PR #263**: refactor: share pad-ring drawing helpers between fit study and assembly
- **Issue #266** (closed): Consolidate I/O-boundary timing constants (inv_1 driver, 4x load) triplicated across synth/pnr/sta flow drivers
- **Issue #264** (closed): Bump klayout-tools pin 44cc42323184 → 0.8.0
- **Issue #262** (closed): Dedupe pad drawing helpers shared by pad_pitch_fit_study and gen_pad_ring_assembly
- **PR #231**: feat(signoff): artifact-anchored evidence for T1 items 1, 2, 9, 10
- **Issue #227** (closed): T1 items 1, 2, 9, 10: bump the signoff grading pin and attest with artifact-anchored envelopes (klt signoff --attest)

### 2026-10-23

- **PR #258**: refactor: share gf180mcu layer table and _box across layout generators
- **Issue #255** (closed): Consolidate duplicated gf180mcu layer table and _box helper across layout generators

### 2026-10-22

- **PR #252**: refactor: import shared pad-fold geometry from pad_pitch_fit_study
- **Issue #242** (closed): Consolidate duplicated pad-fold geometry: gen_pad_ring_assembly.py vs pad_pitch_fit_study.py

### 2026-10-21

- **PR #249**: Bump Repo Skills 0.24.3 -> 0.24.7

### 2026-10-20

- **PR #247**: refactor: share append-only evidence-record tail across flow drivers
- **Issue #246** (closed): Dedupe append-only record-write tail across the five flow/*_tmds_encoder.py drivers
- **PR #244**: refactor: share DUT-translator CLI scaffolding in one helper module
- **Issue #243** (closed): Dedupe DUT-translator CLI scaffolding shared by gen_cml_driver_core_dut and gen_pad_ring_assembly_dut
- **PR #240**: refactor: route flow git-provenance helpers through sim.harness.report
- **Issue #239** (closed): Consolidate duplicate git-provenance helpers: flow/synth_tmds_encoder.py vs sim/harness/report.py

### 2026-10-17

- **PR #235**: docs(spec): correct transposed fd_io pad pitch/depth via DR-0019
- **Issue #234** (closed): docs: pad pitch and depth transposed in pad-ring survey and DR-0011
- **PR #232**: feat(signoff): grade T1 item 5 digital from a klt sta envelope

### 2026-10-16

- **PR #225**: Bump Repo Skills 0.24.1 -> 0.24.3

### 2026-10-15

- **PR #221**: feat(layout): draw VDD-side pd2nw clamp and Nwell tap on the pad-ring DVDD strap
- **Issue #210** (closed): Pad-ring assembly: DVDD ring strap is unlabelled dead metal, so VDD cannot be a proven supply (T1 item 11 analog unmet)
- **PR #218**: Bump Repo Skills 0.19.5 -> 0.24.1

### 2026-10-13

- **PR #216**: chore(loom): drop onIdle [auditor] — follow the fleet idle-role setting

### 2026-10-08

- **PR #211**: T1 item 11 (analog): klt erc supply spec + report for pad-ring assembly (#207)
- **Issue #207** (closed): T1 item 11 (analog): add a klt erc supply spec and report for the pad-ring assembly and cite it
- **PR #208**: feat(erc): declare well ties in digital supply spec; item 11 digital met (#206)
- **Issue #206** (closed): T1 item 11 (digital): declare well and substrate ties[] in layout/erc-supply-spec.json and re-run klt erc
- **PR #204**: feat: per-lane external 10-bit character input + select (DR-0018); ratify DR-0016
- **Issue #186** (closed): Define the block-level top's external 10-bit character input (DR-0016 Option A enabler)

### 2026-10-02

- **Issue #194** (closed): 2am: reuse rule 9 — the PLL this block takes its 270/742.5 MHz bit clock from is unnamed, and gf180-pll is ratified to 200 MHz
- **PR #202**: spec: DR-0017 PLL sourcing — name gf180-pll, 135 MHz half-rate retarget, 720p60 deferred (#194)

### 2026-09-29

- **Issue #199** (closed): Guard telemetry: worktree-write-confinement catastrophic denies on routine /tmp scratch writes during SPICE/klt sanity checks
- **Issue #198** (closed): Guard telemetry: 'git clean -fd' ASK pattern fires on search strings and issue text, not actual clean invocations

