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
    Issue,
    Reading,
    Report,
    evidence_fingerprint,
    normalize_issue,
)
from averis.intelligence import Intelligence
from averis.verification import compare, reading_from_evidence, validate_pair
from averis.versions import (
    ACCEPTANCE_PROFILE,
    CHECKPOINT_VERSION,
    EXTRACTION_POLICY_VERSION,
    NORMALIZATION_PROFILE,
    OCR_PROFILE,
    READER_VERSION,
)

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
    version: str
    evidence: DocumentEvidence
    reader_version: str
    ocr_profile: str
    evidence_fingerprint: str | None = None


class _ExtractionCheckpoint(BaseModel):
    version: str
    role: Literal["SI", "BL", "unknown"]
    role_confidence: float = Field(default=0, ge=0, le=1)
    fields: dict[str, Reading]
    evidence_fingerprint: str | None = None
    acceptance_profile: str
    extraction_policy: str
    normalization_profile: str


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
    issues: list[str | Issue]


class ShipmentPipeline:
    def __init__(
        self,
        intelligence: Intelligence,
        checkpoints: Checkpoints,
        load_document: Callable[[str], bytes],
        reader: DocumentReader,
        remaining_seconds: Callable[[], float],
        classification_profile: tuple[str, str] | None = None,
        acceptance_profile: str = ACCEPTANCE_PROFILE,
        provider_time_reserve: float = PROVIDER_TIME_RESERVE_SECONDS,
    ):
        self._intelligence = intelligence
        self._checkpoints = checkpoints
        self._load_document = load_document
        self._reader = reader
        self._remaining = remaining_seconds
        self._classification_profile = classification_profile
        self._acceptance_profile = acceptance_profile
        self._provider_time_reserve = provider_time_reserve

    def process(self, inputs: ProcessingInput) -> ProcessingResult:
        """Run classification, preparation and comparison without mutating inputs.

        Document preparation returns its updated attachment, readings and
        issues; comparison returns its report and additional issues. Neither
        secretly mutates caller-owned arguments.
        """

        classification = self._classify(inputs.case)
        # Work on copies; inputs.case and its attachments are never mutated.
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
        # Return the prepared attachments (with evidence and roles) in the
        # original order; superseded originals are preserved untouched.
        by_id = {doc.attachment.id: doc.attachment for doc in prepared}
        updated = [by_id.get(item.id, item) for item in attachments]
        report, extra_issues = self._compare(prepared, inputs)
        if report is None:
            extra_issues.extend(
                issue if isinstance(issue, str) else issue.code
                for document in prepared
                for issue in document.issues
                if normalize_issue(issue).blocking
            )
        return ProcessingResult(
            classification, updated, report, sorted(set(extra_issues))
        )

    def _classify(self, case: CaseView) -> Classification:
        if case.classification is not None and case.classification.source == "human":
            return case.classification
        saved = self._checkpoints.load("classification", Classification)
        if saved is not None and (
            self._classification_profile is None
            or (saved.model, saved.policy_version) == self._classification_profile
        ):
            return saved
        # A changed provider profile invalidates only classification. Compatible
        # document checkpoints remain available, and human decisions take priority.
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
            # Unversioned resumable checkpoints cannot be reused.
            if (
                saved.version != CHECKPOINT_VERSION
                or saved.reader_version != READER_VERSION
                or saved.ocr_profile != OCR_PROFILE
            ):
                raise InvalidCheckpoint(
                    "Saved document reading uses an incompatible reader profile"
                )
            if saved.evidence.document_id != attachment.id:
                raise InvalidCheckpoint("Saved document reading has wrong identity")
            return saved.evidence
        if (
            attachment.evidence is not None
            and attachment.evidence.reader_version == READER_VERSION
            and attachment.evidence.ocr_profile == OCR_PROFILE
        ):
            # Legacy evidence without a fingerprint is fingerprinted from its
            # stored contents without claiming a newer parser produced it.
            try:
                fingerprint = evidence_fingerprint(attachment.evidence)
            except Exception:  # noqa: BLE001 - fingerprint never blocks reading
                fingerprint = None
            if attachment.evidence.evidence_fingerprint is None and fingerprint:
                attachment.evidence.evidence_fingerprint = fingerprint
            return attachment.evidence
        content = self._load_document(attachment.id)
        available = self._remaining() - self._provider_time_reserve
        if available <= 0:
            raise TimeoutError("application_deadline")
        evidence = self._reader(
            attachment.id,
            attachment.filename,
            content,
            timeout_seconds=min(PARSER_TIMEOUT_SECONDS, available),
        )
        try:
            fingerprint = evidence_fingerprint(evidence)
        except Exception:  # noqa: BLE001 - fingerprint never blocks reading
            fingerprint = None
        self._checkpoints.save(
            key,
            _DocumentCheckpoint(
                version=CHECKPOINT_VERSION,
                evidence=evidence,
                reader_version=READER_VERSION,
                ocr_profile=OCR_PROFILE,
                evidence_fingerprint=fingerprint or evidence.evidence_fingerprint,
            ),
        )
        return evidence

    def _extract(self, evidence: DocumentEvidence) -> _ExtractionCheckpoint | None:
        key = f"extraction:{evidence.document_id}"
        saved = self._checkpoints.load(key, _ExtractionCheckpoint)
        if saved is not None:
            if (
                saved.version != CHECKPOINT_VERSION
                or saved.acceptance_profile != self._acceptance_profile
                or saved.extraction_policy != EXTRACTION_POLICY_VERSION
                or saved.normalization_profile != NORMALIZATION_PROFILE
            ):
                raise InvalidCheckpoint(
                    "Saved extraction uses an incompatible provider profile"
                )
            try:
                current_print = evidence_fingerprint(evidence)
            except Exception:  # noqa: BLE001 - fingerprint never blocks reuse check
                current_print = evidence.evidence_fingerprint
            expected = saved.evidence_fingerprint or current_print
            if expected and current_print and expected != current_print:
                raise InvalidCheckpoint(
                    "Saved extraction does not match current evidence"
                )
            return saved
        if not evidence.blocks or len(evidence.blocks) > MAX_EVIDENCE_CANDIDATES:
            return None
        from averis.intelligence import ProviderCapacityError

        try:
            extracted = self._intelligence.extract(evidence)
        except ProviderCapacityError:
            # Capacity limitations become visible unsupported-input review
            # outcomes; other provider failures remain processing failures.
            return None
        fields: dict[str, Reading] = {}
        for name, proposal in extracted.fields.items():
            if name != proposal.field:
                raise ValueError("Provider field selection has inconsistent identity")
            reading = reading_from_evidence(
                proposal.field,
                evidence,
                proposal.evidence_ids,
                confidence=proposal.confidence,
                acceptance_basis=proposal.acceptance_basis,
                selection_model=proposal.selection_model,
            )
            # A provider may apply a stricter confidence policy. Rebinding
            # evidence must not clear that uncertainty or its review reason.
            if reading.issue is None and proposal.issue is not None:
                reading.issue = proposal.issue
            reading.selection_request_id = proposal.selection_request_id
            reading.alternative_selection = proposal.alternative_selection
            reading.assistance_error = proposal.assistance_error
            fields[name] = reading
        try:
            fingerprint = evidence_fingerprint(evidence)
        except Exception:  # noqa: BLE001 - fingerprint never blocks saving
            fingerprint = evidence.evidence_fingerprint
        value = _ExtractionCheckpoint(
            version=CHECKPOINT_VERSION,
            role=extracted.role,  # type: ignore[arg-type]
            role_confidence=extracted.role_confidence,
            # Providers select evidence; the core owns source text, provenance
            # and normalization. A replacement adapter cannot fabricate values.
            fields=fields,
            evidence_fingerprint=fingerprint,
            acceptance_profile=self._acceptance_profile,
            extraction_policy=EXTRACTION_POLICY_VERSION,
            normalization_profile=NORMALIZATION_PROFILE,
        )
        self._checkpoints.save(key, value)
        return value

    def _prepare(
        self,
        source: AttachmentView,
        pair: list[str] | None,
        overrides: dict[str, Reading],
    ) -> _PreparedDocument:
        """Return a new attachment, readings and issues; never mutate `source`."""

        if self._remaining() <= self._provider_time_reserve:
            raise TimeoutError("application_deadline")
        attachment = source.model_copy(deep=True)
        evidence = self._read(attachment)
        attachment.evidence = evidence
        issues: list[str | Issue] = list(evidence.issues)
        extracted = self._extract(evidence)
        if extracted is None:
            issues.append("Document cannot be reliably extracted")
            return _PreparedDocument(
                attachment,
                None,
                issues,
            )
        attachment.role_confidence = extracted.role_confidence
        attachment.role = extracted.role  # type: ignore[assignment]
        if pair is not None:
            roles: dict[str, Literal["SI", "BL", "unknown"]] = dict(
                zip(pair, ("SI", "BL"), strict=True)
            )
            attachment.role = roles.get(attachment.id, "unknown")
        try:
            current_print = evidence_fingerprint(evidence)
        except Exception:  # noqa: BLE001 - fingerprint never blocks corrections
            current_print = evidence.evidence_fingerprint
        fields: dict[str, Reading] = {}
        for field, reading in extracted.fields.items():
            override = overrides.get(f"{attachment.id}:{field}")
            # Corrections bind to an exact evidence-set fingerprint, not merely
            # an ordinal block ID. A correction against different evidence
            # requires renewed human review and is ignored here.
            if override is not None:
                expected = override.evidence_fingerprint
                if expected and current_print and expected != current_print:
                    fields[field] = reading
                else:
                    fields[field] = override
            else:
                fields[field] = reading
        return _PreparedDocument(
            attachment,
            fields,
            issues,
        )

    @staticmethod
    def _compare(
        documents: list[_PreparedDocument],
        inputs: ProcessingInput,
    ) -> tuple[Report | None, list[str]]:
        """Pure comparison: return the report and additional issues."""

        sis = [document for document in documents if document.attachment.role == "SI"]
        bls = [document for document in documents if document.attachment.role == "BL"]
        if len(sis) != 1 or len(bls) != 1:
            return None, ["Select the correct SI and draft BL"]
        si, bl = sis[0], bls[0]
        if (
            si.fields is None
            or bl.fields is None
            or si.attachment.evidence is None
            or bl.attachment.evidence is None
        ):
            return None, ["Unreadable comparison documents"]
        manually_paired = inputs.accepted_pair == [si.attachment.id, bl.attachment.id]
        valid = validate_pair(
            si.attachment.evidence, bl.attachment.evidence, manually_paired
        )
        scoped_issues: list[str | Issue] = []
        for document in documents:
            selected = document is si or document is bl
            for issue in document.issues:
                scoped_issues.append(
                    normalize_issue(issue).model_copy(
                        update={
                            "document_id": document.attachment.id,
                            "scope": "selected_pair"
                            if selected
                            else "unused_attachment",
                        }
                    )
                )
        report = compare(
            si.fields, bl.fields, inputs.case.input_revision, valid, scoped_issues
        )
        # Detailed issues stay typed in the report. Assessment decides whether
        # they block the selected comparison; do not duplicate them as strings.
        extra: list[str] = []
        if any(finding.outcome == "unresolved" for finding in report.findings):
            extra.append("Some fields need review")
        return report, extra
