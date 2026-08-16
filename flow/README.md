# flow

Synthesis and place-and-route recipes (Yosys, OpenROAD) driven through `klt`.

## What's here

- `synth_tmds_encoder.py` -- cold-start Yosys synthesis driver for
  `rtl/tmds_encoder.v`. Maps the encoder to the gf180mcu standard-cell
  library and corner `spec/tmds-tx.md` DR-0003 names for the synthesized
  domain (`gf180mcu_fd_sc_mcu9t5v0`, the `tt_025C_3v30` 3.3 V nominal
  corner), and writes a gate-level netlist plus an append-only evidence
  record. See the module's own docstring for the full recipe and the
  cross-checks it runs.
- `pnr_tmds_encoder.py` -- OpenROAD place-and-route driver for the netlist
  `synth_tmds_encoder.py` produced (issue #84). Floorplan, tap/endcap, power
  distribution network, placement, and routing via OpenROAD, then an
  in-process (never a `klayout` subprocess) DEF->GDS merge via the
  `klayout` PyPI package. Writes the routed DEF, the merged block-level GDS
  (`layout/gds/tmds_encoder.gds`), and its own evidence record. See the
  module's own docstring for the full recipe -- including two real,
  found-and-fixed upstream DEF->GDS-merge defects (a DBU mismatch that
  silently dropped via-cut geometry, and a related standard-cell-library
  merge scale corruption) -- and `layout/README.md`'s `tmds_encoder`
  section for the DRC/LVS signoff this GDS was checked against.
- `sdf_tmds_encoder.py` -- OpenSTA back-annotated SDF extraction driver for
  the routed DEF `pnr_tmds_encoder.py` produced (issue #85). Extracts RC
  parasitics from the routed geometry (OpenRCX, gf180's own typical-corner
  rule deck) and writes a back-annotated SDF plus its underlying SPEF, at
  the same `tt_025C_3v30` corner #82/#84 used. No SDC/clock-period
  constraint is read or assumed -- `report_checks -unconstrained` is used
  only to log the worst-case combinational delay found, not to render a
  setup/hold verdict (issue #83's job). See the module's own docstring for
  the full recipe.
- `sta_tmds_encoder.py` -- multi-corner static timing analysis (setup **and**
  hold) driver (issue #83), and the first driver here that renders a
  timing-closure verdict at all. Runs OpenSTA over #82's netlist as
  physically realized by #84's routed DEF with #85's parasitics
  back-annotated, across all five 3.3 V liberty corners the
  `gf180mcu_fd_sc_mcu9t5v0` library ships, at both of `spec/tmds-tx.md`
  §2's pixel-clock rates (720p60's 74.25 MHz and 480p's 27.000 MHz). It
  generates the constraint file it analyses against
  (`tmds_encoder/sta/tmds_encoder.sdc`) rather than assuming one exists,
  mechanically asserts that the DEF really realizes *that* netlist
  (`assert_def_matches_netlist`), and records SHA-256 digests of all three
  inputs so "the exact netlist revision" is verifiable rather than a
  filename. Every constraint assumption that shapes the verdict is stated
  in the module docstring, in the generated SDC, and in the evidence
  record. See that docstring for why the record reports two verdicts
  (register-to-register, and whole-design including the input-port paths).
- `gate_level_sim_tmds_encoder.py` -- re-runs the *exact same, unmodified*
  cocotb testbench (`verification/tmds_encoder/test_tmds_encoder.py`) that
  verifies the RTL, this time against the synthesized netlist with the SDF
  `sdf_tmds_encoder.py` produced back-annotated via Icarus Verilog's
  `$sdf_annotate` (issue #85). Documents and mechanically works around two
  Icarus Verilog 13.0 limitations (`ifnone` + edge-sensitive specify paths;
  `-ginterconnect` net resolution) in its own docstring, and writes its own
  evidence record citing the P&R revision, the SDF extraction tool/version,
  and the re-simulation outcome.
- `tmds_encoder/` -- this module's synthesis, place-and-route, and
  post-layout-verification outputs:
  ```
  tmds_encoder/
    netlist/tmds_encoder.synth.v   current gate-level netlist (regenerated
                                    in place by re-running the driver --
                                    not append-only, same as rtl/ source)
    pnr/tmds_encoder.def           routed DEF (pnr_tmds_encoder.py)
    sta/tmds_encoder.sdf           back-annotated SDF (sdf_tmds_encoder.py)
    sta/tmds_encoder.spef          extracted parasitics (sdf_tmds_encoder.py)
    sta/tmds_encoder.sdc           timing constraints (sta_tmds_encoder.py --
                                    generated, regenerated in place, not
                                    append-only; edit the driver, not this file)
    reports/<record-id>.synth.ys   exact Yosys script run for that record
    reports/<record-id>.synth.log  full Yosys log for that record
    reports/<record-id>.pnr.tcl    exact OpenROAD script run for that P&R record
    reports/<record-id>.pnr.log    full OpenROAD log for that P&R record
    reports/<record-id>.gds_merge.log   DEF->GDS merge log for that P&R record
    reports/<record-id>.sta.tcl    exact OpenSTA script run for that SDF record
    reports/<record-id>.sta.log    full OpenSTA log for that SDF record
    reports/<record-id>.sta_<target>.sdc        exact constraints used for that
                                                 STA record's <target> runs
    reports/<record-id>.sta_<corner>_<target>.tcl  exact OpenSTA script run for
                                                 that STA record's corner x target
    reports/<record-id>.sta_<corner>_<target>.log  full OpenSTA log for it
    reports/<record-id>.gl_sim.build.log  Icarus build log for that gate-level-sim record
    reports/<record-id>.gl_sim.test.log   cocotb test log for that gate-level-sim record
    records/<record-id>.md         append-only evidence record (see below)
  ```

## Running it

From a clean checkout, with the gf180mcu PDK installed (same PDK-pinning
convention as `sim/` -- see `sim/README.md`'s "PDK variant" and
`sim/harness/README.md`'s "Prerequisites"; `sim/pdk.json` pins
`gf180mcuD`, and PDK resolution here reuses `sim/harness/pdk.py` unchanged):

```bash
python3 flow/synth_tmds_encoder.py
```

This requires Yosys on `PATH` (see "Pinned toolchain" below) and the PDK
resolvable via `GF180_PDK_PATH` / `PDK_ROOT`+`PDK` / `sim/pdk.local.json` /
`sim/pdk.json`, in that order -- exactly as `sim/env.sh` sets up for the
analog side. `source sim/env.sh` before running this script works too.

Exit status is non-zero (with an explanatory stderr message) if: the PDK
can't be found, the pinned standard-cell liberty file is missing from it,
Yosys itself fails, or the written netlist contains any cell instance that
is not a `gf180mcu_fd_sc_mcu9t5v0__*` standard cell (an "unmapped cell" --
checked by re-parsing the written netlist, not merely assumed; see the
module docstring's "no unmapped cells" section). A clean run reports the
total cell count and writes the evidence record described below.

Place-and-route (requires OpenROAD on `PATH`, run via the pinned
`openroad/orfs` Docker image, plus the `klayout` PyPI package for the GDS
merge step -- see "Pinned toolchain" below):

```bash
python3 flow/pnr_tmds_encoder.py
```

Takes the netlist `synth_tmds_encoder.py` already wrote, as-is (never
re-synthesizes it). See the module's own docstring for the full recipe,
and `layout/README.md`'s `tmds_encoder` section for how to regenerate the
DRC/LVS reports against the GDS this writes.

Back-annotated SDF extraction (requires OpenROAD on `PATH`, same
`openroad/orfs` Docker image as P&R; requires the routed DEF
`pnr_tmds_encoder.py` already wrote):

```bash
python3 flow/sdf_tmds_encoder.py
```

Multi-corner static timing analysis (requires OpenROAD/OpenSTA on `PATH`,
same `openroad/orfs` Docker image as P&R; requires the routed DEF and the
SPEF `pnr_tmds_encoder.py` / `sdf_tmds_encoder.py` already wrote):

```bash
python3 flow/sta_tmds_encoder.py
```

Runs ten OpenSTA passes (five liberty corners x two pixel-clock targets) and
writes one evidence record covering all of them. `--no-record` runs the
analysis and the per-run logs without minting a record, for iterating on
constraints. Fails loudly if the routed DEF does not realize the committed
netlist, rather than silently timing a stale layout.

Post-layout gate-level re-simulation (requires the PDK for the vendor
cell-library Verilog models, Icarus Verilog + cocotb on `PATH` -- same
toolchain `verification/tmds_encoder/runner.py` uses; requires the SDF
`sdf_tmds_encoder.py` already wrote):

```bash
python3 flow/gate_level_sim_tmds_encoder.py
```

Re-runs `verification/tmds_encoder/test_tmds_encoder.py` unmodified against
the synthesized netlist, SDF-back-annotated. See the module's own docstring
for the two Icarus Verilog 13.0 limitations it works around, and why its
50 ns test clock period is not an operating-frequency claim.

## Evidence record format

`tmds_encoder/records/<record-id>.md` follows the same append-only
discipline `sim/README.md` establishes for the analog side (never edited or
overwritten -- a re-run mints a new `<record-id>`), adapted for a
single-corner synthesis run rather than a PVT sweep. Each record cites:

- the Yosys version and the gf180mcu PDK variant/`open_pdks` version
  actually used;
- the standard-cell library and corner (`gf180mcu_fd_sc_mcu9t5v0`,
  `tt_025C_3v30`);
- the synthesis constraints applied -- for this issue's scope, that is
  *only* the technology-mapping recipe (`proc`/`opt`/`fsm`/`memory`/
  `techmap`/`dfflibmap`/`abc`); no `.sdc`, no clock-period constraint, no
  timing-closure claim (see "Synthesized/custom boundary and what this flow
  does not answer yet" below);
- the resulting cell count and breakdown, and the unmapped-cell check
  result;
- whether the working tree was clean at run time (excluding this run's own
  output under `tmds_encoder/`), for reproducibility.

`sim/check_records.py`'s schema lint does not cover this directory (it is
scoped to `sim/*/records`, per `.github/scripts/lint.sh`) -- this file is
the authoritative convention for `flow/`'s own evidence records, mirroring
`sim/README.md`'s role for `sim/`.

## Pinned toolchain

| Tool | Verified version | Pin mechanism |
|---|---|---|
| Yosys | 0.67 (`yowasp-yosys` locally); CI installs Ubuntu's `yosys` apt package and prints `yosys -V` (`.github/workflows/ci.yml`) | recorded per-record in `tmds_encoder/records/<record-id>.md` |
| OpenROAD | `26Q3-1278-g4421880472`, run via the `openroad/orfs:latest` Docker image (`docker run -v <repo>:<repo> -w <repo bind mount> openroad/orfs:latest bash -c 'source /OpenROAD-flow-scripts/env.sh && python3 flow/pnr_tmds_encoder.py'` -- bind-mount at the *same* absolute path both inside and outside the container, since `pnr_tmds_encoder.py` writes host-absolute paths) | recorded per-record in `tmds_encoder/records/<record-id>.md`; not on `brew`/`pip` |
| `klayout` PyPI package | `0.30.10` (`klayout.db`, `pnr_tmds_encoder.py`'s GDS merge step only) | `pip install klayout` -- not preinstalled in the `openroad/orfs` image |
| OpenSTA (bundled in the `openroad` binary above) | `26Q3-1278-g4421880472` for `sdf_tmds_encoder.py`'s SDF/SPEF extraction; `26Q3-1080-gab6fd26351` for `sta_tmds_encoder.py`'s timing analysis (the `openroad/orfs:latest` tag moved between the two runs -- each record cites the build it actually used, which is why the pin mechanism is the record, not this table) | recorded per-record in `tmds_encoder/records/<record-id>.md`; no separate install |
| Icarus Verilog | 13.0, `gate_level_sim_tmds_encoder.py`'s SDF-annotated re-simulation | same pin as `verification/README.md`'s "Pinned toolchain" |
| cocotb | 2.0.1, `gate_level_sim_tmds_encoder.py`'s SDF-annotated re-simulation | same pin as `verification/tmds_encoder/requirements.txt` |
| gf180mcu PDK | `gf180mcuD`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` | `sim/pdk.json` (shared pin with the analog side) |
| Python | 3.11+ | stdlib only -- no venv, no requirements.txt (same rule `sim/harness/README.md` states for the analog harness) |

### A `yowasp-yosys` filesystem-sandboxing gotcha

The `yowasp-yosys` pip package (a WASM build of Yosys some dev/agent boxes
install, as opposed to the apt/native binary CI installs) can silently fail
to write output files under `/tmp` -- `write_verilog` reports
`Can't open output file ... No such file or directory` -- even though
`read_verilog`/`read_liberty` succeed against arbitrary absolute paths
outside the repo (confirmed directly while building this driver: identical
`write_verilog` calls succeeded when the output path was under this repo's
tree and failed, every time, under `/tmp`). This driver therefore never
writes anywhere outside `flow/tmds_encoder/` under the repo root, which
works with both the WASM build and a native `apt`/`brew`-installed Yosys.
If a future script in this directory needs scratch space, keep it under the
repo tree (e.g. a git-ignored `flow/.work/`), not `/tmp`.

## CI

Full synthesis (this driver) is not run in CI, deliberately, for the same
reason `sim/`'s PVT sweep isn't (`.github/workflows/ci.yml`'s header
comment): it needs the multi-GB gf180mcu PDK, which should not gate every
PR. CI does run a PDK-free Yosys *elaboration* smoke check against
`rtl/tmds_encoder.v` (`hierarchy -check`, no cell mapping) in the
`tmds-encoder-verification` job -- see `verification/README.md`'s "Yosys
smoke check". This driver is intended to be run, and its evidence record
committed, by whoever (human or agent) has the PDK installed, the same
workflow `sim/`'s corner runner already follows. `sdf_tmds_encoder.py`,
`sta_tmds_encoder.py` and `gate_level_sim_tmds_encoder.py` are excluded from
CI for the same reason (the vendor cell-library Verilog models the last one
needs, and the five liberty corners the STA driver reads, also live under
the PDK install).

## Synthesized/custom boundary and what this flow does not answer yet

Per `spec/tmds-tx.md` DR-0003, `rtl/` (and this directory's synthesis
output) is the **synthesized** side of the synthesized/custom boundary: the
TMDS encoder and a first-stage 10:1->2:1 parallel-to-serial reduction target
`gf180mcu_fd_sc_mcu9t5v0` standard cells at the 3.3 V corner. Everything
past that 2:1 reduction -- the final multiplexer and the custom CML output
driver -- is hand-drawn analog/custom work under `design/` and `layout/`,
not this directory.

This directory currently synthesizes the encoder only (`rtl/tmds_encoder.v`
-- the 10:1->2:1 serializer is a deliberate follow-on, per `rtl/README.md`).
Synthesis (#82), place-and-route (#84) and SDF extraction / SDF-annotated
gate-level re-simulation (#85) each deliberately declined to make a
timing-closure claim, deferring it to a dedicated STA step. That step is
`sta_tmds_encoder.py` (issue #83), and it has landed -- so the honest
summary of what this flow now answers is:

- **Hold: PASS** at every 3.3 V corner, at both pixel-clock targets. Pre-CTS
  (no clock tree has been built yet), so it must be re-checked after CTS.
- **Setup: FAIL** at the 720p60 target (74.25 MHz) at four of five corners,
  and at the 480p fallback (27.000 MHz) at the slow/hot corner. The measured
  Fmax of the committed netlist is **22.70 MHz worst-corner** (45.88 MHz
  typical) -- see the STA evidence record for the full matrix.
- **DR-0003's flagged open item** (does the standard-cell library close at
  the 5x-pixel intermediate rate, 371.25 MHz?) now has a *measurement*
  against it rather than a deferral: not with this netlist, by more than an
  order of magnitude. That rate belongs to the not-yet-written serializer,
  not to this encoder.

The critical caveat, stated in the record and repeated here because it is
the whole reason those setup numbers look the way they do: **the netlist
under analysis was synthesized with no timing constraint at all** (#82 ran
an area-oriented mapping, every cell at drive strength 1, no `.sdc`). These
results characterize *that netlist*, not this library's ceiling for this
RTL. Timing-driven re-synthesis plus clock-tree synthesis has never been
attempted here and is the substantive follow-up -- deliberately out of
#83's evidence-gathering scope, and tracked as issue #100.
