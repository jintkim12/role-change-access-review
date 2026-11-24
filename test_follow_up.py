"""Verify effective access after the example remediation and exception expiry."""

import copy
import json
import unittest

from follow_up import follow_up
from review import HERE


class FollowUpTests(unittest.TestCase):
    def test_required_access_survives_and_expired_grant_reopens(self):
        source = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
        unchanged = copy.deepcopy(source)
        before, repaired, expired = (rows for _, rows in follow_up(source))
        self.assertEqual(source, unchanged)
        self.assertEqual(sum(r["status"] in ("review", "missing") for r in before), 3)
        self.assertFalse(any(r["status"] in ("review", "missing") for r in repaired))
        self.assertTrue(any(r["case"] == "MOVE-103" and r["access"] == "staff-coach"
                            and r["status"] == "expected" for r in repaired))
        reopened = [(r["case"], r["access"]) for r in expired if r["status"] == "review"]
        self.assertEqual(reopened, [("MOVE-102", "case-edit")])
