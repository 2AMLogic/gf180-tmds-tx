# Work Log

Chronological record of merged PRs and closed issues, newest first.
Maintained automatically by the Guide triage agent's document-maintenance
phase — see `.claude/skills/loom-guide/guide.md` for how entries are
selected.

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
