#!/usr/bin/env python3
"""Write the post-place-and-route gate-level netlist from the committed routed DEF.

    python3 flow/gen_pnr_netlist.py
    python3 flow/gen_pnr_netlist.py -o /tmp/tmds_encoder.pnr.v

Reads `flow/tmds_encoder/pnr/tmds_encoder.def` (the committed routed DEF that
`flow/pnr_tmds_encoder.py` produced and that `layout/gds/tmds_encoder.gds` was
streamed from) plus the standard-cell LEFs, and writes
`flow/tmds_encoder/netlist/tmds_encoder.pnr.v` via OpenROAD's `write_verilog`.

Why this is a separate script from `flow/pnr_tmds_encoder.py`
------------------------------------------------------------
`pnr_tmds_encoder.py` already writes this netlist -- but into `flow/build/`,
which is not committed, as a by-product of a **full P&R run** (floorplan,
placement, CTS, setup/hold repair, global+detailed route: minutes of work, and
a run that rewrites the routed DEF and re-streams the GDS).

The LVS reference netlist (`layout/scripts/gen_tmds_encoder_ref.py --from-pnr`)
needs the post-P&R netlist as an *input*, so regenerating it must not require
re-running P&R. Re-running P&R to obtain it would also make the LVS reference
depend on P&R reproducing bit-identically -- which it does
(`layout/README.md`'s cold-start audit diffs the routed DEF directly), but
depending on it here would be gratuitous: the DEF is committed, and the DEF is
the thing the GDS was made from.

So this script does the cheap, purely-derivational half: read the committed
DEF, write the netlist it implies. It performs **no** placement, routing,
optimization or timing work, and it writes nothing except its output netlist.
That also makes the resulting netlist provably the same design the committed
GDS is, since both derive from the same committed DEF -- which is exactly the
property LVS needs.

Relationship to `tmds_encoder.synth.v`
--------------------------------------
`flow/tmds_encoder/netlist/tmds_encoder.synth.v` (issue #82/#115) is the
**pre**-P&R synthesized netlist. It does not contain the CTS clock buffers,
hold-repair delay cells, setup-repair resized gates, tap/endcap or fill cells
that P&R inserts, so it cannot be the LVS reference for a routed layout that
does contain them. It remains the input to P&R and the reference for the
synthesis-stage evidence records; it is not superseded by this netlist, and
the two answer different questions. See `layout/README.md`'s `tmds_encoder`
section for which question each LVS run actually settles.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "flow"))

from sim.harness.pdk import PdkNotFound, find_pdk  # noqa: E402
import pnr_tmds_encoder as pnr  # noqa: E402

TOP = "tmds_encoder"
DEF_PATH = REPO_ROOT / "flow" / "tmds_encoder" / "pnr" / f"{TOP}.def"
DEFAULT_OUT = REPO_ROOT / "flow" / "tmds_encoder" / "netlist" / f"{TOP}.pnr.v"


def build_tcl(tech_lef: Path, sc_lef: Path, def_path: Path, out: Path) -> str:
    return (
        f"read_lef {tech_lef}\n"
        f"read_lef {sc_lef}\n"
        f"read_def {def_path}\n"
        f"write_verilog {out}\n"
        "exit\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not DEF_PATH.is_file():
        print(f"ERROR: routed DEF not found: {DEF_PATH}", file=sys.stderr)
        return 1
    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    tech_lef, sc_lef, *_ = pnr.lef_paths(pdk)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # OpenROAD resolves the script path itself; keep it beside the output so a
    # sandboxed run does not depend on a writable shared temp directory.
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        script = Path(tmp) / "def2v.tcl"
        script.write_text(
            build_tcl(tech_lef, sc_lef, DEF_PATH.resolve(), args.output.resolve())
        )
        proc = subprocess.run(
            ["openroad", "-no_init", "-exit", str(script)],
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        print(f"ERROR: openroad exited {proc.returncode}", file=sys.stderr)
        return proc.returncode

    text = args.output.read_text()
    instances = sum(1 for line in text.splitlines() if "gf180mcu_fd_sc_mcu9t5v0__" in line)
    print(
        f"OK: PDK {pdk.variant} ({pdk.version}); read {DEF_PATH.name}; "
        f"{instances} cell instances -- wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
