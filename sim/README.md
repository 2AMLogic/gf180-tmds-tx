# sim/ — evidence record format

This directory holds simulation testbenches and their results. Results are
**append-only evidence**: once a record is written, it is never edited or
deleted. A re-run — even one that corrects a mistake — mints a new record
with a new ID; a correction references the record it supersedes rather than
overwriting it in place.

This convention exists because CLAUDE.md commits this repo to two rules that
need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench. Every
  recorded result carries the full PVT corner matrix (−40/27/125 °C, ±10%
  supply, process corners) unless the record explicitly states why a subset
  was used.
- **`sim/` is append-only evidence.** Re-runs get new records; records are
  never edited or deleted.

**This file is the authoritative convention.** The corner runner that produces
records in this format — how to run it, how to write a testbench, PDK
resolution, corner definitions — is documented in
[`sim/harness/README.md`](harness/README.md). If the harness and this document
ever disagree, this document wins and the harness is the thing that gets fixed.

This harness is ported from [`2AMLogic/gf180-bandgap`](https://github.com/2AMLogic/gf180-bandgap)'s
`sim/harness/` (issue #8), which is itself the origin of the convention below.
Everything in "Directory / naming convention" and "Summary record format"
through **Supersedes** is unchanged from that source. This repo's own
adaptation — because this block's claims are high-speed *transient* (eye/
jitter) claims against two distinct ratified operating points, not the DC/
op-point claims gf180-bandgap and `2AMLogic/gf180-gate-driver` make — is the
**bit-rate axis** and the **Operating point** / **Transient settings** record
fields, both called out explicitly below.

## PDK variant

`sim/pdk.json` pins `gf180mcuC`, per **DR-0010**
(`spec/decisions/0010-pdk-variant.md`, issue #9), which resolved this
section's previously-open `gf180mcuC`-vs-`gf180mcuD` discrepancy: `gf180mcuC`
matches every layout artifact already committed under `layout/` (from issue
#2 onward) and is the conservative (thinner, 0.9 um, top-metal) assumption
for pad ESD margin. `spec/tmds-tx.md`'s DR-0002 citation of `gf180mcuD` is
now qualified by DR-0010's Status-line note (DR-0005's own `gf180mcuD`
citation is superseded in full, via DR-0011).

**This pin changes no numeric result already recorded by this harness.**
DR-0010's own survey diffed both variants directly: `libs.tech/ngspice/`
(the SPICE device models every `sim/` record actually reads) is
byte-for-byte identical between `gf180mcuC` and `gf180mcuD`, and the Metal5
parasitic-capacitance coefficients `design/esd-capacitance-budget.md`'s
figures were computed from are likewise identical. The two variants differ
*only* in Metal5 (top-metal) width/spacing/area DRC thresholds and sheet
resistance — a layout-side concern, not a SPICE-model-side one. So every
`sim/*/records/*.md` record minted before this pin landed, which still
cites `gf180mcuD` in its own Environment/provenance section, remains valid
evidence for the number it reports — only its citation string is stale, per
this directory's own append-only convention (a correction references what
it supersedes rather than rewriting history in place). New records should
cite `gf180mcuC`, matching this file's pin, going forward.

## The PVT matrix (ratified — DR-0013)

**DR-0013** (`spec/decisions/0013-operating-conditions.md`, issue #9)
ratifies exactly the matrix this harness already used as a working default:
**−40/27/125 °C, ±10% supply, the five classic MOS corners** (`tt`/`ff`/
`ss`/`fs`/`sf`) as the minimum for every recorded result, **plus
resistor/BJT skews** (`res_ff`/`res_ss`/`bjt_ff`/`bjt_ss`,
`sim/harness/corners.py`'s `full` corner set) required specifically for any
claim depending on resistor or BJT device parameters — the same defaults
`matrix_conformance()` enforces below. This is now a **spec-derived
requirement**, not merely a working default: do not narrow this matrix to
make runs cheaper; every record in this repo mints evidence against the
full matrix above unless it states a subset justification (see
"Append-only rule" below), and a narrower default would silently weaken
every future record's PVT coverage. DR-0013 also fixes the nominal
supply/tolerance for both this block's own 3.3 V domain and the
receiver-side termination rail (`AVCC`) — see that record for the full
table, and its enumerated pass/fail spec rows.

## The bit-rate axis

`spec/tmds-tx.md` §1 defines two distinct operating points: **742.5 Mbps/
lane** (720p60, the target) and **270 Mbps/lane** (480p, the fallback). A
transient result taken at one is not evidence for the other — this is why
the bit rate is a first-class grid axis (`sim/harness/corners.py`'s
`PvtPoint.rate_mbps`, cross-producted with process × temperature × supply
exactly like any other axis), not a testbench-level constant. A DC/op-point
testbench (no transient claim, no rate axis) behaves identically to the
un-adapted gf180-bandgap harness — this axis is opt-in per testbench, not a
retrofit onto every experiment.

## Directory / naming convention

Each testbench topic gets its own experiment directory:

```
sim/
  <experiment-slug>/                 # e.g. smoke-cml-pair, output-voltage-tc
    testbench/                       # testbench netlist(s) / xschem export used
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.log              # raw ngspice output per PVT (x rate) point
                                      # e.g. ss_-40c_2.97v.log (DC/op-point)
                                      # or tt_27c_3.30v_742p5mbps.log (transient)
    records/
      <record-id>.md                 # append-only summary record
```

- **`<experiment-slug>`** — short, descriptive, kebab-case name for what is
  being verified (`smoke-cml-pair`, `output-voltage-tc`, ...). One directory
  per distinct claim being tested, not per run.
- **`<record-id>`** — unique and traceable:
  `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (e.g. `20260808-032312-430859a`).
  Re-runs simply mint a new `<record-id>`; nothing under `records/` is ever
  edited in place. The same `<record-id>` ties together the netlist snapshot,
  the raw per-corner logs, and the summary record for one run.
- **`<corner-id>`** — `<process>_<temp>c_<supply>[_<rate>]`, e.g.
  `ss_-40c_2.97v.log`, `tt_27c_3.30v.log` (DC/op-point, unchanged from
  gf180-bandgap), or `tt_27c_3.30v_742p5mbps.log`,
  `tt_27c_3.30v_270mbps.log` (transient, this repo's rate-axis extension).
  The grammar, formally:

  ```
  <corner-id> ::= <process> "_" <temp> "c" "_" <supply> ("_" <rate>)?
  <process>   ::= token ("_" token)*        # tt, ss, bjt_ff, res_typical
  <temp>      ::= "-"? digits ("." digits)? # -40c, 27c, 125c
  <supply>    ::= "nosupply" | node? volts "v"   # 2.97v, nwell2p97v
  <rate>      ::= digits ("p" digits)? "mbps"    # 742p5mbps, 270mbps
  ```

  The fields are separated by the **last two or three** underscores (three
  when a `<rate>` field is present), so the process field may itself
  contain one:

  - **`<process>`** — one or more lowercase alphanumeric tokens joined by
    underscores. For a circuit-level run this is the harness corner name
    (`tt`, `ss`, `ff`, `fs`, `sf`, and the passive-skew corners `res_ff`,
    `bjt_ss`, ...). For a device-level testbench that exercises one device
    family it is the gf180mcu model-section name that testbench selects
    (`typical`, `bjt_typical`, `res_ff`, ...). The vocabulary is deliberately
    **open**: gf180mcu ships a `.lib` section per device family (see
    `sim/harness/corners.py`), so the set grows with the families a testbench
    touches, and pinning it to `tt|ss|ff` would misname most device runs.
  - **`<temp>`** — the junction temperature in °C, signed, suffixed `c`:
    `-40c`, `27c`, `125c`. A record may add intermediate points (`-10c`,
    `60c`, `90c`) but never fewer than the PVT-matrix axis without a stated
    reason.
  - **`<supply>`** — one of:
    - `<volts>v` — the swept supply, e.g. `2.97v`, `3.30v`, `3.63v`;
    - `<node><volts>v` — when the swept rail is not the main supply and needs
      naming, e.g. `nwell2p97v`. `p` stands in for the decimal point so the
      field stays a single token with no underscore of its own;
    - `nosupply` — the testbench has no supply rail to sweep (a device
      testbench referred to its own source node and driven by an ideal
      source). This is one of the subset justifications the record's **Corner
      matrix run** field is required to spell out.
  - **`<rate>`** *(this repo's extension — omitted entirely for a DC/
    op-point testbench, in which case `<corner-id>` is byte-identical to the
    un-adapted gf180-bandgap grammar)* — the bit rate in Mbps/lane for this
    point, formatted `<digits>[p<digits>]mbps` (`p` stands in for the decimal
    point, same convention as `<supply>`): `742p5mbps` for 742.5 Mbps/lane
    (720p60 target), `270mbps` for 270 Mbps/lane (480p fallback). Present
    only on a testbench that declares a `rates_mbps` axis in its manifest
    (`sim/harness/testbench.py`) — i.e. only on a transient/eye-measurement
    testbench, never on a DC/op-point one.
- **`testbench/`** is not versioned per record — it holds the current
  testbench netlist(s)/xschem export(s) used to generate records. If the
  testbench itself changes in a way that could affect comparability across
  records, note that in the new record's summary (e.g. under Claim or a
  free-text note).

## Summary record format

Each run produces one `records/<record-id>.md` file with the following
fields. The first nine are unchanged from gf180-bandgap and are **always**
required; **Operating point** and **Transient settings** are a
conditionally-required tenth/eleventh field, present if and only if the
run's per-corner logs carry a `<rate>` token (i.e. the testbench declared a
`rates_mbps` axis) — a DC/op-point record never carries them, same as an
un-adapted gf180-bandgap record.

- **Record ID** — the `<record-id>` for this run (matches the filename and
  the corresponding `netlist-snapshots/` / `corners/` subdirectory).
- **Claim** — which spec parameter/line this record substantiates (reference
  the ratified spec, e.g. `spec/tmds-tx.md#dr-0002`).
- **Netlist provenance** — `schematic` (`design/...`) or `extracted`
  (post-layout, `layout/...`). Required so post-layout re-runs are
  distinguishable from the original schematic-level record.
- **Corner matrix run** — explicit list of (process corner, temperature,
  supply[, rate]) points actually executed. Must be the full PVT (× rate,
  when applicable) matrix from the "PVT matrix" section above unless the
  record states why a subset was used.
- **Operating point** *(rate-bearing records only)* — which of
  `spec/tmds-tx.md` §1's two operating points this record substantiates:
  `742.5 Mbps/lane (target (720p60))`, `270 Mbps/lane (fallback (480p))`, or
  both (a run that sweeps the rate axis over both, like
  `sim/smoke-cml-pair`). Every rate actually present in this record's
  per-corner logs must be named here, and every rate named here must
  actually have been run — `sim/check_records.py` cross-checks this
  mechanically (see "Enforcement" below), which is the concrete mechanism
  that makes a record covering only the 480p fallback unable to pass lint
  while claiming the 720p60 target row.
- **Transient settings** *(rate-bearing records only)* — the transient
  solver settings actually used for this run: `.tran` print/plot step,
  `.tran` stop time, the internal max-timestep ceiling (`tmax`), and the
  `reltol`/`abstol`/`vntol` tolerances (ngspice `.options`). An
  under-resolved `.tran` silently flatters an eye/rise-fall measurement, so
  these are evidence, not incidental detail — "the eye is open" or "the edge
  is fast" is a claim about the circuit only if the timestep controller was
  actually tight enough to resolve it, and this field is where that claim's
  own precondition is recorded. `sim/check_records.py` fails a rate-bearing
  record with this field missing or empty.
- **Statistical convention** (when applicable, e.g. Monte Carlo mismatch
  analysis) — N samples and sigma level reported. Used for distribution
  claims that are not a per-corner pass/fail (e.g. reporting a spread against
  the untrimmed spec).
- **Result** — per-corner pass/fail, plus an overall pass/fail against the
  ratified spec value.
- **Links** — paths to the testbench file(s), the frozen netlist snapshot,
  and the raw per-corner logs used to produce this record.
- **Timestamp / author** — when the record was created and who (human or
  agent) created it.
- **Supersedes** (optional) — the prior `<record-id>` this record supersedes,
  for corrections or for a post-layout extracted re-run that reports a
  schematic-vs-extracted delta against the schematic-level record.

## The stimulus convention for a transient testbench

A transient testbench's manifest names its stimulus pattern via
`transient.pattern` (informative — recorded in **Transient settings**, not
separately enforced). Two conventional values:

- **`worst-case-101010`** — an alternating (maximum-transition-density)
  differential square wave at the bit rate. For a DC-balanced 8b/10b-style
  code such as TMDS, the maximum-toggle-rate pattern is the standard
  worst-case stimulus for ISI/bandwidth-limited eye closure, so this is a
  legitimate, cheap stand-in for a full TMDS-encoded worst-case sequence.
  `sim/smoke-cml-pair` (see below) exercises this pattern.
- **`prbs7`** — a genuine pseudo-random bit sequence (period 127), for a
  statistically meaningful multi-edge eye/jitter measurement. No testbench
  in this repo implements it yet; that is deferred to issue #11's real CML
  driver testbench, where a real driver + load first makes a multi-edge
  jitter histogram a meaningful measurement rather than a demonstration of
  harness plumbing.

A testbench is free to name a different pattern string; these two are simply
the ones this convention gives a name to so future testbenches do not each
invent their own vocabulary.

## Append-only rule

`records/*.md` files are never edited or deleted after creation. A re-run or
a correction always creates a new record with a new `<record-id>`. If it
corrects or replaces a prior result, it references that prior record via
**Supersedes** rather than overwriting it. This applies even to typo fixes —
the append-only guarantee is what makes `sim/` usable as an evidence trail;
"fixing" an existing record in place would defeat that.

## Enforcement

This convention is checked, not merely documented. `sim/check_records.py`
(implementation: `sim/harness/evidence_lint.py`) runs as step 4 of
`.github/scripts/lint.sh`, so `npm run lint` and the CI `lint` job both
execute it on every PR. It reads tracked files only, needs nothing but
`python3` and `git`, and fails on:

- a missing or empty one of the nine always-required fields above;
- a filename that is not a well-formed `<record-id>`, or a **Record ID**
  field that disagrees with its filename;
- a record with no `netlist-snapshots/<record-id>.spice` or no
  `corners/<record-id>/` logs — and, symmetrically, a snapshot or corner
  directory with no summary record to cite it;
- a `<corner-id>.log` name that does not parse under the grammar above;
- a rate-bearing record (any of its per-corner logs carry a `<rate>` token)
  with a missing or empty **Operating point** or **Transient settings**
  field, or whose **Operating point** field names a different set of rates
  than its per-corner logs actually carry — this is the mechanical check
  that makes claiming the 720p60 target row require actually having run
  742.5 Mbps/lane points, not just having run *some* transient points;
- a **Supersedes** value that names a `<record-id>` with no record in the
  same experiment directory (write `(none)` when a record supersedes
  nothing);
- **append-only violations**: any file under `records/`,
  `netlist-snapshots/` or `corners/` modified, renamed, or deleted relative
  to the merge base with `origin/main`. Only additions are allowed.

The append-only half needs real git history; where the base ref does not
resolve (a shallow clone, say) it prints `SKIP` rather than passing silently,
and `--require-append-only` turns that skip into a failure — which is how CI
runs it.

If the checker and this document ever disagree, this document wins and the
checker is the thing that gets fixed. The evidence is never the thing that
gets fixed.

## Worked example: sim/smoke-cml-pair

`sim/smoke-cml-pair` is this repo's first evidence and the harness's own
acceptance test (issue #8): a bare 3.3 V NMOS differential pair with the
DR-0002 load topology (10 mA tail current, 50 Ω/leg to the 3.3 V rail) — no
other design content, and explicitly **not** a CML driver design deliverable
(that is issue #11's job). It exists to prove the transient/rate-axis
machinery end to end: `python3 sim/run_corners.py smoke-cml-pair` runs the
full mandated PVT matrix at both `rates_mbps` (742.5 and 270 Mbps/lane) —
90 points total — mints one record, and records swing/common-mode/10-90%
rise-fall measurements plus the transient solver settings actually used.
See `sim/smoke-cml-pair/records/` for the current record and
`sim/smoke-cml-pair/testbench/tb.json` for the manifest that produces it.

## Post-layout re-runs: same testbench, `--dut` swapped

A post-layout record is only comparable to its schematic-level predecessor
if *nothing else changed*. So a post-layout re-run does not get its own
experiment directory, its own testbench, or its own measurement set — it
re-runs the existing experiment with the DUT netlist swapped:

```bash
python3 sim/run_corners.py cml-driver-eye \
    --dut layout/sim/cml_driver_core_dut.spice \
    --supersedes <schematic-record-id>
```

The harness classifies provenance from the DUT's own path — anything under
`layout/` records itself as `extracted`, with no flag to forget — and folds
the DUT into the record's `netlist-snapshots/` copy, so the record freezes
the exact circuit it measured. Two obligations follow, and both are on the
record's author, not the harness:

- **State the extraction's coverage explicitly.** `extracted` is not one
  thing. A device-level, LVS-clean extraction and a full parasitic-RC
  extraction are different claims, and a reader cannot tell them apart from
  the provenance label. The record's **Claim** field must say which — and
  name what is *not* modelled (parasitic R/C, `NRD`/`NRS`, substrate
  resistance, anything outside the extracted cell).
- **Report the delta, and explain it.** That is what **Supersedes** is for
  here (it points at the schematic record; it does not assert the schematic
  record was wrong). `sim/compare_records.py <experiment> <baseline-id>
  <candidate-id>` computes the worst absolute and relative per-corner delta
  for every shared measurement, plus any verdict change, so the comparison
  is machine-computed rather than transcribed by eye. The explanation of
  those deltas is human-authored prose and belongs in
  `measurements/characterization.md`.

The worked example is `sim/cml-driver-eye`'s record
`20260815-072956-34e5253` (issue #34) against its schematic-level
predecessor `20260810-041436-a2c358b`, analysed in
`measurements/characterization.md` § "DR-0002, post-layout (extracted)
corroboration".

## Cold-start reproducibility audit (2026-08-14, issue #25)

Presence of a testbench is not freshness of its claim, so this audit actually
re-ran every experiment directory that existed at the time — `smoke-cml-pair`,
`cml-driver-eye`, `esd-clamp-cv` — from a clean checkout (`git status`
clean, no local edits), using only the invocation documented in
[`sim/harness/README.md`](harness/README.md)'s "Quick start"
(`python3 sim/run_corners.py <slug>`), against the PDK the machine already had
provisioned per the "Prerequisites" table there.

**Result: all three reproduce cleanly. No gap was found**, so none needed
fixing:

| Experiment | Points | Result | Spot-checked against recorded evidence |
|---|---|---|---|
| `smoke-cml-pair` | 90/90 (full PVT × rate grid) | PASS | `tt_-40c_2.97v_742p5mbps`: `swing_diff_v`/`vcm_v` bit-for-bit match the `records/20260808-032312-430859a.md` row |
| `cml-driver-eye` | 90/90 (full PVT × rate grid) | PASS | same corner: `ui_ref`/`swing_c0`/`vcm_c0` bit-for-bit match `records/20260810-041436-a2c358b.md` |
| `esd-clamp-cv` | 45/45 (full PVT grid) | PASS | `tt_-40c_2.97v`: `cap_base_0v`/`cap_base_opv` bit-for-bit match `records/20260814-193222-dd48630.md` |

Specifically checked:

- **PDK revision**: `sim/pdk.json` pins `gf180mcuD` @ open_pdks
  `c6d73a35f524070e85faff4a6a9eef49553ebc2b`. `python3 sim/run_corners.py
  --check-env` resolved that exact variant/revision on the audit machine
  (`~/.volare/gf180mcuD`), and every existing record's own **Environment**
  section cites the same open_pdks hash (on different machines/paths —
  `/Users/rwalters/.volare` for `smoke-cml-pair`/`esd-clamp-cv`,
  `/home/ubuntu/.volare` for `cml-driver-eye` — which is exactly the point of
  pinning the revision rather than a path: the hash matched everywhere it was
  checked).
- **No undocumented manual steps**: each experiment ran end-to-end from the
  single documented command with no repo edits, path fixes, or hand-run
  intermediate steps.
- **No stale paths**: every testbench fragment (`testbench/*.spice`) is
  self-contained — no hardcoded path outside the fragment itself — and the
  harness resolves the PDK, not the testbench.
- **`sim/check_records.py`** and the harness's own unit tests
  (`python3 -m pytest sim/tests`) both pass against the tree unchanged by this
  audit.

These re-runs used `--no-write` (`sim/harness/README.md`'s documented
debugging mode) rather than minting new records: the goal was confirming the
*existing* records reproduce, not adding new evidence for its own sake, and a
per-corner spot-check (above) against each experiment's current record
confirms the reproduction is exact, not merely "the deck still runs." This is
consistent with the append-only convention above — nothing under `records/`,
`netlist-snapshots/`, or `corners/` was added, edited, or deleted by this
audit.

Two of the three pre-existing records (`smoke-cml-pair`, `esd-clamp-cv`) are
self-flagged in their own **Netlist provenance** field as taken against a
dirty working tree at recording time; that caveat was already on the record
before this audit and is a property of *when the original record was minted*,
not of whether today's clean-checkout re-run reproduces it — which it does.
Nothing about it required a fix here; it is called out because a reader
diffing this note against those records should not read "reproduces cleanly"
as also meaning "was originally recorded against a clean tree."
