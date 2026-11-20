# `sim/pex/` — `klt pex`-shaped testbench requests for the pad-ring assembly

The schematic-vs-extracted (PEX) delta evidence for T1 item 7 (analog) is a
`klt pex` report, and #230 owns producing and citing it. This directory holds
the two halves of that evidence #230 needs that do **not** require a
multi-corner fleet run (issue #371, the same split #312 made for #222):

1. **`gf180_tmds_pad_ring_assembly.spice`** — the simulatable *schematic* DUT:
   the LVS-signed-off assembly connectivity (`layout/lvs/…ref.spice`)
   instantiated with the sized, PDK-bound devices from the eye bench's own DUT
   (`nfet_03v3` MOS + both ESD clamp polarities), behind the verified
   seven-pin declaration. It is the single `.include` of every request body
   below (the leg `klt pex` swaps) and the `--reference-netlist` of the
   committed extract-only report
   (`layout/pex_reports/gf180_tmds_pad_ring_assembly.pex_extract.json`).
2. **`requests/`** — committed `klt sim` request JSONs (one per bench ×
   supply × rate) plus their SPICE bodies under `requests/bodies/`, all
   **generated** by `gen_requests.py` from the existing bench definitions —
   never hand-edited:

   ```sh
   python3 sim/pex/gen_requests.py          # regenerate requests + bodies
   python3 sim/pex/gen_requests.py --check  # offline freshness check (npm run lint)
   ```

Each request runs the full mandated PVT matrix *inside* the request (5 process
corners × 3 temperatures = 15 units; supply ±10 % and the two rates are baked
into the body as `.param`s, one request per point, because the benches' PWL
stimuli expand `{tbit_s}`-style expressions at deck-parse time). Each body
carries exactly one `.include` (the schematic DUT — `klt pex`'s swap point),
the shared six-pin `cml_driver` wrapper wiring the assembly positionally in
its declared seven-pin order, and the bench's netlist fragment inlined
verbatim. The request sets `models.pdk`/`models.lib`/`models.param_file`,
`options.ngspice_init` (`set wnflag=1` — the PDK's models bin on per-finger
width; without it the batch fleet's ngspice dies with "could not find a valid
modelname" — and `set num_threads=1`), and `batch.capacity_wait_s` per the
host rule.

## The reltol override (read before comparing numbers to harness records)

The bodies deliberately carry `.options reltol=1e-3` (ngspice's own default)
instead of the benches' `1e-6`: with `1e-6`, every Linux ngspice build tested
(42 apt, and 47 from two independent builds — this host's and the batch
fleet's) collapses the transient at the bench's FIRST stimulus edge
(t = 9·tbit_s, "timestep too small" on an ideal-source branch of one of the
static DC copies) as soon as the DUT is the assembly; `1e-4` and `1e-5`
collapse too, `1e-3` completes on 42 and 47. The original flat six-pin DUT
converges at `1e-6` on the same builds, and macOS builds converged even the
extracted assembly at `1e-6` (the 2026-09-05 eye records). Both pex legs share
the body byte-identically, so the schematic-vs-extracted *delta* — the thing
`klt pex` grades — is unaffected; absolute values stay close
(swing_c0 = 0.5065 V at `1e-3` vs 0.5066 V at `1e-6`, flat DUT). The
harness's `1e-6` records remain the authoritative absolute evidence.

## Row-8 device-stress probes through the wrapper

Three of the bench's five stress measures read `xvhi.tail`, which does not
exist once the DUT is the assembly: the eye bench's `xvhi` instance is the
shared `cml_driver` wrapper, and the tail node lives one level deeper, inside
the wrapper's `xcore` instance. The generator rewrites the node in those
expressions (`xvhi.tail` → `xvhi.xcore.tail`); `vgs_tail_max` (which reads the
`ib_vhi` node) and `vgd_sw_max` need no rewrite. On the schematic leg all
five resolve (validated below). On the extracted leg the seven-pin extraction
keeps a plain `TAIL` star-hub net inside the assembly (`RTAIL_t<n> TAIL__t<n>
TAIL`), so `xvhi.xcore.tail` exists on both legs — verified against the
committed extract-only report's netlist.

## Validation (issue #371 step 4)

- **All 12 requests pass `klt pex … --dry-run`** (structure, one-include
  rule, pin-order preflight, unit/job split; run 2026-11-20, klt
  `0.9.3.dev2575+g6bd18bbc8637`).
- **One single-unit schematic-leg `klt sim` run executed** at the named
  validation point `tt / 27 °C / 3.30 V / 742.5 Mbps`
  (`cml-driver-eye_3.3v_742.5mbps` restricted to one corner, `backend:
  local`, ngspice 47, the request's own `ngspice_init`): status **pass**, all
  **46 measurements finite**. Representative values: `ui_ref` = 1.3468 ns
  (exactly 1 UI), `dj_ui_c0…cmis` = 1.05e-7 … 1.12e-3 UI (the row-4 PARAM
  chain over the raw TRIG/TARG card results works), `swing_c0` = 0.5065 V,
  `vcm_c0` = 3.047 V, row-8 probes `vgs_sw_max` 1.546 V / `vgd_sw_max`
  1.815 V / `vds_sw_max` 2.416 V / `vgs_tail_max` 1.130 V / `vds_tail_max`
  1.346 V, `icell_dc` = 10.59 mA.

## DR-0013 row coverage (this table is PEX-specific; #372 owns the canonical row-to-measure map and row-5 grading)

| DR-0013 row | In these requests? | Measurements |
|---|---|---|
| 1 — single-ended swing | `cml-driver-eye_*` | `swing_c0/c1/c2/cmis`, `swing_avcclo/avcchi` |
| 2 — common mode | `cml-driver-eye_*` | `vcm_c0/c1/c2`, `vcm_avcclo/avcchi` |
| 3 — total TMDS jitter | out of scope here | system-level (needs the PLL side); this block's contribution is row 4 |
| 4 — this block's jitter contribution | `cml-driver-eye_*` | `dj_ui_c0/c1/c2/cmis` — raw `ui_ref`/`spa_*`/`spb_*` TRIG/TARG cards emitted first, then one `.meas … PARAM='…'` per load reading those named results (the fixture-verified dependency pattern) |
| 5 — 10–90 % rise/fall | `cml-driver-eye_*` | `trise_c0…cmis`, `tfall_c0…cmis` (grading: #372) |
| 6 — passing-eye criterion | `cml-driver-eye-mask_*` | per load: 8 `height_<load>_<bin>` expressions, then `eyeh_max_<load>`, then `eyemask_margin_<load>` — ordered `expr` results resolved by name, dependencies preserved from the bench manifest |
| 7 — output impedance / return loss | N/A by design | DR-0013 records the row N/A (current-mode open-drain); `ro_leg` is still carried by the eye requests as an informative measurement |
| 8 — device voltage stress | `cml-driver-eye_*` | `vgs_sw_max`, `vgd_sw_max`, `vds_sw_max`, `vgs_tail_max`, `vds_tail_max`; the three tail-node probes rewritten through the wrapper (see above), all five resolve on both legs |
| 9 — tail current | `cml-driver-eye_*` | `itail_dc`, `icell_dc`, `ioff_dc` |
| 10 — pad capacitance budget | out of scope here | the pad/C–V work (`sim/esd-*-cv`) owns it |
| 11 — ESD HBM/CDM | out of scope here | DR-0015: accepted pre-silicon limitation |

No row needed `--measure-command` (every in-scope row is expressed by the
generated measurement set above), so no tooling gap was filed for row
coverage. The one tool-behaviour finding of this issue — the Linux-ngspice
`reltol` collapse documented above — is an ngspice-build numerics fact, not a
`klt` gap, and is worked around in the bodies rather than filed upstream.

## What #230 runs (step 8 of the issue)

```sh
klt pex layout/gds/gf180_tmds_pad_ring_assembly.gds \
  sim/pex/requests/cml-driver-eye_*.json sim/pex/requests/cml-driver-eye-mask_*.json \
  --deck gf180mcu --pdk gf180mcuD --top gf180_tmds_pad_ring_assembly \
  --pins IBIAS,INN,INP,OUTN,OUTP,VDD,VSS --wait-for-capacity 600
```

Each request's own `--pins`-matching DUT include is the swap point; the
extracted leg re-points only that one line. The extract-only structural
preflight of the same layout/pins/reference combination is already committed
as `layout/pex_reports/gf180_tmds_pad_ring_assembly.pex_extract.json`
(content hash `sha256:136ec1a3…` = the manifest's GDS citation;
`body_bias.status: biased`, 0 unbiased device bodies; headers identical —
see `layout/README.md`).
