# Development evaluation — 20 September 2026

This is an initial development sample, not holdout accuracy or a full submission.

The organizer bundle contains 520 emails. Deterministic SHA-256 membership assigns 423 to development and 97 to holdout. No holdout inference was run in this evaluation. Earlier exploratory experiments used some organizer examples, so the split must not be described as wholly unseen until those IDs are accounted for.

An initial development run exposed adjacent TXT labels being merged into one evidence block and unrecognized booking-reference labels. It was stopped after 26 completed cases; partial in-flight charges remain conservatively accounted for. These findings led to general parsing and identifier fixes, not per-email answer rules.

The corrected run processed the first 20 development members through the real Processor and Jev integration inside the application container (one CPU, 1 GiB memory), using isolated cases/storage and the authoritative production budget ledger. Ground truth was not mounted into the runtime container. Local artifacts are in ignored `outputs/evaluation-linux-v2`.

- 20 processing runs completed.
- 11/20 cases had representable automatic exports (55% coverage); nine abstained because category confidence was below policy.
- 10/11 accepted categories matched organizer labels. Suggested categories matched 13/20 labels. Neither measure is representative of the full dataset.
- Both comparable SI/BL pairs yielded expected mismatch fields after the fixes.
- Six exported rows exactly matched all organizer fields. Four document-review outcomes disagree with organizer OK labels and require source/rubric investigation; one accepted category was wrong.
- The unchanged official scorer ran separately against this development subset and partial predictions. It defaults absent categories to GENERAL, so its diagnostic score is not presented as automatic accuracy or an eligible full submission.

Thresholds remain category 0.80, Spam 0.95 and field 0.80; model jev-1.13.0. Finish development diagnostics and freeze the final policy before holdout evaluation. No reviewer-assisted corrections were included.

## Source-level disagreements

Development emails 006, 016 and 018 explicitly request that a draft BL be sent for checking; their source JSON attachment arrays are empty. The organizer labels them BL_COMPARISON / OK. Averis retains BL_COMPARISON and routes to missing-attachment review because there is no SI/BL pair to verify. We do not special-case these IDs or infer a successful document check from an absent pair. Email 005 is a separate XLSX reading/inference investigation, not yet a confirmed dataset disagreement.

## Classification policy v2 development check

A fresh run of the same 20 development members used clearer intent definitions, prioritizing the current body over stale subjects and distinguishing supplied SI details from a draft BL check. Thresholds were unchanged. All 20 suggested categories matched the labels; all 14 accepted categories were correct; six cases abstained (70% automatic export coverage). This reused development sample informed the prompt and is not independent evidence. XLSX worksheet titles are now included as evidence, but email 005 abstained at classification in this run, so the role fix is not yet verified through live extraction. Artifacts: `outputs/evaluation-linux-v3`.

## Holdout provenance

The 97-member deterministic holdout overlaps earlier exploratory Jev calls for three source IDs: email_001, email_002 and email_025. Email_002 also has its organizer category persisted in the earlier experiment report. The earlier scorer loaded the full truth file after inference; that does not show the model received it, but rules out a claim of formally blinded experimentation. Report the complete 97-member holdout and a separate 94-member subset excluding these three known exposed examples. Describe both as post-development evaluation with disclosed prior exposure, not an independently controlled benchmark. The Malay/Mandarin experiment used authored synthetic examples and adds no organizer-ID overlap.
