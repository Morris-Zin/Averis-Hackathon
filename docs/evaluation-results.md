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

## Full development baseline (classification-v2, pre-PDF correction)

All 423 development runs completed; one provider timeout recovered on its second substantive attempt using the same run. The 97 holdout cases remained held. No reviewer corrections were applied.

| Measure | Result |
|---|---:|
| Suggested category agrees with organizer | 408 / 423 (96.45%) |
| Accepted category agrees with organizer | 345 / 349 (98.85%) |
| Category abstentions | 74 |
| Automatically exportable rows | 337 / 423 (79.67%) |
| All export blockers / abstentions | 86 |
| Exact organizer row agreement among exported rows | 244 / 337 (72.40%) |
| Representable comparable pairs with exact seven-field results | 58 / 58 |

The last row covers only those 58 exportable comparisons, not all document requests. The 86 blockers comprise 74 unresolved categories, nine unresolved pairings, and three mixed mismatch/unknown reports that the official format cannot honestly represent.

Among exported disagreements, 74 source emails have no attachments but the organizer expects OK. Fifteen are document-role review outcomes requiring further reader/extraction work; four are accepted-category errors. The unchanged scorer and abstention-aware diagnostics are saved separately in `outputs/evaluation-linux-v4/development-report`. The baseline precedes the isolated native-PDF/OCR corrections; do not label it final-version accuracy.

Observed evaluation-container samples reached 246.7 MiB and 76.89% CPU within its one-CPU/1GiB limit. Sampling began after initial cases and is not a guaranteed peak measurement or a production capacity result.

## Post-development evaluation v1 (frozen extraction-v2)

All 97 selected runs completed without failed or incomplete processing. This uses classification-v2, extraction-v2 and evidence-v2, with unchanged category/Spam/field thresholds. No reviewer actions were included. See the prior-exposure disclosure above; these are not formally blinded results.

| Measure | All 97 | Excluding known prior examples (94) |
|---|---:|---:|
| Suggested categories correct | 91/97 (93.81%) | 88/94 (93.62%) |
| Accepted categories correct | 85/88 (96.59%) | 82/85 (96.47%) |
| Automatic export coverage | 75/97 (77.32%) | 73/94 (77.66%) |
| Abstentions/export blockers | 22 | 21 |
| Exact row agreement among exports | 43/75 (57.33%) | 42/73 (57.53%) |

The 22 blockers comprise nine unresolved categories, eight mixed mismatch/unknown reports, two unresolved pairings and three unrepresentable review reasons. The unchanged organizer scorer ran offline alongside these diagnostics. Its missing-category defaults mean the partial-output score is not a full-submission accuracy score. Artifacts: `outputs/holdout-linux-v1/full-97` and `prior-exposure-excluded-94`.

This run exposed an extraction prompt regression: requiring a party's name **and full address** incorrectly rejected name-only notify-party entries. There were 23 unresolved notify-party findings. This is an application defect, not an organizer-label disagreement. Extraction-v3 now asks for the party name and any address actually supplied. A targeted development component check on email_004 recovered the expected consignee and notify-party mismatches with the other five fields matching. It bypassed classification and does not establish end-to-end accuracy. Any rerun of these 97 examples after the fix is reused validation data, not a fresh holdout.

## Corrected rerun (extraction-v3; reused validation data)

The same 97 records were rerun after the name-only party fix. All completed; one interrupted provider request recovered through its existing run and checkpoints. This is a regression-validation rerun, **not an independent holdout**. No reviewer corrections were applied.

| Measure | All 97 | Excluding three previously exposed examples (94) |
|---|---:|---:|
| Suggested categories correct | 91/97 (93.81%) | 88/94 (93.62%) |
| Accepted categories correct | 85/88 (96.59%) | 82/85 (96.47%) |
| Automatic export coverage | 84/97 (86.60%) | 81/94 (86.17%) |
| Abstentions/export blockers | 13 | 13 |
| Exact organizer row agreement among exports | 64/84 (76.19%) | 61/81 (75.31%) |
| Fully comparable exportable pairs with all seven fields correct | 22/22 | 20/20 |

The last row excludes unresolved and unexportable comparisons; it is not accuracy across every document request. The 13 blockers comprise nine unresolved categories, two ambiguous pairings and two mixed mismatch/unknown reports. The 20 exported disagreements comprise 17 missing-attachment review outcomes and three incorrect GENERAL classifications. The missing-attachment cases retain the same source-versus-label disagreement described above; no ID-specific override was added. Artifacts: `outputs/validation-linux-v2/full-97` and `prior-exposure-excluded-94`. The unchanged official scorer was run separately on partial exports, with its missing-category behavior explicitly disclosed.

After these runs, the shared ledger accounted for $0.161933 including prior experiments, development reservations and demo usage. This includes retained uncertain-charge reservations; it is not a provider invoice. The combined $7 ceiling remains in force.
