# Work Plan

This document is regenerated automatically by the Guide triage agent from
current GitHub label state. The region between the markers below is
machine-generated and is overwritten wholesale on each update; nothing
outside the markers is touched. See `.claude/skills/loom-guide/guide.md`
for the generation logic.

<!-- guide:plan-body:start -->
_Generated: 2026-11-28T07:00:18Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#433**: chore: resync installed Loom surfaces

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#222**: Re-run post-layout eye records and measure pd2nw clamp C-V after VDD-side clamp (#210)
- **#306**: Guide docs passes that touch README.md drift T1 item 10 and red-line CI
- **#406**: sim/harness batch per-point path: UI-normalised measures (trise_ui_*, tfall_ui_*, dj_ui_*) come back error in klt sim reports -- batch._measurements emits exprs that read .meas results

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#229**: T1 items 5 and 6 (analog): klt sim envelopes per spec row and a klt yield report for the mismatch campaign
- **#306**: Guide docs passes that touch README.md drift T1 item 10 and red-line CI

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#368**: fix(signoff): stop README churn drifting item 10; add pin tripwire and re-attest *(held)*

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#433**: chore: resync installed Loom surfaces *(held)*

## Proposed

Issues carrying `loom:curated`.

- **#158**: Champion: Merge-Risk Hold Digest *(curated)* *(held)*
- **#222**: Re-run post-layout eye records and measure pd2nw clamp C-V after VDD-side clamp (#210) *(curated)* *(held)*
- **#229**: T1 items 5 and 6 (analog): klt sim envelopes per spec row and a klt yield report for the mismatch campaign *(curated)*
- **#254**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)* *(held)*
- **#306**: Guide docs passes that touch README.md drift T1 item 10 and red-line CI *(curated)*
- **#313**: docs: point the item 7 digital blocker at klayout-tools#5002 and complete the README repo-layout tree *(curated)* *(held)*
- **#317**: Filter ngspice's 'Reference value :' progress trace out of harness logs: 96% of what survives .options noinit *(curated)* *(held)*
- **#370**: sim/harness batch: opt in to options.stage_model_inputs and re-run the one-point fleet probe with the client's own model closure *(curated)* *(held)*
- **#404**: cml-driver-eye-realmux: row-5 rise/fall checks (added by #379) fail at 38/90 corners -- the TRIG/TARG edge indices do not fit the real-mux waveform *(curated)* *(held)*

## Proposed (Architect / Hermit)

_None._

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 0 |
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 1 |
| Curated | 9 |
| Architect / Hermit proposals | 0 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
