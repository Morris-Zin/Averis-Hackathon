# Evidence-reading improvement — 21 September 2026

The selected change improves 32 complete case results on the frozen 720-email
benchmark. Its per-case gate found no losses of previously correct results,
document roles, exact synthetic values, supported exports or known discrepancies.
This is a regression check on reused data, not an independent accuracy estimate.

| Check | Baseline | Selected candidate |
|---|---:|---:|
| Correct category, status and defect fields together | 500/720 (69.44%) | 532/720 (73.89%) |
| Same check on organizer emails | 370/520 (71.15%) | 398/520 (76.54%) |
| Organizer discrepancy cases with a complete, correct export | 23/46 (50%) | 34/46 (73.91%) |
| Exact synthetic document values | 985/1540 (63.96%) | 1288/1540 (83.64%) |
| Incorrectly matching fields where a discrepancy was expected | 4 | 0 |
| Incorrect complete all-clear results | 0 | 0 |

## What changed

- Consume a compound label such as `Notify Party/Intermediate Consignee` once.
  The embedded word `Consignee` does not mean a second field is present. Actual
  separate inline fields remain ambiguous.
- Preserve font runs before assembling PDF words, including overlapping form
  labels. Rejoin touching font fragments within a word without merging an
  overlapping label into its value.
- Complete a machine-selected party source with clearly adjacent address lines
  or worksheet rows from that same document. Original block IDs, text and
  locations remain unchanged. Known headings, pages, columns and extraction
  methods bound the region. An explicit reviewer selection that omits a known
  continuation remains unresolved.
- Recognize the Malay loading-port label `Pelabuhan muat`. Treat port values such
  as `TBA` as missing, not as a port name.

Jev's questions, model and confidence thresholds remain unchanged. Source-region
completion belongs to document evidence preparation; deterministic comparison
still belongs to shipment verification. No rules depend on fixture IDs or answers.

## Experiment and release gate

Baseline: commit `83688840dcf5f7aacf8d1b44ae66d2e841d6c163`, saved under
`outputs/benchmarks/2026-09-20-8368884`. Selected candidate:
`outputs/benchmarks/2026-09-21-candidate-source-completion`.

The [Pro review](https://chatgpt.com/c/6aafd5af-da38-83ec-95d0-bbba81f2c50b)
suggested compound-label handling, complete address evidence, Malay labels,
font-aware reading and explicit missing-port handling. Each was checked against
the source and failures before implementation.

Two alternative experiments supplied grouped party choices directly to Jev.
They achieved 542 complete correct results but introduced two and four uncertain
port readings respectively where the baseline had correct accepted values.
Those versions were rejected. The selected version preserves the original AI
questions and completes source regions deterministically after source selection.

All 720 classification results were reused because classification is unchanged.
Of 512 document requests, 469 had exactly identical model state and questions;
their saved raw responses were decoded through the new source policy. The other
43 requests were rerun through the shared budget authority. This avoids treating
AI sampling differences on unchanged inputs as an implementation improvement.

The selected run incurred $0.016737 in recorded usage. Across the three live
experiments the development ledger increased by $0.173906, including retained
reservations for uncertain charged outcomes. An earlier rejected run had 26
transport/database failures; their original records were archived and only those
failed jobs were retried once. The selected run had no request failures.

The gate checks each case and field, not just average scores. Saved validation
also checks original input hashes, verbatim evidence, document identity, source
locations, complete seven-field all-clear reports and honest exports. New offline
tests cover address differences, omitted continuations, page/column boundaries,
compound labels, overlapping fonts and missing ports.

## Limits

English, Chinese and Malay are included, but language support is uneven. On the
synthetic emails, exact complete outcomes are 57/66 English, 37/52 Chinese and
26/52 Malay. Friend-supplied Chinese and Malay sets each score 7/15 automatically;
pair confirmation and uncertain document roles remain review work. OCR still
uses the English profile. This release does not claim dependable Chinese OCR.

The organizer's answer sheet marks 91 attachment-free emails as OK. Averis does
not claim it compared documents that were absent. These disagreements remain
visible rather than being hidden to increase a score.

The earlier baseline's 36/46 count means cases with *any* mismatch alarm. Only
35/46 flagged an actual expected defect field; one case alarmed on the wrong
field. The stricter complete-correct-export baseline is 23/46, as reported above.

Geometry-based continuation is deliberately bounded, not a general layout
understanding system. Unknown layouts and low confidence still require review.
The saved synthetic fixtures have been used for development; a fresh independent
test set is still needed before making real-world accuracy claims.
