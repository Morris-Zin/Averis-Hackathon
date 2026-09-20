# Validation record — 20 September 2026

This records local and deployed evidence, not an enterprise-capacity claim.

## Verified locally

- After the module cleanup, full application verification passed 190 tests with real PostgreSQL enabled. Two tests were skipped: Linux-only process cleanup on Windows, and the opt-in natural-lease test, which separately passed in 92.75 seconds before this cleanup. Coverage includes concurrent budget reservation/settlement, stale-run rejection, shared demo cleanup, portable delivery and evaluation preparation.
- Cleanup acceptance additionally verifies malformed checkpoint failure without repeating inference, database connection release during source reads, reviewer-state preservation, complete/current result summaries and distinct SI/BL selection. Python/TypeScript formatting and Python complexity checks now run in the same verification entry point. A fresh local browser workspace verified the refactored correction, revision, evidence and activity flows without paid calls.
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

The earlier backend verification after the worker, TXT evidence and identifier fixes passed 139 tests with one platform skip, plus Ruff, strict Pyright and module boundaries. Operator cases retain their development budget purpose across retries; disabled processing leaves queued work untouched.

## Still required

- Development evaluation and reused-validation runs are complete and disclosed in [evaluation results](evaluation-results.md). There is no independent final holdout accuracy claim.
- Sustained deployed load/capacity testing remains outside the measured acceptance scope; Cloud Run remains an undeployed alternative.
- Submission materials and five-minute video.

## Deployed acceptance

Public URL: https://averis-hackathon-production.up.railway.app/

Railway web and private polling worker are online, one replica each, using Neon PostgreSQL and private R2. Fresh-browser entry created eight cases covering all five categories. Workflow changes persisted after refresh. An authenticated document request returned 200; another workspace received 404 and an anonymous request received 401. Session cookies use Secure, HttpOnly and SameSite protections.

A real Jev run completed in one attempt and published the expected port and container-count mismatches with source evidence. This is a smoke test, not a dataset accuracy result. A second live case completed with all seven matching fields; the browser updated from running to completed without refresh. GitHub CI and both Railway deployments passed for 2ca90ee.

## Spending evidence

The current `ad3335d` release was deployed successfully to both Railway services and rechecked through the public browser on 20 September. A controlled clean comparison progressed through live classification and extraction to seven matches in one attempt, without browser refresh. The shared ledger afterward accounted for $0.162180: prior $0.003148, development $0.158357, demo $0.000675. This is a current-release smoke test, not dataset accuracy or a provider invoice.

Before enabling production inference, the TypeSafe dashboard showed 13 requests and 74,941 total tokens, with displayed estimated cost $0.0025. The ledger conservatively accounts $0.003148 for prior use by treating all those tokens as paid input at $0.042 per million, rounded upward. The first deployed comparison settled $0.000214 in the demo bucket. Shared accounted total at that checkpoint: $0.003362 of the $7 ceiling. These are usage estimates and ledger reservations, not an invoice.

## Deployed recovery acceptance

On 20 September, the live Railway polling worker recovered an isolated synthetic run with an expired lease, one abandoned attempt and a persisted GENERAL classification checkpoint. It completed on substantive attempt two in 6.25 seconds, with zero AI reservations for that run. Its workspace expires after 24 hours. This deliberately seeded state verifies deployed lease recovery and checkpoint reuse; it is not an actual platform crash or a capacity test. This result is separate from the later local process-crash and full-duration reader-resource checks below. CI and worker deployment succeeded for 451afc9.

## Document reliability update

Full local verification after evidence-v2 and extraction-v2: 149 tests passed, one Linux-only test skipped on Windows; PostgreSQL tests, Ruff, strict Pyright, module boundaries, OpenAPI/TypeScript drift, frontend types/lint and production build passed. Native PDF evidence now separates field headings while preserving multiline locations. OCR word quality is retained separately from model confidence; missing or low quality requires review. Mixed or wrong-field evidence cannot become a trustworthy reading.

A Linux component check on development scan email_512 produced six unresolved fields and one match, replacing prior false port mismatches. This bypassed email classification and is a component result, not automatic end-to-end accuracy. The earlier native-PDF component email_059 produced seven matches. Subsequent evaluation exposed a name-only party extraction defect; extraction-v3 and the explicitly reused validation results are recorded in the evaluation report.

## Completion-audit checks

The expanded full verification passed **165 tests**, with one Linux-only process-limit test skipped on Windows, plus Python/frontend strict checks, lint, API contract drift and production build. At that revision, PostgreSQL checks covered the former usage quotas. Those quotas and their rejection tests were subsequently removed at the user's request; they are not current behavior. Fake-clock checks reject late processing publication; parser/provider callback checks observe no checked-out database connection on the processing thread (the independent lease heartbeat is excluded).

Document boundary tests cover PDF/OCR page caps, expanded archives, XLSX limits, reader/preview deadlines and visible unsupported-format processing outcomes. See [supplied-format evidence](format-validation.md).

A full-duration offline Linux reader workload processed all 58 supplied PDF/DOCX/XLSX files sequentially with one CPU and a 1 GiB container limit in 24.074 seconds. Kernel process high-water measurements were 32,056 KiB for the parent and 89,952 KiB for the largest child; they are reported separately, not as a measured concurrent aggregate peak. Parent CPU time was 0.409 seconds and cumulative child CPU time 22.548 seconds. Evidence: `outputs/reader-profile.json`. No AI or ground truth was used. This closes the bounded local reader-profile measurement, not deployed load/capacity testing or a real process-crash exercise.

The workload included six documents with OCR evidence. Two PDFs (`email_511_BL.pdf` and `email_515_BL.pdf`) returned explicit `document_unreadable:PdfminerException` issues; processing the workload does not mean every input was readable. All nonempty evidence blocks had locations.

The review layout was browser-checked at 950 pixels after moving Details below the comparison at narrow desktop widths; the temporary viewport was reset afterward.

## Actual process-crash recovery

Final audit follow-up: accepted PNG/JPG/JPEG inputs now share bounded OCR and single-page preview support, with format signatures and image-size checks. HTTP acceptance covers chunked multipart transport rejection, the exact 10 MB attachment boundary, concurrent preview rejection and semaphore release after render errors. `/health` now reports liveness and configuration flags only, without implying dependency or worker readiness. The complete 177-test verification, generated contracts and production frontend build passed after these changes.

A local PostgreSQL acceptance test killed the worker OS process after its classification checkpoint was committed, then started a fresh process after the real lease expired. The natural-expiry run passed in 92.75 seconds, including 89.969 seconds waiting for the persisted lease. Attempt two completed with exactly one classification call across both processes, and the stale report stayed cleared. This used deterministic offline intelligence and no paid calls; it is an actual local process interruption, not a Railway outage simulation.

The default regression performs the same OS kill and explicitly advances lease expiry to keep CI fast. Run the natural variant with `AVERIS_RUN_NATURAL_LEASE_ACCEPTANCE=1`; its evidence is saved in `outputs/process-crash-recovery/natural-expiry.json`. Database credentials reach children through their environment, not command arguments.

## Current hosting observation

Railway CLI observations on 20 September reported $0.004773 current workspace usage, approximately 114 MB current web memory and 104 MB worker memory, against 1 GiB per-service limits. These are point-in-time measurements under light demo traffic, not throughput or sustained-load results. The billing estimate field was lower than current usage and was not used for forecasting.

Railway rejected an attempted spending email alert: the minimum is $5, and usage limits require an active subscription. The trial has no configured spending alert; no paid subscription was purchased. This is an external account limitation. It does not weaken the separate atomic Jev $7 application ledger. Recheck trial availability before judging.


## Local balanced code-quality audit (20 September)

After the local quota removal, a parallel domain/processing/frontend audit and integration fixes passed full verification: **213 passed, 2 expected skips**, all strict/lint/boundary/contract/build gates. Browser control verified queue URL/refresh/back, reviewer attribution and failed switch handling, plus source-bound correction retaining real mismatches. See [audit details and limits](code-quality-audit.md). Publication was subsequently authorized. These are local acceptance results; previous deployed measurements remain historical.
