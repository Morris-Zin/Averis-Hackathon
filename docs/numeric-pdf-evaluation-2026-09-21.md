# Reading joined numeric fields in PDFs

Native PDF extraction sometimes joins container count and gross weight in one
source block. Damaged labels such as `Gross Weightnn` then prevent safe numeric
parsing. The new fallback lets Jev select exact numeric source spans; code still
parses numbers, converts explicit units and compares SI with BL independently.

It runs after the existing Jev/DeepSeek extraction, only for confidently selected
but unparseable numeric readings in native PDFs. Successful readings are preserved.
It does not handle scans, infer kilograms, add item weights, lower pairing
confidence, or use one document's expected values to read the other document.

## Measured comparison

Baseline: deployed `911f0d2`, pairing threshold **0.95**. The rejected 0.90
experiment was not included. The intervening display-only `0666945` exposes
unconfirmed readings but does not change comparison outcomes.

| Measure | Baseline | Numeric fallback |
| --- | ---: | ---: |
| Correct complete case outcomes, saved 720-email benchmark | 575 | 581 |
| Correct organizer case outcomes, 520 emails | 405 | 411 |
| Official scorer's weighted score | 88.34% | 91.36% |
| Correct supported organizer defect exports, 46 defect cases | 38 | 40 |
| Incorrect complete all-clear reports | 0 | 0 |
| Previously correct protected cases/fields regressed | — | 0 |

Six cases improved. Eight PDFs recovered both numeric readings: organizer 160
(SI), 208 (SI and BL), 273 (BL), 313 (BL), 351 (SI), and 411 (SI and BL).
The synthetic exact-value measure stayed 1,524/1,540. Classification, pairing,
document roles, original reader evidence and all non-numeric selections were reused
unchanged. Six new provider requests were needed; two identical development
requests were replayed. Answer sheets were used only for scoring.

For example, organizer 313 now reports SI **5 containers / 118,270 kg** versus BL
**4 containers / 117,770 kg**, flagging both fields. Organizer 351 reports SI
**15 / 359,415 kg** versus BL **16 / 360,415 kg**. Original joined source blocks
remain available beside the rendered PDFs.

## Fresh safety check and limits

Development used two known organizer failures and 22 newly authored prepared-text
documents. At the initially tried numeric confidence of 0.95, 32/48 decisions were
correct. Reusing the application's existing field threshold of **0.80** gave
41/48; that choice was made on development data, not reserved answers. Pairing
stayed 0.95 throughout.

A separate 28-document, 56-field set was frozen before calls and tested once:
**52 correct decisions, four unnecessary abstentions, zero accepted wrong values**.
It covered conflicting counts, equipment sizes, net/tare/per-container weights,
unconfirmed quantities, different shipments, missing units, Chinese/Malay labels,
and instructions embedded in documents. The runtime adapter reproduced all saved
reserved decisions offline. These are synthetic prepared-text checks, not an
independent real-world accuracy estimate or an OCR benchmark.

Reserved-test development spend was **$0.000982**; the six new benchmark calls
cost **$0.001131** according to the shared ledger. The initial development probe's
start/end ledger files were overwritten during a no-op resume, so those two files
cannot establish its incremental cost. Raw token usage remains saved, and all calls
went through the shared budget authority. No paid calls run in ordinary tests.

The fallback adds one optional provider request only for eligible failed numeric
readings. The original benchmark timing figures are not a measurement of its
deployed latency. It deliberately abstains on some clear decimal-tonne and Malay
examples; existing successfully parsed values are not replaced by this fallback.

## Implementation and validation

`numeric_evidence` owns bounded candidate generation and source-span validation;
Jev owns semantic selection; the pipeline independently rebinds every selected
span before saving. Provider-generated values cannot become authoritative. Missing
units and source uncertainty remain review outcomes. Supplemental provider failure
preserves the original readings and records an assistance error.

Backend verification passed **450 tests, two intentional skips**, using real
PostgreSQL. Frontend strict types, lint, **21 tests**, production static build,
generated API contracts and module-boundary checks passed. Fifteen new backend
tests cover source spans, forged references, units, confidence, candidate bounds,
provider failures and pipeline rebinding. One new frontend test covers selected
numeric display.

Browser acceptance on an isolated application imported three cases successfully,
showed both target PDFs' seven-field comparisons and correct numeric mismatches,
loaded both PDF previews for 313, and retained the unitless-weight review outcome
for organizer 055. This local run used recorded provider responses; live release
verification is recorded separately with the deployed commit.

Saved reproducible artifacts:
`outputs/benchmarks/2026-09-21-numeric-candidate/`. Development and reserved input
files, evaluation-only labels, raw responses, ledger snapshots, evidence checks,
case-level regression comparison and browser acceptance are retained locally.
