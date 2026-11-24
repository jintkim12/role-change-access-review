import json
import unittest
from copy import deepcopy

from graph_reconcile import translate_memberships
from review import HERE, evaluate


class MembershipReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
        self.fixture = json.loads((HERE / "graph-members.sample.json").read_text(encoding="utf-8"))
        self.pages = self.fixture["responses_by_group_id"]
        self.page = self.pages[self.fixture["group_ids"]["queue-east"]]

    def translate(self):
        return translate_memberships(self.policy, self.fixture)

    def test_all_direct_edges_and_review_rows_match(self):
        original = deepcopy(self.policy)
        imported = self.translate()
        for name, group in self.policy["groups"].items():
            self.assertCountEqual(group["inherits"], imported["groups"][name]["inherits"])
        for before, after in zip(self.policy["changes"], imported["changes"]):
            self.assertCountEqual(before["groups"], after["groups"])
        expected = evaluate(self.policy)
        self.assertEqual(len(expected), 17)
        self.assertEqual(evaluate(imported), expected)
        self.assertEqual(self.policy, original)

    def test_import_overwrites_source_edges_and_ignores_display_names(self):
        reference = evaluate(self.policy)
        for group in self.policy["groups"].values():
            group["inherits"] = []
        for case in self.policy["changes"]:
            case["groups"] = []
        for page in self.pages.values():
            for member in page["value"]:
                member["displayName"] = "Shared display name"
        self.assertEqual(evaluate(self.translate()), reference)

    def test_missing_page_or_id_mapping_fails(self):
        group_name = "writers"
        del self.pages[self.fixture["group_ids"][group_name]]
        with self.assertRaises(ValueError):
            self.translate()
        del self.fixture["group_ids"][group_name]
        with self.assertRaises(ValueError):
            self.translate()

    def test_next_page_or_incomplete_count_fails(self):
        for patch in [{"@odata.nextLink": "https://example.invalid/page-two"},
                      {"@odata.count": 1000}, {"@odata.count": None}]:
            with self.subTest(patch=patch):
                fixture = deepcopy(self.fixture)
                fixture["responses_by_group_id"][fixture["group_ids"]["queue-east"]].update(patch)
                with self.assertRaises(ValueError):
                    translate_memberships(self.policy, fixture)

    def test_unknown_id_type_mismatch_and_duplicate_member_fail(self):
        member = self.page["value"][0]
        for row in [dict(member, id="unmapped"), dict(member, **{"@odata.type": "#microsoft.graph.device"}),
                    dict(member, **{"@odata.type": "#microsoft.graph.group"}), member]:
            with self.subTest(row=row):
                self.page["value"].append(row)
                self.page["@odata.count"] += 1
                with self.assertRaises(ValueError):
                    self.translate()
                self.page["value"].pop()
                self.page["@odata.count"] -= 1

    def test_valid_membership_difference_changes_real_decision(self):
        page = self.pages[self.fixture["group_ids"]["billing-team"]]
        move101 = self.fixture["user_ids_by_case"]["MOVE-101"]
        page["value"] = [row for row in page["value"] if row["id"] != move101]
        page["@odata.count"] = len(page["value"])
        rows = evaluate(self.translate())
        self.assertFalse(any(r["case"] == "MOVE-101" and r["access"] == "payout-export" for r in rows))
        self.assertNotEqual(rows, evaluate(self.policy))


if __name__ == "__main__":
    unittest.main()
