"""``signoff/analog-spec.json`` DR-0013 row-map tests (issues #372, #383).

    python3 -m unittest sim.tests.test_analog_spec -v

The committed map from every DR-0013 section 3 spec row to the testbench
measure/check that grades it must not be able to rot: every row id appears
exactly once, every named testbench / measure / check exists in that
bench's ``tb.json``, rows 5 and 6 stay unratified, every row records a
disposition (graded evidence, a gap with its ``closes_with``, or DR-0013's
explicit N/A-by-design), and every row's ``target`` restates the *complete*
Target cell of its DR-0013 section 3 row (numbers, units, comparisons and
qualifiers alike -- presentation alone is normalized, #383). The DR rows
are parsed from the decision record itself, so a future DR-0013 edit that
adds, renumbers or re-words a row breaks this test until the map follows.
No PDK, ngspice or network.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO / "signoff" / "analog-spec.json"
DR_PATH = REPO / "spec" / "decisions" / "0013-operating-conditions.md"

# DR-0013 section 3's table is the only numeric-first-cell table in the
# record (the section 1 PVT matrix table's first cells are axis names).
_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|")

# Presentation-only normalization for the target comparison (#383): strip
# Markdown emphasis (bold / code spans) and collapse whitespace. Nothing
# else -- the map must use the source's own characters (en dashes, ~=,
# minus signs, section signs), so a changed bound or qualifier can never
# normalize away.
_EMPHASIS_RE = re.compile(r"\*\*|`")
_WS_RE = re.compile(r"\s+")


def normalize_target_text(text: str) -> str:
    return _WS_RE.sub(" ", _EMPHASIS_RE.sub("", text)).strip()


def dr0013_rows() -> list[tuple[str, str]]:
    """(row id, raw Target cell) per DR-0013 section 3 row, parsed once."""
    rows: list[tuple[str, str]] = []
    for line in DR_PATH.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line)
        if match:
            cells = line.split("|")
            rows.append((match.group(1), cells[3].strip()))
    return rows


def dr0013_row_ids() -> list[str]:
    return [rid for rid, _ in dr0013_rows()]


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def load_tb(bench: str) -> dict:
    return json.loads(
        (REPO / bench / "testbench" / "tb.json").read_text(encoding="utf-8")
    )


def problems(spec: dict) -> list[str]:
    """Every way the map can rot. An empty list means the map is sound."""
    out: list[str] = []
    rows = spec.get("rows", [])
    ids = [str(r.get("id")) for r in rows]
    dr_rows = dr0013_rows()
    dr_ids = [rid for rid, _ in dr_rows]
    dr_targets = {rid: normalize_target_text(cell) for rid, cell in dr_rows}
    for rid in dr_ids:
        n = ids.count(rid)
        if n != 1:
            out.append(
                f"DR-0013 row {rid}: appears {n}x in the map, expected exactly once"
            )
    extra = [i for i in ids if i not in dr_ids]
    if extra:
        out.append(f"row ids not present in DR-0013 section 3: {extra}")

    benches: dict[str, dict] = {}
    for row in rows:
        rid = str(row.get("id"))
        has_ev = bool(row.get("evidence"))
        has_gap = "gap" in row
        has_na = "na_by_design" in row
        if sum(1 for b in (has_ev, has_gap, has_na) if b) != 1:
            out.append(
                f"row {rid}: needs exactly one disposition "
                f"(evidence | gap | na_by_design)"
            )
        if has_gap and "closes_with" not in row:
            out.append(
                f"row {rid}: a declared gap must carry closes_with "
                f"(the open issue that would close it, or null)"
            )
        target = row.get("target")
        if not isinstance(target, str) or not normalize_target_text(target):
            out.append(
                f"row {rid}: target must restate DR-0013 section 3's Target cell"
            )
        elif rid in dr_targets and normalize_target_text(target) != dr_targets[rid]:
            out.append(
                f"row {rid}: target disagrees with DR-0013 section 3's Target cell "
                f"(map: {normalize_target_text(target)!r}; "
                f"DR-0013: {dr_targets[rid]!r})"
            )
        evidence = row.get("evidence", [])
        for entry in evidence:
            bench = str(entry.get("testbench", ""))
            if bench not in benches:
                try:
                    benches[bench] = load_tb(bench)
                except OSError:
                    out.append(f"row {rid}: no testbench at {bench}/testbench/tb.json")
                    benches[bench] = {}
            tb = benches[bench]
            for m in entry.get("measures", []):
                if m not in tb.get("measure", {}):
                    out.append(f"row {rid}: {bench} declares no measure {m!r}")
            checks = entry.get("checks", [])
            if not checks:
                out.append(
                    f"row {rid}: {bench} evidence names no check -- "
                    f"a measure alone does not grade a row"
                )
            for c in checks:
                if c not in tb.get("checks", {}):
                    out.append(f"row {rid}: {bench} declares no check {c!r}")
        primaries = [e for e in evidence if e.get("primary")]
        if len(evidence) > 1 and len(primaries) != 1:
            out.append(
                f"row {rid}: {len(primaries)} of {len(evidence)} benches marked "
                f"primary -- name exactly one"
            )

    for rid in ("5", "6"):
        row = next((r for r in rows if str(r.get("id")) == rid), None)
        if row is not None and row.get("ratified") is not False:
            out.append(
                f"row {rid}: DR-0013 marks this row Proposed; "
                f"ratified must be false in the map"
            )
    return out


class AnalogSpecMapTests(unittest.TestCase):
    def test_dr0013_parser_finds_eleven_rows(self):
        # Guards the parser itself: if DR-0013 is restructured so the
        # regex silently stops matching, the map test below would vacuously
        # pass on an empty id list.
        self.assertEqual(dr0013_row_ids(), [str(i) for i in range(1, 12)])

    def test_dr0013_parser_extracts_nonempty_target_cells(self):
        # Same guard for the Target column: an empty cell list would make
        # every target comparison below vacuous.
        for rid, cell in dr0013_rows():
            self.assertTrue(
                normalize_target_text(cell), f"row {rid}: empty Target cell"
            )

    def test_map_covers_every_row_and_every_name_exists(self):
        self.assertEqual(problems(load_spec()), [])

    def test_rows_5_and_6_carry_ratified_false(self):
        spec = load_spec()
        by_id = {str(r["id"]): r for r in spec["rows"]}
        self.assertIs(by_id["5"]["ratified"], False)
        self.assertIs(by_id["6"]["ratified"], False)

    def test_negative_missing_row_is_reported(self):
        spec = load_spec()
        spec["rows"] = [r for r in spec["rows"] if str(r["id"]) != "9"]
        self.assertTrue(
            any("row 9" in p and "exactly once" in p for p in problems(spec))
        )

    def test_negative_misspelled_check_is_reported(self):
        spec = load_spec()
        for row in spec["rows"]:
            if str(row["id"]) == "5":
                row["evidence"][0]["checks"][0] += "_typo"
        self.assertTrue(
            any("no check 'trise_ui_c0_typo'" in p for p in problems(spec))
        )

    def test_negative_misspelled_measure_is_reported(self):
        spec = load_spec()
        for row in spec["rows"]:
            if str(row["id"]) == "5":
                row["evidence"][0]["measures"][0] += "_typo"
        self.assertTrue(any("no measure" in p for p in problems(spec)))

    def test_negative_duplicated_row_is_reported(self):
        spec = load_spec()
        spec["rows"].append(copy.deepcopy(spec["rows"][0]))
        self.assertTrue(
            any("exactly once" in p for p in problems(spec)),
            problems(spec),
        )

    def test_negative_target_bound_mutation_is_reported(self):
        spec = load_spec()
        for row in spec["rows"]:
            if str(row["id"]) == "1":
                row["target"] = row["target"].replace("600", "900")
        self.assertTrue(
            any("row 1" in p and "target disagrees" in p for p in problems(spec)),
            problems(spec),
        )

    def test_negative_target_qualifier_removal_is_reported(self):
        # A condensed restatement that drops the simultaneous-eye
        # qualifier must fail, not silently pass as "close enough" -- the
        # failure mode #383 was filed against.
        spec = load_spec()
        for row in spec["rows"]:
            if str(row["id"]) == "6":
                row["target"] = row["target"].replace(
                    ", both measured simultaneously", ""
                )
        self.assertTrue(
            any("row 6" in p and "target disagrees" in p for p in problems(spec)),
            problems(spec),
        )

    def test_negative_dash_substitution_is_reported(self):
        # The map must use the source's characters: an ASCII hyphen where
        # DR-0013 writes an en dash is a (small but real) disagreement.
        spec = load_spec()
        for row in spec["rows"]:
            if str(row["id"]) == "1":
                row["target"] = row["target"].replace("–", "-")
        self.assertTrue(
            any("row 1" in p and "target disagrees" in p for p in problems(spec)),
            problems(spec),
        )

    def test_formatting_only_target_edit_still_passes(self):
        # Presentation alone is normalized: added Markdown emphasis and
        # extra whitespace must not trip the comparison.
        spec = load_spec()
        for row in spec["rows"]:
            if str(row["id"]) == "1":
                row["target"] = "**" + row["target"] + "**"
            if str(row["id"]) == "2":
                row["target"] = row["target"].replace(
                    "3.3 V", "3.3  V"
                )
        self.assertEqual(problems(spec), [])


if __name__ == "__main__":
    unittest.main()
