# Attachment context for uncertain email classification

When the filename-assisted classification remains below the existing confidence
threshold, Averis can now read attachment text before deciding the category.
The existing email-only and filename steps remain unchanged. An accepted result
does not trigger this extra reading. Human category decisions always take priority.

## Behaviour and boundaries

The intelligence interface accepts a lazy attachment-preview loader. Jev owns the
decision to request context and the classification prompt; the shipment pipeline
owns document access and reusable reading checkpoints. This avoids provider rules
in HTTP routes or UI components. Existing reader/OCR, provider and deadline failures
remain visible through the worker's failure and retry handling.

The fallback supports at most four current attachments, with at most 2,000 source
characters per preview. Superseded files are excluded. Reading uses the existing
bounded parser/OCR path; it is a full supported read followed by a small text preview,
not a new partial PDF parser. Completed reading is reused for extraction and retries.
Prepared evidence stays available in Sources even when the category needs review
or is not a shipping comparison.

Blocking reading issues and OCR text below 0.80 confidence cannot supply trusted
preview context. Missing or unusable previews, too many attachments, and uncertain
final judgments leave classification unaccepted for human review. Truncation is
explicit. This no longer hides a conflicting uncertain answer behind the earlier
confident General result. No thresholds were lowered: category 0.80, Spam 0.95.

Previews are untrusted context, not instructions. A sender merely sharing SI/BL
documents for records is not requesting comparison. Classification never confirms
document roles, shipment identity, or matching fields. Field extraction still reads
SI and BL independently; deterministic comparison and pairing safeguards are unchanged.

Policy: `classification-v5-document-context`. Existing completed cases require
Retry to use the new policy. Compatible document checkpoints remain reusable.

## Experiment

Compared against filename-only behaviour from `bde27d8`. Forty-four synthetic emails
and their expected categories were frozen before inference: 24 development examples
and 20 reserved examples. The reserved set was run once without subsequent prompt
tuning. Jev 1.13.0 received email text and previews, never the evaluation labels.

| Set | Previous correct automatic categories | Candidate correct automatic categories | Previous wrong / review | Candidate wrong / review |
|---|---:|---:|---:|---:|
| Development, 24 emails | 19 | 23 | 2 / 3 | 1 / 0 |
| Reserved, 20 emails | 16 | 20 | 0 / 4 | 0 / 0 |

Eight improvements and no observed regressions. One extremely vague email remained
wrongly General because the earlier classifier was confident; the fallback never
ran. This is not a solution for confident mistakes. Examples include English, Malay,
Chinese, records-only and cancelled requests, quoted messages, invoice/SI/Spam
controls, and malicious instructions inside attachments.

Runtime replay reproduced the 44 saved decisions. The previous 56 filename examples
also retained their accepted categories: 55 used identical saved responses, while
one newly eligible case needed newly supplied synthetic document contents because
the original experiment had filenames only. That extension remained General despite
malicious filename/document instructions. It is separately labelled, not presented
as an unchanged original document benchmark.

The existing 720-email regression benchmark did not trigger the new fallback.
Recorded-inference replay retained 581 exact outcomes and 1,524/1,540 synthetic field
values, with no protected regressions. Organizer exact results remain 411/520; this
feature does not increase that score. No new organizer-wide AI run was performed.

These examples and labels were created by the same agent, with no independent
bilingual review. Small synthetic tests and reused benchmarks do not establish
real-world accuracy or guarantee absence of regressions.

## Validation and cost

Full verification passed 486 backend tests (two optional tests skipped), 21 frontend
tests, strict typing, lint, module boundaries, generated-contract checks and the
production frontend build, using real PostgreSQL for transactional checks.
New tests cover lazy loading, unreadable/weak OCR, preview limits, retained uncertainty,
source retention across resume, and reading once before field extraction.

The 44-example experiment increased the development ledger by $0.003330. Browser
acceptance and the additional legacy-content judgment are separate usage. All paid
requests use the existing shared budget authority; ordinary CI remains offline.

Evidence is saved locally in `.local/content-classification/` and
`outputs/benchmarks/2026-09-21-content-candidate/`. Frozen inputs, separate labels,
provider responses, source snapshots and regression reports remain outside runtime
images. Older copied manifests describe inherited benchmark evidence; the content
release manifest identifies this change.

The new `classification_preview_documents` counter distinguishes context reading.
Non-comparison cases can now have parser activity when classification needed context;
do not infer zero reading from the existing shipment-processing skip counter alone.
