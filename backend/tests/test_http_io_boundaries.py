"""Slow persistence must not run on the HTTP event loop."""

import asyncio
import json

from fastapi.testclient import TestClient

from averis.api import create_app
from averis.config import Settings
from averis.email_intake import import_email


def test_import_persistence_and_dispatch_run_outside_event_loop(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'http.db'}",
        storage_dir=str(tmp_path / "objects"),
        live_enabled=True,
        budget_verified=True,
    )
    app = create_app(settings)
    calls = []

    def assert_worker_thread():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise AssertionError("Blocking I/O is running on the HTTP event loop")

    def persist(*args, **kwargs):
        assert_worker_thread()
        calls.append("persist")
        return import_email(*args, **kwargs)

    def dispatch(_run_id):
        assert_worker_thread()
        calls.append("dispatch")

    monkeypatch.setattr("averis.routes.persist_import", persist)
    monkeypatch.setattr(app.state.processor, "dispatch", dispatch)
    with TestClient(app, base_url=settings.origin) as client:
        session = client.post(
            "/api/demo/session", headers={"origin": settings.origin}
        ).json()
        response = client.post(
            "/api/manual-imports",
            headers={"origin": settings.origin, "x-csrf-token": session["csrf_token"]},
            data={"email": json.dumps({"subject": "Test", "sender": "", "body": ""})},
        )
        assert response.status_code == 200
        assert calls == ["persist", "dispatch"]
