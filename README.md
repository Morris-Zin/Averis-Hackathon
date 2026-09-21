# Averis — shipping document review

A Jira-inspired shipping operations workspace. It classifies incoming messages, compares draft Bills of Lading against Shipping Instructions, and links each finding to source evidence. English is the first supported language.

Native text recognises common Chinese and Malay shipment labels and units. Scans now use language-directed OCR: Tesseract for English/Malay and bundled RapidOCR for Chinese, with uncertain readings still requiring review. See [measured results and limits](docs/ocr-evaluation-2026-09-21.md).

Word reading includes supported text boxes, content controls and merged-cell handling. Ambiguous labels and unsupported content remain visible review reasons. See the [Word reader fixes and regression results](docs/word-reader-evaluation-2026-09-21.md).

Optional DeepSeek field assistance supplements unresolved Jev readings without replacing classification, document roles, or deterministic comparison. See the [measured comparison, safeguards and setup](docs/deepseek-evaluation-2026-09-21.md). Vision extraction remains experimental and is not enabled.

Jev can also link SI/BL documents through a shared shipment reference with different labels. The review screen shows the supporting source passages; conflicting identifiers and uncertain pairs still require review. See the [pairing benchmark and limitations](docs/pairing-evaluation-2026-09-21.md).

**Live demo:** https://averis-hackathon-production.up.railway.app/

The app and private worker run on Railway with Neon PostgreSQL and private R2 storage. Live Jev processing is enabled under the shared budget guard; a deployed comparison completed with the expected two mismatches. Saved demo classifications are illustrative until a live check is run. Development evaluation and the disclosed reused-validation results are recorded; final submission materials remain in progress. See [measured validation and remaining work](docs/validation.md).

## Run locally

Prerequisites: Python 3.12+, uv, Node 24, pnpm 10.26.2 and PostgreSQL. Scans require Tesseract with `eng`, `msa`, `chi_sim` and `chi_tra` data; the Docker image installs these. The locked Python environment includes RapidOCR's models and headless ONNX/OpenCV dependencies; inference does not download models. Use the Docker image for the tested, resource-bounded Linux reader.

```powershell
uv sync --project backend --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
# Use your local PostgreSQL connection:
$env:AVERIS_DATABASE_URL = 'postgresql+psycopg://averis:averis@localhost:5432/averis'
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn averis.api:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** and choose **Enter demo workspace**. The browser and API share one origin. Every session gets an isolated 24-hour workspace; reviewer names are simulated identities. No mailbox connection is required.

The **Spam** queue keeps accepted spam and unaccepted AI spam suggestions, with an explicit **Suspected** label and a visible count. These messages are excluded from shipment work queues and the outstanding review count; **All cases** still includes them. **Not spam** restores a message to Needs review and asks the reviewer to choose its category. The original AI suggestion and history remain available, and an unresolved category still blocks evaluation export. See [spam workflow verification](docs/spam-workflow-2026-09-22.md).

Choose **Add email** in the queue to paste a subject, sender and message and attach documents. **Bulk import** accepts an organizer-style ZIP of email JSON plus attachments, or several email JSON files, with a preview and per-email accepted/duplicate/failed results; see [bulk import](docs/bulk-import.md). Manual intake requires enabled live processing. Imports use the demonstration budget; there are no per-session or daily run quotas. Identical submissions in the same workspace reuse the existing case. Attachments support TXT, PDF, DOCX, XLSX, PNG and JPEG, up to eight files, 10 MB each and 20 MB combined. Arbitrary revised-document uploads remain operator-only.

The backend also has a SQLite convenience default for quick UI development. PostgreSQL is required for concurrency tests and deployment. Settings load environment variables and an optional ignored `.env`; see [.env.example](.env.example).

See [deployment instructions](docs/deployment.md) for the selected Railway deployment, local Compose, and the retained Cloud Run alternative. Railway runs `python -m averis.runner` as a private background process using the same Python package and PostgreSQL. Cloud Run uses the IAM-protected `averis.worker:app` HTTP entry point. Processing stays outside import requests.

## Verification

```powershell
$env:AVERIS_TEST_DATABASE_URL = $env:AVERIS_DATABASE_URL
uv run --project backend python scripts/verify.py
```

This checks Python formatting, lint, function complexity (maximum 15 for application/scripts), strict types, meaningful offline tests, module boundaries, OpenAPI/TypeScript contract drift, frontend formatting, strict types, lint and the production static build. PostgreSQL tests use temporary schemas. No paid provider is called. `--backend-only` is available for backend work.

Run `uv run --project backend ruff format backend/src backend/tests scripts backend/migrations` and `pnpm --dir frontend format` to apply the enforced formatting. Generated API types remain generator-owned. TypeScript non-null assertions are rejected by ESLint.

For browser acceptance, use the built app through its real API: enter a workspace, open Mismatches, inspect evidence, correct a reading, attach a controlled replacement, change reviewer/workflow and refresh. A completed review does not clear a genuine document mismatch.

## Structure and design

`frontend/` contains Next.js. `backend/` contains the Python project, tests and migrations. Repository-wide tools stay in `scripts/`; deployment configuration stays in `infra/`. Run the commands below from the repository root.

- `backend/src/averis/domain.py`: typed public contracts.
- `intelligence.py`: provider-neutral classification and extraction contracts.
- `processing_components.py`, `processing_setup.py`: versioned adapter bindings and application composition.
- `jev.py`, `jev_prompts.py`, `deepseek.py`: budgeted provider adapters and replaceable Jev questions.
- `documents.py`: bounded TXT/PDF/DOCX/XLSX/OCR reading and previews.
- `verification.py`: source validation, numeric units and seven-field comparison.
- `review.py`: source-bound reviewer decisions, independent of HTTP and persistence.
- `workflow.py`: transactions, immutable revisions, conflict handling and scheduling review work.
- `pipeline.py`: typed checkpoints, classification, independent document preparation and comparison.
- `processing.py`: durable run ownership, leases, publication, outbox dispatch and recovery.
- `case_status.py` and `api_responses.py`: authoritative report summaries and HTTP projections, separate from persisted case state.
- `api.py`, `http_context.py`, `routes.py`: application composition, authentication and HTTP adapters.
- `frontend/`: Next.js static frontend; generated API types, review state hook and focused panels.
- `backend/migrations/`, `infra/`: database migration and deployment configuration.

Read [replaceable components](docs/component-architecture.md), [architecture](docs/build-plan.md), [module contracts](docs/module-contracts.md), [organizer brief](docs/hackathon-brief.md), and [submission checklist](docs/submission.md). Agent-specific instructions and skills are local-only.

See the [expected results and advanced requirements checklist](docs/requirements-checklist.md) for verified feature support, fresh document-reader checks and supported limits.

## Data and evaluation

See the [21 September evidence-reading comparison](docs/accuracy-improvement-2026-09-21.md)
for the latest frozen before/after results, rejected experiments and remaining limits.

Official kits belong under ignored `resources/official/bundle` and `resources/official/docker`. Download them from the [organizer folder](https://drive.google.com/drive/folders/1ouOrFF6GMKvJDaX_asN8R6v467W7P8Df). Ground truth is evaluation-only and excluded from runtime images.

```powershell
uv run --project backend averis inspect
uv run --project backend averis validate resources/official/bundle/sample_submission.json
uv run --project backend averis score resources/official/bundle/sample_submission.json
# Snapshot: JSON object mapping original email IDs to complete CaseView objects
uv run --project backend averis export outputs/case-snapshot.json --output outputs/submission.json --diagnostics outputs/coverage.json
```

The supplied sample submission is a placeholder, **not model output**. The existing score command invokes the unchanged official scorer. Unsupported export states must block export, never be replaced with invented categories or matches. Report automatic coverage, abstentions, and reviewer-assisted results separately.

Known mismatches and unresolved fields are preserved together in export diagnostics. See the [official mapping and regression results](docs/export-evaluation-2026-09-21.md) for when a partial finding can be exported and when review or an explicit blocker remains necessary.

## Cost controls

Live AI defaults off. Verify earlier project spending and provider prices, initialize the shared budget ledger, and only then enable it. The combined Jev ceiling is $7 including earlier experiments: at most $5 development and $2 demonstrations. Reservations are atomic; uncertain charged outcomes retain their reservation. Cloud budget alerts are notifications, not a guaranteed spending cap.
