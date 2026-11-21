# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

### 2026-09-21

- **Issue #190** (closed): T1 item 11 digital column: tmds_encoder LVS power_connectivity verdict missing (graded only on gate-level-verilog compares)
- **PR #193**: feat: add gate-level LVS power-connectivity read for tmds_encoder
- **Issue #189** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **PR #192**: feat: add klt signoff T1 manifest with CI-graded evidence record
- **Issue #188** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo
- **PR #191**: feat: add klt erc supply read and T1 item-11 evidence for tmds_encoder

### 2026-09-15

- **Issue #185** (closed): Re-check the DVI-mode-only framing: dongle now decided audio-in
- **PR #187**: spec: add DR-0016 (Proposed) keeping HDMI data islands outside this block's boundary
- **Issue #183** (closed): DR-0015 / esd-capacitance-budget.md §2a mis-cite spec/pad-ring-esd-survey.md §8 for 'no electrical ESD data' claim
- **PR #184**: docs: fix mis-citation of pad-ring-esd-survey.md §8 in DR-0015 and esd-capacitance-budget.md
- **Issue #145** (closed): Decide: is ESD HBM/CDM qualification (DR-0013 row 11) schedulable work or a permanent pre-silicon limitation?
- **PR #182**: spec: add DR-0015, tracking ESD HBM/CDM qualification as pre-silicon limitation
- **Issue #168** (closed): Process pattern: 3 consecutive PRs (#164, #165, #166) rejected for stale-branch merge conflicts in README status paragraph
- **Issue #181** (closed): Guard telemetry: worktree-write-confinement-unresolved-var denies a klt loop whose per-iteration path can't be statically resolved
- **Issue #180** (closed): Guard telemetry: ask:git-clean-fd pattern matches the phrase in prose/heredoc text, not just a real invocation
- **Issue #179** (closed): Guard telemetry: worktree-write-confinement blocks routine /tmp ngspice scratch-file writes during sim debugging

### 2026-09-11

- **Issue #177** (closed): Lay out the tmds_final_mux cell and sign off DRC/LVS against the sized schematic (the CML driver's #22 step, for the DR-0003 final 2:1 mux)
- **PR #178**: feat: lay out and DRC/LVS sign off tmds_final_mux

### 2026-09-06

- **Issue #175** (closed): Guard trigger review: rm-scope-unresolved-var (catastrophic deny)
- **Issue #171** (closed): design/tmds_final_mux.sch: vswing_m/vswing_s FAIL the 0.8 V floor at sf corner, 125C, 2.97V (issue #163 PVT extension finding)
- **Issue #173** (closed): Re-verify tt/ff/fs/sf PVT corners for tmds-final-mux-eye / cml-driver-eye-realmux against issue #169's RL=5.90u sizing revision
- **PR #176**: feat(sim): re-verify tt/ff/fs/sf process corners for tmds-final-mux-eye and cml-driver-eye-realmux against issue #169's RL fix
- **Issue #169** (closed): design/tmds_final_mux.sch: vswing_m FAILs the 0.8 V floor at ss corner, 2.97 V, 270 Mbps/lane (issue #163 PVT extension finding)
- **PR #174**: fix(design): widen tmds_final_mux RLP/RLN to close ss-corner vswing_m FAIL
- **Issue #163** (closed): Complete the full 5-process-corner PVT grid for sim/tmds-final-mux-eye and sim/cml-driver-eye-realmux
- **PR #172**: feat(sim): land ff/fs/sf process corners for tmds-final-mux-eye and cml-driver-eye-realmux
- **PR #170**: feat(sim): land the ss process corner for tmds-final-mux-eye and cml-driver-eye-realmux
- **Issue #141** (closed): Champion: Merge-Risk Hold Digest
- **Issue #167** (closed): Guard-decision review: stash-scope main-checkout ASK on a stash-drop command (confirm keep flagged)
- **Issue #160** (closed): Post-layout eye-mask (DR-0013 row 6) run against the extracted pad-ring-assembly DUT
- **PR #166**: feat: post-layout eye-mask (DR-0013 row 6) record against the extracted pad-ring-assembly DUT
- **Issue #161** (closed): Expand the gf180_tmds_pad_ring_assembly post-layout PVT record beyond the tt corner (ff/ss/fs/sf)
- **PR #165**: feat: land the remaining ff/ss/fs/sf PVT corners for the pad-ring assembly

### 2026-09-05

- **Issue #159** (closed): Design the 10:1->2:1 serializer / final CML multiplexer joining the TMDS encoder and driver
- **PR #164**: feat: serializer + final CML mux (DR-0014, real analog verification)
- **Issue #154** (closed): [Epic #542] 3A — gf180-tmds-tx maturation + Challenge #5 brief
- **PR #162**: PVT-verify the driver+pad-ring assembly and write the Challenge #5 proposal

