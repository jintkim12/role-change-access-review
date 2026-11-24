"""Reconcile a closed set of local Graph-shaped membership responses with a role review."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from review import HERE, evaluate


def id_index(mapping, expected_names):
    if not isinstance(mapping, dict) or set(mapping) != expected_names:
        raise ValueError("The ID map must cover each policy group or review case exactly once.")
    if any(not isinstance(value, str) or not value.strip() for value in mapping.values()):
        raise ValueError("Every mapped object needs a nonempty ID.")
    index = {object_id: name for name, object_id in mapping.items()}
    if len(index) != len(mapping):
        raise ValueError("An object ID was mapped more than once.")
    return index


def translate_memberships(policy, fixture):
    if fixture["snapshot"] != policy["snapshot"]:
        raise ValueError("Membership and policy snapshots have different dates.")
    result = deepcopy(policy)
    changes = {row["case"]: row for row in result["changes"]}
    groups = result["groups"]
    group_ids = id_index(fixture["group_ids"], set(groups))
    user_ids = id_index(fixture["user_ids_by_case"], set(changes))
    if group_ids.keys() & user_ids.keys():
        raise ValueError("An object ID is mapped to both a user and a group.")
    pages = fixture["responses_by_group_id"]
    if not isinstance(pages, dict) or pages.keys() != group_ids.keys():
        raise ValueError("Provide one complete member response for every mapped security group.")
    for group in groups.values():
        group["inherits"] = []
    for change in changes.values():
        change["groups"] = []
    for group_id, page in pages.items():
        name = group_ids[group_id]
        if not isinstance(page, dict) or "@odata.nextLink" in page:
            raise ValueError(f"{name} requires a complete single-page response.")
        members, count = page.get("value"), page.get("@odata.count")
        if not isinstance(members, list) or type(count) is not int or count != len(members):
            raise ValueError(f"{name} count and supplied member rows do not agree.")
        seen = set()
        for member in members:
            if not isinstance(member, dict) or not isinstance(member.get("id"), str):
                raise ValueError(f"{name} has a member without an object ID.")
            member_id = member["id"]
            if member_id in seen:
                raise ValueError(f"{name} lists the same member twice.")
            seen.add(member_id)
            kind = member.get("@odata.type")
            if kind == "#microsoft.graph.user" and member_id in user_ids:
                changes[user_ids[member_id]]["groups"].append(name)
            elif kind == "#microsoft.graph.group" and member_id in group_ids:
                # A nested group inherits from the group whose direct member it is.
                groups[group_ids[member_id]]["inherits"].append(name)
            else:
                raise ValueError(f"{name} has an unknown ID or unsupported member type.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=HERE / "sample.json")
    parser.add_argument("--members", type=Path, default=HERE / "graph-members.sample.json")
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        fixture = json.loads(args.members.read_text(encoding="utf-8"))
        actual = evaluate(translate_memberships(policy, fixture))
        expected = evaluate(policy)
        if actual != expected:
            raise ValueError("Imported memberships produce different decisions or granting paths.")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(2, f"Reconciliation unavailable: {exc}\n")
    print(f"{len(fixture['group_ids'])} groups, {len(fixture['user_ids_by_case'])} users, "
          f"{len(actual)} review rows matched, including granting paths and reasons.")


if __name__ == "__main__":
    main()
