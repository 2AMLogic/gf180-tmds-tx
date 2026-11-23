# Work Log Archive — 2026-08

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

### 2026-08-27

- **Issue #156** (closed): Dangling reference: ratification/ee-key/MANIFEST.md points to nonexistent ratification/canary-variant.md
- **PR #157**: ratification: fix dangling canary-variant.md reference in ee-key MANIFEST
- **PR #155**: ratification: install the two-key reviewer variant (EE key + market key)

### 2026-08-25

- **Issue #149** (closed): Adopt gf180_tmds_pad_v2's production pad geometry in gf180_tmds_pad_ring_assembly
- **PR #153**: feat: land production 25x25um pad geometry in block-level pad ring
- **Issue #146** (closed): Restore a layout-side _shorted negative control for tmds_encoder LVS (blocked on klayout-tools#1366)
- **PR #152**: Restore layout-side tmds_encoder_shorted LVS negative control (#146)
- **Issue #142** (closed): T1/bronze gap (post-#17): digital LVS mismatch, pad-ring/ESD-budget integration, stale characterization.md row
- **Issue #143** (closed): Investigate: can gf180_tmds_pad_ring_assembly adopt gf180_tmds_pad_v2's production pad geometry at DR-0011's 350 µm pitch?
- **PR #150**: Investigate: gf180_tmds_pad_v2's pad geometry fits DR-0011's 350 um pitch (#143)
- **Issue #144** (closed): Add an eye-mask testbench for the CML driver grading DR-0013 row 6 (combined swing+jitter), full PVT
- **PR #151**: Add eye-mask testbench grading DR-0013 row 6 (combined swing+jitter), full PVT
- **PR #148**: docs+lint: index the Monte Carlo record in characterization.md and enforce record coverage
- **PR #147**: Fix stale pad-capacitance verdict and close the digital LVS mismatch (#142, streams 1-2)

### 2026-08-21

- **Issue #139** (closed): docs: measurements/characterization.md §2 items 4/5 (digital DRC/LVS) are stale, backwards on DRC
- **PR #140**: docs: reconcile characterization.md DRC/LVS rows with current JSON reports
- **Issue #17** (closed): Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)
- **PR #138**: docs: refresh characterization.md and README for landed STA, DR-0013, pad-ring assembly
- **Issue #135** (closed): Guard-decision review: worktree-write-confinement correctly denies direct write to CLAUDE.md (keep flagged)

### 2026-08-19

- **Issue #136** (closed): DR-0010, sim/pdk.json, and sim/README.md still describe layout/ regen against gf180mcuD as pending (issue #127 closed)
- **PR #137**: docs: correct DR-0010, sim/pdk.json, sim/README.md to past tense (issue #127 closed)
- **Issue #123** (closed): DR-0010 pins gf180mcuC, but the operator's ruling was amended to gf180mcuD 6 minutes before the DR-0010 PR merged
- **Issue #131** (closed): CI: tmds-encoder-verification 'Install Icarus Verilog and Yosys' step hangs indefinitely (likely needrestart prompt)
- **PR #134**: ci: prevent apt-get install hang on needrestart prompt
- **Issue #127** (closed): Regenerate and re-sign-off layout/ artifacts (GDS/DRC/LVS) against gf180mcuD
- **PR #133**: layout: regenerate and re-sign-off against gf180mcuD (DR-0010, issue #127)
- **Issue #132** (closed): Guard-decision review: worktree-write-confinement false-denies read-only heredoc + /tmp sed -i scratch during CML/ESD SPICE debugging
- **Issue #129** (closed): gf180_tmds_pad_v2's shorted LVS negative control no longer fails (klt deck drift, not PDK-variant related)
- **PR #130**: layout: enforce LVS negative-control verdicts, re-sign-off gf180_tmds_pad_v2
- **Issue #126** (closed): Correct DR-0010 to pin gf180mcuD per operator's amended ruling; re-cite docs/config/harness defaults
- **PR #128**: docs: correct DR-0010 and downstream citations to pin gf180mcuD
- **Issue #86** (closed): Analog: assemble a single block-level layout with pad-ring + ESD integration (T1 item 2, analog)
- **PR #125**: analog: assemble cml_driver_core + diode-clamped pad-ring block (DR-0011)
- **Issue #87** (closed): Analog: redesign pad/ESD structure to meet DR-0005's pad-capacitance budget (T1 item 5, analog)
- **PR #124**: analog: redesign pad/ESD structure at real 25x25um pad, close DR-0005/DR-0011 capacitance budget (#87)
- **Issue #67** (closed): Guard trigger review: force-op:protected fires on bare 'git reset --hard HEAD' on main (uncommitted-loss discard, not a ref move)
- **Issue #68** (closed): Guard trigger review: stash-scope:create-redirect denied a stash+capture+pop sequence in an issue worktree
- **Issue #14** (closed): Guard trigger review: worktree-write-confinement denies benign /tmp scratch work
- **Issue #105** (closed): Guard trigger review: worktree-write-confinement-unresolved-var denies mkdir/heredoc/cp to var-prefixed worktree paths during PDN generation
- **Issue #107** (closed): Guard trigger review: worktree-write-confinement-unresolved-var denies plain relative-path writes after cd resolves the worktree var
- **Issue #106** (closed): Guard trigger review: worktree-write-confinement fires on a resolved-variable interpreter invocation whose only writes target /tmp
- **Issue #49** (closed): Guard trigger review: destructive-git-family ask pattern matches quoted/inspected text, not just live invocations
- **Issue #40** (closed): Guard trigger review: worktree-write-confinement-unresolved-var denies /tmp log redirection in a backgrounded sim run
- **Issue #77** (closed): Guard trigger review: force-op:detached fires on quoted HEAD~1 example text inside an issue-filing heredoc
- **Issue #78** (closed): Guard trigger review: worktree-write-confinement denies a temporary swap-out/restore of a tracked file for before/after comparison
- **Issue #50** (closed): Guard trigger review: worktree-write-confinement-unresolved-var denies a literal-var-plus-suffix cp destination
- **Issue #56** (closed): Guard trigger review: worktree-write-confinement-unresolved-var denies a heredoc redirect to a var-plus-suffix destination
- **Issue #59** (closed): Guard trigger review: gh-api-rawfield-body-literal-at correctly denied a broken raw-field comment post
- **Issue #118** (closed): Guard-decision: worktree-write-confinement-unresolved-var false-positives on literally-assigned worktree variables
- **Issue #119** (closed): Guard-decision: worktree-write-confinement false-positives on /tmp scratch writes and no-write heredocs
- **Issue #9** (closed): Spec defects: an ambiguous PDK variant, DR-0005 still provisional after #2 closed, and an incomplete PLL contract
- **PR #122**: docs: ratify PDK variant, pad/ESD, PLL-interface, and PVT-matrix decision records

### 2026-08-18

- **Issue #89** (closed): GitHub token for this repo can create issues but cannot comment/label/close/edit any issue (blocks #81 closure and most Loom roles)

### 2026-08-17

- **Issue #115** (closed): Digital: close remaining 720p60 setup gap at ss_125C_3v00/ss_n40C_3v00 after DR-0008's stage1/stage2 pipeline register
- **PR #121**: digital: four-stage tmds_encoder pipeline closes 720p60 setup at all 5 corners (DR-0009)
- **Issue #120** (closed): Guard-decision: stash-scope:create-redirect on scoped git stash push — confirm guard should stand
- **Issue #110** (closed): Digital: pipeline tmds_encoder's stage1->stage2 boundary to close 720p60 setup timing (3/5 corners still fail after #100)
- **PR #116**: digital: pipeline tmds_encoder's stage1->stage2 boundary (DR-0008)
- **PR #114**: refactor: dedupe run_openroad/openroad_version onto pnr_tmds_encoder
- **Issue #112** (closed): Dedupe run_openroad/openroad_version in flow/sta_tmds_encoder.py onto pnr_tmds_encoder.py
- **PR #111**: flow: timing-driven synthesis + CTS/hold-repair for tmds_encoder
- **Issue #100** (closed): Digital: close timing on tmds_encoder at the 720p60 pixel clock (setup fails at 4/5 corners per #83's STA)
- **PR #109**: docs: fold digital-partition results into the block characterization rollup
- **Issue #88** (closed): Fold the digital partition into the block-level characterization report (T1 item 8)

### 2026-08-16

- **PR #104**: refactor: dedupe run_openroad() in sdf_tmds_encoder.py onto pnr_tmds_encoder
- **Issue #103** (closed): Dedupe run_openroad() shell-out: flow/sdf_tmds_encoder.py vs flow/pnr_tmds_encoder.py
- **PR #101**: flow: run multi-corner setup/hold STA on the tmds_encoder gate-level netlist
- **Issue #83** (closed): Digital: run static timing analysis (STA) on the synthesized gate-level netlist (T1 item 5, digital)
- **PR #99**: fix: remove unused import os in gate_level_sim_tmds_encoder.py
- **Issue #96** (closed): Remove dead code: unused 'os' import in flow/gate_level_sim_tmds_encoder.py
- **PR #98**: refactor: dedupe append-only guard across report.py's evidence writers
- **Issue #95** (closed): Dedupe append-only guard across report.py's 4 evidence writers; closes a silent-overwrite gap in write_device_netlist_snapshot
- **PR #93**: flow: extract back-annotated SDF and re-verify gate-level netlist against it
- **Issue #85** (closed): Digital: post-layout verification with back-annotated SDF (T1 item 7, digital)
- **PR #92**: flow: place-and-route tmds_encoder to a gf180mcu digital block-level GDS
- **Issue #84** (closed): Digital: place & route (P&R) to produce a block-level digital layout (T1 item 2, digital)
- **PR #90**: flow: synthesize tmds_encoder to a gf180mcu gate-level netlist
- **Issue #82** (closed): Digital: synthesize tmds_encoder to a gate-level netlist (T1 item 1)
- **Issue #81** (closed): Decompose the T1 re-read's failing items (#65) into dispatchable issues

### 2026-08-15

- **Issue #75** (closed): Dedupe RECORD_ID_RE regex: sim/harness/evidence_lint.py vs sim/compare_records.py
- **PR #79**: refactor(sim): import RECORD_ID_RE from evidence_lint in compare_records
- **Issue #73** (closed): Remove dead code: unused Pdk.klayout_dir property in sim/harness/pdk.py
- **PR #76**: refactor(sim): remove dead Pdk.klayout_dir property
- **Issue #69** (closed): Remove dead code: unused device_log_header and corner_id_rate_mbps helpers
- **PR #71**: refactor(sim): drop unused device_log_header and corner_id_rate_mbps
- **Issue #65** (closed): T1/bronze checklist re-read against current evidence (2026-08-15)
- **Issue #62** (closed): Consolidate duplicated _fmt() scalar formatter: sim/compare_records.py vs sim/harness/report.py
- **PR #63**: refactor(sim): consolidate compare_records._fmt into harness.report._fmt
- **Issue #55** (closed): Dedupe _git() shell-out helper across sim/harness/evidence_lint.py and report.py
- **PR #58**: refactor(harness): dedupe _git() shell-out between report.py and evidence_lint.py
- **Issue #34** (closed): [Epic #17] Post-layout simulation: re-run the spec suite against the layout-extracted CML driver netlist
- **PR #52**: feat(sim): sweep the CML driver's PVT matrix on the extracted netlist
- **Issue #48** (closed): Remove dead device_corner_id() and unused PvtPoint.index in sim/harness/corners.py
- **PR #51**: refactor(sim): remove dead device_corner_id() and unused PvtPoint.index
- **Issue #45** (closed): Dedupe _fmt() scalar formatter in sim/harness/cli.py and report.py
- **PR #44**: refactor(harness): dedupe _fmt() in cli.py by reusing report._fmt
- **Issue #43** (closed): Dedupe _fmt() across sim/harness/cli.py and sim/harness/report.py
- **PR #41**: refactor: dedupe parse_measurements in sim/cml-driver-mismatch/run_mc.py
- **PR #37**: docs(guide): route docs-guide worktree recovery through docs-worktree.sh
- **PR #31**: feat(layout): lay out the CML driver core cell and sign off DRC/LVS (issue #22)
- **PR #33**: docs(measurements): note esd-clamp-cv's dirty-tree caveat in characterization.md
- **PR #32**: feat(sim): add Monte Carlo mismatch evidence for the CML driver's swing/common-mode (issue #23)
- **PR #29**: docs(measurements): add block characterization report aggregating sim evidence
- **PR #28**: docs(sim): record cold-start reproducibility audit for existing experiments
- **PR #27**: docs: refresh README status line and maturity ladder to reflect landed design/pad-ring evidence
- **Issue #39** (closed): Remove duplicated parse_measurements/_MEAS_RE in sim/cml-driver-mismatch/run_mc.py
- **Issue #35** (closed): Guard trigger review: force-op:detached blocks Guide role's ad hoc docs-guide worktree reset
- **Issue #22** (closed): [Epic #17] Lay out the CML driver core cell and sign off DRC/LVS against the sized schematic
- **Issue #30** (closed): characterization.md: note esd-clamp-cv's dirty-tree caveat like smoke-cml-pair's
- **Issue #23** (closed): [Epic #17] Add Monte Carlo mismatch evidence for the CML driver's swing/common-mode
- **Issue #24** (closed): [Epic #17] Aggregate current evidence into a block characterization report
- **Issue #25** (closed): [Epic #17] Audit and fix cold-start reproducibility of sim/ testbenches
- **Issue #26** (closed): [Epic #17] Fix README status line and maturity ladder — stale since #11/#12 closed

### 2026-08-14

- **PR #21**: design: validate DR-0005's ESD/capacitance tension on the real pad cell
- **Issue #12** (closed): Validate DR-0005's open tension: ESD clamp capacitance against the 2 kV / 500 V / 2 pF budget

### 2026-08-11

- **Issue #16** (closed): Guard trigger review: worktree-write-confinement-unresolved-var denies in-worktree variable-path commands

### 2026-08-10

- **PR #20**: docs(spec): add DR-0006 ratifying DR-0002's common-mode window as a nominal-supply figure
- **PR #18**: feat(design): size and verify the CML output driver against DR-0002
- **Issue #19** (closed): DR-0002 common-mode target: clarify as nominal-supply figure vs. supply-tracking envelope
- **Issue #11** (closed): Capture and size the CML output driver to the spec's electrical targets

### 2026-08-08

- **PR #15**: feat(sim): bootstrap analog sim harness, PDK env, and evidence CI
- **PR #13**: feat: implement TMDS encoder RTL with exhaustive cocotb verification
- **Issue #8** (closed): Bootstrap the analog sim harness, PDK environment, and evidence CI
- **Issue #10** (closed): Implement the TMDS encoder in RTL with an exhaustive cocotb verification harness

### 2026-08-05

- **PR #7**: docs: add flow/ directory for synthesis and P&R recipes
- **PR #5**: feat: draw and sign off a minimal custom gf180mcu pad cell
- **PR #3**: docs: ratify TMDS TX target spec with decision records
- **Issue #6** (closed): Missing flow/ directory — needed as soon as the digital half is synthesized
- **Issue #2** (closed): Pad ring and ESD: the untested surface this block exists to open
- **Issue #1** (closed): Ratify the target spec
