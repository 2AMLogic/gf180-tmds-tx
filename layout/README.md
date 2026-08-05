# layout

GDS, DRC/LVS reports, and the pad cell — per the repo README's layout table.

## `pad_min/` — minimal custom pad cell (issue #2)

A first-cut, deliberately trivial custom I/O pad cell (bond-pad-equivalent
Metal2-Metal5 stack + a substrate/well tap guard ring), DRC-clean against
`klt drc --deck gf180mcu`. LVS is attempted but not achieved — blocked by a
filed `klt extract`/`klt lvs` gap (deviceless circuits are purged to
nothing), not by anything left undone here. Full writeup, citations, and
what remains: [`spec/pad-ring-esd.md`](../spec/pad-ring-esd.md).

- `build_pad_min.py` — the (re)build script (drives `klt gen guard_ring` +
  `klayout.db` directly).
- `gf180_tmds_pad_min.gds` — the pad cell.
- `gen_guard_ring_report.json` — the `klt gen guard_ring` invocation's own
  structured report.
- `drc_report.json` — `klt drc --deck gf180mcu` result: clean, 0 violations.
- `extract_report.json`, `gf180_tmds_pad_min.spice` — `klt extract` result:
  empty (0 devices/nets/pins) — see spec doc Sec. 6 for why.
- `reference.spice`, `lvs_request.json`, `lvs_report.json` — the `klt lvs`
  attempt against a hand-written golden netlist, and its (expected, given
  the empty extraction) clean structured failure.
