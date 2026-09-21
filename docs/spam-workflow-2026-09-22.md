# Spam routing and recovery

Implemented 22 September 2026. This is an operator workflow change, not improved classification accuracy or phishing/forgery detection.

Accepted SPAM and unaccepted SPAM suggestions appear in the Spam queue. Unaccepted suggestions show **Suspected**. Human category choices take precedence over the original suggestion. All cases remains an inclusive archive; Mismatches, Needs review, Waiting and Completed exclude spam. The sidebar shows workspace-wide Spam and outstanding Needs review counts, independent of search, category filters and pagination. The SPAM category filter includes suspected spam.

**Not spam** preserves source text, attachments, report and the original suggestion/probabilities/model. It records a reviewer action, increments the input revision to fence late processing results, reopens the workflow and leaves the accepted category empty. The category control then requires an explicit choice. The existing pipeline preserves human decisions through retries. Selecting BL_COMPARISON follows the existing comparison/review path; missing documents cannot become a match.

The domain assessment retains uncertainty and blocking reasons. Queue routing is separate from evidence completeness: an unaccepted category remains blocked in export even while outside the daily review queue. Operational `needs_review` metrics now count outstanding open non-spam work, using the same predicate as the review queue. No threshold, model, five-category contract, source document or export acceptance rule changes.

Persistence uses the existing JSON classification: a human decision with no accepted category records rejection without inventing a sixth category. SQL queue predicates and the pure summary rule have parity tests. Queries read existing stored state directly, so no migration, backfill or new inference is required. These JSON predicates have not been benchmarked at large mailbox scale.

## Verification

- Full offline verification with isolated PostgreSQL schemas: 555 backend tests passed, three optional/platform skips; frontend tests, strict Python/TypeScript checks, lint, formatting, module boundaries, generated API contracts and static production build passed. Final frontend suite contains 26 tests.
- New regressions cover accepted/unaccepted spam, human override precedence, SQL/domain parity, independent counts, category filtering, preserved state/history, optimistic conflicts, Not spam recovery from completed workflow, retry preservation without inference, blocked export and safe BL comparison recovery. The full API recovery scenario also runs against PostgreSQL.
- A headed Chromium browser used the built frontend and real local API with an isolated SQLite workspace. Controlled fixtures: one confirmed spam, one suspected spam and one legitimate unaccepted invoice, alongside the normal saved shipment examples. Initial Spam count 2 / Needs review count 4; both spam messages were absent from Needs review, while the invoice and shipment mismatches remained.
- Browser Not spam recovery for both messages persisted after refresh: Spam 2 → 1 → 0, Needs review 4 → 5 → 6. History and original AI suggestions remained visible. Accept category was disabled until a category was chosen. Choosing Shipping instruction check retained Needs review with “Select the correct SI and draft BL,” rather than producing an all-clear.
- No paid provider calls. No production deployment or accuracy evaluation. Bulk actions and new sorting controls are outside this change; existing category filtering remains available. Browser fixture artifacts remain local under `.local` and `.playwright-cli`.
