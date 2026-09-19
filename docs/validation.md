# Validation record — 20 September 2026

This records local and deployed evidence, not an enterprise-capacity claim.

## Verified locally

- Full application verification passed 126 tests with real PostgreSQL enabled (one Linux-only process cleanup test skipped on Windows), including concurrent budget reservation/settlement, stale-run rejection, shared demo cleanup, portable delivery and evaluation preparation.
- Checks passed: Ruff, strict Pyright, module boundaries, tests, OpenAPI/generated TypeScript drift, frontend types/lint and production Next.js static export. PostgreSQL migration head is a83d6f9e2741.
- Built image `averis:test` runs as UID 10001, includes Tesseract 5.5.0 and the static frontend/migrations.
- The image processed all supplied PDFs with networking disabled and limits of one CPU/1 GiB. After the multiline OCR fix, all six scanned SI/BL documents (512–514) returned 5–8 evidence blocks each, retaining image coordinates with no reader issues. Malformed BL PDFs 511 and 515 returned explicit unreadable errors. This proves reading/location support, not field-selection accuracy.
- Both process-tree cleanup regressions passed in the rebuilt Linux container, including a descendant ignoring SIGTERM. The Windows Job Object counterpart passed in the backend suite.
- Browser acceptance through the real local API verified isolated demo entry, mismatch routing, evidence selection and source-bound correction. Reading the original count of four preserved the mismatch against SI count three. Cases created after the static build opened through the query-based review route.
- Fresh browser workspace showed all eight scenarios covering five categories. Moving a mismatch to Waiting preserved both findings. Attaching a controlled revised draft created a new version, recomputed all seven fields and retained workflow/revision history. Fixed and browser-retested a blank BL selector after revision; it now follows the new accepted pair without enabling a redundant recompute.
- Browser session-expiry check passed against real PostgreSQL: after expiring only the test workspace session, a revision action returned unauthorized and the UI cleared case content and displayed the expired-session welcome. Fixed and browser-retested new-workspace entry from an old review URL: it navigates to the fresh eight-case queue.
- Export regressions verify incomplete ID sets do not create fabricated official submissions, coverage counts missing rows as abstentions, and illustrative demo results cannot masquerade as automatic inference.
- Two independent browser sessions deliberately shared a local synthetic workspace. A stale workflow edit was rejected, the first edit remained intact, and both mismatches remained visible. Fixed and browser-retested the conflict explanation so it survives the automatic refresh and explicitly says the second change was not saved.
- The portable PostgreSQL worker passed 17 focused processing/runner tests, including eligible work behind 256 delayed rows and recovery from transient claim failures without logging sensitive error bodies.

Latest backend verification after the worker, TXT evidence and identifier fixes passed 135 tests with one platform skip, plus Ruff, strict Pyright and module boundaries. Operator cases retain their development budget purpose across retries; disabled processing leaves queued work untouched.

## Still required

- Full dataset evaluation remains incomplete. A corrected 20-email development batch is recorded in [evaluation results](evaluation-results.md).
- Deployed interruption/recovery and resource measurements; Cloud Run remains an undeployed alternative.
- Actual bounded pipeline evaluation, threshold freeze, independent holdout reporting and resource measurements. Existing tiny Jev experiments are not full-pipeline accuracy evidence.
- Submission materials and five-minute video.

## Deployed acceptance

Public URL: https://averis-hackathon-production.up.railway.app/

Railway web and private polling worker are online, one replica each, using Neon PostgreSQL and private R2. Fresh-browser entry created eight cases covering all five categories. Workflow changes persisted after refresh. An authenticated document request returned 200; another workspace received 404 and an anonymous request received 401. Session cookies use Secure, HttpOnly and SameSite protections.

A real Jev run completed in one attempt and published the expected port and container-count mismatches with source evidence. This is a smoke test, not a dataset accuracy result. A second live case completed with all seven matching fields; the browser updated from running to completed without refresh. GitHub CI and both Railway deployments passed for 2ca90ee.

## Spending evidence

Before enabling production inference, the TypeSafe dashboard showed 13 requests and 74,941 total tokens, with displayed estimated cost $0.0025. The ledger conservatively accounts $0.003148 for prior use by treating all those tokens as paid input at $0.042 per million, rounded upward. The first deployed comparison settled $0.000214 in the demo bucket. Shared accounted total at that checkpoint: $0.003362 of the $7 ceiling. These are usage estimates and ledger reservations, not an invoice.
