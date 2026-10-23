"""CLI/IO scaffolding shared by the extracted-netlist -> DUT translators.

`gen_cml_driver_core_dut.py` and `gen_pad_ring_assembly_dut.py` differ only in
their `translate()`; the argument parsing, source-label derivation, stale-output
check and write path live here so a fix lands once.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Callable
from pathlib import Path


class TranslationError(RuntimeError):
    """The extracted netlist is not the shape the translator knows how to bind."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_cli(
    translate: Callable[[str, str, str], str],
    argv: list[str] | None,
    *,
    script: Path,
    repo_root: Path,
    doc: str,
    default_input: Path,
    default_output: Path,
    check_test: str,
) -> int:
    """Parse `argv`, translate the extracted netlist, then write or `--check` it.

    `script` is the calling translator (named in the stale-output regeneration
    hint); `check_test` is the test filename its `--check` help string cites.
    """
    parser = argparse.ArgumentParser(
        description=doc.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=default_input,
        help=f"extracted netlist to translate (default: {default_input})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_output,
        help=f"DUT fragment to write (default: {default_output})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the existing output differs from a fresh "
        f"regeneration (what sim/tests/{check_test} asserts)",
    )
    args = parser.parse_args(argv)

    source = args.input.resolve()
    try:
        label = str(source.relative_to(repo_root))
    except ValueError:
        label = source.name

    try:
        rendered = translate(source.read_text(), label, sha256(source))
    except TranslationError as exc:
        print(f"error: {source}: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not args.output.exists():
            print(f"error: {args.output} does not exist", file=sys.stderr)
            return 1
        if args.output.read_text() != rendered:
            print(
                f"error: {args.output} is stale -- regenerate it with\n"
                f"  python3 {script.relative_to(repo_root)}",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {args.output} matches a fresh regeneration")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0
