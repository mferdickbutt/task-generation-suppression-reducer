#!/usr/bin/env python3
"""Hive Mind Suppression Ledger Reconciler.

Self-contained reconciler that converts sanitized guard-output-like findings into
an auditable downstream suppression ledger for Hive Mind task generation.

This intentionally does not reimplement duplicate or off-grid detection. The
embedded FINDINGS fixture represents the upstream guard output contract, and this
script standardizes reviewer actions, reason codes, confidence bands, evidence
counts, and generator preflight behavior.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

LEDGER_VERSION = "hive-mind-suppression-ledger.v1"
ACTIONS = ("block", "warn", "allow_by_exception", "manual_review", "stale_active_repair")
BLOCKING_FINDING_TYPES = {"duplicate_active", "already_rewarded_reissue", "off_grid_scope"}
MANUAL_REVIEW_TYPES = {"ambiguous_exception", "conflicting_guard_signal"}
WARN_TYPES = {"clean_sanctioned_adjacency", "low_confidence_duplicate"}
REPAIR_TYPES = {"terminal_state_active"}

SEVERITY_RANK = {
    "block": 5,
    "stale_active_repair": 4,
    "manual_review": 3,
    "warn": 2,
    "allow_by_exception": 1,
}

REASON_ACTION_HINTS = {
    "DUPLICATE_ACTIVE_OBJECTIVE": "Do not generate a new task; attach candidate to the active duplicate group.",
    "ALREADY_REWARDED_REISSUE": "Block generation and require a materially new objective before reconsideration.",
    "OFF_GRID_SIDECAR_SCOPE": "Block generation; route the scope through governance approval before tasking.",
    "TERMINAL_STATE_STILL_ACTIVE": "Repair stale active state before any new generation decision.",
    "CLEAN_SANCTIONED_ADJACENCY": "Allow generation but keep adjacency evidence attached for reviewer audit.",
    "AMBIGUOUS_EXCEPTION_SCOPE": "Send to manual review with exception rationale and nearest historical evidence.",
    "CONFLICTING_GUARD_SIGNAL": "Send to manual review; resolve contradictory duplicate and exception signals.",
    "LOW_CONFIDENCE_SIMILARITY": "Warn reviewer; generation may proceed only after checking cited evidence.",
    "CLEAN_NO_FINDINGS": "Allow generation; no suppressing guard findings were present.",
}


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    title: str
    objective: str
    requested_by: str
    scope_zone: str
    exception_ticket: str | None = None


@dataclass(frozen=True)
class HistoricalTask:
    task_id: str
    title: str
    objective: str
    state: str
    reward_state: str
    scope_zone: str


@dataclass(frozen=True)
class Finding:
    candidate_id: str
    finding_type: str
    reason_code: str
    evidence_ids: tuple[str, ...]
    confidence: float
    duplicate_group_id: str | None = None
    exception_id: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class LedgerRow:
    candidate_id: str
    action: str
    reason_code: str
    confidence_band: str
    confidence_score: float
    source_evidence_count: int
    duplicate_group_id: str | None
    normalized_title_fingerprint: str
    normalized_objective_fingerprint: str
    suggested_next_action: str
    evidence_ids: tuple[str, ...]
    finding_types: tuple[str, ...]


CANDIDATES = (
    Candidate("C-001", "Rebuild reward review queue", "Create a new task to rebuild the reward review queue for reviewer assignment.", "generator-alpha", "core"),
    Candidate("C-002", "Re-issue completed reward queue rebuild", "Create another task for reward review queue rebuild after completion.", "generator-alpha", "core"),
    Candidate("C-003", "Repair stale verifier status", "Create a task because a terminal refused verifier record is still marked active.", "generator-beta", "core"),
    Candidate("C-004", "Launch sidecar evidence scout", "Create a task to inspect sidecar evidence outside the approved Hive Mind grid.", "generator-gamma", "sidecar"),
    Candidate("C-005", "Add reviewer note to sanctioned adapter", "Create an adjacent documentation task explicitly allowed by governance exception EX-100.", "generator-delta", "core", "EX-100"),
    Candidate("C-006", "Review ambiguous suppression bypass", "Create a task under a partial exception where scope and reward path do not fully match.", "generator-beta", "core", "EX-200"),
    Candidate("C-007", "Publish clean telemetry fixture", "Create a harmless telemetry fixture task with no historical collision.", "generator-alpha", "core"),
    Candidate("C-008", "Duplicate active guardrail followup", "Create another active duplicate guardrail task with the same objective already open.", "generator-alpha", "core"),
    Candidate("C-009", "Rewarded off-grid audit reissue", "Create a second task for the already rewarded off-grid audit objective.", "generator-gamma", "sidecar"),
    Candidate("C-010", "Terminal cancelled task still active", "Create a task because a cancelled historical row remains active in generator cache.", "generator-beta", "core"),
    Candidate("C-011", "Clean sanctioned adjacency two", "Create adjacent tests under a sanctioned governance exception for nearby but distinct behavior.", "generator-delta", "core", "EX-101"),
    Candidate("C-012", "Conflicting exception duplicate", "Create a task where duplicate evidence exists but an exception ticket is also attached.", "generator-alpha", "core", "EX-300"),
    Candidate("C-013", "Low confidence similarity", "Create a task that is similar to a prior task but not clearly duplicate.", "generator-beta", "core"),
    Candidate("C-014", "Manual scope adjudication", "Create a task whose proposed objective straddles core and sidecar boundaries.", "generator-gamma", "mixed"),
    Candidate("C-015", "Allow novel reviewer dashboard", "Create a new dashboard reviewer task with no suppressing guard signal.", "generator-delta", "core"),
    Candidate("C-016", "Already rewarded verifier patch", "Create a task to repeat a verifier patch that already paid out.", "generator-alpha", "core"),
    Candidate("C-017", "Duplicate active reward review queue", "Create a new task to rebuild the reward review queue for reviewer assignment.", "generator-alpha", "core"),
    Candidate("C-018", "Off-grid sidecar escalation", "Create a task to run sidecar governance checks outside sanctioned scope.", "generator-gamma", "sidecar"),
)

HISTORICAL_TASKS = (
    HistoricalTask("T-101", "Rebuild reward review queue", "Rebuild the reward review queue for reviewer assignment.", "active", "unrewarded", "core"),
    HistoricalTask("T-102", "Reward queue rebuild", "Rebuild reward review queue for reviewer assignment.", "rewarded", "rewarded", "core"),
    HistoricalTask("T-103", "Verifier status repair", "Repair refused verifier record still shown as active.", "refused", "unrewarded", "core"),
    HistoricalTask("T-104", "Sidecar evidence scout", "Inspect sidecar evidence outside approved grid.", "active", "unrewarded", "sidecar"),
    HistoricalTask("T-105", "Sanctioned adapter notes", "Add documentation for sanctioned adapter exception.", "active", "unrewarded", "core"),
    HistoricalTask("T-106", "Suppression bypass review", "Review suppression bypass under partial exception.", "cancelled", "unrewarded", "core"),
    HistoricalTask("T-107", "Duplicate guardrail followup", "Follow up duplicate guardrail task with same open objective.", "active", "unrewarded", "core"),
    HistoricalTask("T-108", "Off-grid audit", "Audit off-grid sidecar scope.", "rewarded", "rewarded", "sidecar"),
    HistoricalTask("T-109", "Cancelled cache cleanup", "Cancelled historical row remains active in generator cache.", "cancelled", "unrewarded", "core"),
    HistoricalTask("T-110", "Verifier patch", "Patch verifier issue already paid out.", "rewarded", "rewarded", "core"),
)

# Guard-output-like findings fixture. These are sanitized downstream facts from
# duplicate/off-grid/terminal-state guards, not live private evidence.
FINDINGS = (
    Finding("C-001", "duplicate_active", "DUPLICATE_ACTIVE_OBJECTIVE", ("T-101", "T-102"), 0.97, "DG-REWARD-QUEUE"),
    Finding("C-002", "already_rewarded_reissue", "ALREADY_REWARDED_REISSUE", ("T-102",), 0.95, "DG-REWARD-QUEUE"),
    Finding("C-003", "terminal_state_active", "TERMINAL_STATE_STILL_ACTIVE", ("T-103",), 0.93),
    Finding("C-004", "off_grid_scope", "OFF_GRID_SIDECAR_SCOPE", ("T-104",), 0.91),
    Finding("C-005", "clean_sanctioned_adjacency", "CLEAN_SANCTIONED_ADJACENCY", ("T-105", "EX-100"), 0.88, exception_id="EX-100"),
    Finding("C-006", "ambiguous_exception", "AMBIGUOUS_EXCEPTION_SCOPE", ("T-106", "EX-200"), 0.62, exception_id="EX-200"),
    Finding("C-008", "duplicate_active", "DUPLICATE_ACTIVE_OBJECTIVE", ("T-107",), 0.94, "DG-DUP-GUARD"),
    Finding("C-009", "already_rewarded_reissue", "ALREADY_REWARDED_REISSUE", ("T-108",), 0.9, "DG-OFFGRID-AUDIT"),
    Finding("C-009", "off_grid_scope", "OFF_GRID_SIDECAR_SCOPE", ("T-108",), 0.89),
    Finding("C-010", "terminal_state_active", "TERMINAL_STATE_STILL_ACTIVE", ("T-109",), 0.96),
    Finding("C-011", "clean_sanctioned_adjacency", "CLEAN_SANCTIONED_ADJACENCY", ("T-105", "EX-101"), 0.86, exception_id="EX-101"),
    Finding("C-012", "duplicate_active", "DUPLICATE_ACTIVE_OBJECTIVE", ("T-101",), 0.84, "DG-REWARD-QUEUE"),
    Finding("C-012", "conflicting_guard_signal", "CONFLICTING_GUARD_SIGNAL", ("T-101", "EX-300"), 0.71, "DG-REWARD-QUEUE", "EX-300"),
    Finding("C-013", "low_confidence_duplicate", "LOW_CONFIDENCE_SIMILARITY", ("T-106",), 0.58),
    Finding("C-014", "ambiguous_exception", "AMBIGUOUS_EXCEPTION_SCOPE", ("T-104", "T-106"), 0.64),
    Finding("C-016", "already_rewarded_reissue", "ALREADY_REWARDED_REISSUE", ("T-110",), 0.93, "DG-VERIFIER-PATCH"),
    Finding("C-017", "duplicate_active", "DUPLICATE_ACTIVE_OBJECTIVE", ("T-101", "T-102"), 0.98, "DG-REWARD-QUEUE"),
    Finding("C-018", "off_grid_scope", "OFF_GRID_SIDECAR_SCOPE", ("T-104",), 0.92),
)


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()[:16]


def confidence_band(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def choose_action(findings: tuple[Finding, ...]) -> tuple[str, str, float, str | None]:
    if not findings:
        return "allow_by_exception", "CLEAN_NO_FINDINGS", 1.0, None

    finding_types = {finding.finding_type for finding in findings}
    if finding_types & MANUAL_REVIEW_TYPES:
        selected = max(findings, key=lambda item: (item.finding_type in MANUAL_REVIEW_TYPES, item.confidence))
        return "manual_review", selected.reason_code, selected.confidence, selected.duplicate_group_id
    if finding_types & REPAIR_TYPES:
        selected = max((item for item in findings if item.finding_type in REPAIR_TYPES), key=lambda item: item.confidence)
        return "stale_active_repair", selected.reason_code, selected.confidence, selected.duplicate_group_id
    if finding_types & BLOCKING_FINDING_TYPES:
        selected = max((item for item in findings if item.finding_type in BLOCKING_FINDING_TYPES), key=lambda item: item.confidence)
        return "block", selected.reason_code, selected.confidence, selected.duplicate_group_id
    if finding_types & WARN_TYPES:
        selected = max((item for item in findings if item.finding_type in WARN_TYPES), key=lambda item: item.confidence)
        if selected.finding_type == "clean_sanctioned_adjacency":
            return "allow_by_exception", selected.reason_code, selected.confidence, selected.duplicate_group_id
        return "warn", selected.reason_code, selected.confidence, selected.duplicate_group_id

    selected = max(findings, key=lambda item: item.confidence)
    return "manual_review", selected.reason_code, selected.confidence, selected.duplicate_group_id


def reconcile(candidates: tuple[Candidate, ...], findings: tuple[Finding, ...]) -> list[LedgerRow]:
    findings_by_candidate: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        findings_by_candidate[finding.candidate_id].append(finding)

    ledger_rows: list[LedgerRow] = []
    for candidate in candidates:
        candidate_findings = tuple(sorted(findings_by_candidate.get(candidate.candidate_id, ()), key=lambda item: (item.reason_code, item.confidence)))
        action, reason_code, score, duplicate_group_id = choose_action(candidate_findings)
        evidence_ids = tuple(sorted({evidence for finding in candidate_findings for evidence in finding.evidence_ids}))
        finding_types = tuple(sorted({finding.finding_type for finding in candidate_findings}))
        ledger_rows.append(
            LedgerRow(
                candidate_id=candidate.candidate_id,
                action=action,
                reason_code=reason_code,
                confidence_band=confidence_band(score),
                confidence_score=round(score, 2),
                source_evidence_count=len(evidence_ids),
                duplicate_group_id=duplicate_group_id,
                normalized_title_fingerprint=fingerprint(candidate.title),
                normalized_objective_fingerprint=fingerprint(candidate.objective),
                suggested_next_action=REASON_ACTION_HINTS[reason_code],
                evidence_ids=evidence_ids,
                finding_types=finding_types,
            )
        )
    return ledger_rows


def queue_priority(row: LedgerRow) -> tuple[int, int, float, int, str]:
    actionability = 1 if row.action in {"block", "stale_active_repair", "manual_review"} else 0
    return (
        -SEVERITY_RANK[row.action],
        -actionability,
        -row.confidence_score,
        -row.source_evidence_count,
        row.candidate_id,
    )


def build_generator_preflight_adapter() -> dict[str, Any]:
    return {
        "contract_version": "generator-preflight-adapter.v1",
        "input_required": {
            "candidate_id": "stable generated candidate id",
            "title": "candidate title before task creation",
            "objective": "candidate objective before task creation",
            "scope_zone": "core, sidecar, mixed, or other sanitized scope bucket",
            "guard_findings": "list of upstream guard-output-like findings keyed by candidate_id",
        },
        "output_action_field": "action",
        "allowed_actions": list(ACTIONS),
        "hard_stop_actions": ["block", "stale_active_repair"],
        "review_required_actions": ["manual_review"],
        "soft_pass_actions": ["warn", "allow_by_exception"],
        "required_ledger_fields": [
            "candidate_id",
            "action",
            "reason_code",
            "confidence_band",
            "source_evidence_count",
            "suggested_next_action",
        ],
        "privacy_posture": "fixtures are sanitized; no private URLs, proprietary payloads, credentials, or external files",
    }


def build_payload() -> dict[str, Any]:
    ledger = reconcile(CANDIDATES, FINDINGS)
    action_counts = {action: 0 for action in ACTIONS}
    action_counts.update(Counter(row.action for row in ledger))

    block_reason_counts = Counter(row.reason_code for row in ledger if row.action == "block")
    duplicate_groups = {row.duplicate_group_id for row in ledger if row.duplicate_group_id}
    prioritized_rows = sorted(
        (row for row in ledger if row.action != "allow_by_exception"),
        key=queue_priority,
    )

    return {
        "ledger_version": LEDGER_VERSION,
        "total_candidates": len(CANDIDATES),
        "action_counts": dict(action_counts),
        "block_reason_counts": dict(sorted(block_reason_counts.items())),
        "duplicate_group_count": len(duplicate_groups),
        "terminal_state_repair_count": action_counts["stale_active_repair"],
        "off_grid_block_count": block_reason_counts.get("OFF_GRID_SIDECAR_SCOPE", 0),
        "exception_allow_count": sum(1 for row in ledger if row.action == "allow_by_exception"),
        "manual_review_count": action_counts["manual_review"],
        "suppression_ledger": [asdict(row) for row in ledger],
        "generator_preflight_adapter": build_generator_preflight_adapter(),
        "prioritized_reviewer_queue": [asdict(row) for row in prioritized_rows],
    }


def main() -> None:
    print(json.dumps(build_payload(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
