"""``signoff/digital-spec.json`` map tests (issue #383).

    python3 -m unittest sim.tests.test_digital_spec -v

The digital map feeds ``signoff/manifest.json``'s item-6.digital citation
(``not_applicable`` via ``signoff/item6-digital-na.json``) but until #383
had no guard at all. These tests pin the two committed digital artifacts
to each other and to the repository files the map cites: every row id is
nonempty and unique, the map's id set is exactly the statement's id set
(no third list to maintain -- the item-6 statement classifies those same
ids), and the leading repository file path of every row's ``source``
resolves, including citations carrying trailing section or DR prose.
No PDK, no ngspice, no network.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO / "signoff" / "digital-spec.json"
ITEM6_PATH = REPO / "signoff" / "item6-digital-na.json"


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def load_item6() -> dict:
    return json.loads(ITEM6_PATH.read_text(encoding="utf-8"))


def problems(spec: dict, item6: dict) -> list[str]:
    """Every way the digital map can rot. An empty list means it is sound."""
    out: list[str] = []
    rows = spec.get("rows", [])
    ids = [str(r.get("id", "")) for r in rows]
    for index, rid in enumerate(ids, 1):
        if not rid.strip():
            out.append(f"spec row #{index}: id must be a nonempty string")
    dupes = sorted({i for i in ids if i.strip() and ids.count(i) > 1})
    if dupes:
        out.append(f"duplicate row ids in the map: {dupes}")

    item6_ids = [str(r.get("id", "")) for r in item6.get("rows", [])]
    for index, rid in enumerate(item6_ids, 1):
        if not rid.strip():
            out.append(f"item6 row #{index}: id must be a nonempty string")
    item6_dupes = sorted(
        {i for i in item6_ids if i.strip() and item6_ids.count(i) > 1}
    )
    if item6_dupes:
        out.append(f"duplicate row ids in item6-digital-na.json: {item6_dupes}")

    missing = [i for i in item6_ids if i.strip() and i not in ids]
    if missing:
        out.append(
            f"ids classified by item6-digital-na.json but absent from the map: "
            f"{missing}"
        )
    extra = [i for i in ids if i.strip() and i not in item6_ids]
    if extra:
        out.append(
            f"map ids not classified by item6-digital-na.json: {extra}"
        )

    for index, row in enumerate(rows, 1):
        rid = str(row.get("id", "")) or f"#{index}"
        source = row.get("source")
        if not isinstance(source, str) or not source.strip():
            out.append(f"row {rid}: source citation must be a nonempty string")
            continue
        # The leading whitespace-separated token is the repository file
        # path; everything after it is section / DR prose ("section 1",
        # "DR-0003") and must not break path resolution.
        leading = source.split()[0].rstrip(",;:")
        if not (REPO / leading).is_file():
            out.append(
                f"row {rid}: source does not resolve to a repository file: "
                f"{leading!r} (from {source!r})"
            )
    return out


class DigitalSpecMapTests(unittest.TestCase):
    def test_committed_map_and_statement_are_sound(self):
        self.assertEqual(problems(load_spec(), load_item6()), [])

    def test_every_row_cites_a_real_leading_path_with_prose_allowed(self):
        # The committed sources are exactly this shape: a real repository
        # file, optionally followed by section or DR prose.
        spec = load_spec()
        sources = {str(r["id"]): r["source"] for r in spec["rows"]}
        self.assertEqual(sources["pixel-clock-720p60"], "spec/tmds-tx.md section 1")
        self.assertEqual(
            sources["serialization-10-bit-character"],
            "spec/tmds-tx.md section 1, DR-0003",
        )
        self.assertTrue(sources["dvi-mode-framing"].endswith(".md"))
        self.assertEqual(problems(spec, load_item6()), [])

    def test_negative_missing_id_is_reported(self):
        spec = load_spec()
        spec["rows"] = [r for r in spec["rows"] if r["id"] != "latency-four-clock"]
        self.assertTrue(
            any(
                "absent from the map" in p and "latency-four-clock" in p
                for p in problems(spec, load_item6())
            ),
            problems(spec, load_item6()),
        )

    def test_negative_extra_id_is_reported(self):
        spec = load_spec()
        spec["rows"].append(
            {"id": "made-up-row", "source": "spec/tmds-tx.md", "text": "x"}
        )
        self.assertTrue(
            any(
                "not classified" in p and "made-up-row" in p
                for p in problems(spec, load_item6())
            ),
            problems(spec, load_item6()),
        )

    def test_negative_duplicate_id_is_reported(self):
        spec = load_spec()
        spec["rows"].append(copy.deepcopy(spec["rows"][0]))
        self.assertTrue(
            any("duplicate" in p for p in problems(spec, load_item6())),
            problems(spec, load_item6()),
        )

    def test_negative_empty_id_is_reported(self):
        spec = load_spec()
        spec["rows"][0] = dict(spec["rows"][0], id="")
        self.assertTrue(
            any("nonempty" in p for p in problems(spec, load_item6())),
            problems(spec, load_item6()),
        )

    def test_negative_nonexistent_source_path_is_reported(self):
        spec = load_spec()
        spec["rows"][0] = dict(
            spec["rows"][0], source="spec/no-such-file.md section 1"
        )
        self.assertTrue(
            any(
                "row pixel-clock-720p60" in p and "no-such-file.md" in p
                for p in problems(spec, load_item6())
            ),
            problems(spec, load_item6()),
        )

    def test_negative_prose_alone_does_not_resolve(self):
        # A citation whose leading token is not a repository file path
        # (bare "DR-0003") must be reported, not silently skipped.
        spec = load_spec()
        spec["rows"][0] = dict(spec["rows"][0], source="DR-0003")
        self.assertTrue(
            any(
                "row pixel-clock-720p60" in p and "does not resolve" in p
                for p in problems(spec, load_item6())
            ),
            problems(spec, load_item6()),
        )

    def test_negative_item6_duplication_is_reported(self):
        item6 = load_item6()
        item6["rows"].append(copy.deepcopy(item6["rows"][0]))
        self.assertTrue(
            any("item6-digital-na.json" in p and "duplicate" in p for p in problems(load_spec(), item6)),
            problems(load_spec(), item6),
        )


if __name__ == "__main__":
    unittest.main()
