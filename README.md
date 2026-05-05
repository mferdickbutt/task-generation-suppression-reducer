# Task Generation Suppression Reducer

Self-contained Python utilities for preflighting generated task candidates before Task Node rewards are wasted. The repository contains two no-dependency scripts with embedded sanitized fixtures only.

## Scripts

| Script | Purpose |
|---|---|
| `task_generation_suppression_reducer.py` | Original reducer for candidate requests against recent-task fingerprints, refusal history, contributor authorization, and load signals. |
| `hive_mind_suppression_ledger_reconciler.py` | Ledger reconciler that converts upstream guard-output-like findings into a reviewer-ready suppression ledger for Hive Mind task generation. |

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

## Output Contract

Running `hive_mind_suppression_ledger_reconciler.py` prints deterministic JSON with these top-level fields:

- `ledger_version`
- `total_candidates`
- `action_counts`
- `block_reason_counts`
- `duplicate_group_count`
- `terminal_state_repair_count`
- `off_grid_block_count`
- `exception_allow_count`
- `manual_review_count`
- `suppression_ledger`
- `generator_preflight_adapter`
- `prioritized_reviewer_queue`

Each suppression ledger row includes candidate id, action, reason code, confidence band, evidence count, normalized fingerprints, suggested next action, evidence ids, and finding types.

## Usage

```bash
python3 task_generation_suppression_reducer.py
python3 hive_mind_suppression_ledger_reconciler.py
```

No external dependencies. Requires Python 3.8+.

## Privacy And Sanitization

This repository is safe to keep public. The fixtures are synthetic and sanitized:

- no private URLs
- no hostnames or server addresses
- no API keys, tokens, passwords, or private keys
- no proprietary task payloads
- no live wallet-sensitive evidence
- no dependencies on external files or services

All evidence references use placeholder ids such as `C-001`, `T-101`, `DG-PAYOUT-QUEUE`, and `EX-100`.

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
