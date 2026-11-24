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
As of this commit the grade is **18/22 T1 items met** (per-partition rows,
11 checklist items × `kind: mixed-signal`'s two partitions):

| met | why (the record's own reason, where unmet) |
| --- | --- |
| #3 DRC clean — analog + digital | `klt drc` `status: clean`, layout hash pinned, on both partitions |
| #4 LVS clean — analog + digital | `klt lvs` `status: match` (regenerated 2026-09-21 under the pinned build; identical 0-error verdicts), layout-hash pinned, `input_verified: true` |
| #8 characterization report — analog + digital | the hand-rolled `kind: "generic"` wrapper over `measurements/characterization.md`, its `content_hash` pinned in both the manifest and the envelope |
| #11 power delivery — analog | **`met`** (issue #210, after #207's `unmet` / `supply_not_continuous`). `11.analog` = `layout/erc_reports/gf180_tmds_pad_ring_assembly.erc.json` + the item-4 LVS report, both pinned to the assembly GDS hash. The DVDD ring strap now carries a `VDD` label at two Nwell taps and is tied to real devices (a `diode_pd2nw_06v0` VDD-side clamp per output pad); the ERC report has zero findings, `VDD` and `VSS` each one island, and both `nwell_vdd_tap` and `substrate_vss_tap` checked (none skipped); the LVS reference carries `VDD` and the report pairs it in `net_correspondence`. `VDD` stayed declared throughout — it was neither omitted nor relabelled to turn the row green; the row moved because the geometry and the reference now carry the supply. The ERC reports were produced by a newer `klt` than the pin (the pin cannot produce `well_layer: null` specs) and read by the pinned build; see `../layout/README.md`, "T1 item 11 (analog)" |
| #11 power delivery — digital | **`met`** (issue #206). `klt erc` on `layout/erc-supply-spec.json` now declares both well ties: `erc_finding_count 0`, `erc.missing_tie` for `nwell_vdd_tap` and `lvpwell_vss_tap` both checked and none skipped, pinned to the committed GDS hash. Branch that graded it: **no place-and-route citation, so the PDN branch is not selected** (`power_delivery.pdn: false`; this block's P&R is `flow/pnr_tmds_encoder.py` driving OpenROAD directly and has no `klt place-and-route` response to cite, and none is fabricated). The grader instead takes the ERC + LVS pair: the cited LVS report is the SPICE-reference `layout/lvs_reports/tmds_encoder.lvs.json` (`power_connectivity: unchecked`, but its reference carries `VDD`/`VSS`, `supply_nets` `["VDD","VSS"]`), which suffices on that branch. The gate-level `tmds_encoder_gate.lvs.json` (`match`) is not the cited report |
| #1 design sources — analog + digital | **`met`** via `klt signoff --attest 1` envelopes (`envelopes/item1-{analog,digital}.json`) pinning versioned inventories (`attest/item1-*.json`): each source is present and each derived netlist passes its freshness check. Analog: the xschem schematics/symbols and `design/netlist/*.spice`, stamped after `klt netlist --check` (xschem 3.4.4) matched. **Digital is weaker, and says so:** the encoder RTL and its `.synth.v`/`.pnr.v` netlists are hash-stamped, but Yosys/OpenROAD were *not* re-run (std-cell library absent on the stamping host); the pins rest on flow record `20260817-110611-37e197a`. `rtl/tmds_serializer.v`/`tmds_tx_lane.v` are listed sources with no synthesized netlist (DR-0014). See "Item 1 freshness" below |
| #2 layout — analog + digital | **`met`** via artifact-anchored generic envelopes bound to the committed GDS (`envelopes/item2-{analog,digital}.json`); the row stays `met` only while the stream re-hashes to its pin. **No regeneration claim is made** for either: re-running `gen_pad_ring_assembly.py` gives a different file hash (the GDS header carries a write timestamp) but an empty per-layer XOR; the digital merge step was not re-run (provenance is `layout/README.md`'s documented P&R determinism). The envelopes disclose this |
| #9 testbenches — analog + digital | **`met`** via `klt signoff --attest 9` (`envelopes/item9-{analog,digital}.json`): every `sim/*/testbench` fragment (resp. `verification/*` bench and negative control) is present, the cold-start command exits 0, and the PDK (`gf180mcuD` @ open_pdks `c6d73a35…`) and tool versions are pinned. The analog cold start is `sim/run_corners.py --list` (manifests load); the PVT sweeps need the PDK and ngspice and are **not** re-run — their results are the append-only `sim/*/records/` |
| #10 repo hygiene — analog + digital | **`met`** via `klt signoff --attest 10` (`envelopes/item10.json`, cited for both partitions): README, spec, LICENSE and CI workflow present; `lint.sh` (shellcheck + append-only required) and the two unit-test suites exit 0 |
| #5 corner verification — digital | **`met`** (issue #228). `flow/tmds_encoder/klt_sta.json` is one `klt sta` response over the committed routed DEF + post-route SPEF at all five 3.3 V corners (`pdk.corners`), 720p60 clock (13.4680 ns), zero I/O delay: every corner `timing_status: "constrained"`, setup WNS from +0.281 ns (`ss_125C_3v00`) up, hold WNS from +0.403 ns (`ff_n40C_3v60`) up, `input_verified: true`. Regenerate with `flow/klt_sta_tmds_encoder.py` (its docstring states the one path normalisation applied). Three disclosed limits: (1) `klt sta` cannot express `set_propagated_clock`, `set_driving_cell` or `set_load`, so it does not reproduce `flow/sta_tmds_encoder.py`'s full SDC; the slowest-corner setup slack nonetheless lands within 2 ps of that flow's record (+0.2799 ns); (2) its `spef_annotation` reports `annotation_complete: false` (0 of 377 design nets matched by name) — read the numbers with that in mind; (3) under `klt` 0.8.0 the grader takes several citations for item 5 and requires both kinds, so the zero-delay functional run (`flow/tmds_encoder/klt_fv_zero_delay.json`, 3/3 pass, generated by `flow/klt_fv_tmds_encoder.py`) is now cited alongside the `sta` report (it records no input hash, so the manifest pins its file only). Tool gaps filed as klayout-tools#3741 (one citation) and #3742 (sta constraints / annotation) |
| #7 post-layout — digital | `no_evidence`. `klt functional-verification` with `options.sdf` aborts `vvp` (`NULL handle passed to vpi_scan`) on this netlist + post-route SDF (zero-delay run of the same sources passes; the repo's own `$sdf_annotate` loader in `flow/gate_level_sim_tmds_encoder.py` also passes, but its Markdown record is not a `klt` envelope). Filed as klayout-tools#3740; nothing fabricated to fill the row |
| #6 statistical claims — digital | **`not_applicable`** (issue #296), not `met`: the digital partition has no statistical spec row. `klt` 0.8.0's recorded `not_applicable` form cites `signoff/digital-spec.json` (ratified rows from `spec/tmds-tx.md` §1, DR-0003, DR-0008/DR-0009 and DR-0016) and the statement `signoff/item6-digital-na.json` (one `{id, class, reason}` entry per row), both content-hash pinned in the manifest's `6.digital` entry. The grader's statistical scan passed without any row being reworded. Corner-bounded rows point at item 5.digital; functional rows at `verification/tmds_encoder`. Counted as `t1_not_applicable_count: 1`; `t1_met_count` unchanged |
| #5 corner verification — analog | `unmet` / `partial_coverage` (issue #229), no longer `no_evidence`. Four `klt sim` envelopes are cited and every one grades `met` with `input_verified: true`; the grader derives their row coverage from the envelopes' own `spec_row` tags, so every DR-0013 row that is not a declared gap is covered: rows 1, 2, 4, 5, 8, 9 by `sim/cml-driver-eye/envelopes/20261124-052134-d358846.json` (90 corners), row 6 by the two `sim/cml-driver-eye-mask/envelopes/20261124-0521{38,39}-d358846.json` rate slices (45 + 45), row 8 again by `sim/tmds-final-mux-eye/envelopes/20261124-052135-d358846.json`. The item stays unmet because `spec_rows."5.analog"` declares the four gaps — row 3 (total jitter needs the PLL, DR-0017), row 7 (N/A by design, DR-0013), row 10 (pad capacitance, open under #222), row 11 (ESD, DR-0015) — and because rows 5 and 6 are Proposed (`ratified: false`). `sim/cml-driver-eye-realmux`'s envelope is committed but **not cited**: it fails its row-5 fall-time checks at 38 of 90 corners (#404). See "T1 items 5 and 6 (analog)" below |
| #6 statistical claims — analog | **`met`** (issue #229), not `not_applicable`: rows 1, 2 and 9 are statistical — their DC levels are set by device matching, which the corner matrix cannot sample — and each of the five process corners carries its own `klt yield` report (`sim/cml-driver-mismatch/yield/20261124-052148-d358846/yield_<corner>.json`, never pooled). Each cites n = 200 mismatch samples with `sample_size.verdict: sufficient` (183 are needed), a negative control `klt yield` grades `detected` on every measurement, and Cpk / sigma-to-spec against the row's own limits; every citation grades `met` with `input_verified: true`. The report status is `reported`, because the ratified spec states no yield target to pass or fail against |
| #7 post-layout — analog | `no_evidence`. No `klt pex` report exists yet: the post-layout eye records under `sim/` are Markdown evidence the grader does not read, and the `klt pex`-shaped requests `sim/pex/` prepares for the pad-ring assembly (#371) have not been run on both legs (#230). Nothing fabricated to fill the row |

## Partition boundary (the `kind: "mixed-signal"` declaration)

Per `design-evidence-tiers.md`'s "Block kind" subsection, a mixed-signal
claim must state explicitly which silicon each partition's evidence covers:

- **analog partition** — the full-custom CML line driver and the pad ring:
  the driver core (xschem `design/cml_driver.sch` →
  `layout/gds/cml_driver_core.gds`) assembled with the production pad cells
  and `diode_nd2ps_06v0` / `diode_pd2nw_06v0` ESD clamps into
  `layout/gds/gf180_tmds_pad_ring_assembly.gds` — the artifact the
  `*.analog` citations grade. Per-cell signoffs (DRC/LVS/extract report
  pairs with negative controls) and the analog measurement records
  (`sim/cml-driver-*`, `sim/esd-*`) live under `layout/` and `sim/` as
  before.
- **digital partition (RTL flow)** — the synthesized `tmds_encoder`:
  `rtl/tmds_encoder.v` → Yosys → OpenROAD P&R →
  `layout/gds/tmds_encoder.gds`, verified by `verification/tmds_encoder/`
  and `flow/tmds_encoder/` — the artifact the `*.digital` citations grade.
  The `rtl/tmds_serializer.v` reduction stage is RTL in the same flow, with
  its own cocotb bench (`verification/tmds_serializer/`).
- **full-custom digital sub-case** — `tmds_final_mux` (DR-0003's custom
  final 2:1 DDR multiplexer) is *not* synthesized RTL: it is captured as a
  schematic and hand-composed GDS (`design/tmds_final_mux.sch` →
  `layout/gds/tmds_final_mux.gds`), exactly the "Full-custom digital
  sub-case" `design-evidence-tiers.md` defines — its artifacts satisfy the
  analog *column*'s shapes (schematic + GDS + DRC/LVS pairs with negative
  controls) while its silicon belongs to the digital side of the signal
  chain. The manifest's per-partition citations name each partition's
  top-level artifact (the assembled analog signal path, the routed
  encoder); the final mux's own committed signoff pair remains under
  `layout/` and — like every drawn cell's — is machine-checked by the lint
  job's `check_lvs_signoff.py` step on every push.

The partition boundary in the signal chain is the serializer → final-mux →
CML-driver handoff into the pad ring's OUTP/OUTN pair;
`spec/tmds-tx.md`'s decision records (DR-0009, DR-0003, DR-0002) are the
authoritative signal-path description. This manifest's job is narrower:
to state which committed evidence covers which silicon.

## Files

| file | what it is |
| --- | --- |
| `manifest.json` | The block manifest: `block` (fleet-rollup identity for 2AMLogic/2am#956, which consumes exactly this file), required `kind: "mixed-signal"`, and the per-item `evidence` citations with pinned `content_hash` on every one |
| `signoff.json` | The committed evidence record — `klt signoff --format json` output, byte-for-byte as the graded build emitted it |
| `characterization-envelope.json` | Item 8's `kind: "generic"` wrapper (the only T1 item with no `klt` verb), asserting `measurements/characterization.md`'s own verdict — **generated** by `gen_characterization_envelope.py`, never hand-edited |
| `attest/item{1,9}-{analog,digital}.json`, `attest/item10.json` | The versioned attestation inventories `klt signoff --attest` reads (schema `t1-attestation-inventory`); the envelope pins each inventory's raw-byte hash |
| `envelopes/item{1,9,10}*.json` | **Tool-produced** attestation envelopes (`klt signoff --attest N --inventory … -o …`). Never hand-edit |
| `envelopes/item2-{analog,digital}.json` | Artifact-anchored generic envelopes bound to each partition's committed GDS (no producer verb for item 2; written by hand, graded by re-hashing the stream) |
| `derived_stamps.py`, `derived-stamps.json` | The toolchain-free item-1 freshness tripwire (below) |
| `gen_characterization_envelope.py` | Regenerates that envelope deterministically from the committed report; `--check` is the CI mode (the same convention lint step 4 uses for generated DUTs) |
| `analog-spec.json` | The committed DR-0013 §3 row-to-measure map (#372, extended by #383): every row id, disposition, and target text — the targets are matched against DR-0013 §3's own Target cells by `sim/tests/test_analog_spec.py`, so map and decision record cannot silently disagree. Since #229 it is also the source of the item-5 envelopes' `spec_row` tags (`sim/run_envelope.py` reads each row's `checks` per bench), and its gaps are restated in the manifest's `spec_rows."5.analog"` |
| `sim/<bench>/envelopes/<ID>.{body.spice,request.json,json}` | **Tool-produced** item-5 evidence (#229): the whole-grid `klt sim` request, its circuit body, and the report the batch fleet run wrote with `--report-out`. Append-only like `records/`; `sim/run_envelope.py verify` is the offline check. Never hand-edit |
| `sim/cml-driver-mismatch/yield/<ID>/` | **Tool-produced** item-6 evidence (#229): per process corner the nominal and negative-control `klt sim` Monte Carlo reports, the `klt yield-samples` document derived from both, and the `klt yield` report (`yield_<corner>.json` is what the manifest cites). Never hand-edit |
| `check_gap_issues.py` | Read-only `closes_with` liveness check (#383), below |
| `../layout/erc-supply-spec.json`, `../layout/drc_reports/`, `../layout/lvs_reports/`, `../layout/erc_reports/` | The cited envelopes. Every manifest citation pins the envelope's own recorded input `content_hash`, and the grader re-hashes the artifact where the envelope names a path (`input_verified: true` on the regenerated LVS citations) |

## The pinned grading build

`klt signoff --manifest`'s grading rules come from the running `klt`
binary, and the eleven-item checklist (item 11, "Power delivery
(structural)", was added 2026-09-17 by klayout-tools#2025) is only graded by
builds newer than the PyPI `0.5.0` release (`0.8.0` grades it). The record's `build` block names
the exact grading code, so the pin is auditable:

- **pin**: `klayout-tools==0.8.0` (PyPI; `klt 0.8.0`, tag `v0.8.0`, commit
  `c572046be644`, `build.is_release: true`; `grading_ruleset_id
  sha256:46c446d84423b7399ee1cf957b3d49801ae4f42a0bda53da92f435776cf977c4`).
  A release pin is preferred over a git pin: a git build reports a dev version
  and no longer satisfies `==0.8.0` (klayout-tools#2823). CI asserts
  `klt --version` prints `klt 0.8.0`. The artifact-anchored generic envelope
  (klayout-tools#2718) and `klt signoff --attest` (klayout-tools#2844) both
  need a build at least this new; the previous pins (a dev-commit
  build after 0.7.0, and before it `e8ca621a`) were git builds
- **Why not PyPI `0.5.0`?** Its bundled tier doc predates item 11, so it
  renders no item-11 row at all, and its grading engine lacks the compound
  erc/lvs/power rules item 11 needs. `--tiers-doc` plus `--describe-grader`
  (see klayout-tools `docs/cli/signoff.md`'s "Identifying the grading
  build") exist to make that divergence visible, but grading against a
  pinned build that actually knows all eleven items is the honest option.
- **Bumping the pin**: when klayout-tools ships a release that changes grading, update the pinned ref below (and in the CI job), re-run the
  regeneration command, and commit the fresh `signoff.json` in the same
  change so the record and the grader never disagree. CI (below) fails the
  build otherwise.

## Regenerating the record

```bash
python3 -m venv .venv-klt && .venv-klt/bin/pip install \
  "klayout-tools==0.8.0"
.venv-klt/bin/pip install -r verification/requirements.txt
export PATH="$PWD/.venv-klt/bin:$PATH"
python3 signoff/gen_characterization_envelope.py   # if item 8's input changed
python3 signoff/derived_stamps.py --refresh        # if a design source/netlist moved (runs klt netlist --check)
klt signoff --attest 1  --inventory signoff/attest/item1-analog.json  -o signoff/envelopes/item1-analog.json    # and the other four
klt signoff --manifest signoff/manifest.json --format json > signoff/signoff.json
# exit 0 (T1) or 3 (rendered, not T1) are both fine; 1 means a malformed
# manifest — fix it, do not commit the error envelope.
```

If a regenerated envelope's recorded input hash moved, sync the manifest's
`content_hash` pin for that item to the new envelope's value in the same
change (a stale pin renders `stale_evidence`, never a false pass).

The item-5 and item-6 evidence is produced with a different install from the
grading build. The grading pin (0.8.0) reads these envelopes, but the *runs*
need what the fleet runs: `klt sim` is the host's `klt` (a 0.9-line client,
matching the batch runner's 0.9.0), and `klt yield` / `klt yield-samples`
need the `yield` extra the plain grading install does not carry, so the
yield reports are derived with the pinned release plus that extra
(`pip install 'klayout-tools[yield]==0.8.0'`). Grading a committed report
needs no extra: `klt signoff` reads the JSON. The commands:

```bash
# item 5: one request per bench (one per rate for a bench with per-rate windows)
python3 sim/run_envelope.py write cml-driver-eye
klt sim sim/cml-driver-eye/envelopes/<ID>.request.json --backend batch \
    --wait-for-capacity 600 --format json \
    --report-out sim/cml-driver-eye/envelopes/<ID>.json -o sim/.work/envelopes/<ID>
python3 sim/run_envelope.py verify cml-driver-eye <ID>
# then cite sim/<bench>/envelopes/<ID>.json in the manifest, pinning the
# envelope's own provenance.input.content_hash, with `rows`

# item 6: the mismatch campaign, then klt yield-samples + klt yield per corner
python3 sim/cml-driver-mismatch/run_yield.py write          # 11 requests
klt sim sim/cml-driver-mismatch/yield/<ID>/<request>.request.json --backend batch \
    --wait-for-capacity 600 --format json \
    --report-out sim/cml-driver-mismatch/yield/<ID>/<request>.json -o sim/.work/yield/<ID>/<request>
python3 sim/cml-driver-mismatch/run_yield.py derive <ID> --klt <klt with the yield extra>
# then cite each yield_<corner>.json, pinning the sha256 of the samples
# document its `samples` field names (what the grader hashes for this kind)
```

Run from the repo root: file-backed evidence paths resolve against the
invoking process's working directory (the same convention
klayout-tools `examples/signoff/` documents), and the reports record their
inputs repo-relative only when invoked that way.

## Gap-closer liveness: `check_gap_issues.py` (analog map, #383)

A declared gap in `analog-spec.json` must name the **open** issue that
would close it. The offline suite (`sim/tests/test_analog_spec.py`)
checks the key exists and the target text matches DR-0013 §3; whether the
named closer is *still open* is a live question, so it is a read-only
command the signoff reviewer runs when consuming the map — never CI, and
never an automated write to GitHub:

```bash
python3 signoff/check_gap_issues.py            # queries 2AMLogic/gf180-tmds-tx via gh api
python3 signoff/check_gap_issues.py --spec signoff/analog-spec.json --repo OWNER/NAME
```

- Each gap with a positive-integer `closes_with` is looked up once and
  must be an **open issue**; an explicit `null` is skipped with no request
  (it records "no open issue would close this row" in the gap text).
- Closed, missing, malformed and pull-request references are reported
  with their row and reference.
- Exit `0` = every non-null closer is open; `1` = problems found; `2` =
  **the GitHub API could not be queried** (no `gh`, no network, bad
  credentials) — a distinct, retryable diagnostic, not a verdict on the
  map. Re-run when the API is reachable.
- Offline fixture coverage lives in `sim/tests/test_gap_issue_check.py`;
  no unit test touches the network.

## CI: the record cannot rot

The `signoff` job in `.github/workflows/ci.yml` re-attests items 1, 9 and 10
(`klt signoff --attest N --inventory … --check <envelope>`, which re-runs every
declared command and exits 3 on any drift of an inventory, an inventoried file,
a check outcome or the envelope), runs `derived_stamps.py --check`, then
re-grades the manifest with `klt signoff --manifest … --check signoff/signoff.json`
against the committed record (that mode ignores the `build` block, which names
the install rather than the commit). Anything that would silently invalidate a
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

## Item 1 freshness: what CI can and cannot prove

`attest/item1-*.json` declare, per derived netlist, a freshness `check`. CI has
no xschem, no PDK and no std-cell library, so that command is
`derived_stamps.py --check --only <row>`: a stdlib hash tripwire over
`derived-stamps.json`, which pins every source and derived file. It fails when
a source or netlist moves without a re-stamp. It does **not** prove the netlist
equals what its generator emits today; that is established when the stamp is
written, by each row's `check_argv` (`klt netlist --check` for the analog rows,
run by `derived_stamps.py --refresh`). The two digital rows have
`check_argv: null` (Yosys/OpenROAD could not be run on the stamping host), so
`--refresh` refuses to re-pin them without `--include-unverified`, and each
row's `basis` field says what its pin rests on. Re-stamp from a host that has
the toolchain and re-run the real flow before relying on those rows.

## T1 items 5 and 6 (analog): `klt sim` envelopes and `klt yield` reports

Items 5 and 6 on the analog partition graded `no_evidence` until #229
produced the two envelope kinds the grader reads — from the same benches,
DUTs, measures and bounds the Markdown records were taken with. No record,
bench or bound was edited; the envelopes sit beside the records and are
cited by the manifest's `5.analog` / `6.analog` entries, each with `rows`
and under a `spec_rows.<item>.analog` declaration.

**Item 5 — one `klt sim` request per bench.** `python3
sim/run_envelope.py write <experiment>` derives a request and its circuit
body from the experiment's own `tb.json`: every `measure` entry in the form
`klt sim` can evaluate (raw `.meas` cards, then `.meas … PARAM` cards over
raw-card results, then dependency-ordered `expr`s — the translator
`sim/pex/gen_requests.py` shares), every `checks` bound as the
measurement's `limits`, and every graded check tagged with its DR-0013 row
(`spec_row`, read from `analog-spec.json`). One request sweeps the whole
mandated grid — `corners.process` × `temperature_c` × a zipped (supply,
rate) `params` axis — so one report covers 90 corners and pins one netlist
hash. `python3 sim/run_envelope.py verify <experiment> <ID>` then holds the
collected report to the bench's contract: `klt sim`'s own verdict, every
grid point exactly once, and the harness's own checks — including the
grid-level `min_spread_pct` check that proves the rate axis reached the
stimulus and that `klt sim` cannot grade per corner. The grader derives a
citation's row coverage from the tags, so the manifest's `rows` cannot
claim more than the envelope shows, and `sim/tests/test_klt_envelope.py`
fails the build when a cited envelope no longer regenerates byte for byte
from its bench or stops passing.

What the cited envelopes show (all on the batch fleet: ngspice-47, worker
PDK `open_pdks f6eeac7d…`, one or two 4xlarge jobs per envelope, runner klt
0.9.0, client klt 0.9.3.dev4954):

| envelope | corners | worst row-tagged value | binding corner |
| --- | --- | --- | --- |
| `cml-driver-eye` | 90/90 pass | row 5 `trise_ui_c2` = 0.1868 UI (limit 0.20) | `ss / 125 °C / 2.97 V / 742.5 Mbps` |
| `cml-driver-eye-mask` (742.5 and 270 Mbps slices) | 45/45 + 45/45 pass | row 6 `eyemask_margin_c2` = 0.871 V (limit 0.20) | `ss / 125 °C / 2.97 V / 742.5 Mbps` |
| `tmds-final-mux-eye` | 90/90 pass | row 8 `vds_mt_max` = 0.936 V (limit 3.63) | `fs / −40 °C / 3.63 V / 270 Mbps` |

The `cml-driver-eye` envelope reproduces its 2026-08-10 schematic record
`20260810-041436-a2c358b` to the record's printed precision — levels and
edge times alike (`swing_c0` 0.506577 V at the nominal point; `trise_c2`
251.588 ps at the binding corner, whence the same row-5 worst 0.1868 UI the
record's raw values give) — so the envelope grades the circuit the records
describe. (The deterministic-jitter figures, a difference of picosecond-scale
crossing times, differ at the 10⁻⁷-UI noise floor, five orders of magnitude
under their 0.15 UI bound.) Three things a reader of these envelopes should
know:

- **`options.ngspice_init: ["set wnflag=1", "set num_threads=1"]` is
  load-bearing.** The driver's `w=128u nf=64` devices resolve a model bin
  only under per-finger-width binning, and the fleet's ngspice reads no
  ambient init. Measured 2026-11-24 on the fleet: the same two-unit request
  aborts every corner with `could not find a valid modelname` without the
  init (job `klt-sim-972e8242a4a0`) and passes with it
  (`klt-sim-fbb03bc8fb56`). That abort is what parked this issue from
  2026-10-27 to 2026-11-24 (klayout-tools#5593, #7590: the fleet-side fix
  is the diagnostic; the remedy is the client's init line). The fleet's runner (klt 0.9.0)
  does not report the init it applied, so each envelope carries a
  `batch_ngspice_init_unverified` warning; the paired probe above is the
  evidence that it took effect.
- **The mask bench's 742.5 Mbps slice runs a 300 ns window, not the
  manifest's 560 ns** (`harness.klt_envelope.TRANSIENT_WINDOWS`). The
  manifest's single window is sized for 270 Mbps; at 742.5 Mbps the pattern
  and every measurement window end at 202 ns, and in the dead time after it
  Linux ngspice-47 fails to converge at exactly 300 × tbit = 404.04 ns at
  every corner (`timestep too small`, node `vinn#branch`; not the cause:
  reltol 1e-6…1e-3 and every solver option tried). A window that stops
  before that event measures the same thing — `eyemask_margin_*` are
  identical at 300 ns, 403 ns and in the aborted 560 ns run — so the
  request for that rate carries it. The bench's records came from macOS
  builds that complete the full window; the bench itself is unchanged and
  still aborts on Linux (#405).
- **`cml-driver-eye-realmux` is not cited.** Its whole-grid envelope
  (`sim/cml-driver-eye-realmux/envelopes/20261124-052136-d358846.json`) is
  committed and fails: the row-5 fall-time checks that #379 added to this
  bench fail at 38 of 90 corners (worst `tfall_ui_c0` = 9.10 UI), while
  every other graded check passes. The raw values equal the committed
  records', where `trise_c0` is *negative* at the same corners — the
  TRIG/TARG edge indices were written for the ideal-source bench and never
  validated on the real-mux waveform. Rows 1, 2, 4, 5, 8, 9 are therefore
  covered by the primary `cml-driver-eye` envelope only; #404 tracks fixing
  the measure and re-running, and says whether a design finding hides
  behind it.

**Item 6 — the mismatch campaign as a sized, self-checked Monte Carlo.**
`python3 sim/cml-driver-mismatch/run_yield.py write` re-expresses
`run_mc.py`'s deck (same DUT, fragment, `sw_stat_mismatch` switch and
sample seeds; the mismatch-off reference reproduces record
`20261118-172641-0900d2d`'s tt point exactly: swing 0.470169 V, vcm
3.064914 V) as one 200-sample `klt sim` Monte Carlo request per process
corner, plus a 200-sample **negative-control campaign** per corner — the
same seeded defect `run_mc.py` uses (`par_tail_val=1e-4`, an artificially
tiny Pelgrom area term on the tail mirror through gf180mcu's own unmodified
mismatch mechanism), drawn from an independent seed offset — plus one
five-corner mismatch-off reference. `derive` then runs `klt yield-samples`
and `klt yield` per corner and refuses any report that would not grade.

Per corner (n = 200, 95 % confidence, ±1 % target half-width; every
measurement `sample_size.verdict: sufficient`, `required_n` 183;
`negative_control.verdict: detected` on all three):

| corner | `swing_dc` (row 1, 0.4–0.6 V) | `vcm_dc` (row 2, 2.8–3.3 V) | `itail_dc` (row 9, 8–12 mA) | control yield, swing / vcm / itail |
| --- | --- | --- | --- | --- |
| `tt` | 0.470144 V, σ 1.18 mV, Cpk 19.9 | 3.06493 V, σ 0.59 mV, Cpk 133 | 9.903 mA, σ 24 µA, Cpk 26.9 | 0.220 / 0.875 / 0.220 |
| `ff` | 0.482753 V, σ 1.26 mV, Cpk 21.8 | 3.05862 V, σ 0.63 mV, Cpk 127 | 10.155 mA, σ 25 µA, Cpk 24.3 | 0.180 / 0.895 / 0.225 |
| `ss` | 0.459196 V, σ 0.92 mV, Cpk 21.5 | 3.07040 V, σ 0.46 mV, Cpk 167 | 9.684 mA, σ 18 µA, Cpk 30.6 | 0.255 / 0.920 / 0.260 |
| `fs` | 0.479723 V, σ 1.37 mV, Cpk 19.5 | 3.06014 V, σ 0.68 mV, Cpk 117 | 10.095 mA, σ 27 µA, Cpk 23.3 | 0.200 / 0.850 / 0.215 |
| `sf` | 0.461531 V, σ 1.09 mV, Cpk 18.8 | 3.06923 V, σ 0.55 mV, Cpk 141 | 9.731 mA, σ 22 µA, Cpk 26.5 | 0.240 / 0.940 / 0.250 |

Each nominal draw is 200/200 inside its limits (Clopper-Pearson lower bound
98.2 %), and each control's interval lies entirely below it — the closest
call is `sf` `vcm_dc`, control [89.8 %, 96.9 %]. The campaign is per corner,
not pooled, so item 6's claim is combined with the deterministic corner
matrix of item 5 rather than instead of it; temperature and supply are held
at nominal for the reason `run_mc.py`'s records state (the full PVT × rate
matrix is `cml-driver-eye`'s deterministic evidence). Disclosed limits: no
`target_yield` is declared, because the ratified spec states none — so the
reports read `reported`, and nothing in them could fail on yield; rows 4, 5,
6 and 8 are transient or stress rows for which this block makes no Monte
Carlo claim and which item 5 grades at the corners; and the mismatch model
is the PDK's own Pelgrom injection on the four driver devices, which says
nothing about the pad ring. `sim/tests/test_run_yield.py` fails the build
when a cited report stops grading, its pinned samples document moves, or
the campaign no longer regenerates from its driver.

## Why some genuinely-passed work grades unmet

The grader only recognizes `klt`-native JSON envelopes. Through #229 the
analog corner and Monte Carlo evidence also exists in that form (above),
derived from the same benches as the `sim/*/records/*.md` records, which
stay the append-only evidence trail `sim/README.md` defines and remain
uncited by the manifest. What still reads `no_evidence` is item 7 (analog
and digital): the post-layout evidence is Markdown or a `klt` report of the
wrong kind. That is a gap being named, not a verdict that the evidence is
unsound — the record says "no `klt` envelope backs this item", which is
true. Closing those rows in *this* artifact means producing the missing
envelope kinds (a `klt pex` run for item 7), separately scoped work in the
tracker, not a manifest edit.

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
- **The item-5 `klt sim` envelopes and item-6 Monte Carlo reports carry one
  submitting-host path each.** `environment.client_ngspice_binary` is the
  client's own ngspice path, an absolute path under the dispatch host's
  home directory — `klt sim` batch reports emit it and a request cannot
  suppress it (klayout-tools#7381, open). Nothing else in them names a
  host: netlists and includes are repo-relative, the PDK is identified by
  its stamp (`open_pdks f6eeac7d…`, the same revision this repo's records
  cite), and artifacts were not kept, so no scratch path appears. They
  were produced by a 0.9-line `klt` (the batch runner is 0.9.0) and are
  graded by the 0.8.0 pin — the grader validates shape, not producer
  version, and every citation reads `input_verified: true`.
- **Two warnings inside those envelopes are expected.** Each item-5
  envelope carries a `timeout_preflight_warning` (the 60 s per-corner
  budget "looks implausible" against a 50 timepoints/s floor) and a
  `batch_ngspice_init_unverified` diagnostic; the measured per-corner
  `runtime_s` in the same report is 0.07–2.4 s, and the init's effect is
  established by the paired probe described under "T1 items 5 and 6
  (analog)" rather than by the runner's receipt, which does not report it.
