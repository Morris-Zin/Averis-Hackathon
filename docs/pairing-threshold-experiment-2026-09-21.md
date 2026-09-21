# Pairing threshold experiment: rejected

Baseline: deployed `911f0d2`, pairing threshold 0.95. Candidate: only lower that threshold to 0.90. The prompt, model, source evidence and conflict rules remained unchanged. No runtime code or live configuration was changed.

On the saved 720-email regression benchmark, correct complete outcomes increased from 575 to 578, with no protected-case losses. That was insufficient to release the candidate.

Before new paid calls, 32 fresh synthetic scenarios were frozen: eight supported pairs and 24 unrelated, conflicting or ambiguous pairs, including English, Chinese and Malay. At 0.95 all eight positives were accepted and all 24 negatives rejected. At 0.90 the positives stayed correct, but two negatives were incorrectly accepted:

- Both documents contained `Customer account reference: LINK-482731`. Jev selected it with 0.93 confidence, although a customer can have many shipments.
- Both documents contained `Production batch: LINK-482731`, with transport references absent. Jev selected it with 0.93 confidence, although a factory batch does not establish shipment identity.

**Decision: reject 0.90 and retain 0.95.** The extra benchmark coverage does not justify automatically linking unrelated documents. Confidence is not calibrated accuracy; even the successful 0.95 result on this small synthetic set is not proof of universal safety.

The first support-ticket scenario request timed out. Its monetary reservation was retained; a single retry completed, and the other 31 responses were reused. No prompt or scenario was tuned against these answers. The previous experiment's reserved scenarios are now reused regression data, not an independent holdout.

Frozen inputs, labels kept outside provider requests, raw responses, manifests, ledger snapshots, per-case comparisons and rejection evidence are saved under ignored `outputs/benchmarks/2026-09-21-threshold-090/`. The subsequent PDF experiment must use the surviving 0.95 runtime checkpoint and remain separately revertible.
