from typing import Self, cast

import pytest
from pytest import MonkeyPatch
from typesafe_sdk import ChoiceAnswer, SystemOneResponse, Usage

from averis.budget import BudgetAuthority
from averis.config import Settings
from averis.contracts import FIELDS
from averis.domain import DocumentEvidence, EvidenceBlock, Location
from averis.intelligence import Jev


def response(answers: dict[str, ChoiceAnswer]) -> SystemOneResponse:
    return SystemOneResponse(
        model="jev-test",
        answers=answers,
        usage=Usage(input_tokens=10, output_tokens=2),
    )


def jev() -> Jev:
    settings = Settings(
        _env_file=None,
        category_threshold=0.8,
        spam_threshold=0.95,
        field_threshold=0.8,
    )
    return Jev(settings, cast(BudgetAuthority, object()), "run-1", "development")


def category_answer(
    choice: str, confidence: float, probabilities: dict[str, float]
) -> ChoiceAnswer:
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities=probabilities,
    )


def test_category_threshold_accepts_a_well_formed_general_decision(
    monkeypatch: MonkeyPatch,
) -> None:
    client = jev()
    answer = category_answer(
        "GENERAL",
        0.8,
        {
            "BL_COMPARISON": 0.05,
            "SI_REQUEST": 0.05,
            "INVOICE_QUERY": 0.05,
            "GENERAL": 0.8,
            "SPAM": 0.05,
        },
    )
    monkeypatch.setattr(client, "_ask", lambda *_: response({"category": answer}))

    result = client.classify("Hello", "Please update the schedule")

    assert result.suggested == "GENERAL"
    assert result.accepted == "GENERAL"
    assert result.confidence == 0.8


def test_spam_uses_the_stricter_threshold(monkeypatch: MonkeyPatch) -> None:
    client = jev()
    answer = category_answer(
        "SPAM",
        0.9,
        {
            "BL_COMPARISON": 0.025,
            "SI_REQUEST": 0.025,
            "INVOICE_QUERY": 0.025,
            "GENERAL": 0.025,
            "SPAM": 0.9,
        },
    )
    monkeypatch.setattr(client, "_ask", lambda *_: response({"category": answer}))

    result = client.classify("Win now", "Promotional message")

    assert result.suggested == "SPAM"
    assert result.accepted is None


def test_classification_rejects_malformed_probabilities(
    monkeypatch: MonkeyPatch,
) -> None:
    client = jev()
    answer = category_answer(
        "GENERAL",
        0.9,
        {"GENERAL": 0.9, "SPAM": 0.1},
    )
    monkeypatch.setattr(client, "_ask", lambda *_: response({"category": answer}))

    with pytest.raises(ValueError, match="requested criteria"):
        client.classify("Hello", "General request")


def test_extract_preserves_role_confidence_separately_from_field_confidence(
    monkeypatch: MonkeyPatch,
) -> None:
    client = jev()
    document = DocumentEvidence(
        document_id="si-1",
        blocks=[
            EvidenceBlock(
                id="si-1:b1",
                text="Shipper: Averis Trading",
                locations=[Location(kind="text", line_start=1, line_end=1)],
            )
        ],
    )
    field_answer = category_answer("si-1:b1", 0.91, {"si-1:b1": 0.91, "NONE": 0.09})
    answers = {field: field_answer for field in FIELDS}
    answers["role"] = category_answer(
        "SI", 0.85, {"SI": 0.85, "BL": 0.1, "unknown": 0.05}
    )
    monkeypatch.setattr(client, "_ask", lambda *_: response(answers))

    result = client.extract(document)

    assert result.role == "SI"
    assert result.role_confidence == 0.85
    assert set(result.fields) == set(FIELDS)
    assert all(reading.confidence == 0.91 for reading in result.fields.values())


class RecordingBudget:
    def __init__(self) -> None:
        self.reserved: list[tuple[str, str, int, int]] = []
        self.settled: list[tuple[str, int | None, int | None, str | None]] = []
        self.retained: list[tuple[str, str]] = []

    def reserve(
        self, run_id: str, purpose: str, payload_bytes: int, questions: int
    ) -> str:
        self.reserved.append((run_id, purpose, payload_bytes, questions))
        return "reservation-1"

    def settle_success(
        self,
        reservation_id: str,
        input_tokens: int | None,
        output_tokens: int | None,
        request_id: str | None = None,
    ) -> bool:
        self.settled.append((reservation_id, input_tokens, output_tokens, request_id))
        return True

    def retain_for_reconciliation(self, reservation_id: str, issue: str) -> None:
        self.retained.append((reservation_id, issue))


class FakeTypeSafeClient:
    def __init__(
        self,
        provider_response: SystemOneResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.provider_response = provider_response
        self.error = error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def system_one(self, **_kwargs: object) -> SystemOneResponse:
        if self.error is not None:
            raise self.error
        assert self.provider_response is not None
        return self.provider_response


def test_provider_usage_settles_before_business_answer_validation(
    monkeypatch: MonkeyPatch,
) -> None:
    budget = RecordingBudget()
    settings = Settings(_env_file=None)
    client = Jev(
        settings,
        cast(BudgetAuthority, budget),
        "run-1",
        "development",
    )
    answer = category_answer("GENERAL", 0.9, {"GENERAL": 0.9, "SPAM": 0.1})
    provider_response = response({"category": answer})
    provider_response.__dict__["_request_id"] = "typesafe-request-1"
    fake = FakeTypeSafeClient(provider_response=provider_response)
    monkeypatch.setattr("averis.intelligence.TypeSafeClient", lambda **_kwargs: fake)

    with pytest.raises(ValueError, match="requested criteria"):
        client.classify("Hello", "General request")

    assert budget.settled == [("reservation-1", 10, 2, "typesafe-request-1")]
    assert budget.retained == []


def test_provider_exception_retains_full_reservation(
    monkeypatch: MonkeyPatch,
) -> None:
    budget = RecordingBudget()
    client = Jev(
        Settings(_env_file=None),
        cast(BudgetAuthority, budget),
        "run-1",
        "development",
    )
    fake = FakeTypeSafeClient(error=TimeoutError("provider timeout"))
    monkeypatch.setattr("averis.intelligence.TypeSafeClient", lambda **_kwargs: fake)

    with pytest.raises(TimeoutError, match="provider timeout"):
        client.classify("Hello", "General request")

    assert budget.settled == []
    assert budget.retained == [
        ("reservation-1", "Provider call did not return a validated response")
    ]


def test_dotenv_provider_key_is_private_and_reaches_sdk(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("TYPESAFE_API_KEY=offline-fake-key\n", encoding="utf-8")
    settings = Settings(_env_file=env)
    assert "offline-fake-key" not in repr(settings)
    captured = {}
    fake = FakeTypeSafeClient(error=TimeoutError("offline synthetic failure"))

    def client_factory(**kwargs):
        captured.update(kwargs)
        return fake

    monkeypatch.setattr("averis.intelligence.TypeSafeClient", client_factory)
    budget = RecordingBudget()
    with pytest.raises(TimeoutError):
        Jev(settings, cast(BudgetAuthority, budget), "run-1", "development").classify("Test", "Test")
    assert captured["api_key"] == "offline-fake-key"


def test_client_configuration_failure_does_not_reserve_budget(monkeypatch):
    budget = RecordingBudget()

    def invalid_client(**_kwargs):
        raise ValueError("Missing local credentials")

    monkeypatch.setattr("averis.intelligence.TypeSafeClient", invalid_client)
    with pytest.raises(ValueError, match="Missing local credentials"):
        Jev(Settings(_env_file=None), cast(BudgetAuthority, budget), "run-1", "development").classify("Test", "Test")
    assert budget.reserved == []
