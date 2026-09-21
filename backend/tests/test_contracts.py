import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from averis.api import create_app
from averis.config import Settings
from averis.contracts import Prediction


def record(**changes):
    return {
        "category": "BL_COMPARISON",
        "status": "OK",
        "review_reason": None,
        "has_defect": False,
        "defect_fields": [],
    } | changes


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "MISMATCH"},
        {"status": "NEEDS_REVIEW"},
        {"has_defect": True},
        {"defect_fields": ["unknown"]},
        {"review_reason": "unreadable"},
        {"category": "SPAM", "status": "NEEDS_REVIEW", "review_reason": "unreadable"},
    ],
)
def test_rejects_contradictory_outputs(changes):
    with pytest.raises(ValidationError):
        Prediction.model_validate(record(**changes))


def test_accepts_review_and_mismatch():
    Prediction.model_validate(
        record(status="NEEDS_REVIEW", review_reason="missing_value")
    )
    Prediction.model_validate(
        record(status="MISMATCH", has_defect=True, defect_fields=["container_count"])
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_health_reports_configuration_not_dependency_readiness(enabled):
    settings = Settings(_env_file=None, live_enabled=enabled, budget_verified=enabled)
    response = TestClient(create_app(settings)).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "live_processing_enabled": enabled,
        "budget_verification_enabled": enabled,
    }
