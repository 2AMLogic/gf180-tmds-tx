# Work Log

Chronological record of merged PRs and closed issues, newest first.
Maintained automatically by the Guide triage agent's document-maintenance
phase — see `.claude/skills/loom-guide/guide.md` for how entries are
selected.

### 2026-08-15

- **PR #31**: feat(layout): lay out the CML driver core cell and sign off DRC/LVS (issue #22)
- **PR #33**: docs(measurements): note esd-clamp-cv's dirty-tree caveat in characterization.md
- **PR #32**: feat(sim): add Monte Carlo mismatch evidence for the CML driver's swing/common-mode (issue #23)
- **PR #29**: docs(measurements): add block characterization report aggregating sim evidence
- **PR #28**: docs(sim): record cold-start reproducibility audit for existing experiments
- **PR #27**: docs: refresh README status line and maturity ladder to reflect landed design/pad-ring evidence
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
