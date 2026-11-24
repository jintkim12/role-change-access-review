# Role Change Access Review

An offline Python project for identity and access management. After an internal transfer, it identifies which permissions carried over, which required permissions are missing, and which exceptions still apply.

**[Read the one-page access review (PDF)](Role-Change-Access-Review.pdf)** for the four decision examples. Download [index.html](index.html) and open it in a browser to filter the decisions and inspect granting paths. The bundled scenario uses invented people, groups, role policies and approvals.

## Sample findings

| Change | Review outcome on November 24, 2026 |
| --- | --- |
| MOVE-101 · Billing analyst to support specialist | Payout export remains through the billing team. The handoff exception expired that morning. |
| MOVE-102 · Support lead to billing analyst | The former case-edit permission has a documented exception through November 30. |
| MOVE-103 · Refund approver to support lead | Refund approval still reaches the user through a former team. The new coaching permission is missing. |
| MOVE-104 · Support specialist to support lead | All five observed permissions are covered by the current policy. |

The four transfers produce 17 entitlement decisions. Two permissions need an excess-access review, one required permission is missing, one active exception applies, and 13 permissions are within policy.

## Reproduce

### Reconcile Microsoft Graph-shaped memberships

Run `python -B graph_reconcile.py` to compare two representations of the same synthetic directory. The [offline fixture](graph-members.sample.json) contains a counted, single-page member response for each of nine security groups. Four user IDs map to HR transfer cases. The adapter rebuilds direct memberships from IDs and object types, including nested group edges. Role definitions, entitlement grants and exception dates come from the separate policy file. All **17 review rows** match, including their granting paths and policy reasons.

Microsoft Graph lists a group's direct members. A nested group therefore belongs to the group whose response contains its ID. The fixture uses `id` and `@odata.type` so display names can be missing or duplicated. The adapter requires every mapped group and case, rejects unsupported object types or unknown IDs, and stops when a response has a next-page link or an inconsistent count. This exercise covers a closed synthetic set of users and security groups. It requires no tenant or credentials. [List group members](https://learn.microsoft.com/en-us/graph/api/group-list-members?view=graph-rest-1.0) · [Microsoft Graph paging](https://learn.microsoft.com/en-us/graph/paging)

### Can the reviewer close the findings?

Run `python -B follow_up.py` to replay a proposed change in memory. On November 25 the sample drops the former billing-team membership in MOVE-101 and replaces the former refund-team membership with lead-desk access in MOVE-103. The model then recomputes **every** effective grant, including inherited grants.

| Synthetic review date | Excess | Missing | Active exceptions | Within policy |
| --- | ---: | ---: | ---: | ---: |
| November 24, before edits | 2 | 1 | 1 | 13 |
| November 25, after simulated edits | 0 | 0 | 1 | 14 |
| December 1, same memberships | 1 | 0 | 0 | 14 |

The last row shows why a single clean review is insufficient. On December 1, EX-021 expires. The person still inherits case-edit from case-workers, so MOVE-102 returns for review. The exercise makes no changes to a directory or to the source fixture.

### Generate the original review

Run these commands from this directory with Python 3.9 or later.

```shell
python -B review.py
python -B -m unittest -v
```

Use these options to evaluate a different offline snapshot.

```shell
python -B review.py --input my-snapshot.json --output my-review.html
```

## How a decision is made

1. Read each person's direct group memberships from [sample.json](sample.json). Each group lists its own grants and any parent groups whose grants it inherits.
2. Traverse memberships breadth first. A visited set handles circular inheritance. Each effective entitlement carries one shortest granting path, with sorted group names breaking ties.
3. Compare effective grants to the destination role. Required and optional permissions may remain. An absent required permission creates a missing-access decision. Absent optional permissions produce no finding.
4. For each remaining grant, look for an exception scoped to that change case and entitlement. An exception is active from its start date through the day before its exclusive end date. The evidence includes the approval reference, owner and purpose. Expired or future exceptions leave the grant open for review.

The tool evaluates explicit grants represented in its input. It reads offline JSON and writes an HTML report. Directory connectors, policy enforcement, deny rules and live tenant state fall outside this model. Review the full membership graph before changing a group, since a user may receive the same grant through multiple routes.

## Files

- [review.py](review.py) validates the snapshot, evaluates policy and renders evidence.
- [report-template.html](report-template.html) contains the self-contained report layout and filter.
- [test_review.py](test_review.py) covers nested and cyclic group paths, role expectations, date boundaries, case scoping, invalid references, overlapping exceptions, and HTML escaping.
