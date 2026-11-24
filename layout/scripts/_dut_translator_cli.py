"""CLI/IO and SPICE-card scaffolding shared by the extracted-netlist -> DUT
translators.

`gen_cml_driver_core_dut.py`, `gen_pad_ring_assembly_dut.py` and
`gen_tmds_final_mux_dut.py` differ only in their `translate()`; the argument
parsing, source-label derivation, stale-output check, write path, and the
`.SUBCKT` / `.ENDS` / MOS-card handling every `translate()` starts from live
here so a fix lands once.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Callable
from pathlib import Path


class TranslationError(RuntimeError):
    """The extracted netlist is not the shape the translator knows how to bind."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: `M<name> <d> <g> <s> <b> <class> <params...>` -- the card `bind_mos_card` rewrites.
_MOS_RE = re.compile(
    r"^M(?P<name>\S+)\s+"
    r"(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+(?P<b>\S+)\s+"
    r"(?P<cls>\S+)\s*(?P<params>.*)$"
)
_SUBCKT_RE = re.compile(r"^\.SUBCKT\s+(?P<name>\S+)\s+(?P<pins>.*)$", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\.ENDS\b", re.IGNORECASE)


def subckt_header(
    stripped: str, extracted_name: str, emitted_name: str | None = None
) -> tuple[list[str], str] | None:
    """Validate a `.SUBCKT` card; return `(pins, header_line)` for the one
    declaring `extracted_name` (`emitted_name` defaults to it --
    `gen_tmds_final_mux_dut.py` renames the extracted cell), else `None`.
    Any other name is a `TranslationError`: a translator handed the wrong
    extraction must fail loudly, not silently translate a foreign cell."""
    match = _SUBCKT_RE.match(stripped)
    if match is None:
        return None
    if match.group("name") != extracted_name:
        raise TranslationError(
            f"expected .SUBCKT {extracted_name}, found {match.group('name')!r}"
        )
    pins = match.group("pins").split()
    return pins, f".SUBCKT {emitted_name or extracted_name} {' '.join(pins)}"


def ends_card(stripped: str, emitted_name: str) -> str | None:
    """Return the `.ENDS` card closing `emitted_name`, if `stripped` is one."""
    if _ENDS_RE.match(stripped):
        return f".ENDS {emitted_name}"
    return None


def bind_mos_card(stripped: str, device_class: str, pdk_subckt: str) -> str | None:
    """Rewrite an extraction-deck `M`-card naming `device_class` as the
    `X`-subcircuit call against `pdk_subckt`, carrying every extracted
    parameter -- including the AS/AD/PS/PD junction geometry -- through
    unchanged; `None` for any non-MOS card. Any other class is a
    `TranslationError`, per each translator's own `DEVICE_CLASS` note."""
    mos = _MOS_RE.match(stripped)
    if mos is None:
        return None
    if mos.group("cls") != device_class:
        raise TranslationError(
            f"unknown device class {mos.group('cls')!r} on card {stripped!r}; "
            f"this script only binds {device_class!r} -> {pdk_subckt!r}"
        )
    params = mos.group("params").strip()
    return (
        f"XM{mos.group('name')} {mos.group('d')} {mos.group('g')} "
        f"{mos.group('s')} {mos.group('b')} {pdk_subckt}"
        + (f" {params}" if params else "")
    )


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
