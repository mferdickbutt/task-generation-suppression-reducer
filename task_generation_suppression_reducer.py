#!/usr/bin/env python3
"""Task Generation Suppression Reducer.

Evaluates sanitized candidate task-generation requests against recent-task
fingerprints, refusal history, target authorization state, and active-load
signals.  Classifies each request and emits a deterministic JSON payload with
aggregate counts and a prioritised action queue.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Disposition(str, Enum):
    ISSUE = "ISSUE"
    MERGE_EXISTING = "MERGE_EXISTING"
    DEFER_OVERLOAD = "DEFER_OVERLOAD"
    SUPPRESS_NO_RESPONSE = "SUPPRESS_NO_RESPONSE"
    SUPPRESS_UNAUTHORIZED = "SUPPRESS_UNAUTHORIZED"
    SUPPRESS_DUPLICATE = "SUPPRESS_DUPLICATE"


SUPPRESSION_DISPOSITIONS = {
    Disposition.SUPPRESS_DUPLICATE,
    Disposition.SUPPRESS_NO_RESPONSE,
    Disposition.SUPPRESS_UNAUTHORIZED,
}


@dataclass(frozen=True)
class RecentTask:
    task_id: str
    title_fingerprint: str
    target: str
    created_epoch: int
    status: str


@dataclass(frozen=True)
class RefusalRecord:
    target: str
    no_response_count: int
    last_refusal_epoch: int
    reason: str


@dataclass(frozen=True)
class ContributorState:
    target: str
    authorized: bool
    role: str


@dataclass(frozen=True)
class LoadSnapshot:
    active_tasks: int
    capacity: int
    queue_depth: int


@dataclass(frozen=True)
class CandidateRequest:
    request_id: str
    title: str
    target: str
    priority: int
    requested_epoch: int
    tags: Tuple[str, ...] = ()


@dataclass
class EvaluatedRequest:
    request_id: str
    title: str
    target: str
    priority: int
    disposition: Disposition
    reason_code: str
    merge_target_id: Optional[str] = None
    risk_score: float = 0.0


def fingerprint(title: str) -> str:
    normalised = " ".join(title.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


RECENT_TASKS: list[RecentTask] = [
    RecentTask("T-001", fingerprint("Align contributor routing priorities"), "contributor-a", 1713000000, "open"),
    RecentTask("T-002", fingerprint("Fix memory leak in session handler"), "contributor-b", 1713000100, "open"),
    RecentTask("T-003", fingerprint("Upgrade auth middleware to v3"), "contributor-c", 1712990000, "merged"),
    RecentTask("T-004", fingerprint("Add telemetry for queue latency"), "contributor-a", 1713000200, "open"),
    RecentTask("T-005", fingerprint("Refactor notification dispatch layer"), "contributor-d", 1713000300, "open"),
]

REFUSAL_HISTORY: list[RefusalRecord] = [
    RefusalRecord("contributor-e", no_response_count=4, last_refusal_epoch=1712900000, reason="no_response"),
    RefusalRecord("contributor-f", no_response_count=1, last_refusal_epoch=1712800000, reason="declined"),
]

CONTRIBUTOR_STATES: list[ContributorState] = [
    ContributorState("contributor-a", True, "maintainer"),
    ContributorState("contributor-b", True, "member"),
    ContributorState("contributor-c", True, "member"),
    ContributorState("contributor-d", True, "member"),
    ContributorState("contributor-e", True, "member"),
    ContributorState("contributor-f", False, "revoked"),
    ContributorState("contributor-g", False, "pending"),
]

LOAD_SNAPSHOT = LoadSnapshot(active_tasks=47, capacity=50, queue_depth=12)

CANDIDATES: list[CandidateRequest] = [
    CandidateRequest("R-01", "Align contributor routing priorities", "contributor-a", 5, 1713001000, ("routing",)),
    CandidateRequest("R-02", "Implement dark-mode toggle for dashboard", "contributor-b", 3, 1713001100, ("ui",)),
    CandidateRequest("R-03", "Investigate stale connection pool entries", "contributor-e", 7, 1713001200, ("infra",)),
    CandidateRequest("R-04", "Migrate billing endpoint to v2 schema", "contributor-f", 4, 1713001300, ("billing",)),
    CandidateRequest("R-05", "Add telemetry for queue latency", "contributor-a", 6, 1713001400, ("observability",)),
    CandidateRequest("R-06", "Patch CVE-2026-1234 in image pipeline", "contributor-c", 9, 1713001500, ("security",)),
    CandidateRequest("R-07", "Seed demo data for staging environment", "contributor-g", 2, 1713001600, ("tooling",)),
    CandidateRequest("R-08", "Refactor notification dispatch layer", "contributor-d", 5, 1713001700, ("core",)),
    CandidateRequest("R-09", "Reduce bundle size by tree-shaking utils", "contributor-b", 4, 1713001800, ("perf",)),
    CandidateRequest("R-10", "Upgrade auth middleware to v3", "contributor-c", 3, 1713001900, ("auth",)),
]

NO_RESPONSE_THRESHOLD = 3
OVERLOAD_RATIO = 0.9


def _is_overloaded(load: LoadSnapshot) -> bool:
    return (load.active_tasks / max(load.capacity, 1)) >= OVERLOAD_RATIO


def evaluate(
    candidate: CandidateRequest,
    recent: List[RecentTask],
    refusals: List[RefusalRecord],
    contributors: List[ContributorState],
    load: LoadSnapshot,
) -> EvaluatedRequest:
    contrib_map = {c.target: c for c in contributors}
    refusal_map = {r.target: r for r in refusals}
    recent_fp_map: Dict[str, RecentTask] = {}
    for t in recent:
        recent_fp_map.setdefault(t.title_fingerprint, t)

    fp = fingerprint(candidate.title)

    duplicate_match = recent_fp_map.get(fp)
    if duplicate_match and duplicate_match.status != "merged":
        return EvaluatedRequest(
            request_id=candidate.request_id,
            title=candidate.title,
            target=candidate.target,
            priority=candidate.priority,
            disposition=Disposition.SUPPRESS_DUPLICATE,
            reason_code="DUPLICATE_RECENT",
            risk_score=0.9,
        )

    if duplicate_match and duplicate_match.status == "merged":
        return EvaluatedRequest(
            request_id=candidate.request_id,
            title=candidate.title,
            target=candidate.target,
            priority=candidate.priority,
            disposition=Disposition.MERGE_EXISTING,
            reason_code="EXISTING_MERGED",
            merge_target_id=duplicate_match.task_id,
            risk_score=0.3,
        )

    contrib = contrib_map.get(candidate.target)
    if contrib and not contrib.authorized:
        return EvaluatedRequest(
            request_id=candidate.request_id,
            title=candidate.title,
            target=candidate.target,
            priority=candidate.priority,
            disposition=Disposition.SUPPRESS_UNAUTHORIZED,
            reason_code=f"TARGET_{contrib.role.upper()}",
            risk_score=0.85,
        )

    refusal = refusal_map.get(candidate.target)
    if refusal and refusal.no_response_count >= NO_RESPONSE_THRESHOLD:
        return EvaluatedRequest(
            request_id=candidate.request_id,
            title=candidate.title,
            target=candidate.target,
            priority=candidate.priority,
            disposition=Disposition.SUPPRESS_NO_RESPONSE,
            reason_code=f"NO_RESPONSE_X{refusal.no_response_count}",
            risk_score=0.75,
        )

    if _is_overloaded(load) and candidate.priority < 7:
        return EvaluatedRequest(
            request_id=candidate.request_id,
            title=candidate.title,
            target=candidate.target,
            priority=candidate.priority,
            disposition=Disposition.DEFER_OVERLOAD,
            reason_code="OVERLOAD_DEFER",
            risk_score=0.4,
        )

    return EvaluatedRequest(
        request_id=candidate.request_id,
        title=candidate.title,
        target=candidate.target,
        priority=candidate.priority,
        disposition=Disposition.ISSUE,
        reason_code="CLEAN",
        risk_score=0.0,
    )


def build_payload(evaluated: List[EvaluatedRequest]) -> Dict[str, Any]:
    disposition_counts: dict[str, int] = {}
    for e in evaluated:
        disposition_counts[e.disposition.value] = disposition_counts.get(e.disposition.value, 0) + 1

    prevented = [e for e in evaluated if e.disposition in SUPPRESSION_DISPOSITIONS]
    prevented_duplicate_count = sum(1 for e in prevented if e.disposition == Disposition.SUPPRESS_DUPLICATE)
    prevented_no_response_count = sum(1 for e in prevented if e.disposition == Disposition.SUPPRESS_NO_RESPONSE)
    prevented_unauthorized_count = sum(1 for e in prevented if e.disposition == Disposition.SUPPRESS_UNAUTHORIZED)

    action_queue = sorted(
        [asdict(e) for e in evaluated],
        key=lambda x: (-x["risk_score"], -x["priority"]),
    )

    return {
        "total_requests": len(evaluated),
        "disposition_counts": disposition_counts,
        "prevented_duplicate_count": prevented_duplicate_count,
        "prevented_no_response_count": prevented_no_response_count,
        "prevented_unauthorized_count": prevented_unauthorized_count,
        "prioritized_action_queue": action_queue,
    }


def main() -> None:
    evaluated: List[EvaluatedRequest] = []
    for c in CANDIDATES:
        evaluated.append(evaluate(c, RECENT_TASKS, REFUSAL_HISTORY, CONTRIBUTOR_STATES, LOAD_SNAPSHOT))

    payload = build_payload(evaluated)

    print("=" * 60)
    print("  Task Generation Suppression Reducer  —  Console Summary")
    print("=" * 60)
    print(f"  Total candidates evaluated : {payload['total_requests']}")
    for disp, count in sorted(payload["disposition_counts"].items()):
        print(f"    {disp:<30s} {count}")
    print(f"  Prevented (duplicate)      : {payload['prevented_duplicate_count']}")
    print(f"  Prevented (no_response)    : {payload['prevented_no_response_count']}")
    print(f"  Prevented (unauthorized)   : {payload['prevented_unauthorized_count']}")
    print("=" * 60)
    print()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
