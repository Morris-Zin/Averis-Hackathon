# Source-bound Jev pairing — 21 September 2026

An SI may label its shipment reference “BL INSTRUCTION” while the draft BL labels the same number “BILL OF LADING” or “ORDER NO.” Previously these documents could remain unpaired even when their independently extracted fields were usable. The new fallback asks Jev to select an existing shared reference, with both source passages and the email as context. It never asks Jev to invent a reference or decide whether the seven fields match.

## Behaviour and boundaries

`pairing.py` owns bounded reference candidates, validation, source binding and acceptance. The Jev adapter returns one typed proposal; the pipeline owns durable checkpoint reuse. Existing valid deterministic or reviewer-selected pairs bypass the model. The additional call uses the existing atomic spending authority and disabled SDK retries. Injected offline intelligence does not silently enable paid pairing.

Confidence must meet the frozen 0.95 pairing policy. This is a decision threshold, not measured accuracy. Explicit conflicting shipment, booking, order, instruction or bill identifiers remain blocking, even with a shared reference elsewhere or human selection. Differences in shipper, consignee, notify party, ports, containers or weight are potential comparison defects, not proof that the documents are unrelated.

No shared source reference, low-quality OCR reference evidence, blocking document problems, too many candidates or an oversized request produces review. Phone, company/tax, commodity and other non-shipment candidates are explicitly rejected by the model instructions; semantic rejection remains probabilistic. The measured negative tests below do not guarantee perfect rejection of every future input.

Accepted evidence records the immutable SI/BL IDs, exact source block IDs, shared reference, model, policy and confidence. The review screen exposes both source quotations and locations. Reading corrections retain this proof. Changes to evidence, document identity, email context, model or pairing policy invalidate the saved pairing judgment. Provider failures remain visible failures.

## Frozen comparison against deployed 1037697

The same 720 emails and 512 documents were replayed through the application. Existing classification and extraction responses were unchanged. Pairing responses were reused only where the full prepared request exactly matched the recorded experiment. Evaluation labels were used only for scoring.

| Measurement | Baseline | Candidate |
|---|---:|---:|
| Correct complete automatic outcomes, all 720 | 568 | 575 |
| Correct complete automatic outcomes, organizer 520 | 398 | 405 |
| Correct official exported rows, organizer | 400 | 404 |
| Exportable organizer rows | 491 | 501 |
| Expected organizer field defects surfaced in the app | 53/72 | 64/72 |
| Official scorer defect cases caught | 35/46 | 38/46 |
| Organizer scorer weighted score | 83.7589% | 88.3427% |
| Synthetic exact extracted values | 1524/1540 | 1524/1540 |
| New protected-case regressions | — | 0 |
| False all-clear cases | 0 | 0 |

The official scorer fills omitted rows using its own default behaviour; its score is not overall real-world accuracy. Exported-row accuracy fell from 400/491 (81.47%) to 404/501 (80.64%) as coverage expanded. Six newly exportable rows still disagree with the organizer, mainly because required values remain unresolved. Previously correct exports were preserved. We did not assume kilograms for unitless weights, relabel unknown results, or change the official scorer to improve results.

Ten of fifteen organizer pairs with candidate references were confirmed. Five remained below 0.95. Eighteen Chinese/Malay friend pairs without usable shared shipment references remained for review. Seven organizer cases gained an exact app outcome; four gained an exact official export. Existing language and format results otherwise stayed unchanged.

## Separate pairing scenarios

The frozen experiment contained 64 pairs: 33 existing examples, 21 new development scenarios and 10 separately reserved scenarios. The development set accepted all five supported positive pairs and rejected all sixteen negative pairs. The reserved set was evaluated once after freezing the prompt and threshold: four positives accepted and six negatives rejected. Negatives include tax/contact/customer numbers, conflicting references, email-only claims and instructions embedded in document text. These are small synthetic checks, not an independent real-world accuracy claim.

No threshold or prompt was retuned against the reserved answers. An initial research harness had invalid synthetic evidence metadata; it was corrected before those calls ran. Existing recorded requests were equality-checked before reuse. The shared ledger's development allocation increased by $0.001112 across this experiment; the total ledger also includes concurrent live demo tests, so its whole-period difference is not attributed entirely to pairing.

## Validation and retained evidence

- 30 new offline pairing tests: evidence binding, hard conflicts, uncertainty, malformed responses, deadlines, checkpoint reuse/invalidation, provider failure and correction provenance.
- Full verification: 434 backend tests passed, two intentional skips; 19 frontend tests passed. PostgreSQL acceptance, strict typing, lint, generated contracts and production build passed.
- Browser acceptance uses an isolated server and unchanged organizer files with recorded provider outputs. It verifies automatic mismatch routing and expandable reference evidence. Fresh deployed-provider checks are recorded with release evidence after rollout.

Ignored local artifacts: `outputs/benchmarks/2026-09-21-pairing-candidate/`, `.local/pairing-research/production-v1/` and the frozen scenario manifest. They include per-case outcomes, raw responses, exact requests, source evidence, budgets and regression checks. Ground truth remains outside runtime imports, images and provider requests.


## Provisional comparisons while pairing awaits review

The seven fields are compared even when the document pair is unconfirmed. The report exposes these as separate `provisional_outcome` values, while confirmed outcomes remain unresolved. The UI labels matches and differences as provisional and explains why a human must confirm the pair. Missing or uncertain readings remain unresolved, including in the provisional comparison.

Provisional results do not create confirmed mismatch counts, clear a case, or enter the official scorer export. The case stays in Needs review. After valid human confirmation, normal comparison publishes confirmed outcomes; conflicting shipment references still cannot be overridden.

Validation: 456 backend tests and 21 frontend tests passed, including PostgreSQL acceptance and generated contract checks. Recomputed the 268 complete reports (automatic and simulated-confirmation paths) in the saved 720-email numeric checkpoint: no changes to confirmed outcomes, assessment, summaries or export decisions. Browser acceptance on the Chinese ZH24002 example showed one provisional shipper difference and six provisional matches; after pair confirmation these became one confirmed mismatch and six matches. No paid inference was used for this validation.
