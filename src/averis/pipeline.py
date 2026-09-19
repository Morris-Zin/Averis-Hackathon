"""Shipment processing without database, transport or worker-lifecycle decisions.

The caller supplies document access and durable checkpoints. This module owns
classification, independent document extraction, overrides and pair comparison.
Only processing-owned outputs are returned; reviewer workflow is never mutated.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from averis.domain import (
    AttachmentView,
    CaseView,
    Classification,
    DocumentEvidence,
    Reading,
    Report,
)
from averis.intelligence import Intelligence
from averis.verification import compare, validate_pair

MAX_EVIDENCE_CANDIDATES = 240
PARSER_TIMEOUT_SECONDS = 120
PROVIDER_TIME_RESERVE_SECONDS = 45
APPLICATION_DEADLINE_SECONDS = 480


class InvalidCheckpoint(ValueError):
    """Persisted processing state cannot be safely resumed."""


class MissingDocument(ValueError):
    """The immutable source referenced by the case is unavailable."""


class DocumentReader(Protocol):
    def __call__(
        self, document_id: str, filename: str, content: bytes, *, timeout_seconds: float
    ) -> DocumentEvidence: ...


class _DocumentCheckpoint(BaseModel):
    evidence: DocumentEvidence


class _ExtractionCheckpoint(BaseModel):
    role: Literal["SI", "BL", "unknown"]
    role_confidence: float = Field(default=0, ge=0, le=1)
    fields: dict[str, Reading]


class Checkpoints:
    """Validate saved stages and persist new ones before exposing their results."""

    def __init__(
        self, saved: dict[str, object], persist: Callable[[str, object], None]
    ):
        self._saved = saved
        self._persist = persist

    def load[T: BaseModel](self, key: str, model: type[T]) -> T | None:
        if key not in self._saved:
            return None
        try:
            return model.model_validate(self._saved[key])
        except ValidationError as exc:
            raise InvalidCheckpoint("Saved processing checkpoint is invalid") from exc

    def save(self, key: str, value: BaseModel) -> None:
        encoded = value.model_dump(mode="json")
        self._persist(key, encoded)
        self._saved[key] = encoded


@dataclass(frozen=True)
class ProcessingInput:
    case: CaseView
    accepted_pair: list[str] | None
    overrides: dict[str, object]


@dataclass(frozen=True)
class ProcessingResult:
    classification: Classification
    attachments: list[AttachmentView]
    report: Report | None
    review_reasons: list[str]

    def apply_to(self, case: CaseView) -> CaseView:
        """Merge only processing-owned fields into the latest reviewer state."""
        return case.model_copy(
            update={
                "classification": self.classification,
                "attachments": self.attachments,
                "report": self.report,
                "review_reasons": self.review_reasons,
                "processing": "completed",
                "stage": "complete",
            }
        )


@dataclass(frozen=True)
class _PreparedDocument:
    attachment: AttachmentView
    fields: dict[str, Reading] | None
    issues: list[str]


class ShipmentPipeline:
    def __init__(
        self,
        intelligence: Intelligence,
        checkpoints: Checkpoints,
        load_document: Callable[[str], bytes],
        reader: DocumentReader,
        remaining_seconds: Callable[[], float],
    ):
        self._intelligence = intelligence
        self._checkpoints = checkpoints
        self._load_document = load_document
        self._reader = reader
        self._remaining = remaining_seconds

    def process(self, inputs: ProcessingInput) -> ProcessingResult:
        classification = self._classify(inputs.case)
        attachments = [item.model_copy(deep=True) for item in inputs.case.attachments]
        if classification.accepted is None:
            return ProcessingResult(
                classification, attachments, None, ["Check category"]
            )
        if classification.accepted != "BL_COMPARISON":
            return ProcessingResult(classification, attachments, None, [])

        overrides = self._decode_overrides(inputs.overrides)
        prepared = [
            self._prepare(item, inputs.accepted_pair, overrides)
            for item in attachments
            if not item.superseded
        ]
        issues = [issue for document in prepared for issue in document.issues]
        report = self._compare(prepared, inputs, issues)
        return ProcessingResult(
            classification, attachments, report, sorted(set(issues))
        )

    def _classify(self, case: CaseView) -> Classification:
        saved = self._checkpoints.load("classification", Classification)
        if saved is not None:
            return saved
        if case.classification is not None and case.classification.source == "human":
            return case.classification
        classification = self._intelligence.classify(case.subject, case.body)
        self._checkpoints.save("classification", classification)
        return classification

    @staticmethod
    def _decode_overrides(saved: dict[str, object]) -> dict[str, Reading]:
        try:
            return TypeAdapter(dict[str, Reading]).validate_python(saved)
        except ValidationError as exc:
            raise InvalidCheckpoint("Saved reviewer readings are invalid") from exc

    def _read(self, attachment: AttachmentView) -> DocumentEvidence:
        key = f"document:{attachment.id}"
        saved = self._checkpoints.load(key, _DocumentCheckpoint)
        if saved is not None:
            return saved.evidence
        if attachment.evidence is not None:
            return attachment.evidence
        content = self._load_document(attachment.id)
        available = self._remaining() - PROVIDER_TIME_RESERVE_SECONDS
        if available <= 0:
            raise TimeoutError("application_deadline")
        evidence = self._reader(
            attachment.id,
            attachment.filename,
            content,
            timeout_seconds=min(PARSER_TIMEOUT_SECONDS, available),
        )
        self._checkpoints.save(key, _DocumentCheckpoint(evidence=evidence))
        return evidence

    def _extract(self, evidence: DocumentEvidence) -> _ExtractionCheckpoint | None:
        key = f"extraction:{evidence.document_id}"
        saved = self._checkpoints.load(key, _ExtractionCheckpoint)
        if saved is not None:
            return saved
        if not evidence.blocks or len(evidence.blocks) > MAX_EVIDENCE_CANDIDATES:
            return None
        extracted = self._intelligence.extract(evidence)
        value = _ExtractionCheckpoint.model_validate(
            {
                "role": extracted.role,
                "role_confidence": extracted.role_confidence,
                "fields": extracted.fields,
            }
        )
        self._checkpoints.save(key, value)
        return value

    def _prepare(
        self,
        attachment: AttachmentView,
        pair: list[str] | None,
        overrides: dict[str, Reading],
    ) -> _PreparedDocument:
        if self._remaining() <= PROVIDER_TIME_RESERVE_SECONDS:
            raise TimeoutError("application_deadline")
        evidence = self._read(attachment)
        attachment.evidence = evidence
        issues = list(evidence.issues)
        extracted = self._extract(evidence)
        if extracted is None:
            issues.append("Document cannot be reliably extracted")
            return _PreparedDocument(attachment, None, issues)
        attachment.role_confidence = extracted.role_confidence
        attachment.role = extracted.role
        if pair is not None:
            roles: dict[str, Literal["SI", "BL", "unknown"]] = dict(
                zip(pair, ("SI", "BL"), strict=True)
            )
            attachment.role = roles.get(attachment.id, "unknown")
        fields = {
            field: overrides.get(f"{attachment.id}:{field}", reading)
            for field, reading in extracted.fields.items()
        }
        return _PreparedDocument(attachment, fields, issues)

    @staticmethod
    def _compare(
        documents: list[_PreparedDocument], inputs: ProcessingInput, issues: list[str]
    ) -> Report | None:
        sis = [document for document in documents if document.attachment.role == "SI"]
        bls = [document for document in documents if document.attachment.role == "BL"]
        if len(sis) != 1 or len(bls) != 1:
            issues.append("Select the correct SI and draft BL")
            return None
        si, bl = sis[0], bls[0]
        if (
            si.fields is None
            or bl.fields is None
            or si.attachment.evidence is None
            or bl.attachment.evidence is None
        ):
            issues.append("Unreadable comparison documents")
            return None
        manually_paired = inputs.accepted_pair == [si.attachment.id, bl.attachment.id]
        valid = validate_pair(
            si.attachment.evidence, bl.attachment.evidence, manually_paired
        )
        report = compare(
            si.fields, bl.fields, inputs.case.input_revision, valid, issues
        )
        issues.extend(report.issues)
        if any(finding.outcome == "unresolved" for finding in report.findings):
            issues.append("Some fields need review")
        return report
