import json
import unittest
from collections import Counter

from review import HERE, effective_grants, evaluate, render


class AccessReviewTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))

    def decision(self, case, access):
        return next(row for row in evaluate(self.data) if (row["case"], row["access"]) == (case, access))

    def test_end_date_is_first_expired_day(self):
        row = self.decision("MOVE-101", "payout-export")
        self.assertEqual(row["status"], "review")
        self.assertIn("EX-018 expired on 2026-11-24", row["reason"])

    def test_last_covered_day_before_expiry(self):
        self.data["snapshot"] = "2026-11-23"
        self.assertEqual(self.decision("MOVE-101", "payout-export")["status"], "exception")

    def test_exception_is_active_on_start_and_scoped_to_case(self):
        self.assertEqual(self.decision("MOVE-102", "case-edit")["status"], "exception")
        self.data["exceptions"][1]["case"] = "MOVE-104"
        self.assertEqual(self.decision("MOVE-102", "case-edit")["status"], "review")

    def test_upcoming_exception_does_not_cover_today(self):
        self.data["exceptions"][1]["start"] = "2026-11-25"
        row = self.decision("MOVE-102", "case-edit")
        self.assertEqual(row["status"], "review")
        self.assertIn("starts on 2026-11-25", row["reason"])

    def test_nested_grant_has_evidence_path(self):
        row = self.decision("MOVE-101", "case-edit")
        self.assertEqual(row["path"], ("queue-east", "support-base", "case-workers"))

    def test_shorter_path_wins_and_cycles_finish(self):
        self.data["groups"]["case-workers"]["inherits"] = ["queue-east"]
        paths = effective_grants(self.data["groups"], ["case-workers", "queue-east"])
        self.assertEqual(paths["case-edit"], ("case-workers",))
        self.assertEqual(paths["billing-view"], ("queue-east", "support-base", "billing-readers"))

    def test_required_access_can_be_missing_despite_other_memberships(self):
        row = self.decision("MOVE-103", "staff-coach")
        self.assertEqual((row["status"], row["path"]), ("missing", ()))

    def test_optional_access_is_allowed_without_creating_missing_entries(self):
        values = {(r["case"], r["access"]): r["status"] for r in evaluate(self.data)}
        self.assertEqual(values["MOVE-104", "kb-publish"], "expected")
        self.assertNotIn(("MOVE-103", "kb-publish"), values)

    def test_unknown_group_is_rejected(self):
        self.data["groups"]["queue-east"]["inherits"] = ["absent"]
        with self.assertRaisesRegex(ValueError, "unknown names"):
            evaluate(self.data)

    def test_overlapping_exceptions_are_rejected(self):
        self.data["exceptions"].append(dict(self.data["exceptions"][0], reference="OTHER"))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            evaluate(self.data)

    def test_future_role_change_is_rejected(self):
        self.data["changes"][0]["effective"] = "2026-11-25"
        with self.assertRaisesRegex(ValueError, "future effective date"):
            evaluate(self.data)

    def test_sample_reconciles_and_output_escapes_input(self):
        self.data["changes"][0]["person"] = "<demo>"
        rows = evaluate(self.data)
        self.assertEqual(Counter(r["status"] for r in rows), {"review": 2, "missing": 1, "exception": 1, "expected": 13})
        html = render(self.data, rows)
        self.assertIn("&lt;demo&gt;", html)
        self.assertNotIn("<demo>", html)
        self.assertEqual(html.count("<tr data-state="), len(rows))


if __name__ == "__main__":
    unittest.main()
