# Jev + DeepSeek field-reading evaluation

The selected change keeps Jev classification and document-role decisions. DeepSeek V4.1 Flash helps only when a document has unresolved field readings. The application still copies original source blocks and performs normalization and SI/BL comparison in code. No generative model decides whether a shipment matches.

## Measured results

Same 720 emails and 512 document inputs as deployed baseline `4c8b2ae`: 520 organizer, 15 Chinese friend, 15 Malay friend, and 170 synthetic emails. Classification responses and prepared evidence were frozen. Two documents had no readable evidence and were not sent to DeepSeek.

| Candidate | Exact email outcomes / 720 | Exact synthetic field values / 1,540 | Regression gate |
|---|---:|---:|---|
| Deployed Jev baseline | 532 (73.9%) | 1,288 (83.6%) | Reference |
| DeepSeek text extraction | 566 (78.6%) | 1,320 (85.7%) | Rejected: five regression records |
| Both models must agree | 542 (75.3%) | 1,288 (83.6%) | Rejected: four role regressions |
| Guarded fallback including roles | 560 (77.8%) | 1,304 (84.7%) | Rejected by conservative export-retention gate |
| **Selected: Jev roles + guarded field assistance** | **542 (75.3%)** | **1,304 (84.7%)** | **No protected-case/value losses** |

The selected policy retained all 532 previously correct email outcomes and all 1,288 previously correct synthetic values. No new false field matches, false complete clears, or false field alarms appeared in the saved regression comparison. The actual production adapter and pipeline reproduced these results; 210 of 512 documents required supplemental selection. Complete Jev readings skip the additional call.

All ten additional exact email outcomes are synthetic cases. Organizer exact outcomes remain **398/520 (76.5%)**; do not present this release as an organizer accuracy increase. Existing missing-attachment disagreements and conservative pairing holds remain. The selected policy is a follow-up derived after inspecting the first three candidates, not an untouched initial hypothesis.

The fallback-with-roles candidate's three export losses need interpretation: previously exported NEEDS_REVIEW rows used `wrong_doc_type`, while better role recognition revealed unresolved pairing or other issues that the official schema cannot represent. We retained the conservative gate and did not fabricate export labels or silently call these rows completed.

## Fresh and operational checks

- A new, frozen 24-document text set covers eight scenario families in English, Chinese and Malay: ordinary fields, full addresses, tonnes, zero, missing weight, net-weight distractors, container-size distractors, and embedded instructions. Both providers and the selected combination correctly handled all 168 expected fields. These are agent-authored, closely related synthetics, not independent human-validated accuracy evidence.
- A separate, preselected 24-document live stability check exercised the production adapter on hash-ordered unresolved inputs. It produced no supplemental failures or previously correct value losses and added 16 dependable synthetic field readings. Responses were not resampled to obtain preferred answers.
- Strict response schemas reject incomplete field sets, foreign/duplicate source IDs and unsupported presence assertions. Core source checks, OCR uncertainty, pairing, revisions and human corrections remain authoritative.
- DeepSeek confidence is `null`; `acceptance_basis=explicit_source` records the policy. The UI says “Selected by DeepSeek · source checks passed,” never a fabricated percentage. Conflicting selections retain the alternative source IDs and request identity for review.
- One non-thinking fallback is allowed only after a truncated high-thinking response. Missing/uncertain answers and model disagreements do not trigger retries. The original text experiment had eight truncations; all eight technical fallbacks completed. Initial attempts and their costs remain saved.
- On supplemental failure, supported Jev readings remain usable. Original unresolved reasons remain, with a separate visible assistance error. A manual retry creates a new processing run. Provider-profile changes cannot silently reuse old extraction checkpoints.

## Separate vision experiment — not enabled

102 scan/image-bearing documents were tested independently from the text comparison. Four truncated responses recovered through the same bounded non-thinking fallback; six responses still failed the strict schema. Model-generated text and boxes remain unverified and do not enter automatic production comparisons.

For the 96 synthetic image documents, counting schema failures as failures:

| Language | Existing OCR + Jev exact raw values | DeepSeek vision exact raw values |
|---|---:|---:|
| English | 224/224 | 203/224 |
| Malay | 192/224 | 217/224 |
| Chinese | 4/224 | 210/224 |

These are transcription/value measurements, not safe automatic case-completion results. Chinese vision is promising, but the English regression and unverified source regions prevent promotion. Production OCR remains English-only.

## Accounting and reproducibility

Research inputs, prompts, hashes, original and fallback responses, failures, per-case comparisons, unchanged official scorer, costs and the production replay are saved under the ignored `outputs/benchmarks/2026-09-21-deepseek-*` and `2026-09-21-hybrid-*` directories. Local experiment scripts live under `.local/deepseek-research/`. Ground truth is evaluation-only and is not read by inference or packaged into runtime images.

The initial DeepSeek research ledger records 648 calls with a conservative peak-price estimate of **$1.4661**, including unsuccessful attempts. Account balance snapshots are rounded and can lag settlement; they are not used as per-call precision claims. Fresh Jev and production-adapter/live deployment checks use the shared atomic application ledger and are additional to that research estimate.

Runtime DeepSeek requests reserve at verified peak prices of $0.30/million input and $1.20/million output tokens. Cache/off-peak discounts are deliberately not assumed. Reservations retain uncertain costs. Supplemental calls use the existing $7 combined runtime guard, preserving the stricter ceiling instead of mispricing them at Jev rates. No daily or per-session run quotas were added.

To enable on an existing deployment, set server-only `DEEPSEEK_API_KEY` and `AVERIS_DEEPSEEK_FIELDS_ENABLED=true` on both web and worker services. Default is disabled. No database migration is required. Disable the flag to return to Jev-only extraction; old incompatible in-flight checkpoints fail visibly and require a new retry.

Browser acceptance also exposed the existing preview semaphore rejecting the second of two simultaneous SI/BL previews. The endpoint now waits up to 20 seconds for the same single renderer; memory/process concurrency remains bounded. A concurrent-request test covers serialization, failure cleanup and timeout rejection.

References: [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/), [vision](https://api-docs.deepseek.com/guides/vision/), [pricing](https://api-docs.deepseek.com/quick_start/pricing/). Pro reviewed the acceptance/provenance approach; measured tests determine the release decision.
