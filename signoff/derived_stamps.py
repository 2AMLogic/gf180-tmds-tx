#!/usr/bin/env python3
"""Toolchain-free freshness tripwire for T1 item 1's derived netlists.

T1 item 1 wants "the netlist derived from the sources, regenerated on design
change". The real regeneration checks (`klt netlist --check`, Yosys, OpenROAD)
need xschem, the gf180mcu PDK and the std-cell library, none of which belong
on the CI `signoff` job (see .github/workflows/ci.yml's header). This script is
the part CI *can* run: `signoff/derived-stamps.json` pins, for each derived
artifact, the sha256 of the artifact and of every source it was derived from.
`--check` fails when any of them has moved since the stamp was written, i.e.
when someone edited a source or a netlist without re-running the real
regeneration check and re-stamping.

It proves "nothing moved since the last regeneration check", not "this netlist
equals what the generator emits today". The second claim is only as strong as
the stamp's own `basis`:

- a row with `check_argv` is re-verified by `--refresh`: the real regeneration
  check runs first (non-zero exit aborts, and the stamp is left untouched);
- a row with `check_argv: null` cannot be regenerated on a host without its
  toolchain; `--refresh` refuses to re-stamp it unless `--include-unverified`
  is passed, and the row's `basis` says what its pin rests on instead.

    python3 signoff/derived_stamps.py --check                  # CI, stdlib only
    python3 signoff/derived_stamps.py --check --only ROW_ID    # one row (the attest inventories)
    python3 signoff/derived_stamps.py --refresh                # local, runs check_argv
    python3 signoff/derived_stamps.py --refresh --include-unverified
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STAMPS = Path(__file__).resolve().parent / "derived-stamps.json"


def sha256_file(rel: str) -> str:
    return "sha256:" + hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()


def load() -> dict:
    return json.loads(STAMPS.read_text())


def check(doc: dict, only: str | None) -> int:
    bad = 0
    rows = [r for r in doc["rows"] if only is None or r["id"] == only]
    if not rows:
        print(f"FAIL: no stamp row with id {only!r}")
        return 1
    for row in rows:
        for kind in ("sources", "derived"):
            for rel, pinned in row[kind].items():
                try:
                    now = sha256_file(rel)
                except OSError as exc:
                    print(f"FAIL [{row['id']}] {kind} {rel}: unreadable ({exc})")
                    bad += 1
                    continue
                if now != pinned:
                    print(f"FAIL [{row['id']}] {kind} {rel}: {now} != stamped {pinned}")
                    bad += 1
    if bad:
        print(
            f"{bad} stamped file(s) moved. Re-run each row's regeneration check, "
            "then `python3 signoff/derived_stamps.py --refresh` (see signoff/README.md)."
        )
        return 1
    print(f"derived-stamps fresh: {len(rows)} row(s), every source and derived hash matches.")
    return 0


def refresh(doc: dict, include_unverified: bool) -> int:
    for row in doc["rows"]:
        argv = row.get("check_argv")
        if argv:
            print(f"[{row['id']}] running {' '.join(argv)}")
            if subprocess.run(argv, cwd=REPO_ROOT, check=False).returncode != 0:
                print(f"FAIL [{row['id']}]: regeneration check failed; stamps not written", file=sys.stderr)
                return 1
        elif not include_unverified:
            print(f"[{row['id']}] has no regeneration check; pass --include-unverified to re-pin it", file=sys.stderr)
            return 1
        for kind in ("sources", "derived"):
            for rel in row[kind]:
                row[kind][rel] = sha256_file(rel)
    STAMPS.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {STAMPS.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify the stamps (default)")
    mode.add_argument("--refresh", action="store_true", help="re-run each row's check_argv, then re-pin")
    ap.add_argument("--only", metavar="ROW_ID", help="with --check: verify just this row")
    ap.add_argument("--include-unverified", action="store_true", help="with --refresh: also re-pin rows without a check_argv")
    args = ap.parse_args()
    doc = load()
    return refresh(doc, args.include_unverified) if args.refresh else check(doc, args.only)


if __name__ == "__main__":
    raise SystemExit(main())
