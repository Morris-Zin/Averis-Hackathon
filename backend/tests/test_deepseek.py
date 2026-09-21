import json
from typing import cast

import pytest
import requests

from averis.budget import BudgetAuthority
from averis.contracts import FIELDS
from averis.deepseek import AssistedIntelligence, combine_fields, read_proposal
from averis.documents import read_document
from averis.intelligence import ExtractionResult, Intelligence
from averis.verification import reading_from_evidence


def document():
    return read_document(
        "doc",
        "doc.txt",
        b"SHIPPING INSTRUCTION\nShipper: CEDAR\nConsignee: BAY\nNotify Party: HARBOR\nPort of Loading: KLANG\nPort of Discharge: PENANG\nContainer Count: 3\nGross Weight: 22000 kg\n",
    )


def proposal(doc):
    return {
        "role": "SI",
        "role_evidence_ids": [doc.blocks[0].id],
        "fields": {
            field: {"status": "present", "evidence_ids": [doc.blocks[index + 1].id]}
            for index, field in enumerate(FIELDS)
        },
    }


def primary(doc, uncertain=False):
    fields = {
        field: reading_from_evidence(
            field, doc, [doc.blocks[index + 1].id], confidence=0.9
        )
        for index, field in enumerate(FIELDS)
    }
    if uncertain:
        fields["container_count"] = fields["container_count"].model_copy(
            update={"confidence": 0.5, "issue": "low_field_confidence"}
        )
    return ExtractionResult("SI", 0.92, fields)


def test_explicit_selection_has_no_fabricated_probability():
    doc = document()
    result = read_proposal(doc, json.dumps(proposal(doc)))
    assert result["container_count"].normalized == "3"
    assert result["container_count"].confidence is None
    assert result["container_count"].acceptance_basis == "explicit_source"
    assert result["container_count"].provenance == "machine"


@pytest.mark.parametrize(
    "mutation", ["foreign", "duplicate", "absent", "extra", "missing-field"]
)
def test_rejects_malformed_source_selection(mutation):
    doc = document()
    value = proposal(doc)
    if mutation == "foreign":
        value["fields"]["shipper"]["evidence_ids"] = ["other-document"]
    if mutation == "duplicate":
        value["fields"]["shipper"]["evidence_ids"] *= 2
    if mutation == "absent":
        value["fields"]["shipper"]["evidence_ids"] = []
    if mutation == "extra":
        value["normalized"] = "fabricated"
    if mutation == "missing-field":
        del value["fields"]["shipper"]
    with pytest.raises(ValueError):
        read_proposal(doc, json.dumps(value))


def test_source_selection_cannot_bypass_wrong_field_or_ocr_guards():
    doc = document()
    value = proposal(doc)
    value["fields"]["container_count"]["evidence_ids"] = value["fields"][
        "gross_weight_kg"
    ]["evidence_ids"]
    result = read_proposal(doc, json.dumps(value))
    assert result["container_count"].issue is not None
    scanned = doc.model_copy(deep=True)
    scanned.blocks[-1].method = "ocr"
    scanned.blocks[-1].ocr_confidence = 0.2
    assert (
        read_proposal(scanned, json.dumps(proposal(scanned)))["gross_weight_kg"].issue
        == "low_ocr_confidence"
    )


def test_combination_preserves_roles_and_exposes_conflicts():
    doc = document()
    base = primary(doc, uncertain=True)
    secondary = read_proposal(doc, json.dumps(proposal(doc)))
    secondary["shipper"] = secondary["shipper"].model_copy(
        update={"normalized": "different"}
    )
    result = combine_fields(base, secondary)
    assert result.role == "SI" and result.role_confidence == 0.92
    assert result.fields["container_count"].issue is None
    assert result.fields["shipper"].issue == "provider_disagreement"
    assert base.fields["shipper"].issue is None


class Primary:
    def __init__(self, result):
        self.result = result

    def extract(self, document):
        return self.result


def assistant(doc, uncertain=True, budget=None):
    return AssistedIntelligence(
        cast(Intelligence, Primary(primary(doc, uncertain))),
        "test-only-key",
        cast(BudgetAuthority, budget or object()),
        "run",
        "development",
    )


def test_complete_primary_never_calls_supplemental_provider(monkeypatch):
    doc = document()
    client = assistant(doc, False)
    monkeypatch.setattr(
        client, "_request", lambda *_a, **_k: pytest.fail("Unneeded paid call")
    )
    assert client.extract(doc).fields["shipper"].normalized == "cedar"


def test_outage_preserves_supported_primary_values_and_remains_visible(monkeypatch):
    doc = document()
    client = assistant(doc)

    def unavailable(*_a, **_k):
        raise requests.Timeout()

    monkeypatch.setattr(client, "_request", unavailable)
    result = client.extract(doc)
    assert result.fields["shipper"].issue is None
    assert result.fields["container_count"].issue == "low_field_confidence"
    assert (
        result.fields["container_count"].assistance_error
        == "supplemental_provider_unavailable"
    )
    assert result.fields["container_count"].confidence == 0.5


def test_only_truncation_gets_one_bounded_fallback(monkeypatch):
    doc = document()
    client = assistant(doc)
    calls = []

    def respond(_doc, *, thinking):
        calls.append(thinking)
        return None if thinking else (json.dumps(proposal(doc)), "request-id")

    monkeypatch.setattr(client, "_request", respond)
    assert client.extract(doc).fields["container_count"].issue is None
    assert calls == [True, False]


def test_null_probability_without_explicit_acceptance_remains_uncertain():
    doc = document()
    reading = reading_from_evidence("shipper", doc, [doc.blocks[1].id], confidence=None)
    assert reading.issue == "low_field_confidence"


def test_request_contains_one_document_and_separate_verified_pricing(monkeypatch):
    doc = document()
    calls = []

    class Budget:
        def reserve_estimate(self, *args, **kwargs):
            calls.append((args, kwargs))
            return "reservation"

        def settle_success(self, *args):
            calls.append(args)
            return True

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "request",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(proposal(doc))},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }

    def post(url, **kwargs):
        assert url == "https://api.deepseek.com/chat/completions"
        body = json.loads(kwargs["data"])
        assert "test-only-key" not in kwargs["data"].decode()
        assert (
            json.loads(body["messages"][1]["content"])["blocks"][0]["id"]
            == doc.blocks[0].id
        )
        return Response()

    monkeypatch.setattr("averis.deepseek.requests.post", post)
    result = assistant(doc, budget=Budget()).extract(doc)
    assert result.fields["container_count"].issue is None
    assert calls[0][1]["pricing"] == ("0.30", "1.20")
    assert calls[1] == ("reservation", 100, 20, "request")
