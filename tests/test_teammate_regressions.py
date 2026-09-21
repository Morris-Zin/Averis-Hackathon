import pytest
from test_case_status import complete_case
from test_documents import _text_pdf

from averis.documents import read_document
from averis.domain import AttachmentView
from averis.pipeline import _pair_selection_reason, _PreparedDocument
from averis.responses import QueueCaseResponse
from averis.verification import reading_from_evidence


def pdf_lines(lines):
    return read_document("sample", "sample.pdf", _text_pdf(lines))


def test_equivalent_pdf_labels_keep_separate_values_and_complete_addresses():
    document = pdf_lines(
        [
            "Exporter / Shipper: Northstar Components",
            "12 Industrial Road",
            "Receiving Party / Consignee: Harbour Tech",
            "Party to Notify: Harbour Tech",
            "Loading Port: Port Klang",
            "Destination Port: Hong Kong",
        ]
    )
    assert len(document.blocks) == 5
    expected = [
        ("shipper", "northstar components 12 industrial road"),
        ("consignee", "harbour tech"),
        ("notify_party", "harbour tech"),
        ("port_of_loading", "port klang"),
        ("port_of_discharge", "hong kong"),
    ]
    for block, (field, value) in zip(document.blocks, expected, strict=True):
        reading = reading_from_evidence(field, document, [block.id])
        assert reading.issue is None
        assert reading.normalized == value
    assert len(document.blocks[0].locations) == 2


@pytest.mark.parametrize(
    "label", ["Port of Discharge", "POD", "卸货港", "Pelabuhan Pelepasan"]
)
def test_destination_does_not_override_a_separate_discharge_port(label):
    document = read_document(
        "ports",
        "ports.txt",
        f"{label}: Singapore\nDestination Port: Hong Kong".encode(),
    )
    explicit, destination = document.blocks
    assert (
        reading_from_evidence("port_of_discharge", document, [explicit.id]).normalized
        == "singapore"
    )
    assert (
        reading_from_evidence("port_of_discharge", document, [destination.id]).issue
        == "destination_port_requires_review"
    )


@pytest.mark.parametrize(
    "count,si,bl,expected",
    [
        (0, 0, 0, "Waiting for documents"),
        (1, 1, 0, "No draft BL identified"),
        (2, 0, 1, "No Shipping Instruction identified"),
        (3, 2, 1, "Several possible shipping documents"),
    ],
)
def test_review_reason_identifies_the_missing_role(count, si, bl, expected):
    documents = [
        _PreparedDocument(AttachmentView(id=str(i), filename="file.txt"), {}, [])
        for i in range(count)
    ]
    assert _pair_selection_reason(documents, si, bl).startswith(expected)


def test_queue_projection_preserves_result_but_excludes_private_document_detail():
    case = complete_case()
    row = QueueCaseResponse.from_case(case).model_dump()
    assert row["summary"]["kind"] == "match"
    assert row["classification"]["confidence"] == 1
    assert not {"body", "attachments", "report", "history"} & row.keys()
    case.report.findings[0].outcome = "mismatch"
    assert QueueCaseResponse.from_case(case).summary.kind == "mismatch"
