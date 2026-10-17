# DR-0019: Correction — the `gf180mcu_fd_io` pad is 75 um along the ring and 350 um deep

**Status: Proposed.** Corrects a factual transposition in
`spec/pad-ring-esd-survey.md` (§1, §8) that DR-0011 adopted. Relaxes no
ratified number and changes no layout, script or test; it records the
corrected facts and lists what must be re-derived. Needs the usual
ratification. DR-0011's decision text is not edited (it is ratified); its
Status line gains a pointer here, as DR-0005's does to DR-0011.

## Context

`spec/pad-ring-esd-survey.md` §1 reads `gf180mcu_fd_io__bi_t.lef`'s
`SIZE 75.000 BY 350.000` as "75 um deep (core-to-pad-edge) by 350 um wide
(along the ring)" and §8 concludes "350 um pad-to-pad pitch, 75 um ring
depth". DR-0011 ("Pad pitch and ring depth: 350 um pitch / 75 um depth")
adopted that reading, and `design/esd-capacitance-budget.md` §10 then reported
fit results as "met, not amended" against a "350 µm slot" (#143, #150).

Found while porting the I/O ring (`2AMLogic/gf180-io-ring#2`), whose
orientation needs the opposite reading.

## Evidence

Read 2026-10-17 from the open_pdks revision `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
installed under `~/.ciel/ciel/gf180mcu/versions/`, all four variants
(`gf180mcuA`–`D`), `libs.ref/gf180mcu_fd_io/lef/` (`grep SIZE`;
`awk '/PIN PAD/,/END PAD/'`). `SIZE` is `x BY y`, so the first number is the
x extent and the second the y extent. The PAD pin sits at low y (y 2–62),
i.e. at one end of the long axis.

| Cell | `SIZE` (x BY y), all four variants |
|---|---|
| `bi_t`, `dvdd`, `in_c` | 75.000 BY 350.000 |
| `fill1` / `fill5` / `fill10` | 1 / 5 / 10 BY 350.000 |
| `brk2` / `brk5` | 2 / 5 BY 350.000 |
| `fillnc` | 0.100 BY 350.000 |

The fillers and breakers are the summable ring-filling cells (survey §1: the
ring is built by tiling cells of equal depth and variable width). Their x
extent is the one that varies, so x is the along-ring axis and y, constant at
350 um, is the depth.

**Corrected geometry: pitch along the ring = 75 um; depth (core to pad edge) = 350 um.**

`fillnc` is 0.100 um wide at this revision; survey §1 quotes 0.42 um.

## PAD landing is revision- and variant-dependent

| Source | Layer | Rect (um) | Size |
|---|---|---|---|
| Survey §1, open_pdks `c6d73a3` (DR-0010's pin) | Metal5 | 25 20 50 45 | 25 x 25 |
| `f6eeac7`, `gf180mcuA` | Metal3 | 7.5 2 67.5 62 | 60 x 60 |
| `f6eeac7`, `gf180mcuB` | Metal4 | 7.5 2 67.5 62 | 60 x 60 |
| `f6eeac7`, `gf180mcuC` / `gf180mcuD` | Metal5 | 7.5 2 67.5 62 | 60 x 60 |

`c6d73a3` is not installed on this host, so the survey's `c6d73a3` figures are
taken as given and **not re-verified**. `klt` resolves `f6eeac7`. Whether the
PAD landing really changed between the two revisions, or the survey read it
differently, is open. This record does not change DR-0010's pin; if the pin
should move, that is a DR-0010 successor's decision.

## Decision

Correct the recorded fact only:

- The standard `gf180mcu_fd_io` pad is **75 um wide along the ring and 350 um
  deep**. Wherever DR-0011 or the survey says "350 um pitch / 75 um depth"
  it means "75 um pitch / 350 um depth" as read from the LEF.
- The PAD landing is revision- and variant-dependent as tabulated above. Any
  figure for it must name the revision and variant it was read from.
- DR-0011's decision to **adopt the library's own pitch and depth** (rather
  than argue for a custom one) is unchanged in intent. Only the numbers it
  names were transposed. Whether the intent still holds at 75 um pitch is
  the first question for the follow-up fit study below, not answered here.
- No ratified number (`spec/tmds-tx.md` §1, HBM/CDM, the <= 2 pF pad-node
  budget) is relaxed, and no result is re-labelled as passing.

## Consequences for DR-0011's "met, not amended" claims

The fit conclusions were derived against a 350 um along-ring slot and a
75 um depth. Neither number is the along-ring or depth dimension of the
real cell.

- **Invalidated (premise wrong).** `design/esd-capacitance-budget.md` §10.2
  "DR-0011 is met, not amended", and its table of "structure width in the
  350 µm slot". Against a 75 um along-ring pitch, the 111-, 222- and 334-finger
  structures (302.0 / 325.4 / 325.4 um wide) do not fit one slot; only the
  20-finger structure (65.4 um) is under 75 um. Whether they fit a
  multi-slot span or a different orientation is a new question.
- **Invalidated.** The "pad structure must sit higher in the ring depth"
  finding and its "30-32 um of the 75 um ring depth unused" figure. The depth
  is 350 um, and the DVDD/DVSS strap band positions must be re-read from the
  library cells' y axis before any clearance is quoted.
- **Needs re-derivation.** "Ring continuity survives the larger pad" (`klt
  components`, tile spanning x 0-700 um): the tile was two 350 um slots wide
  and the straps ran along the wrong axis relative to the real cells.
- **Likely unaffected, to be confirmed.** Cell-level pad-node capacitance
  (§9, 0.225-0.652 pF), clamp device class and HBM/CDM targets do not depend
  on the ring pitch. They do depend on the pad plate, which §9 sized at
  25 x 25 um from the survey's `c6d73a3` landing; the `f6eeac7` landing is
  60 x 60 um.

## Affected code and docs (for follow-up issues; not changed here)

From `git grep` at `2964f73` (re-run before relying on it):

- `layout/scripts/gen_pad_ring_assembly.py` (`PAD_PITCH_UM`, `RING_DEPTH_UM`)
  and `layout/tests/test_gen_pad_ring_assembly.py`
- `layout/scripts/pad_pitch_fit_study.py` and
  `layout/tests/test_pad_pitch_fit_study.py`
- `layout/scripts/gen_pad_v2.py`
- `design/esd-capacitance-budget.md` (§10, plus the 350/75 mentions in §9 and later sections)
- `layout/README.md`, `docs/chipalooza/challenge-5-proposal.md`,
  `measurements/characterization.md`, `spec/tmds-tx.md`
- mentions in DR-0010, DR-0013, DR-0015, DR-0016

Follow-ups, each its own issue after this record is ratified: (1) re-run the
pad-pitch fit study against 75 um x 350 um; (2) correct the layout constants and
tests; (3) re-read the supply-strap positions from the library LEF/GDS;
(4) decide whether a custom pad should span several 75 um slots or argue for a
different pitch (a new decision record).

## Rejected

- **Editing DR-0011 or the survey text in place.** Both are the recorded
  history of what was believed; the survey gets an appended dated note instead.
- **Fixing `layout/` constants in this change.** A spec decision must land
  first, and the geometry change reshapes the fit studies.
- **Re-pinning the PDK revision here.** That is DR-0010's decision.
