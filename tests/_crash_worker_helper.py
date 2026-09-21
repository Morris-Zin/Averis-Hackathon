"""Subprocess entry point for the process-crash recovery acceptance test."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from threading import Event

from psycopg import Connection, sql
from sqlalchemy import event

from averis.config import Settings
from averis.domain import Classification, DocumentEvidence
from averis.intelligence import ExtractionResult, Intelligence
from averis.persistence import Database
from averis.processing import Processor
from averis.runner import DurableRunner, RunnerOptions
from averis.storage import Storage


class LoggedGeneralIntelligence:
    def __init__(self, call_log: Path):
        self.call_log = call_log

    def classify(
        self, subject: str, body: str, *, attachment_filenames: tuple[str, ...] = ()
    ) -> Classification:
        del subject, body
        with self.call_log.open("a", encoding="utf-8") as stream:
            stream.write(f"classify:{os.getpid()}\n")
            stream.flush()
            os.fsync(stream.fileno())
        return Classification(
            suggested="GENERAL",
            accepted="GENERAL",
            confidence=1,
            probabilities={"GENERAL": 1},
            source="fixture",
            model="crash-recovery-double",
        )

    def extract(self, document: DocumentEvidence) -> ExtractionResult:
        del document
        raise AssertionError("GENERAL messages must not reach extraction")


class CheckpointBlockingProcessor(Processor):
    def __init__(
        self,
        database: Database,
        settings: Settings,
        storage: Storage,
        factory: Callable[[str, str], Intelligence],
        ready_file: Path,
    ) -> None:
        super().__init__(database, settings, storage, factory)
        self.ready_file = ready_file

    def _checkpoint(self, run_id: str, token: str, key: str, value: object) -> None:
        super()._checkpoint(run_id, token, key, value)
        if key == "classification":
            self.ready_file.write_text(
                json.dumps({"pid": os.getpid(), "run_id": run_id}),
                encoding="utf-8",
            )
            Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--storage-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--call-log", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--ready-file")
    arguments = parser.parse_args()

    database_url = os.environ["AVERIS_TEST_DATABASE_URL"]
    database = Database(database_url)

    @event.listens_for(database.engine, "connect")
    def set_search_path(
        raw_connection: Connection[tuple[object, ...]],
        _connection_record: object,
    ) -> None:
        cursor = raw_connection.cursor()
        cursor.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(arguments.schema))
        )
        cursor.close()
        raw_connection.commit()

    settings = Settings(
        database_url=database_url,
        storage_backend="local",
        storage_dir=arguments.storage_dir,
        tasks_queue="",
        origin="http://localhost:8000",
        live_enabled=True,
        budget_verified=True,
    )
    intelligence = LoggedGeneralIntelligence(Path(arguments.call_log))

    def factory(_run_id: str, _purpose: str) -> Intelligence:
        return intelligence

    if arguments.ready_file:
        processor = CheckpointBlockingProcessor(
            database,
            settings,
            Storage(settings),
            factory=factory,
            ready_file=Path(arguments.ready_file),
        )
    else:
        processor = Processor(database, settings, Storage(settings), factory=factory)
    runner = DurableRunner(
        processor,
        RunnerOptions(
            concurrency=1,
            poll_seconds=0.05,
            reconcile_seconds=0.1,
            retry_base_seconds=0.1,
            retry_max_seconds=0.1,
        ),
    )
    try:
        outcome = runner.run_available()
        Path(arguments.result_file).write_text(
            json.dumps(outcome, sort_keys=True), encoding="utf-8"
        )
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
