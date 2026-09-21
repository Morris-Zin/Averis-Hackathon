# Complete address checkpoint — 22 September 2026

The source selector could retain a company name but omit the next street-address
line when the document placed slightly more vertical space between them. This
caused unnecessary provider disagreements in the saved Malay scan examples.

The change permits a gap of up to three line heights only for recognizable street
addresses aligned with the party name. Existing page, column, label and extraction
method boundaries remain enforced. Original evidence IDs and text are retained.
OCR and model confidence checks remain unchanged. No missing values or units are
inferred, and no thresholds are lowered.

## Measured comparison

| Check | Previous | Candidate |
| --- | ---: | ---: |
| Complete outcomes, recorded 720-case replay | 581 (80.69%) | 587 (81.53%) |
| Organizer complete outcomes | 411/520 (79.04%) | 411/520 (79.04%) |
| Exact synthetic field values | 1,524 | 1,540 |
| Fresh prepared-evidence checks, live Jev | 3/6 | 5/6 |

No regressions were detected by the paired replay comparator. The six complete
outcome improvements concern Malay PNG, JPEG and scanned-PDF address cases. This
does not increase the organizer score or establish a competition ranking.

The 720-case comparison reuses recorded classifications, document readings,
provider source selections and pairing decisions, then applies current source
validation and deterministic comparison. It is not 720 fresh model calls or a
fresh OCR benchmark. Recorded selections were expanded only through the actual
source-region policy; secondary selections were independently revalidated.

Six additional prepared-evidence scenarios were specified before fresh calls:
Malay, English and Chinese addresses, unrelated prose, a following party label,
and an address in another column. Malay and English improved from partial to
complete readings. All three negative controls passed with both versions. Chinese
remained low-confidence and required review with both versions. These are small
synthetic development checks, not independent real-world accuracy evidence.

## Validation and artifacts

- Full local verification: 510 backend tests passed, two optional tests skipped;
  22 frontend tests passed. PostgreSQL checks, strict typing, lint, formatting,
  module boundaries, generated contracts and production frontend build passed.
- Thirteen new tests cover complete evidence, unrelated text, page/column/gap
  boundaries and low-confidence OCR remaining unresolved.
- Saved paired replay: `outputs/benchmarks/2026-09-22-address-candidate/`.
- Fresh probe specifications and both results: `.local/teammate-audit/`, files
  beginning `address-reserved-`.

Answer sheets remain evaluation-only and were not included in AI requests.
Existing completed reports are not rewritten; new processing uses the updated
extraction and normalization policy versions.
