"""Tests for sim/compare_records.py -- no PDK, no ngspice required.

    python3 -m unittest discover -s sim/tests -v

The comparison a post-layout record owes its schematic-level baseline
(`sim/README.md`'s **Supersedes** convention) is computed, not transcribed,
so the thing computing it needs its own tests: a delta table that silently
mis-parses a record, or reports a delta against the wrong corner, is worse
than no table at all.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

import compare_records as cmp_mod  # noqa: E402

RECORD_TEMPLATE = """# Record {rid}

- **Record ID**: {rid}
- **Netlist provenance**: {provenance}
- **Result**:

  | corner-id | swing | vcm | pass/fail |
  |---|---|---|---|
{rows}

  Spread across the grid:

  | measurement | min | max | mean | spread % | limits |
  |---|---|---|---|---|---|
  | `swing` | 0.5 (`tt_27c_3.30v`) | 0.5 (`tt_27c_3.30v`) | 0.5 | 0 | — |
"""


def _record(path: Path, rid: str, provenance: str, rows: list[tuple]) -> Path:
    body = "\n".join(
        f"  | `{corner}` | {swing} | {vcm} | {verdict} |" for corner, swing, vcm, verdict in rows
    )
    path.write_text(RECORD_TEMPLATE.format(rid=rid, provenance=provenance, rows=body))
    return path


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_parses_measurements_corners_and_verdicts(self):
        path = _record(
            self.dir / "a.md",
            "20260101-000000-abcdef1",
            "schematic",
            [("tt_27c_3.30v", "0.5", "3.05", "PASS"), ("ss_125c_2.97v", "0.48", "3.06", "FAIL")],
        )
        names, values, verdicts = cmp_mod.parse_results(path)
        self.assertEqual(names, ["swing", "vcm"])
        self.assertEqual(sorted(values), ["ss_125c_2.97v", "tt_27c_3.30v"])
        self.assertAlmostEqual(values["tt_27c_3.30v"]["swing"], 0.5)
        self.assertEqual(verdicts["ss_125c_2.97v"], "FAIL")

    def test_spread_table_is_not_mistaken_for_results(self):
        path = _record(
            self.dir / "a.md",
            "20260101-000000-abcdef1",
            "schematic",
            [("tt_27c_3.30v", "0.5", "3.05", "PASS")],
        )
        _, values, _ = cmp_mod.parse_results(path)
        self.assertEqual(list(values), ["tt_27c_3.30v"])

    def test_record_without_a_result_table_is_an_error(self):
        path = self.dir / "empty.md"
        path.write_text("# Record\n\nno tables here\n")
        with self.assertRaises(cmp_mod.RecordError):
            cmp_mod.parse_results(path)

    def test_provenance_is_reported(self):
        path = _record(
            self.dir / "a.md",
            "20260101-000000-abcdef1",
            "extracted — DUT `layout/sim/x.spice`",
            [("tt_27c_3.30v", "0.5", "3.05", "PASS")],
        )
        self.assertEqual(cmp_mod.provenance(path), "extracted")


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.a = _record(
            self.dir / "a.md",
            "20260101-000000-abcdef1",
            "schematic",
            [
                ("tt_27c_3.30v", "0.500", "3.05", "PASS"),
                ("ss_125c_2.97v", "0.400", "3.06", "PASS"),
            ],
        )
        self.b = _record(
            self.dir / "b.md",
            "20260102-000000-abcdef2",
            "extracted",
            [
                ("tt_27c_3.30v", "0.510", "3.05", "PASS"),
                ("ss_125c_2.97v", "0.380", "3.06", "FAIL"),
            ],
        )

    def test_worst_absolute_delta_and_its_corner(self):
        rows, unmatched, verdicts = cmp_mod.compare(self.a, self.b)
        by_name = {row["measurement"]: row for row in rows}
        swing = by_name["swing"]
        self.assertEqual(swing["abs"]["corner"], "ss_125c_2.97v")
        self.assertAlmostEqual(swing["abs"]["delta"], -0.02, places=9)
        self.assertAlmostEqual(swing["abs"]["rel"], -5.0, places=6)
        self.assertEqual(unmatched, [])
        self.assertEqual(verdicts, ["ss_125c_2.97v: PASS -> FAIL"])

    def test_worst_relative_delta_can_differ_from_worst_absolute(self):
        rows, _, _ = cmp_mod.compare(self.a, self.b)
        swing = {row["measurement"]: row for row in rows}["swing"]
        self.assertEqual(swing["rel"]["corner"], "ss_125c_2.97v")
        self.assertAlmostEqual(swing["rel"]["rel"], -5.0, places=6)

    def test_identical_records_report_zero_delta(self):
        rows, _, verdicts = cmp_mod.compare(self.a, self.a)
        self.assertEqual(verdicts, [])
        for row in rows:
            self.assertEqual(row["abs"]["delta"], 0.0)

    def test_measurement_filter_rejects_unknown_names(self):
        with self.assertRaises(cmp_mod.RecordError):
            cmp_mod.compare(self.a, self.b, ["not_a_measurement"])

    def test_corner_present_in_only_one_record_is_reported(self):
        c = _record(
            self.dir / "c.md",
            "20260103-000000-abcdef3",
            "extracted",
            [
                ("tt_27c_3.30v", "0.500", "3.05", "PASS"),
                ("ff_-40c_3.63v", "0.520", "3.04", "PASS"),
            ],
        )
        _, unmatched, _ = cmp_mod.compare(self.a, c)
        self.assertEqual(unmatched, ["ss_125c_2.97v", "ff_-40c_3.63v"])

    def test_disjoint_records_are_an_error(self):
        d = _record(
            self.dir / "d.md",
            "20260104-000000-abcdef4",
            "extracted",
            [("ff_-40c_3.63v", "0.52", "3.04", "PASS")],
        )
        with self.assertRaises(cmp_mod.RecordError):
            cmp_mod.compare(self.a, d)

    def test_render_emits_one_row_per_measurement(self):
        rows, unmatched, verdicts = cmp_mod.compare(self.a, self.b)
        text = cmp_mod.render(
            rows, "demo", "a", "b", self.a, self.b, unmatched, verdicts
        )
        self.assertIn("| `swing` |", text)
        self.assertIn("| `vcm` |", text)
        self.assertIn("ss_125c_2.97v: PASS -> FAIL", text)


class RecordPathTests(unittest.TestCase):
    def test_malformed_record_id_is_rejected(self):
        with self.assertRaises(cmp_mod.RecordError):
            cmp_mod.record_path("cml-driver-eye", "not-a-record-id")

    def test_missing_record_is_reported(self):
        with self.assertRaises(cmp_mod.RecordError):
            cmp_mod.record_path("cml-driver-eye", "19700101-000000-0000000")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
