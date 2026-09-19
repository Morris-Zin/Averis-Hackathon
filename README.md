# Averis — shipping document verification

Hackathon project foundation for Averis x Monash 2026. **This is a development setup, not the completed AI prototype.** The classifier, extraction pipeline, review UI, and cloud deployment are next.

Read [the research brief](docs/hackathon-brief.md), [architecture and build plan](docs/build-plan.md), and [submission checklist](docs/submission.md) first.

## Quick start (PowerShell)

Prerequisites: Python 3.12+ and uv. Run from the repository root.

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
uv sync --locked
.venv/Scripts/averis.exe inspect
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m uvicorn averis.api:app --reload
```

API documentation: http://127.0.0.1:8000/docs; health: http://127.0.0.1:8000/health.
The health response explicitly reports that the pipeline is not implemented.
`AVERIS_DATA_DIR` can override the dataset directory. `.env.example` documents it; the application reads process environment variables, not `.env` automatically.

## Official resources

Already downloaded and extracted locally under `resources/official/bundle` and `resources/official/docker`. These and the ZIPs are Git-ignored to avoid duplicating vendor data/code in the team's source. Original organizer files have not been modified.

On another computer, download both ZIPs from [the official folder](https://drive.google.com/drive/folders/1ouOrFF6GMKvJDaX_asN8R6v467W7P8Df), save them in `resources/downloads`, then run:

```powershell
Expand-Archive resources/downloads/sdoc-hackathon-bundle.zip resources/official/bundle
Expand-Archive resources/downloads/sdoc-hackathon-docker.zip resources/official/docker
```

The static bundle has **520 emails and 250 attachments** (192 TXT, 28 PDF, 8 DOCX, 22 XLSX). Source text snapshots and the auto-generated ceremony transcript are under `docs/`.

## Evaluation

```powershell
.venv/Scripts/averis.exe validate resources/official/bundle/sample_submission.json
.venv/Scripts/averis.exe score resources/official/bundle/sample_submission.json
# Optional official HTTP dataset/evaluator (requires Docker Desktop running):
docker compose -f resources/official/docker/docker-compose.yml up --build
```

`sample_submission.json` is an all-GENERAL placeholder, not model predictions. Its score only verifies the scoring setup. Use your actual predictions when the pipeline exists. The score command validates all 520 IDs and result consistency before invoking the unchanged organizer scorer. Ground truth is used only by evaluation, never by application inference.

The organizer's later Discord clarification explicitly permits the released ground truth for self-evaluation and supersedes the old organizer-only README wording.

## Structure

- `src/averis/`: typed output contract, local dataset reader, CLI, API health endpoint.
- `tests/`: contradictory-result rejection and API smoke checks.
- `docs/`: requirements, source snapshots, roadmap, submission checklist.
- `resources/official/`: unchanged local organizer kits (ignored).
- `outputs/`: generated predictions and score reports (ignored).

No AI provider, paid resource, or cloud deployment has been configured yet.
