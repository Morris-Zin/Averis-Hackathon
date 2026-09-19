# Application boundaries

The application remains one Python backend package and a static Next.js frontend. These boundaries separate decisions that change for different reasons; they do not introduce extra services.

| Entry point | Owns and hides | Caller guarantees |
| --- | --- | --- |
| `ShipmentPipeline.process` | Classification, independent document preparation, extraction checkpoints, reading overrides and comparison | Returns only processing-owned fields. Does not change assignments or employee workflow. Invalid saved stages raise `InvalidCheckpoint`; missing originals raise `MissingDocument`; exhausted execution time raises `TimeoutError`. |
| `Processor.execute` | Run claims, renewable leases, attempt limits, transactions, stale publication checks and recovery | A duplicate delivery cannot publish stale results. Completed stages are reused. Object reads, parsing and inference happen without holding the processing thread's database connection. Delivery outcomes are a finite typed set. |
| `review_case` | Category acceptance, pair selection, source-bound corrections and reviewer transitions | Operates on a private copy and returns explicit changes. Invalid actions raise `ValueError`; the workflow adapter owns revision conflicts, quotas and persistence. |
| `Workflow.apply` | Locked revision checks, durable action history and enqueueing work | Case changes and new runs commit together. Reviewer-only changes do not invalidate extraction inputs. |
| `summarize_case` | Report completeness and result labels | A clear result requires current inputs, a valid pair and all seven matching fields. Known mismatches remain visible beside unresolved findings. Both frontend views consume the same summary. |
| `CaseResponse` | Computed public summary | Adds a read-only projection; persisted `CaseView` remains unchanged and round-trippable. |
| `useReviewWorkspace` | Request cancellation, stale response rejection, polling and review drafts | Panels submit explicit actions and display server outcomes. Correction form state stays inside the dialog. |

The API composes dependencies once. Its routes translate HTTP requests, enforce access and pass explicit commands to application operations. The document reader still owns format handling and limits; the Jev adapter still owns provider calls and the shared spending guard. No provider policy or deterministic shipment comparison moved into React.

## Enforced checks

`uv run python scripts/verify.py` checks import boundaries, Ruff formatting/lint/complexity, strict Pyright, offline tests, API contract drift, Prettier, strict TypeScript, ESLint and the static production build. CI uses PostgreSQL and the same command. Tests may use larger scenario functions; runtime and script functions have a McCabe complexity limit of 15. This metric is a guard against oversized branching, not proof of good design.

Regression coverage includes database connections released before processing storage/parser/provider callbacks, malformed checkpoints failing without repeated inference, publication preserving reviewer state, stale/incomplete summary rejection and rejecting the same document in both pairing roles. Existing concurrency, recovery, format, budget and workspace-isolation tests remain in place.

## Deliberate limits

This cleanup does not change the database schema, provider requests, hosting, parsing limits or paid-call policy. Import/version writes and workspace cleanup retain their existing transaction/storage protocol; changing that safely needs an explicit durable orphan-cleanup design. Some HTTP read/session handlers still contain persistence queries. They do not own shipment comparison rules. The parser stays one cohesive module with private format implementations rather than being split merely to shorten files.
