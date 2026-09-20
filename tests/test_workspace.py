"""Public workspace safety and meaningful reviewer flows, without paid providers."""

from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from averis.api import COOKIE, create_app
from averis.config import Settings
from averis.domain import AttachmentView, CaseView
from averis.persistence import BrowserSession, Case, Database, Document, utcnow


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_dir=str(tmp_path / "objects"),
        operator_token="test-operator",
    )
    db = Database(settings.database_url)
    with TestClient(create_app(settings, db), base_url=settings.origin) as client:
        response = client.post("/api/demo/session", headers={"origin": settings.origin})
        assert response.status_code == 200, response.text
        headers = {
            "origin": settings.origin,
            "x-csrf-token": response.json()["csrf_token"],
        }
        yield client, headers, db, settings


def test_workspace_isolation_csrf_and_expiration(workspace):
    client, _headers, db, settings = workspace
    item = client.get("/api/cases").json()["items"][0]
    action = {
        "kind": "assign",
        "expected_revision": item["revision"],
        "assignee": "Mei Lin",
    }
    assert (
        client.post(f"/api/cases/{item['id']}/actions", json=action).status_code == 403
    )
    with TestClient(create_app(settings, db), base_url=settings.origin) as stranger:
        stranger.post("/api/demo/session", headers={"origin": settings.origin})
        assert stranger.get(f"/api/cases/{item['id']}").status_code == 404
        doc = item["attachments"][0]["id"]
        assert stranger.get(f"/api/documents/{doc}/content").status_code == 404
    token = sha256(client.cookies[COOKIE].encode()).hexdigest()
    with db.session() as session, session.begin():
        row = session.get(BrowserSession, token)
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/cases").status_code == 401


def test_mismatch_routes_without_confirmation_and_completion_preserves_it(workspace):
    client, headers, _, _ = workspace
    items = client.get("/api/cases?view=mismatches").json()["items"]
    assert len(items) == 1
    item = items[0]
    outcomes = {f["field"]: f["outcome"] for f in item["report"]["findings"]}
    assert outcomes["container_count"] == outcomes["port_of_discharge"] == "mismatch"
    result = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "workflow",
            "workflow": "completed",
            "expected_revision": item["revision"],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["report"] == item["report"]
    assert client.get("/api/cases?view=mismatches").json()["total"] == 1
    assert client.get("/api/cases?view=completed").json()["total"] == 1


def test_correction_is_source_bound_and_does_not_hide_genuine_mismatch(workspace):
    client, headers, _, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    bl = next(a for a in item["attachments"] if a["role"] == "BL")
    payload = {
        "kind": "correct",
        "expected_revision": item["revision"],
        "document_id": bl["id"],
        "field": "container_count",
        "evidence_ids": ["container_count"],
        "reason": "Read from the original draft",
    }
    bad = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={**payload, "transcription": "3", "verified": True},
    )
    assert bad.status_code == 422
    result = client.post(
        f"/api/cases/{item['id']}/actions", headers=headers, json=payload
    )
    assert result.status_code == 200, result.text
    finding = next(
        f
        for f in result.json()["report"]["findings"]
        if f["field"] == "container_count"
    )
    assert finding["outcome"] == "mismatch"
    assert finding["bl"]["normalized"] == "4"
    assert finding["bl"]["provenance"] == "human_verified"
    conflict = client.post(
        f"/api/cases/{item['id']}/actions", headers=headers, json=payload
    )
    assert conflict.status_code == 409


def test_controlled_revision_keeps_original_and_recomputes(workspace):
    client, headers, _, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    old = next(a for a in item["attachments"] if a["role"] == "BL")
    original = client.get(f"/api/documents/{old['id']}/content").content
    result = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "revision",
            "expected_revision": item["revision"],
            "reason": "Use controlled revised draft",
        },
    )
    assert result.status_code == 200, result.text
    revised = result.json()
    assert revised["input_revision"] == item["input_revision"] + 1
    assert len(revised["attachments"]) == 3
    assert all(f["outcome"] == "match" for f in revised["report"]["findings"])
    assert client.get(f"/api/documents/{old['id']}/content").content == original


def test_uncertain_category_is_editable_without_paid_processing(workspace):
    client, headers, _, _ = workspace
    item = next(
        c
        for c in client.get("/api/cases?view=review").json()["items"]
        if c["classification"]["accepted"] is None
    )
    result = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "category",
            "category": "BL_COMPARISON",
            "expected_revision": item["revision"],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["classification"]["source"] == "human"
    assert result.json()["report"]["pair_valid"]


def test_operator_import_deduplicates_and_persists_outbox(workspace):
    client, headers, _, _ = workspace
    files = {
        "files": (
            "draft.txt",
            b"Shipment ID: TEST-001\nContainer count: 4",
            "text/plain",
        )
    }
    data = {
        "email": '{"subject":"New case after frontend build","sender":"sender@example.test","body":"Check documents"}'
    }
    assert (
        client.post("/api/imports", data=data, files=files, headers=headers).status_code
        == 403
    )
    headers = {**headers, "x-operator-token": "test-operator"}
    first = client.post("/api/imports", data=data, files=files, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post("/api/imports", data=data, files=files, headers=headers)
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["processing"] == "queued"
    assert client.get("/api/cases?q=New%20case").json()["total"] == 1


def test_report_issue_keeps_case_in_review_after_last_field_correction(workspace):
    client, headers, db, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    bl = next(
        attachment for attachment in item["attachments"] if attachment["role"] == "BL"
    )

    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        assert row is not None
        view = CaseView.model_validate(row.state)
        assert view.report is not None
        finding = next(
            candidate
            for candidate in view.report.findings
            if candidate.field == "shipper"
        )
        finding.bl.issue = "low_field_confidence"
        finding.outcome = "unresolved"
        view.report.issues = ["document_truncated"]
        view.review_reasons = ["document_truncated", "Some fields need review"]
        row.state = view.model_dump(mode="json")

    result = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "correct",
            "expected_revision": item["revision"],
            "document_id": bl["id"],
            "field": "shipper",
            "evidence_ids": ["shipper"],
            "reason": "Confirmed the complete native source block",
        },
    )
    assert result.status_code == 200, result.text
    corrected = result.json()
    assert corrected["report"]["issues"] == ["document_truncated"]
    assert "document_truncated" in corrected["review_reasons"]
    assert all(
        finding["outcome"] != "unresolved"
        for finding in corrected["report"]["findings"]
    )
    review_ids = {
        case["id"] for case in client.get("/api/cases?view=review").json()["items"]
    }
    assert item["id"] in review_ids


def test_superseded_document_is_rejected_for_pair_correction_and_revision(workspace):
    client, headers, _, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    old_bl = next(
        attachment for attachment in item["attachments"] if attachment["role"] == "BL"
    )
    revised_response = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "revision",
            "expected_revision": item["revision"],
            "reason": "Use the controlled revised draft",
        },
    )
    assert revised_response.status_code == 200, revised_response.text
    revised = revised_response.json()
    current_si = next(
        attachment
        for attachment in revised["attachments"]
        if attachment["role"] == "SI" and not attachment["superseded"]
    )
    assert next(
        attachment
        for attachment in revised["attachments"]
        if attachment["id"] == old_bl["id"]
    )["superseded"]

    pair = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "pair",
            "expected_revision": revised["revision"],
            "si_id": current_si["id"],
            "bl_id": old_bl["id"],
            "reason": "Attempt to reuse an earlier draft",
        },
    )
    assert pair.status_code == 422

    correction = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "correct",
            "expected_revision": revised["revision"],
            "document_id": old_bl["id"],
            "field": "shipper",
            "evidence_ids": ["shipper"],
            "reason": "Attempt to correct an earlier draft",
        },
    )
    assert correction.status_code == 422

    revision = client.post(
        f"/api/cases/{item['id']}/revisions",
        headers={**headers, "x-operator-token": "test-operator"},
        data={
            "expected_revision": str(revised["revision"]),
            "document_id": old_bl["id"],
            "reason": "Attempt to branch an earlier draft",
        },
        files={"file": ("replacement.txt", b"replacement", "text/plain")},
    )
    assert revision.status_code == 422
    latest = client.get(f"/api/cases/{item['id']}").json()
    assert (
        len(
            [
                attachment
                for attachment in latest["attachments"]
                if not attachment["superseded"]
            ]
        )
        == 2
    )


def test_operator_import_rejects_combined_attachments_over_twenty_megabytes(workspace):
    client, headers, db, settings = workspace
    with db.session() as session:
        cases_before = session.scalar(select(func.count()).select_from(Case))
        documents_before = session.scalar(select(func.count()).select_from(Document))
    files_before = {
        path for path in Path(settings.storage_dir).rglob("*") if path.is_file()
    }
    megabyte = 1024 * 1024
    files = [
        ("files", ("part-a.txt", b"a" * (7 * megabyte), "text/plain")),
        ("files", ("part-b.txt", b"b" * (7 * megabyte), "text/plain")),
        ("files", ("part-c.txt", b"c" * (6 * megabyte + 1), "text/plain")),
    ]
    response = client.post(
        "/api/imports",
        headers={**headers, "x-operator-token": "test-operator"},
        data={
            "email": '{"subject":"Oversized email","sender":"sender@example.test","body":"Check"}'
        },
        files=files,
    )
    assert response.status_code == 413, response.text
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Case)) == cases_before
        assert (
            session.scalar(select(func.count()).select_from(Document))
            == documents_before
        )
    assert {
        path for path in Path(settings.storage_dir).rglob("*") if path.is_file()
    } == files_before


def test_two_sessions_in_one_workspace_enforce_expected_revision(workspace):
    client, headers, db, settings = workspace
    item = client.get("/api/cases").json()["items"][0]
    primary_hash = sha256(client.cookies[COOKIE].encode()).hexdigest()
    second_raw = "second-explicit-browser-session"
    second_csrf = "second-explicit-browser-csrf"
    with db.session() as session, session.begin():
        primary = session.get(BrowserSession, primary_hash)
        assert primary is not None
        session.add(
            BrowserSession(
                token_hash=sha256(second_raw.encode()).hexdigest(),
                workspace_id=primary.workspace_id,
                actor="Mei Lin",
                csrf=second_csrf,
                expires_at=primary.expires_at,
            )
        )

    with TestClient(create_app(settings, db), base_url=settings.origin) as second:
        second.cookies.set(COOKIE, second_raw)
        assert second.get(f"/api/cases/{item['id']}").status_code == 200
        first_update = client.post(
            f"/api/cases/{item['id']}/actions",
            headers=headers,
            json={
                "kind": "assign",
                "expected_revision": item["revision"],
                "assignee": "Aisha Rahman",
            },
        )
        assert first_update.status_code == 200, first_update.text
        stale_update = second.post(
            f"/api/cases/{item['id']}/actions",
            headers={"origin": settings.origin, "x-csrf-token": second_csrf},
            json={
                "kind": "assign",
                "expected_revision": item["revision"],
                "assignee": "Mei Lin",
            },
        )
        assert stale_update.status_code == 409


def test_expired_session_cannot_read_evidence_but_fresh_same_workspace_session_can(
    workspace,
):
    client, _, db, _ = workspace
    item = client.get("/api/cases").json()["items"][0]
    document_id = item["attachments"][0]["id"]
    expected = client.get(f"/api/documents/{document_id}/content").content
    primary_hash = sha256(client.cookies[COOKIE].encode()).hexdigest()
    fresh_raw = "refreshed-browser-session"
    with db.session() as session, session.begin():
        primary = session.get(BrowserSession, primary_hash)
        assert primary is not None
        workspace_id = primary.workspace_id
        primary.expires_at = utcnow() - timedelta(seconds=1)
        session.add(
            BrowserSession(
                token_hash=sha256(fresh_raw.encode()).hexdigest(),
                workspace_id=workspace_id,
                actor="John Tan",
                csrf="refreshed-browser-csrf",
                expires_at=utcnow() + timedelta(hours=1),
            )
        )

    assert client.get(f"/api/documents/{document_id}/content").status_code == 401
    client.cookies.set(COOKIE, fresh_raw)
    refreshed = client.get(f"/api/documents/{document_id}/content")
    assert refreshed.status_code == 200
    assert refreshed.content == expected


def test_unicode_document_name_keeps_download_available(workspace):
    from urllib.parse import unquote

    client, _, db, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    document_id = item["attachments"][0]["id"]
    filename = "装运指示.txt"
    with db.session() as session, session.begin():
        document = session.get(Document, document_id)
        document.filename = filename
    response = client.get(f"/api/documents/{document_id}/content")
    assert response.status_code == 200
    assert (
        unquote(response.headers["content-disposition"])
        == "inline; filename*=UTF-8''" + filename
    )


def test_controlled_revision_respects_document_cap_without_creating_objects(workspace):
    client, headers, db, settings = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        assert row is not None
        view = CaseView.model_validate(row.state)
        view.attachments.extend(
            AttachmentView(
                id=f"cap-placeholder-{index}", filename=f"version-{index}.txt"
            )
            for index in range(22)
        )
        assert len(view.attachments) == 24
        row.state = view.model_dump(mode="json")

    baseline = client.get(f"/api/cases/{item['id']}").json()
    with db.session() as session:
        documents_before = session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.case_id == item["id"])
        )
    files_before = {
        path for path in Path(settings.storage_dir).rglob("*") if path.is_file()
    }

    response = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "revision",
            "expected_revision": baseline["revision"],
            "reason": "Attempt a version beyond the cap",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Document version limit reached"
    assert client.get(f"/api/cases/{item['id']}").json() == baseline
    with db.session() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.case_id == item["id"])
            )
            == documents_before
        )
    assert {
        path for path in Path(settings.storage_dir).rglob("*") if path.is_file()
    } == files_before


def test_non_comparison_category_rejects_pair_correction_and_revisions_without_mutation(
    workspace,
):
    client, headers, db, settings = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    si = next(
        attachment for attachment in item["attachments"] if attachment["role"] == "SI"
    )
    bl = next(
        attachment for attachment in item["attachments"] if attachment["role"] == "BL"
    )
    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        assert row is not None
        view = CaseView.model_validate(row.state)
        assert view.classification is not None
        view.classification.accepted = "GENERAL"
        view.classification.source = "human"
        row.state = view.model_dump(mode="json")

    baseline = client.get(f"/api/cases/{item['id']}").json()
    with db.session() as session:
        row = session.get(Case, item["id"])
        assert row is not None
        accepted_pair_before = row.accepted_pair
        documents_before = session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.case_id == item["id"])
        )
    files_before = {
        path for path in Path(settings.storage_dir).rglob("*") if path.is_file()
    }
    expected_detail = (
        "Accept the BL comparison category before reviewing shipment documents"
    )

    actions = [
        {
            "kind": "pair",
            "expected_revision": baseline["revision"],
            "si_id": si["id"],
            "bl_id": bl["id"],
            "reason": "Attempt comparison under a general category",
        },
        {
            "kind": "correct",
            "expected_revision": baseline["revision"],
            "document_id": bl["id"],
            "field": "shipper",
            "evidence_ids": ["shipper"],
            "reason": "Attempt correction under a general category",
        },
        {
            "kind": "revision",
            "expected_revision": baseline["revision"],
            "reason": "Attempt controlled revision under a general category",
        },
    ]
    for action in actions:
        response = client.post(
            f"/api/cases/{item['id']}/actions", headers=headers, json=action
        )
        assert response.status_code == 422
        assert response.json()["detail"] == expected_detail

    operator_revision = client.post(
        f"/api/cases/{item['id']}/revisions",
        headers={**headers, "x-operator-token": "test-operator"},
        data={
            "expected_revision": str(baseline["revision"]),
            "document_id": bl["id"],
            "reason": "Attempt operator revision under a general category",
        },
        files={"file": ("replacement.txt", b"replacement", "text/plain")},
    )
    assert operator_revision.status_code == 422
    assert operator_revision.json()["detail"] == expected_detail
    assert client.get(f"/api/cases/{item['id']}").json() == baseline
    with db.session() as session:
        row = session.get(Case, item["id"])
        assert row is not None
        assert row.accepted_pair == accepted_pair_before
        assert (
            session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.case_id == item["id"])
            )
            == documents_before
        )
    assert {
        path for path in Path(settings.storage_dir).rglob("*") if path.is_file()
    } == files_before


def test_successive_category_corrections_preserve_each_transition_and_model_output(
    workspace,
):
    client, headers, _, _ = workspace
    item = next(
        case
        for case in client.get("/api/cases").json()["items"]
        if case["classification"]["accepted"] == "INVOICE_QUERY"
    )
    suggestion = item["classification"]["suggested"]
    probabilities = item["classification"]["probabilities"]

    first = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "category",
            "category": "GENERAL",
            "expected_revision": item["revision"],
            "reason": "Reviewer found a general shipping enquiry",
        },
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "category",
            "category": "SI_REQUEST",
            "expected_revision": first.json()["revision"],
            "reason": "Reviewer confirmed an instruction request",
        },
    )
    assert second.status_code == 200, second.text
    corrected = second.json()
    assert corrected["classification"]["accepted"] == "SI_REQUEST"
    assert corrected["classification"]["source"] == "human"
    assert corrected["classification"]["suggested"] == suggestion
    assert corrected["classification"]["probabilities"] == probabilities
    details = [entry["detail"] for entry in corrected["history"][-2:]]
    assert details == [
        "Category changed from INVOICE_QUERY to GENERAL: Reviewer found a general shipping enquiry",
        "Category changed from GENERAL to SI_REQUEST: Reviewer confirmed an instruction request",
    ]


def test_controlled_revision_remains_available_after_live_classification(workspace):
    client, headers, db, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        view = CaseView.model_validate(row.state)
        view.classification.model = "jev-test-result"
        view.classification.source = "model"
        row.state = view.model_dump(mode="json")
    response = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "revision",
            "expected_revision": item["revision"],
            "reason": "Controlled replacement after live classification",
        },
    )
    assert response.status_code == 200
    assert len(response.json()["attachments"]) == 3
    assert response.json()["report"]["pair_valid"]


def test_unverified_ocr_correction_cannot_remove_existing_mismatch(workspace):
    client, headers, db, _ = workspace
    item = client.get("/api/cases?view=mismatches").json()["items"][0]
    bl_id = next(a["id"] for a in item["attachments"] if a["role"] == "BL")
    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        view = CaseView.model_validate(row.state)
        document = next(a for a in view.attachments if a.id == bl_id)
        next(
            b for b in document.evidence.blocks if b.id == "container_count"
        ).method = "ocr"
        row.state = view.model_dump(mode="json")
    before = client.get(f"/api/cases/{item['id']}").json()
    response = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "correct",
            "expected_revision": item["revision"],
            "document_id": bl_id,
            "field": "container_count",
            "evidence_ids": ["container_count"],
            "transcription": "3",
            "verified": False,
            "reason": "Unverified transcription",
        },
    )
    assert response.status_code == 422
    assert client.get(f"/api/cases/{item['id']}").json() == before
    assert client.get("/api/cases?view=mismatches").json()["total"] == 1
