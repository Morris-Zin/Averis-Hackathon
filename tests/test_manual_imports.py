"""Public manual intake preserves isolation and durability without usage quotas."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from averis.api import create_app
from averis.config import Settings
from averis.persistence import Outbox, Run


@pytest.fixture
def manual_client(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'manual.db'}",
        storage_dir=str(tmp_path / "objects"),
        live_enabled=True,
        budget_verified=True,
    )
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        session = client.post(
            "/api/demo/session", headers={"origin": settings.origin}
        ).json()
        headers = {"origin": settings.origin, "x-csrf-token": session["csrf_token"]}
        yield client, headers, app.state.db


def submit(client, headers, subject="Manual test", files=None):
    return client.post(
        "/api/manual-imports",
        headers=headers,
        data={
            "email": json.dumps(
                {
                    "subject": subject,
                    "sender": "tester@example.test",
                    "body": "Please review these documents.",
                }
            )
        },
        files=files,
    )


def test_import_without_attachments_is_durable_and_deduplicated(manual_client):
    client, headers, db = manual_client
    first = submit(client, headers)
    assert first.status_code == 200
    assert first.json()["processing"] == "queued"
    assert first.json()["attachments"] == []
    assert submit(client, headers).json()["id"] == first.json()["id"]
    with db.session() as session:
        runs = session.scalars(select(Run)).all()
        assert len(runs) == 1
        assert runs[0].purpose == "demo"
        assert session.get(Outbox, runs[0].id) is not None
    assert submit(client, headers, "Second").status_code == 200
    assert submit(client, headers, "Third").status_code == 200
    assert submit(client, headers, "Fourth").status_code == 200
    assert client.get("/api/cases").json()["total"] == 12


def test_public_upload_and_retries_do_not_block_later_imports(manual_client):
    client, headers, _ = manual_client
    response = submit(
        client,
        headers,
        files=[
            (
                "files",
                (
                    "si.txt",
                    b"Shipping instruction\nShipment ID: SYNTHETIC",
                    "text/plain",
                ),
            )
        ],
    )
    assert response.status_code == 200
    case = response.json()
    assert len(case["attachments"]) == 1
    for _ in range(4):
        response = client.post(
            f"/api/cases/{case['id']}/actions",
            headers=headers,
            json={"kind": "retry", "expected_revision": case["revision"]},
        )
        assert response.status_code == 200
        case = response.json()
    assert submit(client, headers, "Another email").status_code == 200


def test_imports_continue_beyond_former_daily_and_workspace_limits(manual_client):
    client, headers, db = manual_client
    for number in range(101):
        assert submit(client, headers, f"Email {number}").status_code == 200
    with db.session() as session:
        assert len(session.scalars(select(Run)).all()) == 101


def test_session_creation_continues_beyond_former_hourly_limit(manual_client):
    client, headers, _ = manual_client
    for _ in range(11):
        response = client.post(
            "/api/demo/session", headers={"origin": headers["origin"]}
        )
        assert response.status_code == 200


def test_manual_import_requires_session_origin_csrf_and_enabled_processing(
    manual_client,
):
    client, headers, _ = manual_client
    assert submit(client, {"origin": headers["origin"]}).status_code == 403
    assert (
        submit(client, {**headers, "origin": "https://different.example"}).status_code
        == 403
    )
    assert (
        submit(client, headers, files=[("files", ("bad.exe", b"bad"))]).status_code
        == 422
    )
    client.app.state.config.live_enabled = False
    assert submit(client, headers).status_code == 422
    client.cookies.clear()
    assert submit(client, headers).status_code == 401
