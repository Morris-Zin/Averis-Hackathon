# Filename-assisted email classification

Attachment names now supplement vague or uncertain email intent. For example,
“Checking / Please check these before release” with Shipping Instruction and draft
BL filenames changed from General to BL Comparison in the development experiment.
This does not make filenames proof of document identity, shipment values or a match.

## Policy and boundary

The existing subject/body classifier runs first. An accepted specific category is
preserved. Only General or an unaccepted category with current attachment filenames
gets one additional Jev classification. An uncertain supplemental answer preserves
the original answer. Acceptance remains 0.80, or 0.95 for Spam. Provider failures
remain visible and follow the existing bounded retry policy.

The intelligence interface accepts optional attachment names; the provider owns the
prompt and fallback. The pipeline excludes superseded attachments. Human category
decisions take priority. Policy version `classification-v4-filename-context`
invalidates incompatible classification checkpoints without changing document
extraction. Filenames are not added to field extraction or pairing judgments.

The supplemental prompt treats names as untrusted clues. Active cancellations,
billing requests, new SI requests and informational updates override filenames.
Names cannot invent a comparison request in an otherwise informational email.

## Measured results

Baseline source: `56e1dbe3165d74d9369eddd64f7161b1e0a7d467`.
Model: Jev 1.13.0. Inputs and expected categories were frozen before inference;
answer labels were never included in requests. The reserved set was run once with
the policy selected on development examples.

| Dataset | Previous correct automatic answers | Candidate correct automatic answers | Previous wrong answers / category reviews | Candidate wrong answers / category reviews |
|---|---:|---:|---:|---:|
| 32 development examples | 28 | 32 | 1 / 3 | 0 / 0 |
| 24 reserved examples | 21 | 24 | 0 / 3 | 0 / 0 |

Seven improvements and no observed regressions. Controls included English, Malay
and Chinese messages, misleading names, cancellation, quoted history, billing,
Spam, archived documents and instructions embedded in filenames. Runtime replay
using saved provider responses reproduced all 56 research decisions.

The existing 720-case benchmark had **zero cases eligible for this fallback**.
Offline replay through the current application pipeline retained 581 exact outcomes
and 1,524 correct synthetic document values out of 1,540, with no protected
regressions. Organizer exact outcomes remain 411/520; this change does not improve
that score. Existing parsing and inference were replayed, not rerun as fresh AI calls.

The 720-case comparison tool reports no improvements on that set; release improvement
comes from the separately frozen 56 examples. Do not describe this as a new full-data
accuracy gain or an untouched independent evaluation.

## Costs, saved evidence and limitations

Development-ledger increase: $0.003515 across both experiments. Concurrent demo
spending is excluded from that experiment amount. The shared ledger ended at
$1.315437 including prior experiments and demo activity, within the $7 guard.

Local evidence is saved under
`outputs/benchmarks/2026-09-21-filename-candidate/`, including frozen inputs,
evaluation-only labels, provider answers, runtime replay, ledger snapshots and the
720-case regression comparison. Research sources remain ignored, outside runtime
images. Copied earlier benchmark manifests describe inherited evidence; the
`filename-release-manifest.json` identifies this experiment.

These small synthetic sets were written and labelled by the same agent, without
independent bilingual review. Their perfect candidate score is not a real-world
accuracy guarantee. General emails with attachments incur an additional provider
call; clear specific requests do not. Filename ambiguity remains possible, and the
normal evidence, confidence, pairing and human-review safeguards still apply.
