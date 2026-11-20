# Work Plan

This document is regenerated automatically by the Guide triage agent from
current GitHub label state. The region between the markers below is
machine-generated and is overwritten wholesale on each update; nothing
outside the markers is touched. See `.claude/skills/loom-guide/guide.md`
for the generation logic.

<!-- guide:plan-body:start -->
_Generated: 2026-11-20T21:08:15Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#299**: sim/harness: add a `--backend batch` path that runs PVT points through `klt sim` *(held)*

## Important

`loom:important`; taken before unlabelled work.

- **#222**: Re-run post-layout eye records and measure pd2nw clamp C-V after VDD-side clamp (#210) *(held)*
- **#306**: Guide docs passes that touch README.md drift T1 item 10 and red-line CI

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#306**: Guide docs passes that touch README.md drift T1 item 10 and red-line CI
- **#370**: sim/harness batch: opt in to options.stage_model_inputs and re-run the one-point fleet probe with the client's own model closure
- **#371**: T1 item 7 (analog) prep: klt pex-shaped testbench requests for the post-#210 pad-ring assembly, plus an extract-only body-bias report
- **#372**: T1 item 5 (analog) prep: commit the DR-0013 row-to-measure map and give row 5 (rise/fall) a graded check
- **#373**: Remove obsolete DRC and LVS verdicts from new place-and-route records

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#368**: fix(signoff): stop README churn drifting item 10; add pin tripwire and re-attest *(held)*
- **#376**: flow: drop stale DRC/LVS verdicts from P&R record template

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#158**: Champion: Merge-Risk Hold Digest *(curated)* *(held)*
- **#222**: Re-run post-layout eye records and measure pd2nw clamp C-V after VDD-side clamp (#210) *(curated)* *(held)*
- **#229**: T1 items 5 and 6 (analog): klt sim envelopes per spec row and a klt yield report for the mismatch campaign *(curated)* *(held)*
- **#254**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)* *(held)*
- **#299**: sim/harness: add a `--backend batch` path that runs PVT points through `klt sim` *(curated)* *(held)*
- **#306**: Guide docs passes that touch README.md drift T1 item 10 and red-line CI *(curated)*
- **#313**: docs: point the item 7 digital blocker at klayout-tools#5002 and complete the README repo-layout tree *(curated)* *(held)*
- **#317**: Filter ngspice's 'Reference value :' progress trace out of harness logs: 96% of what survives .options noinit *(curated)* *(held)*
- **#370**: sim/harness batch: opt in to options.stage_model_inputs and re-run the one-point fleet probe with the client's own model closure *(curated)*
- **#371**: T1 item 7 (analog) prep: klt pex-shaped testbench requests for the post-#210 pad-ring assembly, plus an extract-only body-bias report *(curated)*
- **#372**: T1 item 5 (analog) prep: commit the DR-0013 row-to-measure map and give row 5 (rise/fall) a graded check *(curated)*

## Proposed (Architect / Hermit)

- **#326**: Remove the two pad_pitch_fit *.parasitics_critical_net.json reports: 392 KB whose only new content says the measurement never ran *(hermit)* *(held)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 2 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 0 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 0 |
| Curated | 11 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
