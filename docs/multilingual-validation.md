# Chinese and Malay text acceptance — 20 September 2026

The app now recognises common Chinese (simplified/traditional) and Malay shipment
field labels, full-width punctuation, explicit kilogram/metric-tonne units, and
selected localized shipment-reference labels. Original evidence text and source
locations remain unchanged. Shared vocabulary drives reading and normalization;
no rules depend on email IDs. Reader and normalization versions changed so old
checkpoints cannot silently reuse incompatible evidence.

## What failed and what changed

The friend's Chinese pack split each SI into one large evidence block, did not
recognise Chinese labels or `公斤`, and provided no shipment identifiers inside
the attachments. Cleaner evidence fixes the first two problems. Missing shipment
identifiers still require a reviewer: a PO number in the email subject alone does
not prove that both attachments belong to it.

The Sources panel now offers **Confirm pair and compare** even when the proposed
SI/BL selections have not changed. Previously the unchanged-selection guard
disabled that action. The backend continues rejecting conflicting identifiers,
including when a reviewer tries to confirm them. Pair acceptance is recorded in
history, creates a new input revision and recomputes through the existing worker.

## Measured acceptance

Both friend-provided packs contain 15 synthetic emails. These are development
examples, not organizer data or an independent held-out multilingual benchmark.

- Actual Jev category suggestions: **30/30 correct**. Chinese accepted 15/15;
  Malay accepted 14/15. One correct Malay suggestion had confidence 0.79 and
  correctly required category review under the unchanged 0.80 threshold.
- All **16 complete pairs** (eight per language) produced exactly the expected
  field outcomes after explicit pair confirmation was assumed by the acceptance
  harness. These are reviewer-assisted comparisons, not automatic end-to-end
  results. None of these attachments established automatic pairing.
- The Chinese missing-weight example retained an unresolved weight. Both packs'
  single-document and wrong-document examples lacked a valid SI/BL pair. The
  Malay missing-weight example stopped at category review; its extraction was
  not measured in this run.
- Ground-truth labels were used only to evaluate the returned results, never in
  provider inputs. The runtime prompts and confidence thresholds were unchanged.
- Shared ledger: $0.329006 before, $0.335526 after; **$0.006520** total increase,
  within a separate $0.10 acceptance ceiling and the existing combined $7 guard.
- Full verification: **293 Python tests passed, two intentional skips; 16
  frontend tests**, strict types, lint, boundaries, contracts and production build.
- Browser control used the real local intake/worker/review stack with deterministic
  offline intelligence. The Chinese shipper example required pairing, allowed
  confirmation without changing selectors, then automatically showed one mismatch
  and six matches with original Chinese evidence. This UI test is distinct from
  the actual Jev component results above.

## Limits

OCR remains English-only; this change supports native multilingual text, not a
claim of Chinese/Malay scan accuracy. Translation between different-language
company/port names is not attempted: uncertain or differently expressed names
can still require review. Bare weights without explicit units remain unresolved.
Missing shipment identity is not bypassed merely to improve a test score.

Old cases are not silently rewritten. Retry an old case to reread it with the new
parser, then review its category/pair as needed. Reimporting an identical email
reuses its existing case and is not a substitute for Retry.
