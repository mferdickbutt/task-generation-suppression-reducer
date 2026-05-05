#!/usr/bin/env python3
"""Agent-role noise attribution reducer.

Self-contained deterministic reducer for attributing weak Hive Mind task
issuance back to sanitized agent-role template clauses. The fixtures are
synthetic and require no external files or dependencies.
"""

import json
from collections import Counter, defaultdict
from copy import deepcopy

LINTER_VERSION = "agent-role-noise-attribution-reducer/1.0.0"

SEVERITY_RANK = {
    "off_grid_leak": 5,
    "duplicate_board_language": 4,
    "verification_contract_violation": 4,
    "unsupported_collaboration_dependency": 3,
    "no_response_routing_risk": 2,
    "ambiguous_task_contract": 1,
}

ACTION_RANK = {"block": 4, "manual_review": 3, "warn": 2, "allow": 1}

REPLACEMENT_CLAUSES = {
    "mission_lane": "Issue only tasks inside the named mission lane and reject adjacent work unless the template explicitly lists the adjacency.",
    "allowed_scopes": "Before issuing, match the candidate to one allowed scope token and include that token in the task contract.",
    "forbidden_scopes": "Block candidates that ask to reopen boards, duplicate prior work, modify live data, or operate outside the declared scope.",
    "evidence_rules": "Every task must name verifiable evidence artifacts, acceptance checks, and reviewer-visible proof before issuance.",
    "collaboration_rules": "Require one accountable owner; dependencies on unnamed, external, or unavailable collaborators must route to manual review.",
    "routing_rules": "Route to a named owner, reviewer, and response channel; do not use passive language such as someone or whoever.",
}

ROLE_TEMPLATES = [
    {
        "template_id": "RT-001",
        "role_name": "Evidence Triage Analyst",
        "mission_lane": "evidence-quality",
        "allowed_scopes": ["evidence-audit", "proof-normalization", "acceptance-checks"],
        "forbidden_scopes": ["live-data-mutation", "reward-release", "identity-adjudication"],
        "evidence_rules": ["must cite fixture ids", "must include reproducible checks"],
        "collaboration_rules": ["single named reviewer", "no external dependency before issuance"],
        "known_weak_clauses": [
            {"clause_id": "RT-001-C1", "field": "evidence_rules", "text": "Evidence can be summarized when obvious."},
            {"clause_id": "RT-001-C2", "field": "routing_rules", "text": "Someone should pick up unclear evidence follow-up."},
        ],
    },
    {
        "template_id": "RT-002",
        "role_name": "Scope Boundary Steward",
        "mission_lane": "scope-control",
        "allowed_scopes": ["scope-audit", "lane-classification", "boundary-note"],
        "forbidden_scopes": ["dashboard-redesign", "reward-release", "production-deploy"],
        "evidence_rules": ["must identify allowed scope token", "must identify blocked scope token"],
        "collaboration_rules": ["named owner only"],
        "known_weak_clauses": [
            {"clause_id": "RT-002-C1", "field": "allowed_scopes", "text": "May help with adjacent operational cleanup."},
            {"clause_id": "RT-002-C2", "field": "mission_lane", "text": "Can take nearby work if it seems useful."},
        ],
    },
    {
        "template_id": "RT-003",
        "role_name": "Board Hygiene Coordinator",
        "mission_lane": "task-board-hygiene",
        "allowed_scopes": ["dedupe-note", "status-reconciliation", "archive-candidate"],
        "forbidden_scopes": ["duplicate-active-board", "reissue-rewarded-task", "new-feature-request"],
        "evidence_rules": ["must include prior board id", "must state terminal status"],
        "collaboration_rules": ["reviewer plus board owner"],
        "known_weak_clauses": [
            {"clause_id": "RT-003-C1", "field": "forbidden_scopes", "text": "It is okay to reopen similar board items for visibility."},
            {"clause_id": "RT-003-C2", "field": "evidence_rules", "text": "Prior board references are optional."},
        ],
    },
    {
        "template_id": "RT-004",
        "role_name": "Collaboration Router",
        "mission_lane": "review-routing",
        "allowed_scopes": ["owner-routing", "reviewer-assignment", "handoff-note"],
        "forbidden_scopes": ["external-team-blocker", "unnamed-owner", "multi-party-dependency"],
        "evidence_rules": ["must name owner", "must name response channel"],
        "collaboration_rules": ["one accountable owner", "one optional reviewer", "no external team dependency"],
        "known_weak_clauses": [
            {"clause_id": "RT-004-C1", "field": "collaboration_rules", "text": "Coordinate with any related team before response."},
            {"clause_id": "RT-004-C2", "field": "routing_rules", "text": "Whoever has context can answer."},
        ],
    },
    {
        "template_id": "RT-005",
        "role_name": "Reward Queue Auditor",
        "mission_lane": "reward-readiness",
        "allowed_scopes": ["reward-readiness-check", "blocker-summary", "reviewer-queue"],
        "forbidden_scopes": ["reward-release", "wallet-action", "live-ledger-edit"],
        "evidence_rules": ["must include blocker ids", "must include reviewer proof"],
        "collaboration_rules": ["named queue reviewer"],
        "known_weak_clauses": [
            {"clause_id": "RT-005-C1", "field": "forbidden_scopes", "text": "May prepare release tasks when blockers look resolved."},
            {"clause_id": "RT-005-C2", "field": "evidence_rules", "text": "Reviewer proof may be inferred from queue position."},
        ],
    },
    {
        "template_id": "RT-006",
        "role_name": "Clean Issuance Scribe",
        "mission_lane": "task-contract-writing",
        "allowed_scopes": ["contract-draft", "acceptance-criteria", "fixture-only-example"],
        "forbidden_scopes": ["live-data-mutation", "production-deploy", "secret-handling"],
        "evidence_rules": ["must include acceptance criteria", "must use sanitized fixtures only"],
        "collaboration_rules": ["single owner and reviewer"],
        "known_weak_clauses": [],
    },
]

GENERATED_TASK_EXAMPLES = [
    {
        "example_id": "GT-001",
        "template_id": "RT-001",
        "title": "Summarize evidence because the failure is obvious",
        "requested_scope": "evidence-audit",
        "body": "Evidence looks obvious, so no fixture id is needed.",
        "evidence": [],
        "collaboration_dependency": "single named reviewer",
        "owner": "owner-a",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-002",
        "template_id": "RT-001",
        "title": "Someone should follow up on unclear proof",
        "requested_scope": "proof-normalization",
        "body": "Someone should chase the missing proof when they have time.",
        "evidence": ["EX-101"],
        "collaboration_dependency": "single named reviewer",
        "owner": "",
        "response_channel": "",
    },
    {
        "example_id": "GT-003",
        "template_id": "RT-002",
        "title": "Classify boundary for dashboard redesign",
        "requested_scope": "dashboard-redesign",
        "body": "This is adjacent operational cleanup and should be issued now.",
        "evidence": ["EX-102"],
        "collaboration_dependency": "named owner only",
        "owner": "owner-b",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-004",
        "template_id": "RT-002",
        "title": "Prepare a production deploy note from scope review",
        "requested_scope": "production-deploy",
        "body": "Nearby work seems useful after the lane classification.",
        "evidence": ["EX-103"],
        "collaboration_dependency": "named owner only",
        "owner": "owner-b",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-005",
        "template_id": "RT-003",
        "title": "Reopen duplicate board item DG-REWARD-QUEUE",
        "requested_scope": "duplicate-active-board",
        "body": "Reopen the same board item again for visibility.",
        "evidence": ["DG-REWARD-QUEUE"],
        "collaboration_dependency": "reviewer plus board owner",
        "owner": "owner-c",
        "response_channel": "board-comment",
    },
    {
        "example_id": "GT-006",
        "template_id": "RT-003",
        "title": "Create another task for already rewarded queue cleanup",
        "requested_scope": "reissue-rewarded-task",
        "body": "Same as board DG-REWARD-QUEUE, but issue another copy.",
        "evidence": [],
        "collaboration_dependency": "reviewer plus board owner",
        "owner": "owner-c",
        "response_channel": "board-comment",
    },
    {
        "example_id": "GT-007",
        "template_id": "RT-004",
        "title": "Route blocker after external team confirms",
        "requested_scope": "owner-routing",
        "body": "Wait for the external team before the owner can respond.",
        "evidence": ["EX-104"],
        "collaboration_dependency": "external-team-blocker",
        "owner": "owner-d",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-008",
        "template_id": "RT-004",
        "title": "Ask whoever has context to respond",
        "requested_scope": "reviewer-assignment",
        "body": "Whoever has context can answer when available.",
        "evidence": ["EX-105"],
        "collaboration_dependency": "multi-party-dependency",
        "owner": "",
        "response_channel": "",
    },
    {
        "example_id": "GT-009",
        "template_id": "RT-005",
        "title": "Prepare reward release from inferred proof",
        "requested_scope": "reward-release",
        "body": "The queue position proves this is ready for release.",
        "evidence": [],
        "collaboration_dependency": "named queue reviewer",
        "owner": "owner-e",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-010",
        "template_id": "RT-005",
        "title": "Audit reward readiness blockers",
        "requested_scope": "reward-readiness-check",
        "body": "Check blocker ids EX-106 and EX-107 before queue review.",
        "evidence": ["EX-106", "EX-107"],
        "collaboration_dependency": "named queue reviewer",
        "owner": "owner-e",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-011",
        "template_id": "RT-006",
        "title": "Draft fixture-only acceptance criteria",
        "requested_scope": "acceptance-criteria",
        "body": "Use sanitized fixtures and list reviewer-visible acceptance checks.",
        "evidence": ["EX-108"],
        "collaboration_dependency": "single owner and reviewer",
        "owner": "owner-f",
        "response_channel": "review-thread",
    },
    {
        "example_id": "GT-012",
        "template_id": "RT-006",
        "title": "Draft contract for live data mutation",
        "requested_scope": "live-data-mutation",
        "body": "Use the contract template to update live data after review.",
        "evidence": ["EX-109"],
        "collaboration_dependency": "single owner and reviewer",
        "owner": "owner-f",
        "response_channel": "review-thread",
    },
]


def _by_template():
    return {template["template_id"]: template for template in ROLE_TEMPLATES}


def _weak_clause(template, field):
    clauses = [c for c in template["known_weak_clauses"] if c["field"] == field]
    if clauses:
        return clauses[0]
    return {
        "clause_id": f"{template['template_id']}-IMPLICIT-{field.upper()}",
        "field": field,
        "text": "Implicit template contract lacks a strict guard for this failure mode.",
    }


def _finding(root_cause, template, field, example, detail):
    clause = _weak_clause(template, field)
    return {
        "root_cause": root_cause,
        "severity": SEVERITY_RANK[root_cause],
        "clause_id": clause["clause_id"],
        "clause_field": field,
        "weak_clause_text": clause["text"],
        "detail": detail,
        "example_id": example["example_id"],
    }


def classify_example(example, template):
    findings = []
    text = f"{example['title']} {example['body']}".lower()
    requested_scope = example["requested_scope"]

    if requested_scope not in template["allowed_scopes"]:
        if requested_scope in template["forbidden_scopes"]:
            detail = f"Requested forbidden scope '{requested_scope}'."
        else:
            detail = f"Requested scope '{requested_scope}' is outside allowed scopes."
        findings.append(_finding("off_grid_leak", template, "allowed_scopes", example, detail))

    duplicate_terms = ("duplicate", "same as board", "reopen", "another copy", "again")
    if any(term in text for term in duplicate_terms):
        findings.append(_finding(
            "duplicate_board_language",
            template,
            "forbidden_scopes",
            example,
            "Task text contains duplicate-board or reissue language.",
        ))

    unverifiable_terms = ("obvious", "inferred", "looks resolved", "no fixture id", "no evidence")
    if not example["evidence"] or any(term in text for term in unverifiable_terms):
        findings.append(_finding(
            "verification_contract_violation",
            template,
            "evidence_rules",
            example,
            "Evidence is missing, inferred, or not reviewer-verifiable.",
        ))

    if example["collaboration_dependency"] not in template["collaboration_rules"]:
        findings.append(_finding(
            "unsupported_collaboration_dependency",
            template,
            "collaboration_rules",
            example,
            f"Unsupported dependency '{example['collaboration_dependency']}'.",
        ))

    passive_terms = ("someone should", "whoever", "when available", "when they have time")
    if not example["owner"] or not example["response_channel"] or any(term in text for term in passive_terms):
        findings.append(_finding(
            "no_response_routing_risk",
            template,
            "routing_rules",
            example,
            "Routing lacks a named owner, response channel, or direct-response wording.",
        ))

    if not findings:
        action = "allow"
    elif any(f["severity"] >= 4 for f in findings):
        action = "block"
    elif any(f["root_cause"] == "unsupported_collaboration_dependency" for f in findings):
        action = "manual_review"
    else:
        action = "warn"

    return {
        "example_id": example["example_id"],
        "template_id": template["template_id"],
        "role_name": template["role_name"],
        "requested_scope": requested_scope,
        "action": action,
        "root_causes": sorted({f["root_cause"] for f in findings}),
        "attributed_clauses": sorted(
            [
                {
                    "clause_id": f["clause_id"],
                    "clause_field": f["clause_field"],
                    "root_cause": f["root_cause"],
                    "weak_clause_text": f["weak_clause_text"],
                }
                for f in findings
            ],
            key=lambda c: (c["root_cause"], c["clause_id"]),
        ),
        "findings": sorted(findings, key=lambda f: (-f["severity"], f["root_cause"], f["clause_id"])),
    }


def build_patch_suggestions(classified):
    template_map = _by_template()
    grouped = defaultdict(list)
    for row in classified:
        for finding in row["findings"]:
            grouped[(row["template_id"], finding["clause_id"], finding["clause_field"])].append(finding)

    suggestions_by_template = defaultdict(list)
    for (template_id, clause_id, field), findings in grouped.items():
        root_counts = Counter(f["root_cause"] for f in findings)
        primary_root = sorted(root_counts.items(), key=lambda kv: (-kv[1], -SEVERITY_RANK[kv[0]], kv[0]))[0][0]
        template = template_map[template_id]
        clause = _weak_clause(template, field)
        suggestions_by_template[template_id].append({
            "clause_id": clause_id,
            "clause_field": field,
            "current_clause_text": clause["text"],
            "replacement_clause_text": REPLACEMENT_CLAUSES[field],
            "root_cause": primary_root,
            "severity": SEVERITY_RANK[primary_root],
            "recurrence": len(findings),
            "implicated_examples": sorted({f["example_id"] for f in findings}),
        })

    role_patch_suggestions = []
    for template_id in sorted(suggestions_by_template):
        template = template_map[template_id]
        suggestions = sorted(
            suggestions_by_template[template_id],
            key=lambda s: (-s["severity"], -s["recurrence"], s["clause_id"]),
        )
        role_patch_suggestions.append({
            "template_id": template_id,
            "role_name": template["role_name"],
            "mission_lane": template["mission_lane"],
            "patches": suggestions,
        })
    return role_patch_suggestions


def build_fix_queue(role_patch_suggestions):
    queue = []
    for role in role_patch_suggestions:
        for patch in role["patches"]:
            queue.append({
                "template_id": role["template_id"],
                "role_name": role["role_name"],
                "clause_id": patch["clause_id"],
                "root_cause": patch["root_cause"],
                "severity": patch["severity"],
                "recurrence": patch["recurrence"],
                "replacement_clause_text": patch["replacement_clause_text"],
                "priority_score": patch["severity"] * 100 + patch["recurrence"] * 10,
            })
    return sorted(queue, key=lambda q: (-q["priority_score"], q["template_id"], q["clause_id"]))


def build_payload():
    template_map = _by_template()
    classified = [classify_example(example, template_map[example["template_id"]]) for example in GENERATED_TASK_EXAMPLES]

    root_cause_counts = Counter()
    action_counts = Counter()
    weak_templates = set()
    for row in classified:
        action_counts[row["action"]] += 1
        if row["findings"]:
            weak_templates.add(row["template_id"])
        for root in row["root_causes"]:
            root_cause_counts[root] += 1

    for root in SEVERITY_RANK:
        root_cause_counts.setdefault(root, 0)
    for action in ACTION_RANK:
        action_counts.setdefault(action, 0)

    role_patch_suggestions = build_patch_suggestions(classified)
    blocked_examples = [
        {
            "example_id": row["example_id"],
            "template_id": row["template_id"],
            "role_name": row["role_name"],
            "requested_scope": row["requested_scope"],
            "root_causes": row["root_causes"],
            "attributed_clause_ids": [c["clause_id"] for c in row["attributed_clauses"]],
        }
        for row in classified
        if row["action"] == "block"
    ]
    blocked_examples = sorted(blocked_examples, key=lambda r: r["example_id"])

    payload = {
        "linter_version": LINTER_VERSION,
        "total_role_templates": len(ROLE_TEMPLATES),
        "total_generated_examples": len(GENERATED_TASK_EXAMPLES),
        "weak_template_count": len(weak_templates),
        "off_grid_leak_count": root_cause_counts["off_grid_leak"],
        "duplicate_board_language_count": root_cause_counts["duplicate_board_language"],
        "verification_contract_violation_count": root_cause_counts["verification_contract_violation"],
        "unsupported_collaboration_dependency_count": root_cause_counts["unsupported_collaboration_dependency"],
        "no_response_routing_risk_count": root_cause_counts["no_response_routing_risk"],
        "action_counts": dict(sorted(action_counts.items())),
        "root_cause_counts": dict(sorted(root_cause_counts.items())),
        "role_patch_suggestions": role_patch_suggestions,
        "blocked_generation_examples": blocked_examples,
        "prioritized_template_fix_queue": build_fix_queue(role_patch_suggestions),
    }
    return payload


def main():
    payload = build_payload()
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
