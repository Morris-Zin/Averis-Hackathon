# Averis — shipping document review

A Jira-inspired shipping operations workspace. It classifies incoming messages, compares draft Bills of Lading against Shipping Instructions, and links each finding to source evidence. English is the first supported language.

**Implementation status:** the local application, durable processing code, format readers and deployment configuration are implemented. Public cloud deployment and paid end-to-end evaluation remain pending service configuration. See [measured validation and remaining work](docs/validation.md). Demo classification is explicitly illustrative; its seven-field comparisons run the actual deterministic rules.

## Run locally

Prerequisites: Python 3.12+, uv, Node 24, pnpm 10.26.2 and PostgreSQL. Tesseract with English data is required for scans; the Docker image installs it.

```powershell
uv sync --locked
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web build
# Use your local PostgreSQL connection:
$env:AVERIS_DATABASE_URL = 'postgresql+psycopg://averis:averis@localhost:5432/averis'
uv run alembic upgrade head
uv run uvicorn averis.api:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** and choose **Enter demo workspace**. The browser and API share one origin. Every session gets an isolated 24-hour workspace; reviewer names are simulated identities. No mailbox connection is required.

The backend also has a SQLite convenience default for quick UI development. PostgreSQL is required for concurrency tests and deployment. Settings load environment variables and an optional ignored `.env`; see [.env.example](.env.example).

See [deployment instructions](docs/deployment.md) for the selected Railway deployment, local Compose, and the retained Cloud Run alternative. Railway runs `python -m averis.runner` as a private background process using the same Python package and PostgreSQL. Cloud Run uses the IAM-protected `averis.worker:app` HTTP entry point. Processing stays outside import requests.

## Verification

```powershell
$env:AVERIS_TEST_DATABASE_URL = $env:AVERIS_DATABASE_URL
uv run python scripts/verify.py
```

This checks Python lint and strict types, meaningful offline tests, module boundaries, OpenAPI/TypeScript contract drift, frontend strict types, lint and the production static build. PostgreSQL tests use temporary schemas. No paid provider is called. `--backend-only` is available for backend work.

For browser acceptance, use the built app through its real API: enter a workspace, open Mismatches, inspect evidence, correct a reading, attach a controlled replacement, change reviewer/workflow and refresh. A completed review does not clear a genuine document mismatch.

## Structure and design

- `src/averis/domain.py`: typed public contracts.
- `intelligence.py`: budgeted Jev classification and independent document extraction.
- `documents.py`: bounded TXT/PDF/DOCX/XLSX/OCR reading and previews.
- `verification.py`: source validation, numeric units and seven-field comparison.
- `workflow.py`: explicit reviewer actions, immutable revisions and conflict handling.
- `processing.py`: durable runs, leases, checkpoints, outbox dispatch and recovery.
- `apps/web/`: Next.js static frontend; generated API types.
- `migrations/`, `infra/`: database migration and deployment configuration.

Read [architecture](docs/build-plan.md), [organizer brief](docs/hackathon-brief.md), and [submission checklist](docs/submission.md). Agent-specific instructions and skills are local-only.

## Data and evaluation

Official kits belong under ignored `resources/official/bundle` and `resources/official/docker`. Download them from the [organizer folder](https://drive.google.com/drive/folders/1ouOrFF6GMKvJDaX_asN8R6v467W7P8Df). Ground truth is evaluation-only and excluded from runtime images.

```powershell
uv run averis inspect
uv run averis validate resources/official/bundle/sample_submission.json
uv run averis score resources/official/bundle/sample_submission.json
# Snapshot: JSON object mapping original email IDs to complete CaseView objects
uv run averis export outputs/case-snapshot.json --output outputs/submission.json --diagnostics outputs/coverage.json
```

The supplied sample submission is a placeholder, **not model output**. The existing score command invokes the unchanged official scorer. Unsupported export states must block export, never be replaced with invented categories or matches. Report automatic coverage, abstentions, and reviewer-assisted results separately.

## Cost controls

Live AI defaults off. Verify earlier project spending and provider prices, initialize the shared budget ledger, and only then enable it. The combined Jev ceiling is $7 including earlier experiments: at most $5 development and $2 demonstrations. Reservations are atomic; uncertain charged outcomes retain their reservation. Public sessions also have processing quotas. Cloud budget alerts are notifications, not a guaranteed spending cap.
