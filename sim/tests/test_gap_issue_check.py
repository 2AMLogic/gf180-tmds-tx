"""Offline tests for ``signoff/check_gap_issues.py`` (issue #383).

    python3 -m unittest sim.tests.test_gap_issue_check -v

The closes_with liveness check's contract (#383): each gap's positive-
integer closer must be an open issue; explicit null makes no request;
closed / missing / malformed / PR references are reported with their row;
an unavailable API is a distinct, retryable outcome, never a verdict.
Every network touchpoint is faked or mocked -- no test reaches GitHub.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "signoff"))

import check_gap_issues as cgi  # noqa: E402

SPEC_PATH = REPO / "signoff" / "analog-spec.json"


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def open_issue(ref):
    return {"kind": "issue", "state": "open"}


class CheckTests(unittest.TestCase):
    def test_committed_map_with_open_closer_is_clean(self):
        calls = []

        def fetch(ref):
            calls.append(ref)
            return {"kind": "issue", "state": "open"}

        findings, unavailable = cgi.check(load_spec(), fetch)
        self.assertEqual(findings, [])
        self.assertIsNone(unavailable)
        # Row 10's 222 is the only non-null closer on the committed map;
        # the explicit-null rows (3, 11) must not produce requests.
        self.assertEqual(calls, [222])

    def test_explicit_null_makes_no_request(self):
        spec = {
            "rows": [
                {"id": "3", "gap": "no end-to-end route", "closes_with": None},
                {"id": "11", "gap": "pre-silicon", "closes_with": None},
            ]
        }
        fetch = mock.Mock()
        findings, unavailable = cgi.check(spec, fetch)
        self.assertEqual((findings, unavailable), ([], None))
        fetch.assert_not_called()

    def test_closed_issue_is_reported(self):
        spec = {"rows": [{"id": "10", "gap": "x", "closes_with": 222}]}
        findings, unavailable = cgi.check(
            spec, lambda ref: {"kind": "issue", "state": "closed"}
        )
        self.assertIsNone(unavailable)
        self.assertTrue(
            any("row 10" in p and "#222" in p and "closed" in p for p in findings),
            findings,
        )

    def test_pr_reference_is_reported(self):
        spec = {"rows": [{"id": "10", "gap": "x", "closes_with": 222}]}
        findings, _ = cgi.check(spec, lambda ref: {"kind": "pr", "state": "open"})
        self.assertTrue(
            any("row 10" in p and "pull request" in p for p in findings), findings
        )

    def test_missing_issue_is_reported(self):
        spec = {"rows": [{"id": "10", "gap": "x", "closes_with": 999999}]}
        findings, _ = cgi.check(spec, lambda ref: {"kind": "missing", "state": ""})
        self.assertTrue(
            any("row 10" in p and "999999" in p and "Not Found" in p for p in findings),
            findings,
        )

    def test_malformed_references_are_reported_without_any_request(self):
        fetch = mock.Mock()
        for bad in ("222", 0, -5, 1.5, True, [222]):
            with self.subTest(bad=bad):
                spec = {"rows": [{"id": "10", "gap": "x", "closes_with": bad}]}
                findings, unavailable = cgi.check(spec, fetch)
                self.assertIsNone(unavailable)
                self.assertTrue(
                    any(
                        "row 10" in p and "positive integer" in p
                        for p in findings
                    ),
                    findings,
                )
        fetch.assert_not_called()

    def test_gap_without_closes_with_is_reported(self):
        spec = {"rows": [{"id": "10", "gap": "x"}]}
        findings, _ = cgi.check(spec, open_issue)
        self.assertTrue(any("must carry closes_with" in p for p in findings))

    def test_closes_with_on_non_gap_row_is_reported(self):
        spec = {"rows": [{"id": "1", "evidence": [], "closes_with": 222}]}
        findings, _ = cgi.check(spec, open_issue)
        self.assertTrue(any("no gap disposition" in p for p in findings))

    def test_unavailable_api_is_distinct_and_retryable(self):
        spec = {"rows": [{"id": "10", "gap": "x", "closes_with": 222}]}

        def fetch(ref):
            raise cgi.ApiUnavailable("gh executable not found")

        findings, unavailable = cgi.check(spec, fetch)
        self.assertEqual(findings, [])
        self.assertIsNotNone(unavailable)
        self.assertIn("222", unavailable)

    def test_unavailable_api_stops_querying_later_rows(self):
        spec = {
            "rows": [
                {"id": "10", "gap": "x", "closes_with": 222},
                {"id": "12", "gap": "y", "closes_with": 333},
            ]
        }
        fetch = mock.Mock(side_effect=cgi.ApiUnavailable("network down"))
        findings, unavailable = cgi.check(spec, fetch)
        fetch.assert_called_once_with(222)
        self.assertEqual(findings, [])
        self.assertIsNotNone(unavailable)


class GhFetchTests(unittest.TestCase):
    """The ``gh api`` adapter, with subprocess faked -- no network."""

    @staticmethod
    def _run_result(returncode=0, stdout="", stderr=""):
        result = mock.Mock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_open_issue_payload(self):
        payload = json.dumps({"state": "open"})
        with mock.patch(
            "subprocess.run", return_value=self._run_result(stdout=payload)
        ):
            self.assertEqual(
                cgi.gh_fetch_issue("o/r", 222), {"kind": "issue", "state": "open"}
            )

    def test_pr_payload_is_a_pr(self):
        payload = json.dumps({"state": "open", "pull_request": {"url": "x"}})
        with mock.patch(
            "subprocess.run", return_value=self._run_result(stdout=payload)
        ):
            self.assertEqual(
                cgi.gh_fetch_issue("o/r", 222), {"kind": "pr", "state": "open"}
            )

    def test_not_found_is_missing_not_unavailable(self):
        with mock.patch(
            "subprocess.run",
            return_value=self._run_result(
                returncode=1, stderr="gh: Not Found (HTTP 404)"
            ),
        ):
            self.assertEqual(
                cgi.gh_fetch_issue("o/r", 222), {"kind": "missing", "state": ""}
            )

    def test_other_api_error_is_unavailable(self):
        with mock.patch(
            "subprocess.run",
            return_value=self._run_result(returncode=1, stderr="bad credentials"),
        ):
            with self.assertRaises(cgi.ApiUnavailable):
                cgi.gh_fetch_issue("o/r", 222)

    def test_missing_gh_binary_is_unavailable(self):
        with mock.patch(
            "subprocess.run", side_effect=FileNotFoundError("gh")
        ):
            with self.assertRaises(cgi.ApiUnavailable):
                cgi.gh_fetch_issue("o/r", 222)

    def test_unparseable_json_is_unavailable(self):
        with mock.patch(
            "subprocess.run", return_value=self._run_result(stdout="<html>")
        ):
            with self.assertRaises(cgi.ApiUnavailable):
                cgi.gh_fetch_issue("o/r", 222)


class MainTests(unittest.TestCase):
    def test_main_exit_codes(self):
        spec = str(SPEC_PATH)
        for fetch, expected in (
            (lambda _repo, ref: {"kind": "issue", "state": "open"}, 0),
            (lambda _repo, ref: {"kind": "issue", "state": "closed"}, 1),
            (cgi.ApiUnavailable("gh gone"), 2),
        ):
            with self.subTest(expected=expected):
                if isinstance(fetch, Exception):

                    def boom(*_args, _exc=fetch):
                        raise _exc

                    patched = boom
                else:
                    patched = fetch
                with mock.patch.object(cgi, "gh_fetch_issue", side_effect=patched):
                    with mock.patch.object(
                        cgi, "repo_from_origin", return_value="o/r"
                    ):
                        self.assertEqual(
                            cgi.main(["--spec", spec, "--repo", "o/r"]), expected
                        )


if __name__ == "__main__":
    unittest.main()
