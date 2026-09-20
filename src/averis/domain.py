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


class Issue(Model):
    """One scoped, blocking-aware problem; technical failures stay separate.

    Legacy persisted issues are plain strings. They are interpreted as
    unknown-scope blocking issues until their scope can be established and are
    never silently discarded.
    """

    code: str = PydanticField(max_length=256)
    scope: Literal[
        "selected_pair", "unused_attachment", "case", "document", "field", "unknown"
    ] = "unknown"
    document_id: str | None = None
    field: Field | None = None
    detail: str = PydanticField(default="", max_length=4_000)
    blocking: bool = True


def normalize_issue(issue: str | Issue) -> Issue:
    """Interpret legacy strings as unknown-scope blocking issues."""

    if isinstance(issue, Issue):
        return issue
    text = issue.strip() or "unknown_issue"
    # Structured issue strings use "code:detail" or "code:document:detail".
    code, _, detail = text.partition(":")
    return Issue(
        code=code.strip() or "unknown_issue",
        scope="unknown",
        detail=detail.strip(),
        blocking=True,
    )


def issue_is_blocking(issue: str | Issue) -> bool:
    return normalize_issue(issue).blocking


class DocumentEvidence(Model):
    document_id: str
    blocks: list[EvidenceBlock] = PydanticField(
        default_factory=lambda: list[EvidenceBlock]()
    )
    issues: list[str | Issue] = PydanticField(
        default_factory=lambda: list[str | Issue]()
    )
    parser_version: str = "evidence-v2"
    language: str = "eng"
    reader_version: str = "reader-v1"
    ocr_profile: str = "eng-psm6"
    source_sha256: str | None = None
    evidence_fingerprint: str | None = None


def evidence_fingerprint(evidence: DocumentEvidence) -> str:
    """Fingerprint text, locations, methods and block IDs for correction binding.

    Legacy evidence without a stored fingerprint can be fingerprinted from its
    stored contents without claiming a newer parser produced it.
    """

    import hashlib
    import json

    payload = {
        "document_id": evidence.document_id,
        "blocks": [
            {
                "id": block.id,
                "text": block.text,
                "method": block.method,
                "ocr_confidence": block.ocr_confidence,
                "locations": [loc.model_dump(mode="json") for loc in block.locations],
            }
            for block in evidence.blocks
        ],
        "reader_version": evidence.reader_version,
        "ocr_profile": evidence.ocr_profile,
        "parser_version": evidence.parser_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


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
    evidence_fingerprint: str | None = None


class Finding(Model):
    field: Field
    si: Reading
    bl: Reading
    outcome: Literal["match", "mismatch", "unresolved"]


class Report(Model):
    input_revision: int
    pair_valid: bool
    findings: list[Finding] = PydanticField(default_factory=lambda: list[Finding]())
    issues: list[str | Issue] = PydanticField(
        default_factory=lambda: list[str | Issue]()
    )
    policy_version: str = "comparison-v1"


class AttachmentView(Model):
    id: str
    filename: str
    role: Literal["SI", "BL", "unknown"] = "unknown"
    evidence: DocumentEvidence | None = None
    superseded: bool = False
    role_confidence: float | None = PydanticField(default=None, ge=0, le=1)


class ReadingCorrection(Model):
    before: Reading
    after: Reading
    input_revision: int


class AuditEntry(Model):
    at: str
    actor: str
    action: str
    detail: str
    correction: ReadingCorrection | None = None


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


class BaseAction(Model):
    expected_revision: int = PydanticField(ge=1)


class CategoryAction(BaseAction):
    kind: Literal["category"] = "category"
    category: Category
    reason: str = PydanticField(default="", max_length=4_000)


class PairAction(BaseAction):
    kind: Literal["pair"] = "pair"
    si_id: str = PydanticField(min_length=1, max_length=256)
    bl_id: str = PydanticField(min_length=1, max_length=256)
    reason: str = PydanticField(default="", max_length=4_000)


class CorrectAction(BaseAction):
    kind: Literal["correct"] = "correct"
    field: Field
    document_id: str = PydanticField(min_length=1, max_length=256)
    evidence_ids: list[Annotated[str, PydanticField(max_length=256)]] = PydanticField(
        max_length=100
    )
    transcription: str | None = PydanticField(default=None, max_length=16_000)
    verified: bool = False
    reason: str = PydanticField(default="", max_length=4_000)


class AssignAction(BaseAction):
    kind: Literal["assign"] = "assign"
    assignee: str = PydanticField(min_length=1, max_length=100)
    reason: str = PydanticField(default="", max_length=4_000)


class WorkflowAction(BaseAction):
    kind: Literal["workflow"] = "workflow"
    workflow: Literal["open", "waiting", "completed"]
    reason: str = PydanticField(default="", max_length=4_000)


class RetryAction(BaseAction):
    kind: Literal["retry"] = "retry"
    reason: str = PydanticField(default="", max_length=4_000)


class RevisionAction(BaseAction):
    kind: Literal["revision"] = "revision"
    reason: str = PydanticField(default="", max_length=4_000)


Action = (
    CategoryAction
    | PairAction
    | CorrectAction
    | AssignAction
    | WorkflowAction
    | RetryAction
    | RevisionAction
)
