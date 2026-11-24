"""Replay proposed group edits and the subsequent exception expiry in memory."""

import copy
import json
from collections import Counter

from review import HERE, evaluate


def follow_up(original):
    scenario = copy.deepcopy(original)
    cases = {change["case"]: change for change in scenario["changes"]}
    cases["MOVE-101"]["groups"].remove("billing-team")
    cases["MOVE-103"]["groups"].remove("refund-crew")
    cases["MOVE-103"]["groups"].append("lead-desk")
    scenario["snapshot"] = "2026-11-25"
    after_changes = evaluate(scenario)
    scenario["snapshot"] = "2026-12-01"
    after_expiry = evaluate(scenario)
    return [(original["snapshot"], evaluate(original)),
            ("2026-11-25", after_changes), ("2026-12-01", after_expiry)]


if __name__ == "__main__":
    original = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
    for day, decisions in follow_up(original):
        counts = Counter(row["status"] for row in decisions)
        print(f"{day} | excess {counts['review']} | missing {counts['missing']} | "
              f"active exception {counts['exception']} | within policy {counts['expected']}")
        for row in decisions:
            if row["status"] == "review":
                print(f"  Review {row['case']} / {row['access']} via {' > '.join(row['path'])}")
