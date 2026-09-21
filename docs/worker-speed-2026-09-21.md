# Worker speed checkpoint, 21 September 2026

## Recovery code

Recovery previously locked every queued/running run before checking whether a worker still owned a live lease. While holding those locks it fetched each outbox row separately. A worker trying to save a checkpoint or extend its lease could therefore wait behind recovery.

Recovery now filters healthy leases and recently dispatched work in SQL before locking, and fetches outbox data in the same query. Exhausted attempts remain eligible for finalization, abandoned work remains recoverable, and missing outboxes are repaired. Document inference, thresholds, comparison, budget accounting and version fencing are unchanged.

Validation: `uv run --project backend python scripts/verify.py` with real PostgreSQL passed: 452 backend tests, 2 optional skips, 21 frontend tests, strict types, lint, generated contracts and production build. New PostgreSQL acceptance checks show healthy/recent rows can be locked independently during recovery and two independent runners process distinct jobs exactly once. Existing process-crash recovery and retry checks passed.

## Deployment and timing

Recovery fix `67c8e26` passed CI 35611797030 and deployed first in California. Worker placement then changed to Singapore, near the Neon `ap-southeast-1` database, followed by scaling from one to two replicas. Each replica runs one job at a time. Railway accepted both replicas on the existing trial; no plan upgrade was made. A 500-second shutdown grace period is configured. The public web service remains in California.

The same ZIP of three source-document comparisons (055, 313, 351; XLSX/DOCX and native PDF) was imported through the normal public bulk API into separate demo workspaces. Every batch made 15 actual provider calls and completed on its first attempt. All normalized field values, field outcomes, categories, pairing decisions and review decisions were identical. The four known mismatches remained mismatches; the unitless weight remained unresolved.

| Configuration | First dispatch to final result | Per-email delivery windows | Longest queue wait |
| --- | ---: | --- | ---: |
| Before: California, one worker, `bb4494b` | 293.3 s | 107.0 / 89.1 / 94.1 s | 236.6 s |
| Recovery fix + Singapore, one worker | 55.3 s | 20.1 / 18.5 / 16.7 s | 31.4 s |
| Recovery fix + Singapore, two workers | 51.2 s | 28.1 / 28.1 / 23.0 s | 23.5 s |

The final batch was 82.6% shorter than baseline. Two simultaneously RUNNING Railway instances and overlapping execution of distinct run IDs verified real parallel processing. The second replica improved this small batch by only 7.4%; this is not evidence of twice the throughput. Individual calls varied and deliveries were slower under the two-worker trial. Larger workloads need their own measurements.

The large improvement is measured for the combined recovery/region changes; a clean recovery-only production timing trial was not completed because another live batch was already queued. Do not attribute an exact share of the gain to either change. The previously investigated 15-job batch took 806.7 seconds, but it was a different workload and was not rerun here. These measurements do not establish a 15-job latency guarantee or a new accuracy score.

All 16 jobs present during the region move eventually completed. One interrupted run resumed from its saved checkpoint on attempt two; the other 15 completed in one attempt. Both controlled timing batches ran after the deployment settled. The queue was empty after acceptance. Live browser verification also confirmed the queue and the existing seven-field mismatch report remained usable.

Timing uses durable dispatch timestamps and the first `processed` history event belonging to each run, excluding demo-session setup and HTTP upload time. Local artifacts are under ignored `outputs/worker-speed/`: deployment snapshots, baseline/single/two-worker results, equality checks, instance status and the queue transition. The unchanged test ZIP SHA-256 is `86cb267d7d1277ff57563aacdb077db90eb795fd6182408cf0c27a72abdd41c1`. New controlled runs cost $0.021919 in settled provider charges, through the shared budget. Railway reported $4.8220 trial credit remaining at verification; this is a snapshot, not a spend guarantee.

The unrelated UI wording commit `29564cb` deployed during this work; its backend is identical to the recovery checkpoint. It was allowed to settle before both controlled timing batches. No threshold, extraction or comparison changes were included in this speed checkpoint.

## Rollback

Replica count and placement are independent Railway service settings. To return to one worker, set the worker's multi-region configuration to `{"sin":{"numReplicas":1}}`; to restore the original placement, use `{"sfo":{"numReplicas":1}}`. Verify actual instance state after the update: Railway applies scaling to existing deployments, whose saved manifest may still show the old replica count. Avoid changing placement during active work when possible; retain the recovery lease/checkpoint protections. Keep the public service and credentials unchanged. Revert `67c8e26` only if reverting the recovery implementation is specifically needed.
