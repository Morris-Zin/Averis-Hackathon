"""Framework-independent contracts shared by the application modules."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from averis.contracts import Category, Field

REVIEWERS = ("John Tan", "Aisha Rahman", "Mei Lin")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(Model):
    kind: Literal["text", "pdf", "docx", "xlsx", "image"]
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    sheet: str | None = None
    cell: str | None = None
    paragraph: int | None = None
    bbox: tuple[float, float, float, float] | None = None


class EvidenceBlock(Model):
    id: str
    text: str
    locations: list[Location]
    method: Literal["native", "ocr"] = "native"
    ocr_confidence: float | None = PydanticField(default=None, ge=0, le=1)


class DocumentEvidence(Model):
    document_id: str
    blocks: list[EvidenceBlock] = PydanticField(
        default_factory=lambda: list[EvidenceBlock]()
    )
    issues: list[str] = PydanticField(default_factory=list)
    parser_version: str = "evidence-v2"
    language: str = "eng"


class Classification(Model):
    suggested: Category
    confidence: float = PydanticField(ge=0, le=1)
    probabilities: dict[str, float]
    accepted: Category | None = None
    source: Literal["model", "human", "fixture"] = "model"
    model: str
    policy_version: str = "classification-v1"


class Reading(Model):
    field: Field
    document_id: str
    evidence_ids: list[Annotated[str, PydanticField(max_length=256)]] = PydanticField(
        default_factory=list, max_length=100
    )
    text: str | None = None
    normalized: str | None = None
    confidence: float = 0
    provenance: Literal["machine", "human_transcribed", "human_verified"] = "machine"
    issue: str | None = None


class Finding(Model):
    field: Field
    si: Reading
    bl: Reading
    outcome: Literal["match", "mismatch", "unresolved"]


class Report(Model):
    input_revision: int
    pair_valid: bool
    findings: list[Finding] = PydanticField(default_factory=lambda: list[Finding]())
    issues: list[str] = PydanticField(default_factory=list)
    policy_version: str = "comparison-v1"


class AttachmentView(Model):
    id: str
    filename: str
    role: Literal["SI", "BL", "unknown"] = "unknown"
    evidence: DocumentEvidence | None = None
    superseded: bool = False
    role_confidence: float | None = PydanticField(default=None, ge=0, le=1)


class AuditEntry(Model):
    at: str
    actor: str
    action: str
    detail: str


class CaseView(Model):
    id: str
    subject: str
    sender: str
    body: str
    received_at: str
    revision: int
    input_revision: int
    classification: Classification | None = None
    processing: Literal["queued", "running", "completed", "failed"]
    stage: str
    processing_run_id: str | None = None
    processing_attempts: int = PydanticField(default=0, ge=0, le=3)
    processing_error: str | None = None
    workflow: Literal["open", "waiting", "completed"]
    assignee: str
    review_reasons: list[str]
    attachments: list[AttachmentView]
    report: Report | None = None
    history: list[AuditEntry]


class CasePage(Model):
    items: list[CaseView]
    total: int
    page: int
    page_size: int


class SessionView(Model):
    actor: str
    csrf_token: str
    expires_at: str
    live_enabled: bool
    reviewers: list[str] = list(REVIEWERS)


class Action(Model):
    expected_revision: int = PydanticField(ge=1)
    kind: Literal[
        "category", "pair", "correct", "assign", "workflow", "retry", "revision"
    ]
    category: Category | None = None
    si_id: str | None = None
    bl_id: str | None = None
    field: Field | None = None
    document_id: str | None = None
    evidence_ids: list[Annotated[str, PydanticField(max_length=256)]] = PydanticField(
        default_factory=list, max_length=100
    )
    transcription: str | None = PydanticField(default=None, max_length=16_000)
    verified: bool = False
    reason: str = PydanticField(default="", max_length=4_000)
    assignee: str | None = None
    workflow: Literal["open", "waiting", "completed"] | None = None
