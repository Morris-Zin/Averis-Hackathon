# External audit follow-up (20 September 2026)

Reviewed Pro's audit of bf4cfc4 against the newer multilingual release 4b7849a. Kept the existing module boundaries and deployment architecture.

## Fixes

- Party comparison treats spaced table-cell pipes and semicolon address separators as layout. Company punctuation and address numbers remain significant. The actual organizer email_055 XLSX/DOCX party values now compare equally; synthetic address-number changes still differ.
- Explicit `kgs` labels establish kilograms; unitless weights remain unresolved. `Not available` and conservative punctuation variants are missing values, never successful matches.
- Inline mixed-field PDF blocks are unresolved. Consecutive ordinary Word party paragraphs are grouped with their original paragraph locations. Sparse native headings over large page images enter bounded OCR instead of concealing a scanned body.
- New runs reread attachments from their immutable originals when the stored reader/OCR profile is old. Compatible checkpoints still avoid repeated work. Incompatible in-flight checkpoints fail visibly; manual retry starts a new run. Evidence fingerprints continue to bind corrections.
- The processing boundary rebuilds provider readings from selected evidence and machine provenance, retaining stricter provider uncertainty. Providers cannot supply authoritative text or normalized values.
- Structured issue scope and blocking flags survive the pipeline. Problems with unused attachments stay visible without invalidating a sound selected-pair comparison. Unknown legacy strings remain conservative.
- Open mismatches appear in Needs review, including cases persisted before this release. Completed/waiting cases remain in their respective workflow queues; findings remain available in Mismatches.
- New correction history stores before/after readings, evidence references, provenance and input revision. Existing historical entries remain readable; missing past detail cannot be reconstructed.
- Pair confirmation now records the reviewer's explanation. Unchanged proposed pairs can still be confirmed. Conflicting shipment identifiers remain blocked.
- Source images have loading/error states and manual retry. Field-specific uncertainty and structured report issues are visible instead of generic object text.

## Validation

- Full offline verification with real PostgreSQL: 309 backend tests passed, two environment-specific skips; 17 frontend tests; Ruff, Pyright, module boundaries, generated API drift, strict TypeScript, ESLint and production export passed.
- Sixteen focused audit regressions cover the actual organizer pair, address changes, missing markers, units, mixed labels, Word paragraph locations, OCR selection, outdated evidence, provider value fabrication, typed issue preservation, mismatch routing and two persisted correction transitions.
- All 58 supplied PDF/DOCX/XLSX attachments ran through current readers in an offline Linux container with one CPU and 1 GiB: 28.65 seconds. Two malformed PDFs remain explicit unreadable cases. This checks reader execution, not field extraction accuracy.
- Local browser testing uses deterministic intelligence, not Jev: Needs review includes the Chinese mismatch, Retry automatically returns to the same one-mismatch/six-match report, and the updated source form preserves Chinese email and document text.
- No paid inference calls for this work. No new independent accuracy percentage is claimed.

## Deliberate limits

General PDF column reconstruction and arbitrary Word layouts remain unsupported rather than guessed. The scan detector is conservative and bounded, not a guarantee that every image/text mixture is understood. OCR remains English-first. Old saved reports are not silently rewritten: Retry is required to apply new reading/comparison behavior.

Adding missing/revised attachments directly to an existing public case is still a separate feature; the existing operator revision path remains. Broader access quotas were previously removed at the user's request and were not reintroduced. We prioritized the reproduced correctness and review defects over extra features or a framework migration.
