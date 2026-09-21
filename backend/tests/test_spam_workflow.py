"""Spam routing never accepts an uncertain category or clears shipment work."""

from unittest.mock import Mock

import pytest
from sqlalchemy import select

from averis.case_status import assess_case, spam_status
from averis.domain import CaseView
from averis.exporting import adapt_case
from averis.persistence import Case
from averis.pipeline import Checkpoints, ProcessingInput, ShipmentPipeline

pytest_plugins = ["test_workspace", "test_postgres"]


def spam_case(workspace, *, suspected=True, source="model"):
    client, _, db, _ = workspace
    item = next(
        item
        for item in client.get("/api/cases").json()["items"]
        if item["classification"]["accepted"] == "SPAM"
    )
    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        state = dict(row.state)
        state["classification"] = {
            **state["classification"],
            "accepted": None if suspected else "SPAM",
            "source": source,
        }
        state["review_reasons"] = ["classification_uncertain"] if suspected else []
        state["workflow"] = "open" if suspected else "completed"
        row.state = state
    return client.get(f"/api/cases/{item['id']}").json()


@pytest.mark.parametrize("suspected", [True, False])
def test_isolation_counts_recovery_and_export(workspace, suspected):
    client, headers, db, _ = workspace
    item = spam_case(workspace, suspected=suspected)
    page = client.get("/api/cases?view=spam").json()
    assert [case["id"] for case in page["items"]] == [item["id"]]
    assert page["total"] == page["counts"]["spam"] == 1
    assert client.get("/api/cases?view=spam&category=SPAM").json()["total"] == 1
    assert item["summary"]["kind"] == ("suspected_spam" if suspected else "spam")
    case = CaseView.model_validate(
        {key: value for key, value in item.items() if key != "summary"}
    )
    assert not assess_case(case).can_be_clear
    if suspected:
        assert assess_case(case).needs_review
        assert adapt_case(case).diagnostics.blockers == ["category_unresolved"]
    else:
        prediction = adapt_case(case.model_copy(update={"history": []})).prediction
        assert prediction is not None and prediction.category == "SPAM"
    review = client.get("/api/cases?view=review").json()
    assert item["id"] not in [case["id"] for case in review["items"]]
    assert review["total"] == page["counts"]["review"] > 0
    filtered = client.get("/api/cases?view=spam&q=no-such-message").json()
    assert filtered["total"] == 0 and filtered["counts"] == page["counts"]
    response = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "not_spam",
            "expected_revision": item["revision"],
        },
    )
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored["classification"]["suggested"] == "SPAM"
    assert restored["classification"]["accepted"] is None
    assert restored["classification"]["source"] == "human"
    assert restored["summary"]["kind"] == "needs_review"
    assert restored["workflow"] == "open"
    for field in ["body", "attachments", "report"]:
        assert restored[field] == item[field]
    assert restored["history"][:-1] == item["history"]
    assert restored["history"][-1]["action"] == "not_spam"
    assert client.get(f"/api/cases/{item['id']}").json() == restored
    page = client.get("/api/cases?view=review").json()
    assert page["total"] == review["total"] + 1 == page["counts"]["review"]
    assert page["counts"]["spam"] == 0
    with db.session() as session:
        saved = CaseView.model_validate(
            session.scalar(select(Case).where(Case.id == item["id"])).state
        )
    assert adapt_case(saved).diagnostics.blockers == ["category_unresolved"]
    # A retry must preserve the human rejection, without another AI call.
    inference = Mock()
    pipeline = ShipmentPipeline(
        inference, Checkpoints({}, Mock()), Mock(), Mock(), lambda: 400
    )
    result = pipeline.process(ProcessingInput(saved, None, {}))
    assert result.classification == saved.classification
    inference.classify.assert_not_called()
    # Stale action is rejected; a subsequent deliberate non-spam choice works.
    assert (
        client.post(
            f"/api/cases/{item['id']}/actions",
            headers=headers,
            json={
                "kind": "not_spam",
                "expected_revision": item["revision"],
            },
        ).status_code
        == 409
    )
    changed = client.post(
        f"/api/cases/{item['id']}/actions",
        headers=headers,
        json={
            "kind": "category",
            "category": "BL_COMPARISON",
            "expected_revision": restored["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["summary"]["kind"] == "needs_review"
    assert client.get("/api/cases?view=spam").json()["total"] == 0


@pytest.mark.parametrize(
    "accepted,source,expected",
    [
        (None, "model", "suspected"),
        (None, "fixture", "suspected"),
        (None, "human", None),
        ("SPAM", "human", "confirmed"),
        ("GENERAL", "human", None),
        ("BL_COMPARISON", "human", None),
    ],
)
def test_sql_and_domain_agree_on_human_overrides(workspace, accepted, source, expected):
    client, _, db, _ = workspace
    item = spam_case(workspace)
    with db.session() as session, session.begin():
        row = session.get(Case, item["id"])
        state = dict(row.state)
        state["classification"] = {
            **state["classification"],
            "accepted": accepted,
            "source": source,
        }
        row.state = state
    detail = client.get(f"/api/cases/{item['id']}").json()
    case = CaseView.model_validate(
        {key: value for key, value in detail.items() if key != "summary"}
    )
    assert spam_status(case) == expected
    assert client.get("/api/cases?view=spam").json()["total"] == int(
        expected is not None
    )


def test_postgres_spam_counts_and_recovery(postgres_db):
    from fastapi.testclient import TestClient

    from averis.api import create_app

    db, settings, _, _ = postgres_db
    settings = settings.model_copy(update={"live_enabled": False})
    with TestClient(create_app(settings, db), base_url=settings.origin) as client:
        response = client.post("/api/demo/session", headers={"origin": settings.origin})
        headers = {
            "origin": settings.origin,
            "x-csrf-token": response.json()["csrf_token"],
        }
        test_isolation_counts_recovery_and_export((client, headers, db, settings), True)
