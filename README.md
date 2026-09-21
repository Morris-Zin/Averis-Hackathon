# Averis — shipping document review

Averis classifies incoming shipping emails, compares draft Bills of Lading against
Shipping Instructions, and links findings to source evidence.

**[Live demo](https://averis-hackathon-production.up.railway.app/)**

## Workflow

- Classify messages as BL comparison, SI request, invoice query, general or spam.
- Compare seven fields against the SI: shipper, consignee, notify party, loading
  port, discharge port, container count and gross weight.
- Route mismatches automatically to review. Missing, uncertain or unreadable
  evidence cannot establish a match; known mismatches remain visible alongside it.
- Inspect original documents and source passages. Correct a reading, recompute
  the comparison and retain the original documents and revision history.
- Keep confirmed and suspected spam in a separate queue. **Not spam** restores
  a message to review for category selection without erasing its AI suggestion.

The app accepts TXT, PDF, DOCX, XLSX, PNG and JPEG attachments. English is the
primary language; readers also recognize supported Chinese and Malay labels.
Scans use Tesseract for English/Malay and RapidOCR for Chinese. Ambiguous layouts,
weak OCR and uncertain shipment pairing remain review work. Optional DeepSeek
assistance supplements unresolved Jev field readings. Code owns source validation,
unit conversion and comparison; provider confidence is not measured accuracy.

Gross-weight policy: a complete numeric weight with no unit defaults to kilograms,
independently for each document. The reading records `unit_source: default_kg`
and the UI shows “kg (assumed—unit not supplied)”. Explicit kg, pounds, grams and
metric tonnes are converted to kg; contradictory or unsupported units, missing
values and uncertain readings still require review. This is a business default,
not proof of the source unit: an unlabeled pounds value will be interpreted as kg.
Isolated numeric fragments selected from complex PDF blocks still require a unit.

## Run locally

Requires Python 3.12+, uv, Node 24, pnpm 10.26.2 and PostgreSQL. Scans require
Tesseract with `eng`, `msa`, `chi_sim` and `chi_tra` data; the Docker image includes
these. RapidOCR models are bundled with the locked Python dependencies.

```powershell
uv sync --project backend --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
$env:AVERIS_DATABASE_URL = 'postgresql+psycopg://averis:averis@localhost:5432/averis'
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn averis.api:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** and choose **Enter demo workspace**. Each session
gets an isolated persistent workspace with illustrative saved cases and simulated
reviewer identities. Uploaded documents and cases are not automatically deleted.
The private browser cookie is renewed on authenticated requests for up to 400 days
(subject to browser policies). Existing stored session tokens retain access past
the old 24-hour cutoff. Logging out revokes that token; clearing cookies or prior
deletion cannot be recovered automatically. New sessions remain separate workspaces.
No mailbox connection is required. SQLite is also available
for quick local UI development; deployment and concurrency tests use PostgreSQL.
Configuration is documented in [.env.example](.env.example); keep secrets in
server-side environment variables or an ignored `.env` file.

Alternatively, `docker compose up --build` starts the local database, app and
worker. The optional `object-storage` profile adds MinIO for S3 adapter testing.

**Add email** accepts pasted email content and attachments. **Bulk import** accepts
email JSON files or an organizer-style ZIP containing email JSON and attachments,
with preview and per-email accepted/duplicate/failed results. Identical submissions
in the same workspace reuse the existing case. Limits are eight attachments,
10 MB per file and 20 MB combined. New processing requires live AI configuration
and the verified spending guard. Arbitrary revised-document uploads are operator-only.

## Architecture and deployment

Next.js builds a static frontend served by a Python FastAPI API. A private Python
worker processes durable jobs in PostgreSQL; private R2 stores original documents.
The deployed services run on Railway with Neon PostgreSQL. Versioned reader and
AI adapters can be replaced without moving comparison rules into HTTP or UI code.

Document formats, OCR, previews and subprocess limits live inside
`backend/src/averis/documents/`, behind the public evidence-reading interface.
`case_queries.py` owns workspace-scoped queue filters, pagination and counts;
HTTP routes translate its results into API responses. `maintenance.py` invokes
run recovery without deleting workspace data or original documents.
The processor owns job leases, checkpoints and publication of current results.

Railway uses the root [Dockerfile](Dockerfile) for both services:

- Public service: `AVERIS_ROLE=web`, `/health` health check, and
  `alembic upgrade head` before deployment. Configure the public HTTPS origin,
  production mode, PostgreSQL, private R2 and provider credentials server-side.
- Private worker: start command `python -m averis.runner`, with no public domain.
  The current configuration uses two Singapore replicas, one job per replica,
  and a 500-second shutdown grace period. Place services near the database.
- [Railway configuration](infra/railway) records intended settings; the current
  deployment applies these through Railway service settings, not automatically
  through those JSON files. Leave Google task settings empty for this deployment.

Live inference defaults off. Verify provider spending and initialize the shared
budget ledger before enabling it. Reservations are atomic; uncertain charged
outcomes retain their reservations. Cloud budget alerts are not spending caps.
The project's combined Jev allowance is $7, including earlier experiments.

## Verification

```powershell
$env:AVERIS_TEST_DATABASE_URL = $env:AVERIS_DATABASE_URL
uv run --project backend python scripts/verify.py
```

Checks include Python formatting, lint, complexity, strict types, module boundaries,
tests, API contract drift, frontend formatting, types, lint, Knip, tests and a
production build. PostgreSQL tests use temporary schemas. No paid provider is
called. `--backend-only` runs just the backend checks.

Run `pnpm --dir frontend knip` for unused frontend dependencies and exports.
Generated API types remain generator-owned and are checked against OpenAPI.

## Repository layout

- `frontend/`: Next.js pages, review UI, generated API types and frontend tests.
- `backend/src/averis/`: contracts, readers, providers, comparison, review,
  persistence, API and workers.
- `backend/migrations/`, `backend/tests/`: schema migrations and offline checks.
- `scripts/`: verification, evaluation, operations and port-directory generation.
- `infra/railway/`: intended public-service and worker settings.

Research notes, historical reports, evaluation outputs and video-authoring assets
are kept locally rather than versioned with the application.

## Evaluation and reference data

Place organizer kits under ignored `resources/official/bundle` and
`resources/official/docker` from the
[organizer folder](https://drive.google.com/drive/folders/1ouOrFF6GMKvJDaX_asN8R6v467W7P8Df).
Ground truth is evaluation-only and excluded from runtime images.

```powershell
uv run --project backend averis inspect
uv run --project backend averis validate resources/official/bundle/sample_submission.json
uv run --project backend averis score resources/official/bundle/sample_submission.json
uv run --project backend averis export outputs/case-snapshot.json --output outputs/submission.json --diagnostics outputs/coverage.json
```

The sample submission is a placeholder, not model output. Scoring invokes the
unchanged official scorer. Report automatic coverage, abstentions and any human
assistance separately; unsupported export states remain blocked.

The two-column SI/BL spreadsheet template can establish a shared order from its
native A3/B3 header when the worksheet structure matches. This does not equate
arbitrary instruction and bill numbers; conflicting references still block
pairing. Unitless weights remain unresolved. OCR-only field uncertainty without
known mismatches can export `NEEDS_REVIEW / unreadable`; mixed unsupported issues
remain blocked and existing known-mismatch exports retain their diagnostics.

Port normalization uses a bundled, checksum-verified UN/LOCODE reference with
conservative alias rules. See its [provenance and license](backend/src/averis/reference_data/README.md).
