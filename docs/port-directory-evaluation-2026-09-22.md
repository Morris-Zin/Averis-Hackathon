# Port-directory comparison checkpoint

The app can recognize an exact port name and its UN/LOCODE as the same location.
For example, `Conakry, Guinea` and `Conakry, Guinea (GNCKY)` match without
rewriting either document reading. The result includes its location code and
directory version. This does not confirm document pairing.

## Measured result

The frozen 720-email comparison replay inspected 490 automatic port findings.
Three false warnings disappeared: Conakry, Nantong and Singapore with/without
their matching codes. No protected discrepancy disappeared and no recorded
case regressed. Complete correct cases remain **587/720**; synthetic exact field
values remain **1,540**. These three emails still have other problems, so their
complete results and official exports do not improve.

The existing release comparator reports `passed: false` because it requires a
complete-case or extracted-value gain. We retain that result unchanged. This
narrow checkpoint instead passes a separate field-result gate: remove real false
port alarms, retain protected differences, preserve the overall results.

Forty authored synthetic decisions (20 development, 20 reserved) yielded 38
expected decisions: 14/16 supported aliases recognized and all 24 contradictory
or unsupported inputs left unmatched. Two genuine aliases safely abstained
because of globally ambiguous names. Unsupported translations were explicitly
expected to abstain; they are not evidence that Chinese aliases are handled.
No model or threshold was tuned. These small agent-authored tests are not an
independent estimate of real shipping accuracy. A later directory-wide audit
found 50 names that also spell codes; a new guard abstains on all 50. The reserved
set was rerun after that conservative guard, and is no longer untouched holdout.

## Design and limits

- UNECE UN/LOCODE 2025-1 supplies the names/codes. Only 16,127 eligible maritime
  locations can establish matches; all directory names contribute ambiguity.
- Each value must independently resolve in full. No fuzzy matching, inferred
  translations, terminal deletion, or conflicting-code override.
- Missing/uncertain readings stay unresolved. Unconfirmed document pairs stay
  under human review, with provisional comparison results.
- The immutable private R2 artifact is round-trip SHA-256 verified. Identical
  bytes are bundled as a local cache, so comparison performs no network calls.
  Missing/corrupt cache disables this additional matching capability.
- This is a comparison capability, not a new OCR model or port extraction model.
  It cannot repair unreadable documents or invent missing values.

Reference attribution, hashes, build instructions and filtering are in
`backend/src/averis/reference_data/README.md`. Runtime code does not load labels,
email IDs, or benchmark results. The cache is below 1 MB compressed.

## Evidence retained locally

- `.local/port-research/`: unchanged source ZIP, prototype, synthetic decisions,
  directory-wide collision audit, R2 round-trip metadata and verification logs.
- `outputs/benchmarks/2026-09-22-port-directory-candidate/`: replayed cases,
  unchanged inputs/labels/extractions, original comparator result and narrow
  field-result gate.

All research here is offline; no Jev or DeepSeek requests were made.
