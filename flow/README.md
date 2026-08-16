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
- `tmds_encoder/` -- this module's synthesis and place-and-route outputs:
  ```
  tmds_encoder/
    netlist/tmds_encoder.synth.v   current gate-level netlist (regenerated
                                    in place by re-running the driver --
                                    not append-only, same as rtl/ source)
    pnr/tmds_encoder.def           routed DEF (pnr_tmds_encoder.py)
    reports/<record-id>.synth.ys   exact Yosys script run for that record
    reports/<record-id>.synth.log  full Yosys log for that record
    reports/<record-id>.pnr.tcl    exact OpenROAD script run for that P&R record
    reports/<record-id>.pnr.log    full OpenROAD log for that P&R record
    reports/<record-id>.gds_merge.log   DEF->GDS merge log for that P&R record
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
workflow `sim/`'s corner runner already follows.

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
Static timing analysis against the pixel-domain-derived rate (5x pixel
clock = 371.25 MHz @ 720p60, DR-0003's flagged open item) is explicitly
**out of scope for this synthesis step** -- a separate, sequenced issue
(#83) owns it, so that this driver's job stays "does the RTL map cleanly to
this library's cells," not "does it close timing." Place-and-route
(`pnr_tmds_encoder.py`, above) has since landed (issue #84) -- also without
a timing-closure claim, since #83 hasn't landed yet either (no clock-tree
synthesis is run; see that module's own "No CTS" docstring section).
