"""Public input bounds are enforced before data can grow workspace history."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from averis.api import create_app
from averis.config import Settings
from averis.domain import Action


def test_action_contract_bounds_free_text_and_evidence_selection():
    for payload in (
        {"reason": "x" * 4001},
        {"transcription": "x" * 16001},
        {"evidence_ids": ["a"] * 101},
        {"evidence_ids": ["a" * 257]},
    ):
        with pytest.raises(ValidationError):
            Action(kind="correct", expected_revision=1, **payload)


def test_public_json_transport_limit_handles_chunked_body(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'limits.db'}",
        storage_dir=str(tmp_path / "objects"),
    )
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        response = client.post("/api/demo/session", headers={"origin": settings.origin})
        csrf = response.json()["csrf_token"]
        chunks = (chunk for chunk in (b'{"actor":"', b"a" * 262144, b'"}'))
        response = client.post(
            "/api/session/actor",
            content=chunks,
            headers={
                "content-type": "application/json",
                "origin": settings.origin,
                "x-csrf-token": csrf,
            },
        )
        assert response.status_code == 413
        assert client.get("/api/session").json()["actor"] == "John Tan"
