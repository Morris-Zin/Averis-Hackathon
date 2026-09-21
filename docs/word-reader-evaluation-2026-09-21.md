# Word reader and label fixes — 21 September 2026

Baseline: deployed `4200637`. This evaluation covers document preparation and
source validation, not a new email-classification prompt or model.

## Confirmed problems and changes

- `Loading Port` was absent from the shared label vocabulary. It now follows the
  same normalization and field-boundary rules as `Port of Loading`.
- A supplied complex Word file stored its title, shipper and consignee in a text
  box. The former paragraph/table traversal omitted those contents without an
  issue. The reader now selects one OOXML compatibility representation and reads
  supported text boxes once, retaining complete text and logical paragraph
  locations. These locations are structured-preview references, not page numbers.
- Merged table cells are visited once rather than through repeated grid aliases.
- Content controls and hyperlinks preserve supported visible body text. Nested
  table text is recovered with an explicit layout-review issue. Unsupported
  structures, images, tracked edits, hidden text and external text parts require
  review instead of silently disappearing.
- Unrecognized labelled port expressions remain unresolved. A model selecting
  `Port Of Shame: Port Klang` cannot make that expression a trusted port value.
- A row containing `Shipper | ALPHA | Consignee | BETA` is mixed-field evidence,
  not a complete shipper value. The source validator now recognizes table
  separators as well as colons when detecting multiple labels.
- Word nonbreaking hyphens are preserved. Unknown symbol glyphs retain an
  explicit unknown-character boundary and review issue: `10–20 kg` must never
  become `1020 kg` because punctuation disappeared.
- Compatibility branches are selected using every required namespace URI,
  including renamed prefixes. Unsupported choices use the fallback; conflicting
  supported representations require review. Source XML cannot certify itself.
- Multiline party addresses stay together with fullwidth, equals-sign and
  space-separated labels. Vertically merged tables require review because a
  partial company name is not proof that the complete address was checked.
- Split `Container Number` labels retain their value context. A bare number under
  `Number of containers or packages` remains unresolved unless explicit container
  wording or equipment notation establishes what is being counted.

`Container Number: 3` deliberately remains ambiguous: that label can identify a
container rather than count containers. The reader does not infer a count merely
to complete the report. `Container Count: 3` remains supported.

The public document-reading operation remains unchanged. A private Word module
owns XML traversal and completeness issues; comparison rules remain in the
shared deterministic validator. Reader and normalization versions invalidate
stale processing inputs through the existing compatibility checks.

## New supplied examples

The teammate ZIP contains 14 documents, but no original email subjects/bodies.
Expected source values and deliberate unknowns were recorded before inference.
The application provider path (Jev plus guarded DeepSeek assistance) was used.
Identical provider requests reuse their recorded responses; changed text-box
evidence receives fresh inference. Current validation is rerun on those source
selections rather than retaining stale normalization results.

| Check | Baseline | Candidate |
|---|---:|---:|
| Correct accepted document roles | 13/14 | 14/14 |
| Correct resolved values actually present in the source | 89/92 | 92/92 |
| Deliberately ambiguous/invalid values left unresolved | 4/6 | 6/6 |
| Expected field states, including those unknowns | 93/98 | 98/98 |
| Previously correct field states lost | — | 0 |

These are small, reused development examples, not independent real-world
accuracy. The vague-subject classification report remains unverified without
the original email text. No filename-based category shortcut was introduced.

## Release verification

The regression run and browser acceptance results are saved under ignored
`outputs/benchmarks/2026-09-21-word-candidate` and
`outputs/benchmarks/2026-09-21-word-friend`.

- Existing 720-email/512-document regression corpus: zero per-case or per-field
  regressions; 568 exact automatic outcomes and 1,524/1,540 raw synthetic values
  remain unchanged. This is not a fresh classification accuracy measurement.
- All 512 documents were reread in Linux. Unchanged evidence and current-policy
  validation justified replaying recorded model selections instead of introducing
  model sampling differences. Final production-image parity covers all 46 old
  Word documents plus the 14 newly supplied documents.
- The original benchmark gate requires an improvement inside its own corpus.
  Its `passed=false` with zero losses and zero gains is retained. The release gate
  combines zero old-corpus losses with five improvements on the supplied documents.
- 393 backend tests passed, including real PostgreSQL checks; two optional tests
  skipped. Ruff, strict Pyright and module-boundary checks passed. The unchanged
  frontend passed 18 tests, strict types, lint, contract checks and production build.
- Browser testing confirmed automatic updates and a crucial negative case: all
  seven extracted values may match, but hidden Word content still keeps the case
  in Needs review instead of granting a document all-clear.

Pro's advisory review identified additional cases involving special characters,
compatibility branches, hidden styling and ambiguous labels. Each adopted finding
was reproduced in a regression test; the advice was not treated as verification.

An initial harness run accidentally loaded the installed baseline wheel instead
of mounted candidate source. Version checks exposed this; that run is preserved
as `2026-09-21-word-harness-baseline` and is explicitly invalid as candidate
evidence. Its apparent score changes must not be reported as application results.
The replacement uses the built candidate image and checks its installed reader
version. Runtime source hashes are checked against the checkout.

Browser acceptance uses actual parsing, persistence and workflow with recorded
document inference and an explicitly labelled classification fixture. It checks
manual import, bulk import, automatic result updates, the seven-field complex
Word comparison, source previews, and continued review for ambiguous or invalid
documents. A live-provider deployment smoke check is separate.

## Remaining limits

Logical Word extraction does not reproduce page layout. Floating-region order,
unsupported table layouts, image-only Word content, external text parts and
tracked revisions require review where not safely supported. This release does
not claim universal DOCX support or solve every OCR/layout problem.
Hidden-style detection is conservative: a hidden property in a used inheritance
chain requires review even if a later formatting layer might override it. The
reader does not implement Word's complete rendering/style cascade.
