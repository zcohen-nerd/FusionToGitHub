"""The consolidated acceptance matrix (tests/acceptance): valid, rendered, and referenced IDs exist."""

import os
import re
import sys
import unittest

import _paths  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import acceptance  # noqa: E402

sys.path.remove(os.path.join(ROOT, "scripts"))


class AcceptanceMatrixTests(unittest.TestCase):
    def setUp(self):
        self.criteria = acceptance.read_csv(acceptance.CRITERIA)
        self.steps = acceptance.read_csv(acceptance.STEPS)
        self.ids = {row["id"] for row in self.criteria}

    def test_the_matrix_is_valid_and_its_renders_are_current(self):
        self.assertEqual(acceptance.problems(self.criteria, self.steps), [])
        self.assertEqual(acceptance.main(["check"]), 0)
        self.assertGreaterEqual(len(self.criteria), 100)

    def test_every_workflow_from_the_brief_has_criteria(self):
        covered = {row["workflow"] for row in self.criteria}
        self.assertEqual(covered, set(acceptance.WORKFLOWS))

    def test_nothing_simulated_is_recorded_as_passed_without_evidence(self):
        recorded = [row for row in self.criteria if row["status"] != "Not Run"]
        self.assertEqual([r["id"] for r in recorded if not r["evidence"]], [])
        for row in self.criteria:
            if row["status"] in ("Pass", "Fail"):
                self.assertTrue(row["evidence"], row["id"])

    def test_live_check_ids_cited_elsewhere_exist(self):
        cited = set()
        for rel in ("docs/RISK_REGISTER.md", "tests/fakes/README.md", "branding/README.md", "docs/RESTORE.md"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                for line in fh:
                    if re.search(r"live|checklist|check [A-Z]\d", line, re.IGNORECASE):
                        cited.update(re.findall(r"\b([ABCDFGHIJKLMNPRUVWX]\d{1,2})\b", line))
        missing = sorted(cited - self.ids)
        self.assertEqual(missing, [], "IDs cited as live checks but not in tests/acceptance/criteria.csv")

    def test_problems_are_reported(self):
        bad = dict(self.criteria[0], status="Done", id="")
        found = acceptance.problems([bad], self.steps)
        self.assertTrue(any("status must be" in p for p in found))
        self.assertTrue(any("missing or duplicate id" in p for p in found))


if __name__ == "__main__":
    unittest.main()
