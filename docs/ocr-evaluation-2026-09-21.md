# Multilingual document-reading checkpoint — 21 September 2026

This candidate improves Chinese scan reading and recognition of Malay shipping instructions. Classification, deterministic comparison, source binding and human-review safeguards remain unchanged. It builds on commit `a4bd1f9`.

## Measured results

| Check | Previous checkpoint | Candidate |
|---|---:|---:|
| Exact extracted values, existing synthetic documents | 1,304 / 1,540 (84.7%) | 1,524 / 1,540 (99.0%) |
| Correct category, status and defect fields, all 720 emails | 542 / 720 | 568 / 720 |
| Same complete outcome, 170 synthetic emails | 130 / 170 | 156 / 170 (91.8%) |
| Exact values, 36 fresh scanned documents | 164 / 252 (65.1%) | 245 / 252 (97.2%) |
| Complete outcome, 18 fresh emails | 12 / 18 | 13 / 18 |

Exact extracted values include correctly read values that remain uncertain; they are **not** the rate of fully automatic, dependable reports. On the fresh set, 219/252 values were both correct and resolved. Missing values and weak character confidence continue to require review. The saved corpus has no newly wrong values, newly missed known mismatches, false clearances, wrong alarms or processing failures relative to the previous checkpoint.

Organizer outcomes remain 398/520. Many organizer rows expect OK despite missing documents; Averis continues to say that a comparison has not been performed. Friend-provided Chinese and Malay sets remain 7/15 complete outcomes each, primarily because automatic pairing requires adequate shipment context. These limitations must not be hidden behind the improved extraction percentage.

## What changed

- A multilingual Tesseract probe chooses the page recognizer using script and language clues. English retains its existing recognizer; Malay uses `eng+msa`; Chinese uses RapidOCR 3.9.2's bundled PP-OCRv6 small models.
- The OCR module exposes one page-reading operation and returns text, coordinates and confidence. Document parsing, evidence grouping, provider selection and comparison stay in their existing modules.
- Chinese confidence uses the weakest covered character, including digits, decimal points and name punctuation. Only the first label separator and preceding label parentheses are structural. An average line score cannot hide an uncertain value character.
- Jev's document-role question includes Malay and Chinese document titles, while still distinguishing a document from a reference to one. Its field questions and email classification policy are unchanged.
- Reader and extraction versions invalidate incompatible cached results. Language metadata defaults to undetermined instead of incorrectly claiming English.

The models are pinned and bundled; there is no request-time model download. ONNX threads are bounded and telemetry is disabled. Parsing still runs in a subprocess with time and resource limits. The tested Chinese reader required a 1,536 MiB virtual-address ceiling; a representative constrained run used about 570 MiB peak resident memory inside a 1 GiB container. Virtual address space is not resident memory. Keep worker concurrency at one unless measured capacity supports more.

## Evaluation method and limitations

The 720-email benchmark reuses frozen classification results because that code did not change. All 512 document inputs were read with the candidate. Inference was rerun when prepared evidence changed; identical evidence reused recorded extraction and the separately measured localized role question. SI and BL were read independently. Answer sheets were used only by scoring scripts.

Fresh scans cover English, Malay and Chinese with new names and values, multiline addresses, slight rotation, JPEG compression, missing weights, net-weight distractions and conflicting references. Their expectations were frozen before inference. They are agent-generated examples, not an independent human or real-world holdout. Traditional Chinese data is installed for detection, but this evaluation does not establish broad Traditional Chinese accuracy.

The original strict gate is preserved: it flags six saved-set and two fresh-set lost exports. Examination shows every flagged baseline export already had the wrong review reason (`wrong_doc_type`). That gate omitted the reason when deciding an export was correct. A separate requirements-aware diagnostic records this defect and finds no actual regression. No runtime export was changed to improve the score. Some new results honestly block official export because pairing uncertainty or mixed review reasons are not representable in that schema.

Artifacts remain local under `outputs/benchmarks/2026-09-21-multilingual-candidate`, `2026-09-21-multilingual-fresh`, and `2026-09-21-multilingual-fresh-baseline`. They contain input hashes, recorded evidence, provider results, complete pipeline replays, original gates and requirements-aware diagnostics. The unchanged official scorer and evidence validator were run on the saved candidate.

Do not describe these figures as production accuracy guarantees. Difficult layouts, handwriting, poor scans and unfamiliar languages can still fail. Unreadable or uncertain evidence must remain reviewable rather than becoming a match.
