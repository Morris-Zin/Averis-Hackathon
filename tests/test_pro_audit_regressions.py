"""Independent regressions from the external audit, without provider calls."""

from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from docx import Document
from test_case_status import complete_case

from averis.case_status import assess_case
from averis.documents import read_document
from averis.domain import (
    AttachmentView,
    DocumentEvidence,
    EvidenceBlock,
    Issue,
    Location,
)
from averis.pipeline import Checkpoints, ShipmentPipeline
from averis.verification import normalize, reading_from_evidence
from averis.versions import READER_VERSION


@pytest.mark.parametrize(
    "marker", ["Not available", "NOT AVAILABLE.", "N.A.", "Not provided:"]
)
def test_missing_markers_cannot_match(marker):
    assert normalize("notify_party", marker) is None


def test_party_layout_equivalence_preserves_real_address_differences():
    cells = "AL GURG STATIONERY LLC | P.O. BOX 5069; DUBAI, UNITED ARAB EMIRATES"
    lines = "AL GURG STATIONERY LLC\nP.O. BOX 5069\nDUBAI, UNITED ARAB EMIRATES"
    assert normalize("consignee", cells) == normalize("consignee", lines)
    assert normalize("consignee", cells) != normalize(
        "consignee", lines.replace("5069", "5070")
    )
    assert normalize("consignee", "A-B LTD") != normalize("consignee", "AB LTD")


def test_weight_label_establishes_unit_but_bare_number_does_not():
    assert normalize("gross_weight_kg", "Gross Wt (kgs): 243,588") == "243588"
    assert normalize("gross_weight_kg", "Gross Wt: 243,588") is None


def test_inline_pdf_columns_are_not_a_trustworthy_party_reading():
    document = DocumentEvidence(
        document_id="a",
        blocks=[
            EvidenceBlock(
                id="b",
                text="Shipper: ACME PAPER LTD Consignee: BUYER LTD",
                locations=[Location(kind="pdf", page=1)],
            )
        ],
    )
    reading = reading_from_evidence("shipper", document, ["b"])
    assert reading.issue == "ambiguous_source_fields"
    assert reading.normalized is None


def test_docx_party_paragraphs_include_address_and_locations():
    document = Document()
    for text in [
        "Shipper:",
        "ACME LTD",
        "10 Main Road",
        "Consignee:",
        "BUYER LTD",
        "20 Other Road",
        "Gross Weight: 20 KG",
    ]:
        document.add_paragraph(text)
    payload = BytesIO()
    document.save(payload)
    evidence = read_document("d", "source.docx", payload.getvalue())
    assert not evidence.issues
    assert evidence.blocks[0].text == "Shipper:\nACME LTD\n10 Main Road"
    assert [loc.paragraph for loc in evidence.blocks[0].locations] == [1, 2, 3]
    assert evidence.blocks[1].text == "Consignee:\nBUYER LTD\n20 Other Road"


def test_retry_reads_legacy_evidence_from_original():
    old = DocumentEvidence(document_id="d", reader_version="old")
    fresh = DocumentEvidence(document_id="d", reader_version=READER_VERSION)
    reader = Mock(return_value=fresh)
    pipeline = ShipmentPipeline(
        Mock(),
        Checkpoints({}, lambda *_: None),
        lambda _: b"original",
        reader,
        lambda: 400,
    )
    assert (
        pipeline._read(AttachmentView(id="d", filename="a.txt", evidence=old)) is fresh
    )
    reader.assert_called_once()
    reader.reset_mock()
    assert (
        pipeline._read(AttachmentView(id="d", filename="a.txt", evidence=fresh))
        == fresh
    )
    reader.assert_not_called()


def test_nonblocking_issue_keeps_its_meaning():
    case = complete_case()
    assert case.report is not None
    case.report.issues.append(Issue(code="layout_note", blocking=False))
    assert assess_case(case).can_be_clear
    case.report.issues.append(Issue(code="unused_bad", scope="unused_attachment"))
    assessment = assess_case(case)
    assert assessment.can_be_clear
    assert "unused_bad" in assessment.unused_warnings


def test_mismatch_requires_review_even_with_all_fields_read():
    case = complete_case()
    assert case.report is not None
    case.report.findings[0].outcome = "mismatch"
    assert assess_case(case).needs_review
    assert assess_case(case).has_mismatch


def test_actual_organizer_cross_format_parties():
    root = Path("resources/official/bundle/attachments")
    paths = [root / "email_055_SI.xlsx", root / "email_055_BL.docx"]
    if not all(path.exists() for path in paths):
        pytest.skip("Organizer files are local evaluation assets")
    docs = [read_document(str(i), p.name, p.read_bytes()) for i, p in enumerate(paths)]
    for field, label in [
        ("shipper", "Shipper"),
        ("consignee", "Consignee"),
        ("notify_party", "Notify"),
    ]:
        values = [
            next(b.text for b in d.blocks if b.text.lower().startswith(label.lower()))
            for d in docs
        ]
        assert normalize(field, values[0]) == normalize(field, values[1])


def test_native_heading_does_not_hide_scanned_body(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from averis import documents

    page = SimpleNamespace(
        width=600,
        height=800,
        images=[{"x0": 0, "x1": 600, "top": 100, "bottom": 800}],
        extract_words=lambda **_: [
            {"text": "DOCUMENT COPY", "x0": 10, "x1": 100, "top": 10, "bottom": 20}
        ],
    )
    monkeypatch.setattr(
        "pdfplumber.open", lambda _: nullcontext(SimpleNamespace(pages=[page]))
    )
    ocr = Mock(return_value=([], ["ocr_test_unreadable"]))
    monkeypatch.setattr(documents, "_ocr_pdf_pages", ocr)
    result = documents._read_pdf("scan", b"fixture")
    assert ocr.call_args.args[2] == [1]
    assert "ocr_test_unreadable" in result.issues
    assert not result.blocks


def test_provider_cannot_supply_fabricated_normalized_value_or_provenance():
    from averis.domain import Reading
    from averis.intelligence import ExtractionResult

    document = DocumentEvidence(
        document_id="d",
        blocks=[
            EvidenceBlock(
                id="b",
                text="Shipper: REAL LTD",
                locations=[Location(kind="text", line_start=1)],
            )
        ],
    )
    provider = Mock()
    provider.extract.return_value = ExtractionResult(
        "SI",
        1,
        {
            "shipper": Reading(
                field="shipper",
                document_id="another",
                evidence_ids=["b"],
                text="FAKE LTD",
                normalized="fake ltd",
                confidence=1,
                provenance="human_verified",
            )
        },
    )
    pipeline = ShipmentPipeline(
        provider, Checkpoints({}, lambda *_: None), Mock(), Mock(), lambda: 400
    )
    extracted = pipeline._extract(document)
    assert extracted is not None
    reading = extracted.fields["shipper"]
    assert reading.document_id == "d"
    assert reading.text == "Shipper: REAL LTD"
    assert reading.normalized == "real ltd"
    assert reading.provenance == "machine"


def test_selected_pair_keeps_unused_issues_scoped_through_pipeline():
    from averis.demo import evidence
    from averis.intelligence import ExtractionResult
    from averis.pipeline import ProcessingInput

    values = {
        "shipper": "ACME",
        "consignee": "BUYER",
        "notify_party": "AGENT",
        "port_of_loading": "KLANG",
        "port_of_discharge": "SINGAPORE",
        "container_count": "3",
        "gross_weight_kg": "22000 KG",
    }
    documents = {
        key: evidence(key, role, "SHIP-1234", values)
        for key, role in [("si", "SI"), ("bl", "BL"), ("extra", "BL")]
    }
    for doc in documents.values():
        doc.reader_version = READER_VERSION
    documents["si"].issues = [Issue(code="advisory", blocking=False)]
    documents["extra"].issues = [Issue(code="broken_unused", detail="page unreadable")]
    case = complete_case()
    case.attachments = [
        AttachmentView(id=key, filename=key + ".txt", evidence=doc)
        for key, doc in documents.items()
    ]
    provider = Mock()
    provider.classify.return_value = case.classification
    provider.extract.side_effect = lambda doc: ExtractionResult(
        "SI" if doc.document_id == "si" else "BL",
        1,
        {field: reading_from_evidence(field, doc, [field]) for field in values},
    )
    pipeline = ShipmentPipeline(
        provider, Checkpoints({}, lambda *_: None), Mock(), Mock(), lambda: 400
    )
    result = pipeline.process(ProcessingInput(case, ["si", "bl"], {}))
    restored = type(case).model_validate_json(result.apply_to(case).model_dump_json())
    assessment = assess_case(restored)
    assert assessment.can_be_clear
    assert not assessment.blocking_issues
    assert assessment.unused_warnings
    assert restored.report is not None
    assert any(isinstance(i, Issue) and not i.blocking for i in restored.report.issues)


def test_two_corrections_keep_before_and_after_in_persisted_history(tmp_path):
    from test_domain_review import comparison_case, evidence

    from averis.config import Settings
    from averis.domain import CaseView, CorrectAction
    from averis.persistence import Base, Case, Database
    from averis.storage import Storage
    from averis.workflow import Workflow

    db = Database(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(db.engine)
    storage = Storage(
        Settings(
            _env_file=None,
            storage_backend="local",
            storage_dir=str(tmp_path / "objects"),
        )
    )
    case = comparison_case(bl_evidence=evidence("bl", "Shipper: ACME"))
    case.attachments[1].evidence.blocks.append(
        EvidenceBlock(
            id="bl:b2",
            text="Shipper: OTHER",
            locations=[Location(kind="text", line_start=2)],
        )
    )
    with db.session() as session, session.begin():
        session.add(
            Case(
                id=case.id,
                workspace_id="w",
                revision=1,
                input_revision=1,
                state=case.model_dump(mode="json"),
            )
        )
    workflow = Workflow(db, storage)
    for revision, block in [(1, "bl:b1"), (2, "bl:b2")]:
        workflow.apply(
            "w",
            case.id,
            "John Tan",
            CorrectAction(
                expected_revision=revision,
                field="shipper",
                document_id="bl",
                evidence_ids=[block],
                reason="Checked original",
            ),
            False,
        )
    with db.session() as session:
        restored = CaseView.model_validate(session.get(Case, case.id).state)
    first, second = [entry.correction for entry in restored.history]
    assert first.after.text == second.before.text == "Shipper: ACME"
    assert second.after.text == "Shipper: OTHER"
    assert first.input_revision == 2 and second.input_revision == 3
    assert first.after.evidence_ids == ["bl:b1"]
    db.engine.dispose()
