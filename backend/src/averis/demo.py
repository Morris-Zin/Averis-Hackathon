"""Synthetic demonstration scenarios, explicitly labelled; never evaluation answers."""

from datetime import timedelta

from sqlalchemy.orm import Session

from averis.contracts import FIELDS
from averis.domain import (
    REVIEWERS,
    AttachmentView,
    AuditEntry,
    CaseView,
    Classification,
    DocumentEvidence,
    EvidenceBlock,
    Location,
    Reading,
)
from averis.persistence import Case, Document, Workspace, uid, utcnow
from averis.storage import Storage
from averis.verification import compare, reading_from_evidence

VALUES = {
    "shipper": "Meridian Paper Trading\n18 Jalan Pelabuhan, Klang, Malaysia",
    "consignee": "Pacific Distribution Ltd\n72 Harbour Road, Singapore",
    "notify_party": "Pacific Distribution Ltd\n72 Harbour Road, Singapore",
    "port_of_loading": "Port Klang",
    "port_of_discharge": "Singapore",
    "container_count": "3",
    "gross_weight_kg": "Gross weight (kg): 24000",
}


def evidence(
    document_id: str, role: str, reference: str, values: dict[str, str]
) -> DocumentEvidence:
    blocks = [
        EvidenceBlock(
            id="header",
            text=f"{'Shipping Instruction' if role == 'SI' else 'Draft Bill of Lading'}\nShipment ID: {reference}",
            locations=[Location(kind="text", line_start=1, line_end=2)],
        )
    ]
    line = 4
    for name in FIELDS:
        value = values[name]
        text = (
            value
            if name == "gross_weight_kg"
            else f"{name.replace('_', ' ').title()}: {value}"
        )
        end = line + text.count("\n")
        blocks.append(
            EvidenceBlock(
                id=name,
                text=text,
                locations=[Location(kind="text", line_start=line, line_end=end)],
            )
        )
        line = end + 2
    return DocumentEvidence(
        document_id=document_id, blocks=blocks, parser_version="controlled-demo-v1"
    )


def seed(session: Session, workspace: Workspace, storage: Storage) -> None:
    scenarios = [
        ("Draft BL review · Port Klang to Singapore", "mismatch"),
        ("Shipping documents · Penang export", "match"),
        ("Please check these details before release", "uncertain"),
        ("Invoice INV-2094 · freight charge query", "invoice"),
        ("Prepare SI for next week's sailing", "si"),
        ("Draft BL · gross weight missing", "missing"),
        ("Confirm tomorrow's delivery appointment", "general"),
        ("Exclusive crypto freight promotion", "spam"),
    ]
    for index, (subject, scenario) in enumerate(scenarios):
        case_id = uid()
        category = (
            "INVOICE_QUERY"
            if scenario == "invoice"
            else "SI_REQUEST"
            if scenario == "si"
            else "GENERAL"
            if scenario == "general"
            else "SPAM"
            if scenario == "spam"
            else "BL_COMPARISON"
        )
        now = utcnow() - timedelta(minutes=index * 23)
        view = CaseView(
            id=case_id,
            subject=subject,
            sender="shipping@meridian.example",
            body="Please review the attached shipping instruction and draft bill of lading before release. Thank you."
            if category == "BL_COMPARISON"
            else subject,
            received_at=now.isoformat(),
            revision=1,
            input_revision=1,
            classification=Classification(
                suggested=category,
                confidence=0.61 if scenario == "uncertain" else 1,
                probabilities={
                    category: 0.61 if scenario == "uncertain" else 1,
                    **({"GENERAL": 0.39} if scenario == "uncertain" else {}),
                },
                accepted=None if scenario == "uncertain" else category,
                source="fixture",
                model="controlled-demo",
            ),
            processing="completed",
            stage="saved_demo",
            workflow="open",
            assignee=REVIEWERS[index % len(REVIEWERS)],
            review_reasons=["Check category"] if scenario == "uncertain" else [],
            attachments=[],
            history=[
                AuditEntry(
                    at=now.isoformat(),
                    actor="Demo setup",
                    action="created",
                    detail="Controlled synthetic scenario; deterministic comparison, illustrative classification. Not a live AI result.",
                )
            ],
        )
        readings: dict[str, dict[str, Reading]] = {}
        if category == "BL_COMPARISON":
            for role in ("SI", "BL"):
                doc_id = uid()
                values = dict(VALUES)
                if role == "BL" and scenario == "mismatch":
                    values["container_count"] = "4"
                    values["port_of_discharge"] = "Jakarta"
                if role == "BL" and scenario == "missing":
                    values["gross_weight_kg"] = ""
                doc = evidence(doc_id, role, f"AVR-2026-{index + 1:04}", values)
                content = "\n\n".join(b.text for b in doc.blocks).encode()
                key, digest = storage.put_seed(content, doc_id)
                filename = f"shipment-{index + 1}-{role}.txt"
                session.add(
                    Document(
                        id=doc_id,
                        case_id=case_id,
                        workspace_id=workspace.id,
                        filename=filename,
                        object_key=key,
                        sha256=digest,
                        size=len(content),
                    )
                )
                view.attachments.append(
                    AttachmentView(
                        id=doc_id, filename=filename, role=role, evidence=doc
                    )
                )
                readings[role] = {
                    name: reading_from_evidence(name, doc, [name]) for name in FIELDS
                }
            if scenario != "uncertain":
                view.report = compare(readings["SI"], readings["BL"], 1, True)
                if scenario == "missing":
                    view.review_reasons = ["Missing gross weight"]
        session.add(
            Case(
                id=case_id,
                workspace_id=workspace.id,
                revision=1,
                input_revision=1,
                state=view.model_dump(mode="json"),
            )
        )


def controlled_revision(
    session: Session, row: Case, view: CaseView, storage: Storage
) -> None:
    """Attach a labelled synthetic replacement; the original remains immutable."""
    from averis.verification import shipment_references

    old = next((a for a in view.attachments if a.role == "BL"), None)
    si = next((a for a in view.attachments if a.role == "SI"), None)
    if not old or not si or not si.evidence:
        raise ValueError("This controlled scenario has no draft to replace")
    references = shipment_references(si.evidence)
    if len(references) != 1:
        raise ValueError("Controlled replacement reference is unavailable")
    doc_id = uid()
    doc = evidence(doc_id, "BL", next(iter(references)), dict(VALUES))
    content = "\n\n".join(b.text for b in doc.blocks).encode()
    key, digest = storage.put(content)
    name = "controlled-revised-draft.txt"
    session.add(
        Document(
            id=doc_id,
            case_id=row.id,
            workspace_id=row.workspace_id,
            filename=name,
            object_key=key,
            sha256=digest,
            size=len(content),
        )
    )
    old.role = "unknown"
    old.superseded = True
    view.attachments.append(
        AttachmentView(id=doc_id, filename=name, role="BL", evidence=doc)
    )
    view.workflow = "open"
