# DR-0010: PDK variant and revision this block is designed and verified against

**Status: Accepted.**

**Supersedes**: the `gf180mcuD` variant citation in `spec/tmds-tx.md`'s
DR-0002 (Status line only — no other DR-0002 text changes) and fully
supersedes DR-0005 (superseded in full by DR-0011, which restates its own
PDK-variant citation against this record).

**Renumbering note**: this repository's own convention
(`spec/README.md`) numbers decision records "monotonically increasing across
the whole spec, not per file." Issue #9's own body drafted this record (and
its three siblings) as `DR-0006`–`DR-0009`. Between the time issue #9 was
filed (2026-08-08) and the time it was built, four *unrelated* decision
records — `DR-0006` (DR-0002's common-mode supply-tracking derating),
`DR-0007` (the encoder's synthesized-domain clock ceiling), `DR-0008` (the
`tmds_encoder` two-stage pipeline) and `DR-0009` (the `tmds_encoder`
four-stage pipeline) — were ratified against those exact numbers by other
issues (#87-adjacent analog work and #100/#110/#115's digital-partition
timing closure). Reusing `DR-0006`–`DR-0009` for this issue's records would
collide with already-ratified, already-cited decisions. This record and its
three siblings are therefore numbered `DR-0010`–`DR-0013` instead — the next
open block after the highest number `spec/tmds-tx.md` already ratifies. See
`spec/README.md` for where this is recorded going forward.

## Context

`spec/tmds-tx.md`'s DR-0002 and (pre-supersession) DR-0005 both cite the PDK
as *"gf180mcuD / open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, as
checked out via volare, 2026-08-05."* But `spec/pad-ring-esd-survey.md`'s
preamble (issue #2) records that every layout artifact actually committed to
this repository — `layout/gds/gf180_tmds_pad_min.gds`, its shorted negative
control, and (mirrored since) `layout/gds/cml_driver_core.gds` and
`layout/gds/tmds_encoder.gds` — was produced against a *different* variant:

> PDK root: `~/.volare/gf180mcuC` (variant `gf180mcuC`)
> `open_pdks` commit: `c6d73a35f524070e85faff4a6a9eef49553ebc2b`

Same `open_pdks` commit, different variant letter. `sim/pdk.json` and
`sim/harness/pdk.py` independently pin `gf180mcuD` for every SPICE-level
analog record (`sim/cml-driver-eye/`, `sim/esd-clamp-cv/`,
`sim/smoke-cml-pair/`, `sim/cml-driver-mismatch/`) and for the common-mode
supply-tracking analysis DR-0006 (the *existing*, unrelated one) ratifies.
`flow/` (the digital synthesis/PnR/STA flow behind DR-0007/0008/0009, the
*existing*, unrelated ones) also resolves the PDK via
`sim/harness/pdk.py`, i.e. also against `gf180mcuD`. So today: **layout
evidence cites C, every simulation and digital-flow record cites D**, and
nothing in this repository had ruled on which one this block is actually
designed and verified against.

### What C and D actually differ on (measured, not assumed)

Both variants are installed locally (`~/.volare/gf180mcuC`,
`~/.volare/gf180mcuD`), at the identical `open_pdks` commit
`c6d73a35f524070e85faff4a6a9eef49553ebc2b` the existing citations already
name. `.config/nodeinfo.json` states the headline difference:

| Variant | `nodeinfo.json` description |
|---|---|
| `gf180mcuC` | *"...5 metal layer backend stack + **0.9um thick top metal** + 2fF/um^2 MiM caps..."* |
| `gf180mcuD` | *"...5 metal layer backend stack + **1.1um thick top metal** + 2fF/um^2 MiM caps..."* |

Rather than stop at that headline, every asset tree under both variant
roots was diffed directly:

- **`libs.tech/ngspice/` (SPICE device models): byte-identical.** `diff -rq`
  between `libs.tech/ngspice/gf180mcuC` and `.../gf180mcuD` reports **zero**
  differing files — `sm141064.ngspice` (the transistor/diode/resistor/
  capacitor model deck DR-0002 and DR-0005 both cite) is bit-for-bit the
  same file under both variants. Every SPICE-level electrical result this
  repository has recorded (`sim/cml-driver-eye/`, `sim/esd-clamp-cv/`,
  `sim/smoke-cml-pair/`, `sim/cml-driver-mismatch/`, and the common-mode
  AVCC-sensitivity data DR-0006 reads) used exactly the same device models
  regardless of which variant letter its citation names.
- **`libs.tech/klayout/tech/drc/` (klt's underlying rule source): also
  byte-identical.** `diff -rq` reports zero differing files. This is
  consistent with `klt`'s own curated gf180mcu deck
  (`klayout_tools/decks/gf180mcu.py`) hard-coding its rule thresholds in
  Python rather than reading them from the vendored PDK tree per-variant —
  so `klt drc`/`klt extract`/`klt lvs` results are identical regardless of
  which variant directory is passed, and every `layout/` DRC/LVS report this
  repo has produced is unaffected by the C-vs-D question at the tool level.
- **`libs.tech/magic/*.tech` (the vendored, variant-scoped DRC/parasitic
  deck): differs in exactly four rule blocks, all Metal5 (top-metal)
  specific** — confirmed by diffing the two `.tech` files with the node name
  itself normalized out (so only substantive rule deltas surface):

  | Rule | `gf180mcuC` (0.9um) | `gf180mcuD` (1.1um) |
  |---|---|---|
  | Metal5 min width (`MT.1`) | 0.440 um | 0.360 um |
  | Metal5 min spacing (`MT.2a`) | 0.460 um | 0.380 um |
  | Metal5 min area (`MT.4`) | 0.5265 um² | 0.5625 um² |
  | Metal5 wide-metal spacing (`MT.2b`-class, >=10um width trigger) | 0.600 um | 0.500 um |
  | Metal5 sheet resistance, 3 named corners | 40 / 49 / 31 mOhm/sq | 60 / 70 / 50 mOhm/sq |
  | Named top-metal resistor device | `rsubcircuit tm9k` | `rsubcircuit tm11k` |

  `defaultareacap`/`defaultperimeter` (the Metal5-to-substrate parasitic
  capacitance coefficients `design/esd-capacitance-budget.md`'s 7.95 pF
  figure was computed from, at all three named process corners) are **not**
  in this diff — they are identical between variants. So the one existing
  numeric result most exposed to the C-vs-D question (the pad-capacitance
  budget study) is, by direct inspection of the coefficients it reads,
  **unaffected in value** by which variant it cites.

  The `tm9k`/`tm11k` resistor-model naming (kAngstrom: 9000 Å = 0.9 um,
  11000 Å = 1.1 um) directly corroborates `nodeinfo.json`'s thickness claim.
  The sheet-resistance numbers themselves do **not** move in the naively
  expected direction (thicker metal is usually lower sheet resistance;
  here `gf180mcuD`'s values are higher, not lower, than `gf180mcuC`'s) —
  this is reported as measured, not explained; no claim is made here about
  why, only that the values differ and by how much.
- **`libs.ref/gf180mcu_fd_io/` (the I/O library actually relevant to this
  block's pad ring): every LEF/GDS/`.mag` file differs**, but by inspection
  the *only* substantive geometry delta is the bond pad's own Metal5 shape,
  shifted by exactly 0.1 um per edge — e.g. `gf180mcu_fd_io__bi_t.lef`'s
  Metal5 pad rectangle is `RECT 1.600 69.400 73.400 348.390` under
  `gf180mcuC` and `RECT 1.500 69.500 73.500 348.390` under `gf180mcuD`, the
  same delta reproduced identically across every pad cell in the library
  (`bi_24t`, `asig_5p0`, `dvdd`, `dvss`) — a direct, visible consequence of
  the Metal5 width/spacing rule delta above.
- **`libs.ref/gf180mcu_fd_sc_mcu9t5v0/` (the standard-cell library DR-0003's
  synthesized domain, and DR-0007/0008/0009's timing-closure work, target):
  `lef/` and `lib/` (liberty timing) are byte-identical between variants.**
  Only the library's own `.gds`/`.mag` files differ (again consistent with a
  Metal5-only geometric delta — standard cells route on lower metals). This
  means **DR-0007/0008/0009's synthesis/CTS/STA closure results are
  unaffected by this record** — they read LEF and liberty only, and both are
  identical under either variant.

### Net effect of the survey

The two variants are not "close enough to ignore" nor "so different that
every existing result is invalid." They differ in exactly one respect that
matters to this repository: **Metal5 (top-metal, pad-adjacent) DRC
thresholds and sheet resistance**, driven by the 0.9 um vs 1.1 um top-metal
thickness difference `nodeinfo.json` states. SPICE device models, `klt`'s
own DRC/LVS rule engine, standard-cell LEF/liberty, and the specific
parasitic-capacitance coefficients `design/esd-capacitance-budget.md`
already used are all identical either way.

## Decision

**This block is designed and verified against `gf180mcuD`** — per the
operator's ruling amendment on issue #9 (2026-08-19T04:35:28Z), which
explicitly supersedes this record's original `gf180mcuC` ruling. The
amendment's own stated rationale: the product landscape record documents
that wafer.space's GF180MCU shuttle runs advertise the `gf180mcuD` stack,
and TinyTapeout's GF shuttles also submit via wafer.space — every observed
tape-out path for these canaries is `D`. This is exactly the scenario the
original ruling's own contingency anticipated ("revisit this pin only if a
future tape-out shuttle explicitly mandates `gf180mcuD`," see `##
Contingency` below) — it fired within the same review cycle that ratified
the original ruling, six minutes before PR #122 (which carried the original
`gf180mcuC` text) merged, but the amendment was not seen before that merge
landed (see the correction note trailing this section's history: PR #122
was created 2026-08-19T04:35:08Z, twenty seconds before the amendment
posted, and merged 2026-08-19T04:41:03Z without incorporating it).

`open_pdks` commit `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, as checked
out via volare, is unchanged from the existing citations — only the variant
letter changes.

## Alternatives considered

- **Pin `gf180mcuC`** (matching every layout artifact and every `klt
  drc`/`klt extract`/`klt lvs` signoff report already committed to this
  repository at the time of the original ruling, and matching `gf180mcuC`'s
  thinner (0.9 um) top metal, the more conservative assumption for pad ESD
  margin) was this record's *original* ruling. **Superseded** by the
  operator's amendment above: matching the actual tape-out shuttle stack
  (`gf180mcuD`, per wafer.space's advertised GF180MCU runs, which both this
  program's and TinyTapeout's GF shuttles submit through) takes priority
  over avoiding a `layout/` re-run. Every `layout/` artifact must now be
  regenerated and re-signed off against `gf180mcuD` — a strictly larger
  practical cost than the citation-only re-cite this correction performs,
  but the cost the amendment ruling accepts as correct (tracked as sub-issue
  B of #123's decomposition, filed as #127).
- **Leave the discrepancy unresolved and let each future issue pick locally**
  was considered and rejected outright — this is exactly the ambiguity
  issue #9 exists to close, and it directly blocks #12/#87's ESD-capacitance
  redesign work, which cannot proceed against two simultaneously-cited PDK
  variants.
- **Treat the discrepancy as immaterial and not worth a decision record**
  was considered and rejected once the survey above found a real (if
  narrow) Metal5 delta — "the two variants don't matter" would have been an
  assumption, not a finding; this record exists so the claim is evidenced
  either way.

## Consequences

### Artifacts already committed

- **`layout/` was originally produced against `gf180mcuC` and has since been
  regenerated against `gf180mcuD`.** Every `layout/` DRC/LVS artifact
  committed to this repository through issue #2 onward was first drawn and
  signed off against `gf180mcuC` — the variant this record's original ruling
  pinned, matching what was already on disk at the time. The operator's
  amendment (`## Decision` above) required regenerating and re-signing off
  that work against `gf180mcuD` instead (Metal5 pad geometry moves by the
  deltas measured in `## Context` above); that regeneration is complete.
  Tracked as sub-issue B of #123's decomposition (#127, closed) — out of
  scope for this citation-only correction (sub-issue A).
- **`sim/` (every analog SPICE record) and `flow/` (the digital synthesis/
  PnR/STA flow) cite `gf180mcuD`** (`sim/pdk.json`, `sim/harness/pdk.py`'s
  `DEFAULT_VARIANT`, `flow/README.md`) as of this correction, matching the
  ratified pin — no further re-citing needed there:
  - Every analog record's underlying SPICE device models
    (`sm141064.ngspice`) are byte-identical between variants, so no
    `sim/*/records/*.md` result changes numerically. `design/
    esd-capacitance-budget.md`'s 7.95 pF figure specifically used
    coefficients (`defaultareacap`/`defaultperimeter`) that are also
    byte-identical between variants, so it is likewise unaffected in value.
  - Every digital-flow record's underlying LEF/liberty are byte-identical
    between variants, so DR-0007/0008/0009's 720p60 closure results are
    unaffected in value.
  - This correction updates `sim/pdk.json`, `sim/harness/pdk.py`'s
    `DEFAULT_VARIANT`, `sim/README.md`, `sim/harness/README.md`,
    `sim/env.sh`, `flow/README.md`, `spec/tmds-tx.md`'s Status-line note, and
    the live-pin passages of `design/esd-capacitance-budget.md` — but does
    not rewrite the historical, append-only `sim/*/records/*.md`/
    `flow/*/records/*.md` files themselves — per `sim/README.md`'s own
    append-only convention, a correction references what it supersedes
    rather than overwriting history in place.
- **No numeric result recorded anywhere in this repository is invalidated**
  by this ruling — the survey above establishes that every place C and D
  actually differ (Metal5 width/spacing/area/resistance, and the I/O
  library's pad Metal5 geometry) is untouched by any result this repo has
  computed so far. This decision closes a citation ambiguity, not a
  correctness defect.

### Contingency

**Fired.** The original text of this section read: "Revisit this pin only
if a future tape-out shuttle explicitly mandates `gf180mcuD` (or another
variant)." The operator's amendment ruling on issue #9 (2026-08-19T04:35:28Z,
see `## Decision` above) fired this contingency immediately: the product
landscape record documents that wafer.space's GF180MCU shuttle runs
advertise the `gf180mcuD` stack, and TinyTapeout's GF shuttles also submit
via wafer.space — every observed tape-out path for these canaries is `D`.

Per the original anticipation of this scenario: every `layout/` artifact
has now been regenerated and re-signed off against `gf180mcuD` (Metal5 pad
geometry moved by the deltas measured in `## Context` above), and `sim/`/
`flow/` citations have flipped to match. That layout regeneration was
tracked as sub-issue B of #123's decomposition (#127, closed) — a much
larger body of analog/DRC/LVS work, out of scope for this record's own
citation-only correction (sub-issue A) but now complete in its own right.
Per the survey above, no *numeric* sim/flow result needed recomputation,
only the layout/pad-adjacent geometry and its DRC/LVS signoff.

## Status

**Accepted.** Supersedes DR-0002's PDK-variant citation (Status-line note
only; DR-0002's driver-topology decision itself is unchanged) and DR-0005 in
full (superseded by DR-0011).
