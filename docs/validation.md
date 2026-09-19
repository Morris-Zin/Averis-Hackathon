# Validation record — 20 September 2026

This records local evidence, not a deployment or enterprise-capacity claim.

## Verified locally

- Latest full verification passed 126 tests with real PostgreSQL enabled (one Linux-only process cleanup test skipped on Windows), including concurrent budget reservation/settlement, stale-run rejection, shared demo cleanup, portable delivery and evaluation preparation.
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

## Still required

- Browser retest of active processing polling.
- Railway deployment and recovery checks; Cloud Run remains an undeployed alternative.
- Actual bounded pipeline evaluation, threshold freeze, independent holdout reporting and resource measurements. Existing tiny Jev experiments are not full-pipeline accuracy evidence.
- Fresh-browser public demo checks, submission materials and five-minute video.

## Cloud setup state

GCP project `averis-hackathon-509115` exists without linked billing. Railway deployment is now selected after the user delegated the hosting choice; account setup and worker delivery adaptation are in progress, not deployed. Neon free project `noisy-union-19187328` / database `averis` exists in Singapore. Cloudflare R2 is activated; bucket `averis-hackathon-documents` was created with Standard storage and public access disabled. Runtime storage credentials are not configured yet. The user approved scoped Terraform corrections; deployed infrastructure remains unverified.

## Spending evidence

The TypeSafe usage dashboard and ten saved experiment responses agree on 73,856 total tokens: 59,061 input and 14,795 output. At the displayed input price of $0.042 per million and free output, estimated prior cost is $0.002480562 (dashboard $0.0025). This is usage-derived estimated spending, not an invoice. No new paid calls were made during these implementation checks.
