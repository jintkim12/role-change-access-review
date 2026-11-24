"""Review effective access after a recorded job change using an offline snapshot."""

import argparse
import json
from collections import Counter, defaultdict, deque
from datetime import date, timedelta
from html import escape
from pathlib import Path
from string import Template


HERE = Path(__file__).resolve().parent
STATUS = {
    "review": "Review access",
    "missing": "Missing access",
    "exception": "Active exception",
    "expected": "Within policy",
}


def check_names(values, catalog, location):
    if not isinstance(values, list) or not all(isinstance(name, str) for name in values):
        raise ValueError(f"{location} must be a list of names")
    unknown = set(values) - catalog.keys()
    if unknown:
        raise ValueError(f"{location} references unknown names: {', '.join(sorted(unknown))}")
    if len(set(values)) != len(values):
        raise ValueError(f"{location} contains duplicate names")


def validate(source):
    snapshot = date.fromisoformat(source["snapshot"])
    roles, groups, access = (source[key] for key in ("roles", "groups", "entitlements"))
    for role, policy in roles.items():
        for category in ("required", "optional"):
            check_names(policy[category], access, f"{role} {category}")
        if set(policy["required"]) & set(policy["optional"]):
            raise ValueError(f"{role} repeats access across required and optional")
    for group, spec in groups.items():
        check_names(spec["inherits"], groups, f"{group} inheritance")
        check_names(spec["grants"], access, f"{group} grants")
    cases = {}
    for change in source["changes"]:
        case = change["case"]
        if case in cases:
            raise ValueError(f"Duplicate change case {case}")
        if date.fromisoformat(change["effective"]) > snapshot:
            raise ValueError(f"{case} has a future effective date")
        if change["from"] not in roles or change["to"] not in roles:
            raise ValueError(f"{case} references an unknown role")
        check_names(change["groups"], groups, f"{case} direct groups")
        cases[case] = change
    histories = defaultdict(list)
    for exc in source["exceptions"]:
        if exc["case"] not in cases or exc["access"] not in access:
            raise ValueError("Exception references an unknown change or entitlement")
        start = date.fromisoformat(exc["start"])
        end = date.fromisoformat(exc["end_exclusive"])
        if start >= end:
            raise ValueError(f"{exc['reference']} has an empty or reversed date window")
        key = (exc["case"], exc["access"])
        if any(start < prev_end and prev_start < end for prev_start, prev_end, _ in histories[key]):
            raise ValueError(f"Overlapping exceptions for {key[0]} / {key[1]}")
        histories[key].append((start, end, exc))
    return snapshot, histories


def effective_grants(groups, starting_groups):
    """Return one deterministic shortest membership path for each effective grant."""
    queue = deque((name,) for name in sorted(starting_groups))
    visited = set(starting_groups)
    paths = {}
    while queue:
        path = queue.popleft()
        spec = groups[path[-1]]
        for access in spec["grants"]:
            paths.setdefault(access, path)
        for parent in sorted(spec["inherits"]):
            if parent not in visited:
                visited.add(parent)
                queue.append((*path, parent))
    return paths


def classify_extra(history, snapshot, was_expected):
    reason = (
        "Allowed by the former role. The new role does not allow this access."
        if was_expected else "Outside both the former and current role policies."
    )
    for start, end, exc in history:
        if start <= snapshot < end:
            return "exception", (
                f"{exc['reference']} · {exc['owner']}. {exc['purpose']} "
                f"Valid {start.isoformat()} through {(end - timedelta(days=1)).isoformat()}."
            )
    previous = [(end, exc) for start, end, exc in history if end <= snapshot]
    upcoming = [(start, exc) for start, end, exc in history if start > snapshot]
    if previous:
        end, exc = max(previous, key=lambda item: item[0])
        reason += f" {exc['reference']} expired on {end.isoformat()}."
    if upcoming:
        start, exc = min(upcoming, key=lambda item: item[0])
        reason += f" {exc['reference']} starts on {start.isoformat()}."
    return "review", reason


def evaluate(source):
    snapshot, histories = validate(source)
    records = []
    for change in source["changes"]:
        policy = source["roles"][change["to"]]
        former = source["roles"][change["from"]]
        old_access = set(former["required"]) | set(former["optional"])
        paths = effective_grants(source["groups"], change["groups"])
        for access in sorted(set(paths) | set(policy["required"])):
            path = paths.get(access, ())
            if not path:
                status, reason = "missing", "Required by the new role. No grant path in the snapshot."
            elif access in policy["required"]:
                status, reason = "expected", "Required by the new role."
            elif access in policy["optional"]:
                status, reason = "expected", "Optional access allowed by the new role."
            else:
                history = histories[(change["case"], access)]
                status, reason = classify_extra(history, snapshot, access in old_access)
            records.append(dict(case=change["case"], access=access, path=path, status=status, reason=reason))
    return records


def render(source, records):
    esc = escape
    counts = Counter(r["status"] for r in records)
    grouped = defaultdict(list)
    for row in records:
        grouped[row["case"]].append(row)
    sections = []
    for change in source["changes"]:
        case = change["case"]
        rows = []
        for row in sorted(grouped[case], key=lambda r: (list(STATUS).index(r["status"]), r["access"])):
            access_label = esc(source["entitlements"][row["access"]])
            path = ' <span aria-hidden="true">→</span> '.join(esc(node) for node in row["path"])
            evidence = f'<span class="path">{path}</span>' if path else '<span class="no-path">No granting group</span>'
            status = row["status"]
            rows.append(
                f'<tr data-state="{status}"><td><span class="badge {status}">{STATUS[status]}</span></td>'
                f'<td><strong>{access_label}</strong><code>{esc(row["access"])}</code></td>'
                f'<td>{evidence}</td><td>{esc(row["reason"])}</td></tr>'
            )
        sections.append(
            f'<section class="case"><header><div><span class="case-id">{esc(case)}</span>'
            f'<h3>{esc(change["person"])}</h3></div><p>{esc(change["from"])} → <b>{esc(change["to"])}</b>'
            f'<small>Effective {esc(change["effective"])}</small></p></header>'
            '<div class="scroll"><table><thead><tr><th>Decision</th><th>Entitlement</th>'
            '<th>Granting group path</th><th>Policy evidence</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>'
        )
    cards = "".join(
        f'<div class="metric {key}"><span>{label}</span><b>{counts[key]}</b></div>' for key, label in STATUS.items()
    )
    actionable_cases = len({r["case"] for r in records if r["status"] in ("review", "missing")})
    return Template((HERE / "report-template.html").read_text(encoding="utf-8")).substitute(
        snapshot=esc(source["snapshot"]), dataset=esc(source.get("dataset", "Offline snapshot")),
        case_count=len(source["changes"]), records=len(records),
        actionable=actionable_cases, cards=cards, sections="".join(sections)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "sample.json")
    parser.add_argument("--output", type=Path, default=HERE / "index.html")
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("Input and output must be different files")
        source = json.loads(args.input.read_text(encoding="utf-8"))
        records = evaluate(source)
        document = render(source, records)
        args.output.write_text(document, encoding="utf-8")
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(2, f"Review unavailable: {error}\n")
    counts = Counter(r["status"] for r in records)
    print(" | ".join(f"{label}: {counts[key]}" for key, label in STATUS.items()))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
