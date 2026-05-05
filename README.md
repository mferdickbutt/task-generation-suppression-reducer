# Task Generation Suppression Reducer

Self-contained Python utilities for preflighting generated task candidates before Task Node rewards are wasted. The repository contains no-dependency scripts with embedded sanitized fixtures only.

## Scripts

| Script | Purpose |
|---|---|
| `task_generation_suppression_reducer.py` | Original reducer for candidate requests against recent-task fingerprints, refusal history, contributor authorization, and load signals. |
| `hive_mind_suppression_ledger_reconciler.py` | Ledger reconciler that converts upstream guard-output-like findings into a reviewer-ready suppression ledger for Hive Mind task generation. |
| `agent_role_noise_attribution_reducer.py` | Agent-role template attribution reducer that maps weak generated-task issuance back to role-template clauses and emits a deterministic patch queue. |

## Agent Role Noise Attribution Reducer

`agent_role_noise_attribution_reducer.py` is the next layer after duplicate/off-grid guards and prompt-contract linting. It does not touch live data and does not call external services. It uses embedded synthetic fixtures for six agent-role templates and twelve generated-task examples, then deterministically classifies issuance noise into reviewer actions.

The reducer answers one operational question: which weak agent-role template clauses are causing bad Hive Mind task candidates, and what should reviewers patch first?

### Architecture

The reducer has four layers:

1. Fixture model
2. Rule classifier
3. Clause attribution engine
4. Reviewer output builder

The data flow is:

```text
role template + generated task
        |
        v
deterministic rule checks
        |
        v
root-cause classification
        |
        v
clause-level attribution
        |
        v
block / warn / allow / manual-review action
        |
        v
template patch suggestion
        |
        v
prioritized reviewer queue
```

### Fixture Model

`ROLE_TEMPLATES` is the embedded source-of-truth model for sanitized role templates. Each role template includes:

- `template_id`
- `role_name`
- `mission_lane`
- `allowed_scopes`
- `forbidden_scopes`
- `evidence_rules`
- `collaboration_rules`
- `known_weak_clauses`

The important design choice is that weak clauses are represented explicitly. A template does not only describe what a role may do; it also carries risky wording that may produce weak task issuance. That lets the reducer attribute a bad generated task to an exact clause such as `RT-002-C1`, instead of only saying that the role template is weak in general.

`GENERATED_TASK_EXAMPLES` is the embedded synthetic task corpus. Each generated example is mapped to a template and includes the requested scope, title, body, evidence IDs, collaboration dependency, owner, and response channel. These fields give the reducer enough signal to detect scope leakage, duplicate-board language, weak evidence, unsupported dependencies, and no-response-prone routing.

### Rule Classifier

`classify_example(example, template)` evaluates each generated task against five deterministic root-cause families:

| Root cause | Detection logic | Reviewer meaning |
|---|---|---|
| `off_grid_leak` | Requested scope is not listed in `allowed_scopes`; explicit forbidden scopes are treated as stronger evidence of the same leak. | The role template allowed or failed to block work outside its mission lane. |
| `duplicate_board_language` | Title/body contains stable terms such as `duplicate`, `same as board`, `reopen`, `another copy`, or `again`. | The candidate is trying to reopen, duplicate, or reissue board work that should not become a fresh task. |
| `verification_contract_violation` | Evidence is missing or task text relies on terms such as `obvious`, `inferred`, `looks resolved`, `no fixture id`, or `no evidence`. | The generated task cannot be verified from reviewer-visible artifacts. |
| `unsupported_collaboration_dependency` | The task dependency is not allowed by the role template's `collaboration_rules`. | The candidate depends on an unnamed, external, unavailable, or unsupported collaborator. |
| `no_response_routing_risk` | Owner or response channel is missing, or task text uses passive routing such as `someone should`, `whoever`, or `when available`. | The task is likely to produce no response because accountability is unclear. |

The classifier is deliberately rule-based and deterministic. It does not use randomness, external model calls, current board state, or live production data.

### Clause Attribution

Each finding is created through `_finding(...)`, which attaches a root cause to a template field and a clause.

The attribution mapping is intentionally simple:

| Root cause | Template field patched |
|---|---|
| `off_grid_leak` | `allowed_scopes` |
| `duplicate_board_language` | `forbidden_scopes` |
| `verification_contract_violation` | `evidence_rules` |
| `unsupported_collaboration_dependency` | `collaboration_rules` |
| `no_response_routing_risk` | `routing_rules` |

`_weak_clause(template, field)` looks for an explicit weak clause on that field. If one exists, the reducer attributes the finding to that clause ID. If no explicit weak clause exists, it creates an implicit clause ID such as `RT-006-IMPLICIT-ALLOWED_SCOPES`. That distinction gives reviewers two different patch shapes:

- replace a known weak clause
- add a missing guard clause

### Action Routing

After collecting findings, each generated example receives exactly one action:

| Action | Meaning |
|---|---|
| `block` | Do not issue the generated task. |
| `warn` | Keep the task available but surface a weaker routing or quality issue. |
| `manual_review` | Pause automation because collaboration evidence requires human judgment. |
| `allow` | The candidate passed the reducer's checks. |

Severity is defined centrally:

```python
SEVERITY_RANK = {
    "off_grid_leak": 5,
    "duplicate_board_language": 4,
    "verification_contract_violation": 4,
    "unsupported_collaboration_dependency": 3,
    "no_response_routing_risk": 2,
    "ambiguous_task_contract": 1,
}
```

Routing rules are deterministic:

- no findings -> `allow`
- any finding with severity `4` or higher -> `block`
- unsupported collaboration without a block-level finding -> `manual_review`
- lower-risk findings only -> `warn`

This makes off-grid leaks, duplicate-board language, and unverifiable evidence block-level issues. Unsupported collaboration is routed to manual review unless it appears alongside a more severe failure. No-response routing risk alone is a warning.

### Patch Suggestions

`build_patch_suggestions(classified)` groups findings by:

```python
(template_id, clause_id, clause_field)
```

That grouping turns individual bad generated examples into reusable template patches. For each implicated clause, the reducer emits:

- clause ID
- clause field
- current weak clause text
- replacement clause text
- primary root cause
- severity
- recurrence
- implicated example IDs

Replacement text comes from the fixed `REPLACEMENT_CLAUSES` map, which keeps the output deterministic and reviewer-ready. The reducer does not generate fresh prose differently on each run.

### Prioritized Fix Queue

`build_fix_queue(role_patch_suggestions)` flattens all patch suggestions into `prioritized_template_fix_queue`.

Each queue item gets this score:

```python
priority_score = severity * 100 + recurrence * 10
```

The queue is sorted by:

1. highest `priority_score`
2. `template_id`
3. `clause_id`

For example, a recurring off-grid leak with severity `5` and recurrence `2` receives:

```text
5 * 100 + 2 * 10 = 520
```

This means severe recurring template failures rise above one-off lower-risk issues. The queue is designed to be a deterministic patch order for Task Node reviewers.

### Output Contract

Running `agent_role_noise_attribution_reducer.py` prints only deterministic JSON with these top-level fields:

- `linter_version`
- `total_role_templates`
- `total_generated_examples`
- `weak_template_count`
- `off_grid_leak_count`
- `duplicate_board_language_count`
- `verification_contract_violation_count`
- `unsupported_collaboration_dependency_count`
- `no_response_routing_risk_count`
- `action_counts`
- `root_cause_counts`
- `role_patch_suggestions`
- `blocked_generation_examples`
- `prioritized_template_fix_queue`

`role_patch_suggestions` includes concise replacement clause text for implicated template clauses. `prioritized_template_fix_queue` is sorted deterministically by severity, recurrence, template id, and clause id.

### Design Boundary

The reducer does not replace upstream duplicate, off-grid, or prompt-contract guards. It assumes those controls already exist and focuses on the next layer: identifying which role-template clauses are generating bad task candidates before reviewer time or reward capacity is wasted.

The reducer also does not touch live boards, live rewards, production systems, external services, or private data. All fixtures are synthetic and embedded in the script.

## Hive Mind Suppression Ledger Reconciler

The reconciler is a downstream action-contract layer. It does not reimplement duplicate, terminal-state, or off-grid detection. Instead, it ingests sanitized guard-output-like findings and emits exactly one action for each candidate:

| Action | Meaning |
|---|---|
| `block` | Stop generation because the candidate is a duplicate active objective, already rewarded reissue, or off-grid sidecar scope. |
| `warn` | Surface weak or low-confidence evidence while keeping the candidate available for reviewer judgment. |
| `allow_by_exception` | Allow generation because the candidate is clean or covered by a sanctioned adjacency exception. |
| `manual_review` | Pause automation because exception, scope, or guard evidence is ambiguous or conflicting. |
| `stale_active_repair` | Stop generation until a terminal-state row that is still active in downstream state is repaired. |

### Architecture

The ledger reconciler separates detection from routing:

1. Candidate task fixtures model generated task requests.
2. Historical task fixtures provide sanitized active, rewarded, cancelled, and refused examples.
3. Guard findings represent upstream duplicate, off-grid, exception, and terminal-state signals.
4. The reconciler maps findings to one deterministic action per candidate.
5. The output supplies a generator preflight adapter contract and prioritized reviewer queue.

Manual-review signals intentionally preempt hard blocks when a candidate has contradictory exception or scope evidence. A hard block is appropriate for clean duplicate, rewarded reissue, or off-grid findings. A mixed case is routed to human review because the reconciler should not silently adjudicate governance exceptions.

## Usage

```bash
python3 task_generation_suppression_reducer.py
python3 hive_mind_suppression_ledger_reconciler.py
python3 agent_role_noise_attribution_reducer.py
```

No external dependencies. Requires Python 3.8+.

## Privacy And Sanitization

This repository is safe to keep public. The fixtures are synthetic and sanitized:

- no private URLs
- no hostnames or server addresses
- no API keys, tokens, passwords, or private keys
- no proprietary task payloads
- no live financial, credential, identity, or infrastructure-sensitive evidence
- no dependencies on external files or services

All evidence references use placeholder ids such as `C-001`, `T-101`, `DG-REWARD-QUEUE`, and `EX-100`.

## Original Reducer Dispositions

The original reducer emits these dispositions:

| Disposition | Meaning |
|---|---|
| `ISSUE` | Clean request; all guardrails passed. |
| `MERGE_EXISTING` | Matches a recently merged task; recommend merging into it. |
| `DEFER_OVERLOAD` | System at capacity and request is not high priority; defer. |
| `SUPPRESS_NO_RESPONSE` | Target has excessive no-response history; suppress. |
| `SUPPRESS_UNAUTHORIZED` | Target contributor is not authorized; suppress. |
| `SUPPRESS_DUPLICATE` | Duplicate of a recent open or active task; suppress. |

## License

MIT
