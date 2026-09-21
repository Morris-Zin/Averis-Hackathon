# Exporting known findings without losing uncertainty

This changes the evaluation adapter only. Classification, extraction, pairing,
comparison, queues and human-review actions are unchanged.

## Mapping and contract

The unchanged organizer participant README defines `MISMATCH` as at least one
field differing. The dataset README separately requires `NEEDS_REVIEW` for
missing/unreadable required evidence, with no official defect fields. The official
schema cannot carry both review reasons and mismatch fields in the same row.

The adapter therefore applies a narrow policy:

- A valid, current, complete seven-field report with a known mismatch and only
  unrelated field-selection uncertainty exports `MISMATCH`, listing only the
  proven mismatching fields. Allowed uncertainty reasons are low field confidence,
  low OCR confidence and provider disagreement. This is a partial finding, not a
  claim that every field was successfully checked.
- A missing required value remains `NEEDS_REVIEW / missing_value`, including when
  another field differs. Known mismatches and unresolved field names are retained
  in the separate diagnostics file, not fabricated into an unsupported official
  review row.
- Document-wide problems, unknown failures, unresolved pairing, stale reports,
  incomplete reports and unaccepted categories remain blocked where the official
  schema cannot faithfully represent them.
- Only seven dependable matches with no blocking problems can export `OK`.

The app still shows every known mismatch, every unresolved field and its source,
and requires human review. Export does not mutate the case. The diagnostics sidecar
now carries `known_mismatches`, `unresolved_fields` and `review_reasons` in addition
to existing reviewer provenance and export blockers. Pair-invalid/stale/incomplete
reports do not publish purported known findings through this sidecar.

Source references: unchanged local organizer `resources/official/bundle/README.md`,
`resources/official/docker/data_v2/README.md` and
`resources/official/docker/server/scoring.py`. No email-ID rules or evaluation
imports are added to runtime code.

## Saved regression check

Baseline is the deployed Word reader checkpoint `b888d4c`. Replayed all 720 saved
cases; no new AI calls or new accuracy claims. Results are saved in ignored
`outputs/benchmarks/2026-09-21-export-known-findings`.

- All 720 app cases, assessments and UI summaries remain exactly unchanged.
- Every previously exported prediction remains exactly unchanged.
- 13 additional exact official-format rows become representable: five organizer
  missing-value review cases and eight synthetic known-mismatch cases.
- Organizer export coverage increases from 486/520 to 491/520. The remaining 29
  rows stay explicitly blocked; complete submission export still refuses to
  silently fill them with invented answers.
- The unchanged official weighted score rises from 83.52% to 83.76%. Defect catch
  remains 35/46. Required-review recall rises from 12/20 to 17/20.
- The scorer's category result rises because fewer rows are omitted and defaulted
  to General, not because Jev became better at classification.

The existing 568 exact automatic app outcomes and 1,524/1,540 raw synthetic field
values are unchanged. The original per-case gate reports zero regressions and
13 improved exports; a separate gate checks exact equality of all app states and
all previously published predictions. New tests cover missing values, unrelated
uncertainty, document-wide errors, stale/invalid reports and unmodified review
state. These reused examples establish regression behavior, not independent
real-world accuracy.
