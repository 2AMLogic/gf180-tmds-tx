# Captured regression: a defeated LVS negative control (issue #129)

These two files are a **real, captured `klt lvs` report pair**, not a
hand-written fixture. They are what the drifted gf180mcu extraction deck
reported for `gf180_tmds_pad_v2_shorted` — the deliberately-shorted negative
control whose whole job is to fail LVS — while klayout-tools#1196 was live:

```
status: match
mismatches: 3        (all three severity: warning)
  nets: layout=2  reference=2  matched=2
```

`status: match` on a cell whose drawn geometry still shorts `PAD` to `VSS`.

## Provenance (reproducible)

| | |
|---|---|
| Layout | `layout/gds/gf180_tmds_pad_v2_shorted.gds`, unmodified, as committed |
| Reference | `layout/lvs/gf180_tmds_pad_v2.ref.spice`, unmodified, as committed |
| Request | `layout/lvs/gf180_tmds_pad_v2.lvs_request_shorted.json`, unmodified |
| `klt` version | `0.2.0` |
| klayout-tools commit | `74a1bb0` (= `e5763f3~1`, the commit immediately before the upstream fix) |
| gf180mcu deck `content_hash` | `sha256:e2726af899d1837fe8c9a99688483f145b23c92ded07323f54d627d06bdb2bbf` |

Neither the GDS, the reference netlist, nor the request document differ in any
way from the committed, signed-off versions — the only variable is the deck.

Regenerate (from a `klayout-tools` clone, with `74a1bb0` extracted to
`$OLD_SRC`):

```bash
cd layout
PYTHONPATH="$OLD_SRC/src" python3 -c "
import sys
from klayout_tools.cli import main
sys.argv = ['klt', 'lvs', '--format', 'json',
            'lvs/gf180_tmds_pad_v2.lvs_request_shorted.json']
main()
"
```

## Root cause

At `74a1bb0` the deck bound `diode_nd2ps_06v0`'s anode to the deck's
synthesized `substrate_net` global (`vsubs`) with no way for this cell's
drawn `Pplus`/`Comp` substrate tap to join that same global — so the anode
resolved to `vsubs` instead of the cell's real, labeled `VSS`. In the shorted
cell that left two extracted nets (`PAD|VSS` and `vsubs`) against the
reference's two (`PAD`, `VSS`): a coincidental size match, so the comparer
reported `match` and the real short went unreported. Fixed upstream in
klayout-tools `e5763f3` (PR #1113, issue #1084), which derives the well/
substrate tap from the `Nplus`/`Pplus` implants and ties it into the same
global. Full write-up: `layout/README.md`, `gf180_tmds_pad_v2` section.

## What uses this

`layout/tests/test_check_lvs_signoff.py::RegressedFixtureTest` — the guard in
`layout/scripts/check_lvs_signoff.py` must reject this pair. Do not "fix" or
regenerate these files against a current `klt`: their value is that they are
the broken output.
