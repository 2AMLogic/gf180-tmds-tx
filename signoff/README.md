# Signoff — the block's graded T1 verdict of record

This directory is this repo's **machine-graded** answer to "what is the gap
to T1", produced by `klt signoff --manifest` against the
[klayout-tools design-evidence tier ladder](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md).
It replaces the hand-maintained checkbox list that used to live in gap-to-T1
tracker issue #17: that issue now points here, and the manifest graded in
`signoff/signoff.json` is the **verdict of record**. Per
`CLAUDE.md`'s evidence rule ("no claim without a testbench"), a prose
checklist nobody re-reads is not a verdict; this is.

## The current verdict (don't hand-transcribe — read the record)

`signoff/signoff.json` is the byte-for-byte stdout of

```bash
klt signoff --manifest signoff/manifest.json --format json
```

as emitted by the graded build pinned below. Exit code `3` is the tool's
documented "rendered but not T1" signal, not an error: `tier` is `null`
until every T1 item is met, which is the honest state for this block today.
As of this commit the grade is **6/22 T1 items met** (per-partition rows,
11 checklist items × `kind: mixed-signal`'s two partitions):

| met | why (the record's own reason, where unmet) |
| --- | --- |
| #3 DRC clean — analog + digital | `klt drc` `status: clean`, layout hash pinned, on both partitions |
| #4 LVS clean — analog + digital | `klt lvs` `status: match` (regenerated 2026-09-21 under the pinned build; identical 0-error verdicts), layout-hash pinned, `input_verified: true` |
| #8 characterization report — analog + digital | the hand-rolled `kind: "generic"` wrapper over `measurements/characterization.md`, its `content_hash` pinned in both the manifest and the envelope |
| #11 power delivery — analog | `no_evidence`: the analog partition has no `klt erc` supply spec or report yet (open work, unfiled) |
| #11 power delivery — digital | `supply_spec_incomplete`: the committed `layout/erc-supply-spec.json` deliberately omits `ties[]` (klayout-tools#2169 — declaring one collapses the design into one island and reports a false `erc.supply_short`), so `erc.missing_tie` is uncomputed; and the digital column's `power_connectivity` verdict is `unchecked` (see #190) |
| #1, #2, #9, #10 | `no_evidence` by design — `klt signoff` cannot check topical relevance for the no-verb items, and citing an unrelated passing envelope to make a row go green is exactly the dishonesty this mechanism exists to prevent |
| #5, #6, #7 | `no_evidence` — the analog corner/Monte-Carlo/post-layout evidence in `sim/` and `flow/` is committed as this repo's own Markdown evidence records, which are not `klt sim`/`klt yield`/`klt pex` JSON envelopes and are rejected by the grader regardless of how sound they are. The grading gap (not the engineering gap) is real and named: see "Why some genuinely-passed work grades unmet" below |

## Files

| file | what it is |
| --- | --- |
| `manifest.json` | The block manifest: `block` (fleet-rollup identity for 2AMLogic/2am#956, which consumes exactly this file), required `kind: "mixed-signal"`, and the per-item `evidence` citations with pinned `content_hash` on every one |
| `signoff.json` | The committed evidence record — `klt signoff --format json` output, byte-for-byte as the graded build emitted it |
| `characterization-envelope.json` | Item 8's `kind: "generic"` wrapper (the only T1 item with no `klt` verb), asserting `measurements/characterization.md`'s own verdict — **generated** by `gen_characterization_envelope.py`, never hand-edited |
| `gen_characterization_envelope.py` | Regenerates that envelope deterministically from the committed report; `--check` is the CI mode (the same convention lint step 4 uses for generated DUTs) |
| `../layout/erc-supply-spec.json`, `../layout/drc_reports/`, `../layout/lvs_reports/`, `../layout/erc_reports/` | The cited envelopes. Every manifest citation pins the envelope's own recorded input `content_hash`, and the grader re-hashes the artifact where the envelope names a path (`input_verified: true` on the regenerated LVS citations) |

## The pinned grading build

`klt signoff --manifest`'s grading rules come from the running `klt`
binary, and the eleven-item checklist (item 11, "Power delivery
(structural)", was added 2026-09-17 by klayout-tools#2025) is only graded by
builds newer than the PyPI `0.5.0` release. The record's `build` block names
the exact grading code, so the pin is auditable:

- **pin**: `klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@e8ca621a6961879cec1af60cc932c3b3d58ddcaa`
  (`klt 0.5.0+ge8ca621a6961`, `grading_ruleset_id
  sha256:c4a9f5af2a27f886a08a4436781716326f072b356bb155f83bf2d6ddfc4f46e8`)
- **Why not PyPI `0.5.0`?** Its bundled tier doc predates item 11, so it
  renders no item-11 row at all, and its grading engine lacks the compound
  erc/lvs/power rules item 11 needs. `--tiers-doc` plus `--describe-grader`
  (see klayout-tools `docs/cli/signoff.md`'s "Identifying the grading
  build") exist to make that divergence visible, but grading against a
  pinned build that actually knows all eleven items is the honest option.
- **Bumping the pin**: when klayout-tools ships a release with item-11
  grading, update the pinned ref below (and in the CI job), re-run the
  regeneration command, and commit the fresh `signoff.json` in the same
  change so the record and the grader never disagree. CI (below) fails the
  build otherwise.

## Regenerating the record

```bash
python3 -m venv /tmp/klt-signoff && /tmp/klt-signoff/bin/pip install \
  "klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@e8ca621a6961879cec1af60cc932c3b3d58ddcaa"
python3 signoff/gen_characterization_envelope.py   # if item 8's input changed
/tmp/klt-signoff/bin/klt signoff --manifest signoff/manifest.json --format json > signoff/signoff.json
# exit 0 (T1) or 3 (rendered, not T1) are both fine; 1 means a malformed
# manifest — fix it, do not commit the error envelope.
```

If a regenerated envelope's recorded input hash moved, sync the manifest's
`content_hash` pin for that item to the new envelope's value in the same
change (a stale pin renders `stale_evidence`, never a false pass).

Run from the repo root: file-backed evidence paths resolve against the
invoking process's working directory (the same convention
klayout-tools `examples/signoff/` documents).

## CI: the record cannot rot

The `signoff` job in `.github/workflows/ci.yml` re-runs the grading command
on every PR and push and byte-compares the fresh output against the
committed `signoff/signoff.json`. Anything that would silently invalidate a
published verdict instead breaks the build:

- **a cited artifact changes** (a regenerated GDS, an edited LVS envelope) —
  either the citation's pinned `content_hash` no longer matches the
  envelope's (the item flips `met` → unmet, `stale_evidence`), or the
  envelope no longer matches the artifact on disk (`input_verified` flips
  to `false` in the record, the #2196 disclosure the grader re-hashes for
  native kinds); both change the record bytes, so the byte-compare fails;
- **`measurements/characterization.md` changes** — `klt signoff` never
  re-hashes a generic citation's input (its provenance field names are the
  author's choice by contract), so the same gate is enforced one link
  earlier and mechanically: `python3 signoff/gen_characterization_envelope.py
  --check` fails until the envelope is regenerated (which itself flips the
  item-8 pin to `stale_evidence` until the manifest follows, then the record);
- **the manifest cites something new or drops a citation** — the verdict
  rows themselves change, same failure;
- **the checklist or grader changes under the pin** — `source_doc_content_hash`
  and the `build` block change, same failure.

Fixing it is always the same sequence: regenerate the affected `klt`
envelope(s) under the pinned build (see `layout/README.md` for each cell's
commands), refresh the manifest's pins, re-run the regeneration command, and
commit record + evidence together. Never hand-edit `signoff/signoff.json` —
it is grader output or it is nothing.

## Why some genuinely-passed work grades unmet

The grader only recognizes `klt`-native JSON envelopes. This repo's analog
evidence (per-corner sweeps, Monte Carlo, post-layout eye sims) is committed
as `sim/*/records/*.md` evidence records under the append-only
`sim/README.md` schema, and the digital pipeline's records live under
`flow/tmds_encoder/records/` — none of which are `klt sim`/`klt yield`/`klt
pex` envelopes. Items 5, 6 and 7 therefore read `no_evidence` here even
where the engineering is done and recorded. That is the gap being named, not
a verdict that the evidence is unsound: the record says "no `klt` envelope
backs this item", which is true. Closing those rows in *this* artifact means
producing the missing envelope kinds (e.g. a `klt pex` run for item 7) —
separately scoped work in the tracker, not a manifest edit.

## Provenance notes for the reader

- **DRC citations show `input_verified: null`.** The committed `klt drc`
  envelopes were produced by klt 0.2.0/0.3.0-era builds, which recorded the
  layout `content_hash` in `provenance.input` without a resolvable file
  path — the grader re-hashes only what an envelope names, so it reports
  "nothing was re-hashed" (`null`) rather than fabricating verification.
  The pinned layout hashes were verified against the committed GDS files at
  manifest-commit time and match (see the manifest pins; re-checkable with
  `sha256sum layout/gds/*.gds`).
- **LVS envelopes cited here were regenerated 2026-09-21** under the pinned
  build, because the previously committed envelopes (klt 0.3.0) recorded
  their input hash in `environment.layout_sha256` rather than
  `provenance.input`, which post-#1969 builds (and this manifest's pinned
  citations) require — a pinned citation against the old shape renders
  `unverifiable_provenance` no matter how sound the report is. The
  regeneration reproduced the committed verdicts exactly (`match`, 0 errors,
  the pad ring's same 2 warning-only topology findings; the encoder side
  0 findings). Envelope delta vs the committed pair is additive only:
  `provenance.input`, `power_connectivity` (`unchecked`, plain-element
  reference — "does not apply" per the grader's own note), `body_verification`,
  `supply_nets` echo. Deck `content_hash` moved
  `79e71a1e…` → `95c2eb91…` and the resolved KLayout engine reported
  `0.30.12` (the pinned build was tested against `0.30.10` — "verdict
  itself is unaffected" per the tool's own warning); both are tool-side
  churn, recorded here rather than left for the next reader to rediscover.
  The `_shorted`/`_negctl` negative-control reports are untouched and
  still guard the same verdicts via `layout/scripts/check_lvs_signoff.py`.
