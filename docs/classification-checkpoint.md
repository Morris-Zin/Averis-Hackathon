# Classification checkpoint: thread references

The selected classifier uses Jev `jev-1.13.0`, the existing 0.80 acceptance
threshold (0.95 for Spam), clearer category descriptions, and lossless email
sections. The provider module owns both question construction and preparation;
callers continue to use `classify(subject, body)`.

Preparation separates recognizable external notices, trailing signatures and
quoted history while preserving every original character. Ambiguous layouts stay
in the current body. It is a conservative plain-text formatter, not a MIME parser.
No document extraction or shipment comparison rules changed.

The classifier follows an earlier request when the latest sender explicitly asks
to act on it. Cancelled, replaced and completed requests are not treated as active.
The original email remains available for review. Classification prompt and policy
versions changed so resumable processing cannot reuse incompatible inference.

## Evidence and tradeoff

On 520 reused synthetic organizer emails, the selected research run suggested the
correct category for all 520: 513 were accepted automatically (98.65%), seven
required review, and none was automatically accepted incorrectly. On 60 synthetic
thread examples (20 reused and 40 newly AI-authored), all category suggestions
were correct; 52 were accepted and eight required review. Both original
thread-reference failures were corrected.

The preceding cleaner-input version automatically handled 519 organizer emails
but misunderstood thread-reference examples. The selected checkpoint trades six
additional organizer reviews for better handling of those examples. It missed
the predeclared research target of preserving 519 automatic answers; the user
explicitly accepted this tradeoff. Organizer comparisons are historical runs,
not concurrent controls. These are development measurements, not an independent
accuracy guarantee or a measurement of document-checking accuracy.

The integrated question and prepared inputs were checked for exact equality with
the selected research snapshot on all 580 examples, without new paid calls.
Research inputs, answer sheets, provider responses and budget artifacts remain
outside runtime imports and images.

## Release verification

Full offline verification with real PostgreSQL passed: 240 Python tests, two
intentional platform/opt-in skips, five frontend tests, strict Python/TypeScript
checks, formatting, lint, import boundaries, generated API contracts and static
production build. Offline tests use provider doubles, not live paid inference.
Resume regression tests verify that changed model/policy profiles reclassify,
unchanged profiles reuse completed classification without another provider call,
and human category decisions take precedence over saved model results.

Browser control exercised a fresh local workspace: automatic mismatch filtering,
source-bound correction with mismatch retention, reload persistence, assignment,
waiting status, controlled immutable revised draft, previous-document retention,
activity history, submitted search, manual category change, review completion and
the completed queue. Manual intake correctly disables submission when live AI is
off. A 390-pixel viewport exposed navigation controls without document overflow.

Browser review also identified and fixed two presentation problems: categorized
non-comparison emails no longer show seven empty shipment fields; comparison
progress counts resolved fields rather than labelling all findings as read.

This is representative workflow coverage, not proof of every possible UI/input
combination. Parser formats, request bounds, access isolation, concurrent changes,
stale results and processing recovery additionally have automated coverage.
