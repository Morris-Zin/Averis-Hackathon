# Averis

**Check shipping documents. See the evidence.**

Averis helps shipping teams sort emails and check draft Bills of Lading (BL)
against Shipping Instructions (SI). The SI is the reference document. Averis
shows differences, links them to the source, and sends unclear cases to a person.

Built by **Team GoodLord**: Aung Phone Khant, Pei En, Congye and Ella.

- [Open the demo](https://averis-hackathon-production.up.railway.app/)
- [Read the project document](PROJECT.md): architecture, implementation, challenges, results and roadmap.
- [See the benchmark report](BENCHMARKS.md): scores, test methods and saved outputs.
- [View the source code](https://github.com/Morris-Zin/Averis-Hackathon)

## Try the demo

1. Open the demo and choose **Enter demo workspace**.
2. Open a saved case and view the SI and BL values side by side.
3. Open the source evidence for a finding.
4. Correct a reading. The app checks the fields again and keeps the history.
5. Use **Add email** for one email or **Bulk import** for email JSON files or a ZIP with emails and attachments.

Saved demo cases are examples. Processing new emails needs enabled AI services
and available budget. Each browser session gets its own workspace. Keep that
browser session to return to your cases. Logging out or clearing its cookie can
remove your access. Uploaded files are not deleted automatically.

## What Averis checks

Emails go into five categories: **BL comparison**, **SI request**, **invoice query**,
**general** and **spam**. Only BL comparison emails enter shipment checking.

The seven fields are shipper, consignee, notify party, loading port, discharge
port, container count and gross weight.

```mermaid
flowchart TD
    A[Import email and attachments] --> B[Classify email]
    B -->|Other categories| C[Show in the right queue]
    B -->|Uncertain category| G[Human review]
    B -->|BL comparison| D[Read documents and extract fields]
    D --> E[Compare seven fields against the SI]
    E -->|All seven match with valid evidence| F[No mismatch detected]
    E -->|Difference or missing or unclear evidence| G
    G --> H[Check source and correct the reading]
    H --> E
```

- Differences go to review automatically.
- Missing or unclear evidence cannot count as a match.
- A known difference stays visible even when another field is unclear.
- A correction changes the app's reading. It does not change the uploaded file.
- Files can be TXT, PDF, DOCX, XLSX, PNG or JPEG. OCR reads text from scanned pages and images.
- English is the main language. Readers also support Chinese and Malay text and labels, with limits on difficult layouts.

For gross weight, a complete number with no unit is treated as kilograms. The
app shows that this is an assumption. Explicit supported units are converted to
kilograms. Missing values, conflicting units and unclear readings still need
review. A number meant to be pounds but written with no unit can be read as
kilograms, so this default needs care.

## Run on your computer

### Option 1: Docker

Install Git and Docker Desktop. Start Docker Desktop, then run:

```powershell
git clone https://github.com/Morris-Zin/Averis-Hackathon.git
cd Averis-Hackathon
docker compose up --build
```

Wait for the services to start, then open **http://localhost:8000**. The first
build downloads dependencies and OCR tools. Docker starts PostgreSQL, the web
app and a worker service. Files and database records use local volumes.

This setup lets you explore the saved demo and review tools. New AI processing
is off. You do not need an API key to show the saved demo.

To stop the services and keep saved data:

```powershell
docker compose down
```

### Option 2: Local development

Install Git, Python 3.12 or newer, uv, Node.js 24, pnpm 10.26.2 and PostgreSQL.
The commands below use PowerShell and run from the repository root.

1. Clone the repository and install dependencies:

```powershell
git clone https://github.com/Morris-Zin/Averis-Hackathon.git
cd Averis-Hackathon
uv sync --project backend --locked
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
Copy-Item .env.example .env
```

Do not overwrite an existing `.env` when repeating setup.

2. Create a PostgreSQL database. With Docker Desktop, this command creates a
   local development database on port 5432:

```powershell
docker run --name averis-dev-db -e POSTGRES_USER=averis -e POSTGRES_PASSWORD=averis -e POSTGRES_DB=averis -p 5432:5432 -v averis-dev-db-data:/var/lib/postgresql/data -d postgres:16-alpine
```

If PostgreSQL is already running, create an `averis` database there and set
`AVERIS_DATABASE_URL` in `.env` to its connection URL instead. The example
username and password above are only for local development.

3. Wait for the database to be ready, then create its tables and start the API:

```powershell
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn averis.api:app --host 127.0.0.1 --port 8000
```

4. Open **http://localhost:8000**. The API serves the built frontend too.

5. In a second terminal at the repository root, start the background worker:

```powershell
uv run --project backend python -m averis.runner
```

Leave `AVERIS_TASKS_QUEUE` empty with this worker. Both processes read the same
root `.env`. They need the same database and storage settings.

For scans, install Tesseract and make `tesseract` available on your PATH. Install
its `eng`, `msa`, `chi_sim` and `chi_tra` language data. RapidOCR comes with the
locked Python dependencies. The Docker image includes the Tesseract tools.

### Enable new AI processing

Saved cases work with AI off. To process new uploads, set these values in the
root `.env` locally, or in both services' server settings for deployment:

| Setting | What to enter |
| --- | --- |
| `TYPESAFE_API_KEY` | Your TypeSafe key for Jev |
| `AVERIS_INPUT_USD_PER_MILLION` | The verified input price for your model |
| `AVERIS_OUTPUT_USD_PER_MILLION` | The verified output price for your model |
| `AVERIS_PRIOR_SPEND_USD` | Spending before this database's budget record was created |
| `AVERIS_BUDGET_VERIFIED` | `true` after checking prices and prior spending |
| `AVERIS_LIVE_ENABLED` | `true` when ready to allow paid processing |

The budget code reserves spending before each call. The project has a shared
$7 Jev allowance, including experiments. See [the budget code](backend/src/averis/budget.py)
for the limits and saved budget rules. Restart the API and worker after changing settings.

After creating the database tables and verifying prices and prior spending,
initialize the budget record once:

```powershell
uv run --project backend python scripts/manage.py init-budget --confirm-starting-usage
uv run --project backend python scripts/manage.py budget
```

The first command refuses to reset an existing budget. Keep the prior spending
setting consistent with the saved record. These two commands do not call AI.

DeepSeek field help is optional. Set `DEEPSEEK_API_KEY` and
`AVERIS_DEEPSEEK_FIELDS_ENABLED=true` to use it. Keep keys on the server. Never
commit `.env`. Docker Compose fixes AI processing to off. Enabling it there also
needs both services' environment settings changed in your local Compose setup.

Uploads allow up to eight attachments, 10 MB per file and 20 MB total. An identical
submission in the same workspace reuses its existing case.

## How it runs in the cloud

Railway runs the FastAPI web service and private Python workers. FastAPI serves
the static Next.js frontend. Neon PostgreSQL stores cases, jobs and history.
Private Cloudflare R2 stores uploaded files. Workers read prepared document text
with Jev and optional DeepSeek help, then Python code compares the fields.

The Railway workers poll PostgreSQL for jobs. Google Cloud Tasks is an alternative
supported in the code, but is not used in this deployment.

See [the architecture diagram and code guide](PROJECT.md#technical-architecture).

## Run the checks

After local setup, use a development PostgreSQL database where tests can create
temporary schemas. Set its URL in the terminal:

```powershell
$env:AVERIS_TEST_DATABASE_URL = 'postgresql+psycopg://averis:averis@localhost:5432/averis'
uv run --project backend python scripts/verify.py
```

This runs backend tests, type and style checks, API contract checks, frontend
tests, and a production frontend build. It makes no paid AI calls. Add
`--backend-only` for backend checks only.

## Code guide

| Folder | What it contains |
| --- | --- |
| `frontend/` | Pages, review tools, API types and frontend tests |
| `backend/src/averis/` | Email intake, readers, AI adapters, comparison, API and workers |
| `backend/migrations/` | Database changes |
| `backend/tests/` | Automated backend checks |
| `scripts/` | Verification, evaluation and support scripts |
| `infra/railway/` | Reference settings for deployment |

Organizer answer labels are used only for evaluation. They are not used by the
app to decide results and are not included in its runtime image. Port names use
a bundled UN/LOCODE reference. See its
[source and license](backend/src/averis/reference_data/README.md).

## Results and next steps

The recorded organizer benchmark reached **99.63/100 across 520 emails**, with
**46/46 planted defect cases caught** at checkpoint `68ffe2e`. This was a replay
of saved AI/OCR results on reused development data. It is not a claim of 99.63%
accuracy on new shipments or a hackathon judging score.

Read the [project document](PROJECT.md) for the architecture, test results,
challenges and next steps.
