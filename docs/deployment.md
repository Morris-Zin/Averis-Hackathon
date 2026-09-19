# Averis deployment

This document describes the accepted deployment shape. It is configuration and an operator runbook; it does not provision a cloud account, buy services, or contain credentials.

## Railway deployment in progress

Railway is the selected hosting target after the user delegated provider selection. The public service uses the root Dockerfile and `/infra/railway/web.json`: one replica, `/health` startup check, and `alembic upgrade head` as its pre-deploy command. Set `AVERIS_ROLE=web`, the exact Railway HTTPS origin, production mode, Neon PostgreSQL and private R2 credentials as server-side variables. Never commit secret values.

The background service uses `/infra/railway/worker.json` and `python -m averis.runner`, with one replica and one concurrent run by default. It consumes durable PostgreSQL runs through the existing Processor, with periodic recovery in the same process. Do not generate a public domain or expose the IAM-dependent `averis.worker` HTTP service for this service. Deploy the public service and its migrations before starting the worker. Its local delivery/recovery checks pass; deployed acceptance remains pending integration. Leave Google task settings empty for this target. Live inference remains disabled until the shared budget ledger and current account usage have been verified.

The configuration is preparation, not evidence that Railway is deployed. Account agreements, runtime credentials, container deployment and fresh-browser acceptance remain required. The sections below document the retained Cloud Run alternative.

## Cloud Run runtime shape

The repository builds one image with Python 3.12, the FastAPI application, the worker entry point, and the Next.js static export under `apps/web/out`. The container selects its process from `AVERIS_ROLE`:

- `web` runs `averis.api:app` and serves the public frontend and same-origin API.
- `worker` runs `averis.worker:app` and is deployed as a private Cloud Run service.

The public service is request-based with minimum instances 0 and a 480-second request timeout. The private worker is request-based with minimum instances 0, maximum instances 2, concurrency 1, and a 600-second request timeout. The worker's application-level processing deadline is 480 seconds so it can return a bounded response before the platform deadline.

The public service is open to browser traffic. The worker uses internal Cloud Run ingress and IAM. Cloud Tasks sends authenticated `POST /internal/runs/{run_id}` requests using the tasks service account selected on each task. Cloud Scheduler sends an authenticated `POST /internal/reconcile` request every 15 minutes using its scheduler service account. Both delivery identities receive only `roles/run.invoker` on the worker. The public and worker runtime identities can enqueue on this queue and can act as only the tasks delivery service account, which is required to attach its OIDC token. They do not receive project-wide service-account impersonation.

Cloud Tasks is configured for at most two concurrent dispatches and retries failed delivery for up to one hour with backoff. Delivery attempts include startup, routing and lease-contention failures, so the queue does not use a delivery-count limit. The worker and database own the limit of three substantive processing attempts and return success once the run is terminal. A Cloud Run maximum instance setting is a scaling guard, not a guaranteed spend cap: quotas, retries, traffic bursts, and other project resources can still affect billing.

PostgreSQL is external Neon PostgreSQL, supplied through `AVERIS_DATABASE_URL`. Documents use private Cloudflare R2 Standard through the S3-compatible API. R2 credentials and all other secrets are Secret Manager references; secret values are never in Terraform, Compose, or CI.

## Local development

The default Compose profile starts PostgreSQL, the public container on `http://localhost:8000`, and the worker on `http://localhost:8001`. It uses filesystem storage at `/data`, so local development does not require R2 credentials or a live AI provider:

```powershell
docker compose up --build
```

The optional S3-compatible MinIO service is available for storage adapter work:

```powershell
docker compose --profile object-storage up --build
```

The Compose worker is reachable from the public container at `http://worker:8080`; it is not a substitute for Cloud Run IAM. Keep local credentials in an untracked environment file if a test needs them.

## Google Cloud configuration

Terraform files live in [`infra/terraform`](../infra/terraform). They create the Artifact Registry repository, two Cloud Run services, Cloud Tasks queue, 15-minute Scheduler job, runtime service accounts, IAM bindings, and empty Secret Manager records. They do not create a Neon database, an R2 bucket, Secret Manager versions, a billing account, or secret values.

The worker target uses Cloud Run's deterministic default URL, `https://SERVICE-PROJECT_NUMBER.REGION.run.app`, derived from the selected project's number. This gives the public and worker revisions the same stable target before the worker exists and avoids a Terraform self-reference when `AVERIS_WORKER_URL` is injected into the worker. Cloud Tasks and Scheduler require the default `run.app` endpoint to remain enabled.

The GCP project needs billing enabled and an operator with permission to enable APIs, create the listed resources, attach service accounts, and grant IAM. Cloud costs depend on traffic, storage, egress, database usage, AI usage, logs, and retries. The configured instance and queue limits reduce accidental concurrency but do not guarantee a cost ceiling. Set independent GCP budgets and provider limits before using production data.

Before applying:

1. Create or select a GCP project with billing and enable the relevant APIs, or allow Terraform to enable them.
2. Create the Neon database and private R2 bucket out of band.
3. Create `infra/terraform/terraform.tfvars` from the example. Set `project_id`, the pushed image, and the final HTTPS `public_origin`.
4. Push the image to the Artifact Registry repository. The Cloud Run resources reference an existing image; Terraform does not build it.
5. Run `terraform init`, `terraform validate`, and `terraform plan`, then review the plan. Confirm the computed worker URL contains the expected project number. Apply only after the resource names, region, ingress, IAM bindings, and secret names are correct.
6. Add Secret Manager versions for the names shown by the `secret_names` output. Populate `AVERIS_DATABASE_URL`, `AVERIS_R2_ACCESS_KEY_ID`, `AVERIS_R2_SECRET_ACCESS_KEY`, `AVERIS_OPERATOR_TOKEN`, and `TYPESAFE_API_KEY` using the secret management process. Do not put values in `.tfvars` or commits.
7. Set `r2_endpoint` and `r2_bucket` in `terraform.tfvars`. The endpoint is not a credential; keep the access key values in Secret Manager.
8. Re-apply so both Cloud Run services receive the secret references and final environment values.

The runtime environment names are:

| Name | Kind | Purpose |
| --- | --- | --- |
| `AVERIS_DATABASE_URL` | secret | Neon PostgreSQL connection string |
| `AVERIS_ORIGIN` | value | Public canonical origin |
| `AVERIS_STORAGE_BACKEND` | value | `r2` in Cloud Run, `local` in Compose |
| `AVERIS_STORAGE_DIR` | value | `/data` for local filesystem storage |
| `AVERIS_R2_ENDPOINT` | value | R2 S3-compatible endpoint |
| `AVERIS_R2_BUCKET` | value | Private document bucket |
| `AVERIS_R2_ACCESS_KEY_ID` | secret | R2 access key |
| `AVERIS_R2_SECRET_ACCESS_KEY` | secret | R2 secret key |
| `AVERIS_TASKS_QUEUE` | value | Full Cloud Tasks queue name |
| `AVERIS_WORKER_URL` | value | Private worker Cloud Run URL |
| `AVERIS_TASKS_SERVICE_ACCOUNT` | value | Cloud Tasks OIDC identity |
| `AVERIS_LIVE_ENABLED` | value | `false` until live provider use is explicitly enabled |
| `AVERIS_OPERATOR_TOKEN` | secret | Operator-only internal controls |
| `TYPESAFE_API_KEY` | secret | TypeSafe provider key |
| `AVERIS_ENV` | value | `production` in Cloud Run |

## CI contract

`.github/workflows/ci.yml` runs against PostgreSQL 16 and performs the locked Python sync, pytest, Ruff, Pyright, `python scripts/verify.py`, and the frontend's frozen pnpm install, contract/type check, lint, and static export build. CI sets `AVERIS_LIVE_ENABLED=false` and uses local storage, so it does not make paid provider calls or require cloud credentials.

The workflow is intentionally strict about `uv.lock` and `apps/web/pnpm-lock.yaml`. A dependency change must update its lockfile in the same change. The verification script runs all configured gates; CI does not silently skip missing contract checks.

## Operational checks after deployment

Check `/health` on the public URL and verify that the response is from the expected revision. Confirm a browser request reaches the same-origin API. Enqueue one synthetic run and confirm Cloud Tasks shows an authenticated delivery to the worker, then inspect worker logs for run ID, stage, attempt, and outcome. Trigger or wait for one Scheduler run and confirm `POST /internal/reconcile` succeeds. Finally, verify that a malformed or unauthenticated worker request is rejected and that no document content or secret value is written to logs.

This repository configuration has been validated locally only. Until a reviewed plan is applied and the checks above pass against real resources, Cloud Run reachability, OIDC delivery, IAM permissions and retry behavior remain deployment-unverified.

## Operator observability

Run `uv run python scripts/manage.py metrics` with the deployment database configured to read aggregate run states, attempts, retried runs, oldest queue age, undispatched outbox entries and review rate. The command does not call Jev. Worker logs include delivery duration, run ID and outcome; no document body or signed URL is included in these events. `scripts/manage.py budget` reads reserved/settled bucket totals. Cloud resource/OCR CPU and memory measurements remain a deployment acceptance task.
