# Task Generation Suppression Reducer

A self-contained Python utility that evaluates candidate task-generation requests against recent-task fingerprints, refusal history, target authorization state, and active-load signals. It classifies each request into one of six dispositions and emits a deterministic JSON payload with aggregate counts and a prioritised action queue.

## Dispositions

| Disposition | Meaning |
|---|---|
| `ISSUE` | Clean request — all guardrails passed |
| `MERGE_EXISTING` | Matches a recently merged task — recommend merging into it |
| `DEFER_OVERLOAD` | System at capacity and request is not high priority — defer |
| `SUPPRESS_NO_RESPONSE` | Target has excessive no-response history — suppress |
| `SUPPRESS_UNAUTHORIZED` | Target contributor is not authorized — suppress |
| `SUPPRESS_DUPLICATE` | Duplicate of a recent open/active task — suppress |

## Evaluation Rules (applied in order)

1. **Duplicate check** — SHA-256 fingerprint of the normalised title is matched against recent tasks. Open matches get `SUPPRESS_DUPLICATE`.
2. **Merge check** — Same fingerprint but the existing task status is `merged`. Classifies as `MERGE_EXISTING` with a pointer to the existing task ID.
3. **Authorization check** — Target looked up in contributor states. If not authorized, `SUPPRESS_UNAUTHORIZED`.
4. **No-response check** — Target looked up in refusal history. If no-response count exceeds threshold (default 3), `SUPPRESS_NO_RESPONSE`.
5. **Overload check** — If active tasks / capacity >= 90% and priority < 7, `DEFER_OVERLOAD`. High-priority requests punch through.
6. **Clean pass** — No guardrail triggered, `ISSUE`.

## Output

The action queue is sorted descending by `(-risk_score, -priority)` so the highest-risk prevented requests appear first.

The JSON payload contains:

- `total_requests` — number of candidates evaluated
- `disposition_counts` — count per disposition
- `prevented_duplicate_count` — suppressed duplicates
- `prevented_no_response_count` — suppressed no-response targets
- `prevented_unauthorized_count` — suppressed unauthorized targets
- `prioritized_action_queue` — sorted list of all evaluated requests with full detail

## Usage

```bash
python3 task_generation_suppression_reducer.py
```

No external dependencies. Requires Python 3.8+.

## Fixtures

All fixtures (recent tasks, refusal history, contributor states, load snapshot, and 10 candidate requests) are embedded directly in the script. Replace them with live data sources as needed for production use.

## License

MIT
