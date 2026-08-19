# sim/harness — the PVT (and bit-rate) corner runner

Reproducible ngspice simulation against the gf180mcu PDK. This document
covers **how to run** the harness and **how to write a testbench**.

The *output* of a run — directory layout, record-id format, the summary
record field set, the corner-id grammar (including the bit-rate axis), and
the append-only rule — is defined by [`sim/README.md`](../README.md), not
here. That convention is authoritative; this harness exists to produce
records that conform to it.

```
sim/
  run_corners.py            CLI entry point (stdlib python3, no venv)
  check_records.py          evidence-record format checker (sim/README.md)
  env.sh                    `source sim/env.sh` to export the same PDK to your shell
  pdk.json                  committed PDK defaults (variant, extra search roots)
  harness/                  the runner itself (this directory)

  <experiment-slug>/        one per claim under test -- see sim/README.md
    testbench/               tb.json + netlist fragment      <- you write these
    netlist-snapshots/       frozen netlist per record        <- the harness writes these
    corners/<record-id>/     raw <corner-id>.log per PVT (x rate) point
    records/<record-id>.md   append-only summary record
  .work/                    generated ngspice decks (git-ignored, disposable)
```

This harness is ported from [`2AMLogic/gf180-bandgap`](https://github.com/2AMLogic/gf180-bandgap)
(`sim/harness/`). Its adaptation for this repo is the **bit-rate axis** (this
block's claims are transient/eye claims against two ratified operating
points, not a DC claim) — see "The bit-rate axis" and "Threshold-crossing
measurements" below. Everything else is unchanged.

## Quick start

```bash
python3 sim/run_corners.py --check-env     # is ngspice + the PDK present?
python3 sim/run_corners.py --list          # experiments, corners, corner sets
python3 sim/run_corners.py smoke-cml-pair  # run the full PVT x rate grid, mint a record
python3 sim/check_records.py               # check every record against sim/README.md
```

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| `ngspice` | simulation | `brew install ngspice` / `apt-get install ngspice` |
| gf180mcu PDK (`gf180mcuC`, DR-0010) | device models | `pip install volare && volare enable --pdk gf180mcu <hash>` |
| `xschem` | schematic capture (optional for simulation) | `brew install xschem` / distro package |
| python3 ≥ 3.9 | the harness | stdlib only, no packages |

The harness never hardcodes a PDK path. It resolves one, in order:

1. `GF180_PDK_PATH` — the *variant* directory, e.g. `~/.volare/gf180mcuC`
   (the one containing `libs.tech/`).
2. `PDK_ROOT` (+ `PDK`, default `gf180mcuC`) — the open_pdks / OpenLane convention.
3. `sim/pdk.local.json` — machine-local, git-ignored.
4. `sim/pdk.json` — committed default: `gf180mcuC` (see `sim/README.md`'s
   "PDK variant" section, and DR-0010, for why this variant).
5. Built-in search roots: `~/.volare`, `~/.ciel`, `/usr/share/pdk`,
   `/usr/local/share/pdk`, `~/share/pdk`, `/opt/pdk`.

If nothing is found the runner exits 3 with install instructions rather than
producing a misleading result. `sim/run_corners.py --print-env` emits the
resolved paths as shell exports; `source sim/env.sh` applies them so that an
interactive ngspice or xschem session uses the identical PDK.

## The PVT grid

`sim/README.md` requires PVT corners on every recorded result (the working
default matrix, pending issue #9's ratification — see `sim/README.md`). The
defaults are baked into `corners.py` and are what a testbench gets unless its
manifest says otherwise:

- **Temperature**: −40, 27, 125 °C
- **Voltage**: nominal ±10 % (3.3 V flavor → 2.97 / 3.3 / 3.63 V)
- **Process**: see below

gf180mcu has no single global corner switch — each device family carries its
own `.lib` section in `sm141064.ngspice`, so a named corner here is a bundle of
six sections (MOS, resistor, BJT, diode, MOS cap, MIM cap):

| Corner | Meaning |
|---|---|
| `tt` | everything typical |
| `ff` / `ss` | every device family fast / slow |
| `fs` / `sf` | fast-N/slow-P and slow-N/fast-P, passives typical |
| `res_ff` / `res_ss` | resistor sheet rho skewed, rest typical |
| `bjt_ff` / `bjt_ss` | BJT skewed, rest typical |

Corner sets: `tt` (1), `mos` (5, the default), `full` (9). `mos` × 3
temperatures × 3 supplies = 45 operating points for a DC/op-point testbench;
a transient testbench with two `rates_mbps` doubles that to 90.

Each point becomes one `<corner-id>` — `<process>_<temp>c_<supply>v[_<rate>]`,
the naming `sim/README.md` ratifies — and one raw log under
`corners/<record-id>/`.

Override any axis from the command line:

```bash
python3 sim/run_corners.py smoke-cml-pair --corner-set full -j 8
python3 sim/run_corners.py smoke-cml-pair --corners tt --temps -40 125
python3 sim/run_corners.py smoke-cml-pair --rates 742.5   # target rate only (needs --subset-reason or --no-write)
```

**Subsets need a reason.** `sim/README.md` requires every record's *Corner
matrix run* field to be the full mandated matrix "unless the record states why
a subset was used". The runner enforces that: if the grid you asked for is
missing a mandated temperature, a mandated supply, has fewer than three
process corners, or (for a testbench with a declared rate axis) is missing a
mandated rate, it refuses to write a record unless you supply
`--subset-reason '<why>'` (which is copied verbatim into the record), or pass
`--no-write` because you are only debugging.

```bash
# debugging: runs, records nothing
python3 sim/run_corners.py smoke-cml-pair --corners tt --temps 27 --rates 742.5 --no-write

# a deliberate, justified subset: runs and records, with the reason on the record
python3 sim/run_corners.py smoke-cml-pair --corners tt --temps 27 \
    --subset-reason "debugging the 742.5 Mbps edge only; not a full-matrix claim"
```

## The bit-rate axis

`spec/tmds-tx.md` §1 defines two operating points this repo's transient
claims are made against: **742.5 Mbps/lane** (720p60, target) and **270
Mbps/lane** (480p, fallback). A testbench opts into this axis by declaring
`rates_mbps` in its manifest (see "Writing a testbench" below); every point
in its PVT grid is then cross-produced with every declared rate
(`sim/harness/corners.py`'s `build_grid`), and `<corner-id>` carries a
trailing `<rate>` field (`742p5mbps`, `270mbps`). A testbench with no
`rates_mbps` behaves identically to the un-adapted gf180-bandgap harness —
this axis never applies unless a testbench asks for it.

A `rates_mbps` axis requires a paired `transient` block declaring the
solver settings actually used (`tstep_s`, `tstop_s`, and optionally
`tmax_s`/`reltol`/`abstol`/`vntol`/`pattern`) — see "Writing a testbench".
These land in the record's **Transient settings** field and, together with
**Operating point**, are enforced by `sim/check_records.py` on every
rate-bearing record (`sim/README.md`'s "Enforcement" section).

## Writing a testbench

Create `sim/<experiment-slug>/testbench/` with a manifest and a netlist
fragment. The slug is the experiment directory from `sim/README.md`: one per
distinct claim under test, kebab-case.

`tb.json` (DC/op-point testbench, unchanged from gf180-bandgap):

```json
{
  "name": "my-experiment",
  "description": "one line, shows up in --list and in the record",
  "claim": "spec/tmds-tx.md#dr-0002",
  "netlist": "my_tb.spice",
  "nominal_supply_v": 3.3,
  "supply_tolerance": 0.1,
  "temperatures_c": [-40, 27, 125],
  "corners": ["mos"],
  "analyses": ["op"],
  "params": {"iload": "10u"},
  "options": ["reltol=1e-5"],
  "measure": {"vref": "v(vref)"},
  "checks": {"vref": {"min": 1.15, "max": 1.25, "max_spread_pct": 2.0}}
}
```

A **transient testbench with a bit-rate axis** additionally declares
`rates_mbps` and `transient` (see `sim/smoke-cml-pair/testbench/tb.json` for
a complete worked example):

```json
{
  "rates_mbps": [742.5, 270.0],
  "transient": {
    "tstep_s": 2e-12,
    "tstop_s": 20e-9,
    "tmax_s": 2e-12,
    "reltol": 1e-6,
    "abstol": 1e-9,
    "vntol": 1e-6,
    "pattern": "worst-case-101010"
  },
  "analyses": ["tran 2e-12 20e-9 0 2e-12"]
}
```

`rates_mbps` and `transient` must be declared together — a rate axis with no
solver-settings provenance, or solver settings with no declared operating
point, are both load errors at manifest-load time
(`sim/harness/testbench.py`'s `validate_transient`), which also
cross-checks that `transient.tstep_s`/`tstop_s` actually match the `tran`
line in `analyses` (a drifted-apart pair is exactly the kind of mistake that
silently invalidates a "the eye is open" claim).

`claim` is the default for the record's **Claim** field — the ratified spec
line this experiment substantiates. `--claim` overrides it per run.

`dut` (optional) names a **device under test**: a second fragment holding
nothing but subcircuit definitions, `.include`d ahead of the testbench —
useful once a schematic-level or post-layout-extracted netlist exists to
swap in via `--dut`. No testbench in this repo uses it yet.

`subset_reason` (optional) pre-declares why this experiment's grid is a
deliberate subset of the mandated matrix — for a testbench that sweeps an
axis internally, say. `--subset-reason` still overrides it, and either way the
text is copied verbatim onto the record, which is where `sim/README.md` wants
the justification to live.

The netlist is a **fragment**, not a complete deck. It must not contain
`.include`, `.lib`, `.temp`, `.control`, `.endc` or `.end` — the harness owns
all of those, which is what lets one netlist sweep the whole grid unedited.
The loader rejects fragments that break this rule instead of silently pinning
every corner to 27 °C. The harness hands the fragment:

| Parameter | Value |
|---|---|
| `vdd_val` | supply for this PVT point |
| `vdd_nom` | nominal supply, for ratio measurements |
| `temp_c` | temperature for this PVT point (also applied via `.temp`) |
| `rate_val` | bit rate in Mbps/lane for this point *(only when `rates_mbps` is declared)* |

### Measurements: `let` expressions and threshold-crossing (`TRIG`) measurements

Each `measure` entry becomes, by default, `let m_<name> = <expr>` followed by
`print` inside the control block, so the expression must reduce to a
**scalar**: fine for `op`; for `tran`/`ac` reduce with `vecmax()`, `mean()`,
etc.

A `measure` entry whose value starts with `TRIG ` (case-insensitive) is
instead emitted as a raw ngspice `meas tran m_<name> <value>`
threshold-crossing measurement — the mechanism a rise/fall-time or
eye-opening measurement needs and a `let` vector expression cannot express:

```json
"measure": {
  "trise_10_90": "TRIG v(vdiff) VAL=-0.4 RISE=1 TARG v(vdiff) VAL=0.4 RISE=1"
}
```

ngspice's `v(a,b)` two-terminal differential-probe syntax parses inside
`print`/`let` but was found **not** to parse inside a `meas` `TRIG`/`TARG`
expression (confirmed against the installed ngspice-46 while developing
`sim/smoke-cml-pair`); the documented workaround is a 1× VCVS onto a real
node (`sim/smoke-cml-pair/testbench/smoke_cml_pair.spice`'s `edif`) so
`meas` has an actual differential vector to trigger on.

`checks` are evaluated after the sweep:

| Key | Applies to | Meaning |
|---|---|---|
| `min` / `max` | every point | hard limit; failure names the offending corner-id |
| `max_spread_pct` | the grid | `(max−min)/\|mean\|` must stay under the limit |
| `min_spread_pct` | the grid | must *exceed* it — asserts the sweep really moved |

`min_spread_pct` is a harness-integrity check: if `.temp` or a `.lib` section
silently failed to apply, a strongly PVT-sensitive measurement would come back
flat, and this catches that instead of reporting a suspiciously perfect result.

## What a run writes

One run mints one `<record-id>` (`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`) and
writes, under `sim/<experiment-slug>/`:

| Path | Contents |
|---|---|
| `records/<record-id>.md` | the append-only summary record (the fields from `sim/README.md`, plus an Environment section with PDK / ngspice / harness / git provenance and the per-corner model sections) |
| `netlist-snapshots/<record-id>.spice` | verbatim frozen copy of the testbench fragment, with its sha256 |
| `corners/<record-id>/<corner-id>.log` | raw ngspice output, one file per PVT (x rate) point |

Nothing is ever overwritten: the runner refuses to write over an existing
record or snapshot, and mints a later record-id if one is somehow already
taken. Corrections and re-runs get a new record-id and reference the prior one
with `--supersedes <record-id>`. Do not edit or delete anything under
`records/`, `netlist-snapshots/` or `corners/` — see the append-only rule in
`sim/README.md`.

A run taken against a dirty working tree says so in the record's **Netlist
provenance** field and is not citable as a clean-tree result.

Exit codes: `0` pass · `1` a check failed · `2` a simulation failed or did not
converge · `3` environment problem (no ngspice, no PDK, bad manifest,
unjustified PVT subset).

Generated decks land in `sim/.work/<experiment-slug>/<record-id>/` and are
git-ignored, so a failing corner can be reproduced by hand with
`ngspice -b sim/.work/<slug>/<record-id>/<corner-id>.spice`.

## sim/smoke-cml-pair

`sim/smoke-cml-pair/` is the harness's acceptance test for the transient/
bit-rate machinery, not a circuit deliverable and not a spec claim — see
`sim/README.md`'s "Worked example" section. Its testbench is a bare 3.3 V
NMOS differential pair with the DR-0002 load topology (10 mA tail, 50 Ω/leg
to the 3.3 V rail); its manifest sweeps both spec/tmds-tx.md operating
points (742.5 and 270 Mbps/lane) across the full PVT matrix (90 points) and
records differential swing, common-mode level, and 10-90 % rise/fall time.
