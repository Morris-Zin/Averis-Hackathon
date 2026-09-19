# Evaluation preparation and bounded runs

`scripts/evaluate.py` prepares a reproducible evaluation workspace without calling Jev. The default mode reads the organizer inbox, imports each source email through the same `averis.intake.import_email` capability used by the API, holds the resulting runs out of outbox delivery, and writes a manifest plus a source-keyed case snapshot.

Use an evaluation database that has no public worker or reconciler pointed at it. The CLI defaults preparation to an isolated SQLite database at `outputs/evaluation/evaluation.db`; a live run must name this case database with `--database-url` and the application’s authoritative PostgreSQL budget database with `--budget-database-url`. Evaluation cases never create a second budget ledger. The evaluation case database must use `AVERIS_ENV=evaluation` (the offline tests use `test`) and an empty `AVERIS_TASKS_QUEUE`. Before a live run, an operator must verify the shared application ledger and set `AVERIS_BUDGET_VERIFIED=true`.

```powershell
.venv/Scripts/python.exe scripts/evaluate.py `
  --data resources/official/bundle `
  --output outputs/evaluation `
  --database-url sqlite:///outputs/evaluation/evaluation.db `
  --limit 20 `
  --split all `
  --dry-run
```

Preparation is also the default when `--dry-run` is omitted. It creates:

- `manifest.json`, containing the source email ID, generated case ID, run ID, deterministic split, workspace chunk, attachment paths, and frozen policy metadata;
- `snapshot.json`, containing cases keyed by source email ID and diagnostics from the existing official export adapter.

Preparation refuses to replace an existing manifest. Use `--overwrite` only when intentionally rebuilding that evaluation workspace; it still performs no provider calls. Runs created during preparation are marked held and have no outbox delivery row, so a worker cannot process them accidentally while the manifest is being inspected.

The split is deterministic: SHA-256 of `email_id` is assigned to one holdout bucket out of five, with the other four buckets assigned to development. The policy records the split algorithm, model name, thresholds, purpose, and limits so later artifacts can be interpreted against the exact preparation settings. Ground truth is never read or passed to intake, processing, or Jev.

Each workspace accepts at most 100 imports because that is the application quota. Larger bounded selections are divided into deterministic workspace chunks. `--limit` is required to remain between 1 and 1,000; increase it deliberately when preparing more source emails.

An explicit run requires a prepared manifest and a verified live budget. It processes only the selected split sequentially through `Processor`, sharing one `BudgetAuthority` over the database ledger:

```powershell
$env:AVERIS_ENV = "evaluation"
$env:AVERIS_TASKS_QUEUE = ""
$env:AVERIS_LIVE_ENABLED = "true"
$env:AVERIS_BUDGET_VERIFIED = "true"
.venv/Scripts/python.exe scripts/evaluate.py `
  --output outputs/evaluation `
  --database-url "$env:AVERIS_EVALUATION_DATABASE_URL" `
  --budget-database-url "$env:AVERIS_DATABASE_URL" `
  --run `
  --run-split development
```

The command refuses to run when the evaluation environment or queue gate fails, live inference is disabled, budget verification is false, the singleton shared budget ledger does not exist, the authoritative budget URL is missing or is not PostgreSQL, or the frozen manifest does not match the case database, model, or thresholds. `--run` requires explicit case and authoritative budget database URLs; it never creates a ledger. Tests inject a deterministic intelligence double; normal `--run` uses the existing `Jev` implementation through `Processor` and the shared `BudgetAuthority`, and does not implement a second inference pipeline. No paid execution is performed by CI or by preparation mode.

After a run, `snapshot.json` is refreshed with processing state, run outcomes, source-keyed case views, adapter predictions, diagnostics, coverage, and blocker counts. Blockers remain visible when processing is incomplete, category resolution is unavailable, evidence is unreadable, or the official adapter cannot represent the result. The snapshot is an evaluation artifact and does not claim accuracy. Holdout membership and policy metadata are frozen in the manifest; this tooling does not import ground truth or calculate a score.

The organizer scorer remains a separate command. Use the existing CLI only when an explicit submission payload and the organizer’s scoring environment are available; evaluation preparation does not import or use ground truth and does not invoke the scorer.
