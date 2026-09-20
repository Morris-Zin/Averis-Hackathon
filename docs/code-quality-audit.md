# Code quality audit — 20 September 2026

This audit builds on release `9fc8e2c` and the subsequent removal of application usage quotas. It does not change hosting or introduce new services. Publication was authorized after local verification; the evidence below records the pre-release checks.

## Scope and approach

Parallel reviews covered document reading/verification/reviewer workflow, durable processing/budget/provider boundaries, and frontend state/navigation. Integration review covered HTTP intake, storage, access boundaries, contracts, persistence projections and evaluation/export entry points. The goal was concrete correctness and simpler ownership, not reducing file length or adding extension frameworks. Organizer data and paid inference were not used for testing.

## Changes

- Uploads and document revisions share one attachment-preparation policy. Their blocking database, object-storage and dispatch work runs outside the async HTTP event loop. The intake module still owns deduplication and durable creation; HTTP callers only prepare input and pass an explicit budget purpose.
- Original storage reads are bounded for both local files and R2. Remote response streams close on both successful and failed reads.

- Processing eligibility belongs to `Processor`, shared by polling and HTTP delivery. Disabled work stays queued without consuming an attempt; completed duplicates remain acknowledged. Failed expired-workspace cleanup is logged without blocking run reconciliation.
- Shipment references stop at line boundaries and tolerate common table/punctuation delimiters. Repeated evidence selections are deduplicated before constructing readings.
- OCR corrections require explicit verification, including mixed native/OCR selections. Current-report and source-pair checks prevent a correction from promoting stale evidence. Unresolved issues from both documents remain visible.
- Frontend queue changes update the URL. Session changes have pending/error state shared with mutation controls. OCR evidence changes invalidate previous attestation; review tabs identify their panels.

## Acceptance evidence

Browser control against an isolated local SQLite workspace verified queue URL changes, refresh persistence and browser Back, a reviewer switch followed by a correctly attributed workflow-history entry, and a failed reviewer change while the test server was stopped. The failed change displayed an error and preserved the previous reviewer. A source-bound native correction also recomputed successfully while preserving the two real shipment mismatches and the employee's Waiting workflow state. No paid processing or production writes occurred.

Final `uv run python scripts/verify.py` with isolated real-PostgreSQL acceptance schemas passed **213 tests**, with two expected skips (Linux-only resource limit and separately opt-in natural-lease recovery). Module boundaries, Ruff formatting/lint/complexity, Pyright strict, generated API contract drift, frontend formatting/strict types/lint and production static export all passed. The existing Starlette/AnyIO deprecation warning remains. Browser OCR attestation interactions and deliberate slow-network race timing were not separately exercised; backend OCR verification regressions pass.

## Limits of this review

This is a code and local regression audit, not a production load test or enterprise-readiness certification. Upload/database cleanup still uses the existing compensating deletion protocol; making it resilient to a crash between object creation and metadata commit would require a durable orphan-cleanup design. No framework migration or new abstraction was added for that hypothetical extension.

Provider authentication and malformed-request failures currently use the same bounded application retry policy as transient failures. They never become matches, but error-specific early termination remains a possible improvement. Evaluation workspace grouping is retained for compatibility with saved manifests.
