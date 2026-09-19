"""Private HTTP worker; Cloud Run IAM is mandatory in production."""

import logging

from fastapi import FastAPI, HTTPException

from averis.config import Settings
from averis.persistence import Database
from averis.processing import Processor
from averis.storage import Storage

logging.basicConfig(level=logging.WARNING)
logging.getLogger("averis.processing").setLevel(logging.INFO)

settings = Settings()
settings.validate_deployment()
db = Database(settings.database_url)
processor = Processor(db, settings, Storage(settings))
app = FastAPI(title="Averis private processor", docs_url=None, openapi_url=None)


@app.post("/internal/runs/{run_id}")
def execute(run_id: str) -> dict[str, str]:
    result = processor.execute(run_id)
    if result in {"busy", "retry"}:
        raise HTTPException(503, "Task not terminal; retry delivery")
    return {"status": result}


@app.post("/internal/reconcile")
def reconcile() -> dict[str, int]:
    return {"dispatched": processor.reconcile()}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "role": "private-worker"}
