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

The reducer covers these root causes:

| Root cause | Meaning |
|---|---|
| `off_grid_leak` | Candidate scope is outside the role template's allowed scopes or explicitly forbidden. |
| `duplicate_board_language` | Candidate text asks to reopen, duplicate, or reissue board work. |
| `verification_contract_violation` | Candidate lacks reviewer-verifiable evidence or relies on inferred/obvious proof. |
| `unsupported_collaboration_dependency` | Candidate depends on unnamed, external, or unsupported collaborators. |
| `no_response_routing_risk` | Candidate has passive routing, no owner, or no response channel. |

Actions are `block`, `warn`, `allow`, and `manual_review`. Severe findings block generation. Routing-only risks warn. Unsupported collaboration without severe evidence routes to manual review. Clean examples are allowed.

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
