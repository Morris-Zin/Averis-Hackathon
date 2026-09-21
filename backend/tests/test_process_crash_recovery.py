"""OS-process crash and durable worker restart acceptance test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import Connection, sql
from sqlalchemy import create_engine, event, text

from averis.domain import AuditEntry, CaseView, Report
from averis.persistence import Base, Case, Database, Outbox, Run, utcnow
from averis.processing import assume_utc_if_naive

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(__file__).with_name("_crash_worker_helper.py")


@pytest.fixture
def crash_database(tmp_path: Path) -> Generator[tuple[Database, str, str, Path]]:
    url = os.getenv("AVERIS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AVERIS_TEST_DATABASE_URL is not configured")

    admin = create_engine(url, pool_pre_ping=True)
    schema = f"averis_crash_{uuid4().hex[:16]}"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    database = Database(url)

    @event.listens_for(database.engine, "connect")
    def set_test_schema(
        raw_connection: Connection[tuple[object, ...]],
        _connection_record: object,
    ) -> None:
        cursor = raw_connection.cursor()
        cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        cursor.close()
        raw_connection.commit()

    Base.metadata.create_all(database.engine)
    try:
        yield database, url, schema, tmp_path
    finally:
        database.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _seed_interrupted_run(database: Database) -> tuple[str, str]:
    case_id, run_id = str(uuid4()), str(uuid4())
    view = CaseView(
        id=case_id,
        subject="Crash recovery fixture",
        sender="fixture@example.test",
        body="This general message has no document comparison.",
        received_at="2026-09-20T00:00:00+00:00",
        revision=1,
        input_revision=1,
        processing="queued",
        stage="queued",
        workflow="open",
        assignee="Unassigned",
        review_reasons=[],
        attachments=[],
        report=Report(
            input_revision=0,
            pair_valid=True,
            issues=["stale report fixture"],
        ),
        history=[
            AuditEntry(
                at="2026-09-20T00:00:00+00:00",
                actor="fixture",
                action="created",
                detail="process crash recovery fixture",
            )
        ],
    )
    with database.session() as session, session.begin():
        session.add(
            Case(
                id=case_id,
                workspace_id="workspace-crash",
                revision=1,
                input_revision=1,
                active_run_id=run_id,
                state=view.model_dump(mode="json"),
            )
        )
        session.add(
            Run(
                id=run_id,
                case_id=case_id,
                input_revision=1,
                purpose="development",
                status="queued",
            )
        )
        session.add(Outbox(run_id=run_id))
    return case_id, run_id


def _worker_command(
    *,
    schema: str,
    storage_dir: Path,
    run_id: str,
    call_log: Path,
    result_file: Path,
    ready_file: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(HELPER),
        "--schema",
        schema,
        "--storage-dir",
        str(storage_dir),
        "--run-id",
        run_id,
        "--call-log",
        str(call_log),
        "--result-file",
        str(result_file),
    ]
    if ready_file is not None:
        command.extend(["--ready-file", str(ready_file)])
    return command


def _start_worker(command: list[str], database_url: str) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    source = str(ROOT / "src")
    environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
    environment["AVERIS_TEST_DATABASE_URL"] = database_url
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_ready(process: subprocess.Popen[str], ready_file: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if ready_file.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(f"crash worker exited before checkpoint: {stdout=} {stderr=}")
        time.sleep(0.05)
    process.kill()
    stdout, stderr = process.communicate(timeout=5)
    pytest.fail(f"checkpoint readiness timed out: {stdout=} {stderr=}")


def _exercise_crash_recovery(
    crash_database: tuple[Database, str, str, Path],
    *,
    accelerate_lease: bool,
) -> dict[str, object]:
    database, url, schema, tmp_path = crash_database
    case_id, run_id = _seed_interrupted_run(database)
    ready_file = tmp_path / "classification-ready.json"
    call_log = tmp_path / "provider-calls.log"
    crashed_result = tmp_path / "crashed-result.json"
    restarted_result = tmp_path / "restarted-result.json"
    storage_dir = tmp_path / "objects"
    process = _start_worker(
        _worker_command(
            schema=schema,
            storage_dir=storage_dir,
            run_id=run_id,
            call_log=call_log,
            result_file=crashed_result,
            ready_file=ready_file,
        ),
        url,
    )
    started = time.monotonic()
    try:
        _wait_for_ready(process, ready_file)
        checkpoint_elapsed = time.monotonic() - started
        process.kill()
        process.communicate(timeout=10)
        assert process.poll() is not None
        assert not crashed_result.exists()

        with database.session() as session:
            interrupted = session.get(Run, run_id)
            row = session.get(Case, case_id)
            assert interrupted is not None
            assert row is not None
            assert interrupted.status == "running"
            assert interrupted.attempts == 1
            assert interrupted.result is None
            assert interrupted.lease_until is not None
            assert assume_utc_if_naive(interrupted.lease_until) > utcnow()
            assert set(interrupted.checkpoint) == {"classification"}
            assert CaseView.model_validate(row.state).report is None

        lease_wait_started = time.monotonic()
        if accelerate_lease:
            with database.session() as session, session.begin():
                interrupted = session.get(Run, run_id)
                outbox = session.get(Outbox, run_id)
                assert interrupted is not None
                assert outbox is not None
                interrupted.lease_until = utcnow() - timedelta(seconds=1)
                outbox.dispatched_at = utcnow() - timedelta(seconds=1)
        else:
            deadline = time.monotonic() + 100
            while time.monotonic() < deadline:
                with database.session() as session:
                    interrupted = session.get(Run, run_id)
                    assert interrupted is not None
                    assert interrupted.lease_until is not None
                    if assume_utc_if_naive(interrupted.lease_until) <= utcnow():
                        break
                time.sleep(0.25)
            else:
                pytest.fail("persisted worker lease did not expire within 100 seconds")
        lease_wait_elapsed = time.monotonic() - lease_wait_started

        restarted = _start_worker(
            _worker_command(
                schema=schema,
                storage_dir=storage_dir,
                run_id=run_id,
                call_log=call_log,
                result_file=restarted_result,
            ),
            url,
        )
        try:
            stdout, stderr = restarted.communicate(timeout=20)
            assert restarted.returncode == 0, f"{stdout=} {stderr=}"
            assert json.loads(restarted_result.read_text(encoding="utf-8")) == {
                run_id: "completed"
            }

            calls = call_log.read_text(encoding="utf-8").splitlines()
            assert len(calls) == 1
            assert calls[0].startswith("classify:")
            ready = json.loads(ready_file.read_text(encoding="utf-8"))
            assert calls == [f"classify:{ready['pid']}"]

            with database.session() as session:
                completed = session.get(Run, run_id)
                row = session.get(Case, case_id)
                assert completed is not None
                assert row is not None
                saved = CaseView.model_validate(row.state)
                assert completed.status == "completed"
                assert completed.attempts == 2
                assert completed.error is None
                assert completed.result is not None
                assert set(completed.checkpoint) == {"classification"}
                assert saved.processing == "completed"
                assert saved.processing_attempts == 2
                assert saved.classification is not None
                assert saved.classification.accepted == "GENERAL"
                assert saved.report is None
                assert "stale report fixture" not in saved.review_reasons
                assert not row.has_mismatch
                assert not row.needs_review

            return {
                "checkpoint_elapsed_seconds": round(checkpoint_elapsed, 3),
                "lease_wait_seconds": round(lease_wait_elapsed, 3),
                "first_process_returncode": process.returncode,
                "restart_process_returncode": restarted.returncode,
                "attempts": 2,
                "classification_calls": 1,
                "outcome": "completed",
                "lease_mode": "accelerated" if accelerate_lease else "natural",
            }
        finally:
            if restarted.poll() is None:
                restarted.kill()
                restarted.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_killed_worker_resumes_checkpoint_after_accelerated_lease_expiry(
    crash_database: tuple[Database, str, str, Path],
) -> None:
    result = _exercise_crash_recovery(crash_database, accelerate_lease=True)
    assert result["outcome"] == "completed"
    assert result["classification_calls"] == 1


@pytest.mark.skipif(
    os.getenv("AVERIS_RUN_NATURAL_LEASE_ACCEPTANCE") != "1",
    reason="set AVERIS_RUN_NATURAL_LEASE_ACCEPTANCE=1 for the 90-second lease check",
)
def test_killed_worker_recovers_after_natural_lease_expiry(
    crash_database: tuple[Database, str, str, Path],
) -> None:
    result = _exercise_crash_recovery(crash_database, accelerate_lease=False)
    lease_wait = result["lease_wait_seconds"]
    assert isinstance(lease_wait, float)
    assert lease_wait >= 85
    output = ROOT.parent / "outputs" / "process-crash-recovery"
    output.mkdir(parents=True, exist_ok=True)
    (output / "natural-expiry.json").write_text(
        json.dumps(
            {
                "scope": (
                    "Local PostgreSQL OS-process kill and natural lease recovery; "
                    "deterministic offline intelligence, no paid calls."
                ),
                **result,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
