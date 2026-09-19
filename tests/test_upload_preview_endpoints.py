"""Transport, attachment and preview concurrency boundaries through HTTP."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from averis.api import create_app
from averis.config import Settings
from averis.documents import DocumentPreviewError


@pytest.fixture
def endpoint_client(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'api.db'}",
                        storage_dir=str(tmp_path / "objects"), operator_token="offline-test")
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        session = client.post("/api/demo/session", headers={"origin": settings.origin})
        headers = {"origin": settings.origin, "x-csrf-token": session.json()["csrf_token"],
                   "x-operator-token": "offline-test"}
        yield client, headers


def test_chunked_multipart_transport_limit_prevents_case_creation(endpoint_client):
    client, headers = endpoint_client
    before = client.get("/api/cases").json()["total"]
    boundary = "averis-offline-boundary"

    def chunks():
        yield (f'--{boundary}\r\nContent-Disposition: form-data; name="email"\r\n\r\n'
               '{"subject":"Transport limit","sender":"fixture@example.test","body":""}\r\n').encode()
        for index in range(3):
            yield (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                   f'filename="sample{index}.txt"\r\nContent-Type: text/plain\r\n\r\n').encode()
            for _ in range(9):
                yield b"a" * (1024 * 1024)
            yield b"\r\n"
        yield f"--{boundary}--\r\n".encode()

    response = client.post("/api/imports", content=chunks(), headers={
        **headers, "content-type": f"multipart/form-data; boundary={boundary}"})
    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert "transport size limit" in response.json()["detail"]
    assert client.get("/api/cases").json()["total"] == before


@pytest.mark.parametrize("extra,status", [(0, 200), (1, 413)])
def test_individual_attachment_http_boundary(endpoint_client, extra, status):
    client, headers = endpoint_client
    before = client.get("/api/cases").json()["total"]
    response = client.post("/api/imports", headers=headers,
        data={"email": json.dumps({"subject": "Attachment limit", "sender": "fixture@example.test", "body": ""})},
        files=[("files", ("sample.txt", b"a" * (10 * 1024 * 1024 + extra), "text/plain"))])
    assert response.status_code == status, response.text
    assert client.get("/api/cases").json()["total"] == before + (status == 200)


def test_preview_slot_rejects_overlap_and_releases_after_failure(endpoint_client, monkeypatch):
    client, _ = endpoint_client
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    url = f"/api/documents/{item['attachments'][0]['id']}/preview"
    started, release = Event(), Event()

    def failing_preview(*args, **kwargs):
        started.set()
        assert release.wait(5), "test failed to release preview"
        raise DocumentPreviewError("fixture render failure")

    monkeypatch.setattr("averis.documents.render_preview_bounded", failing_preview)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(client.get, url)
        try:
            assert started.wait(5)
            assert client.get(url).status_code == 429
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 422
    monkeypatch.setattr("averis.documents.render_preview_bounded", lambda *args, **kwargs: b"fixture-png")
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"fixture-png"
