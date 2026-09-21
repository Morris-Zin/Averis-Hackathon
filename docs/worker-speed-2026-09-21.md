# Worker speed checkpoint, 21 September 2026

## Recovery code

Recovery previously locked every queued/running run before checking whether a worker still owned a live lease. While holding those locks it fetched each outbox row separately. A worker trying to save a checkpoint or extend its lease could therefore wait behind recovery.

Recovery now filters healthy leases and recently dispatched work in SQL before locking, and fetches outbox data in the same query. Exhausted attempts remain eligible for finalization, abandoned work remains recoverable, and missing outboxes are repaired. Document inference, thresholds, comparison, budget accounting and version fencing are unchanged.

Validation: `uv run python scripts/verify.py` with real PostgreSQL passed: 452 backend tests, 2 optional skips, 21 frontend tests, strict types, lint, generated contracts and production build. New PostgreSQL acceptance checks show healthy/recent rows can be locked independently during recovery and two independent runners process distinct jobs exactly once. Existing process-crash recovery and retry checks passed.

## Deployment and timing

Region and replica changes are separate operational checkpoints. Timing acceptance is pending; local correctness tests do not establish a production speedup. The prior 15-job batch took 806.7 seconds from first dispatch to last result, with 764.2 seconds spent in serial delivery windows. This is a workload-specific observation, not a service-level guarantee.
