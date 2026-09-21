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
    PairingEvidence,
    Reading,
    Report,
    evidence_fingerprint,
    normalize_issue,
)
from averis.intelligence import (
    MAX_CLASSIFICATION_DOCUMENTS,
    AttachmentPreview,
    Intelligence,
)
from averis.numeric_evidence import bind_numeric_selection
from averis.pairing import (
    PairingJudge,
    PairingProposal,
    accept_pairing,
    prepare_pairing,
)
from averis.timing import count, measure, timed
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


class _ClassificationCheckpoint(Classification):
    implementation: str = "legacy-unspecified"


class _DocumentCheckpoint(BaseModel):
    version: str
    evidence: DocumentEvidence
    reader_version: str
    ocr_profile: str
    evidence_fingerprint: str | None = None


class _ExtractionCheckpoint(BaseModel):
    implementation: str = "legacy-unspecified"
    version: str
    role: Literal["SI", "BL", "unknown"]
    role_confidence: float = Field(default=0, ge=0, le=1)
    fields: dict[str, Reading]
    evidence_fingerprint: str | None = None
    acceptance_profile: str
    extraction_policy: str
    normalization_profile: str


class _PairingCheckpoint(BaseModel):
    fingerprint: str
    proposal: PairingProposal


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


def _pair_selection_reason(
    documents: list[_PreparedDocument], si_count: int, bl_count: int
) -> str:
    if not documents:
        return "Waiting for documents: attach a Shipping Instruction and draft BL. Not checked yet."
    if any(document.fields is None for document in documents):
        return "A comparison document could not be read. Replace it with a readable SI or draft BL."
    if si_count > 1 or bl_count > 1:
        return "Several possible shipping documents were found. Select one SI and one draft BL."
    missing = (
        "draft BL"
        if si_count == 1
        else "Shipping Instruction"
        if bl_count == 1
        else "SI and draft BL"
    )
    return f"No {missing} identified. Attach the missing document or select its correct role. Not checked yet."


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
        pairing_judge: PairingJudge | None = None,
        reader_profile: tuple[str, str] = (READER_VERSION, OCR_PROFILE),
        extraction_profile: str = "legacy-unspecified",
        pairing_profile: str | None = None,
        classification_identity: str = "legacy-unspecified",
    ):
        self._intelligence = intelligence
        self._checkpoints = checkpoints
        self._load_document = load_document
        self._reader = reader
        self._remaining = remaining_seconds
        self._classification_profile = classification_profile
        self._acceptance_profile = acceptance_profile
        self._provider_time_reserve = provider_time_reserve
        self._pairing_judge = pairing_judge
        self._reader_version, self._ocr_profile = reader_profile
        self._extraction_profile = extraction_profile
        self._pairing_profile = pairing_profile
        self._classification_identity = classification_identity

    def process(self, inputs: ProcessingInput) -> ProcessingResult:
        """Run classification, preparation and comparison without mutating inputs.

        Document preparation returns its updated attachment, readings and
        issues; comparison returns its report and additional issues. Neither
        secretly mutates caller-owned arguments.
        """

        # Work on copies; inputs.case and its attachments are never mutated.
        attachments = [item.model_copy(deep=True) for item in inputs.case.attachments]
        classification = self._classify(inputs.case, attachments)
        # A resumed classification may already have prepared context before its
        # checkpoint was published. Restore Sources without repeating parsing.
        for attachment in attachments:
            if (
                attachment.evidence is None
                and self._checkpoints.load(
                    f"document:{attachment.id}", _DocumentCheckpoint
                )
                is not None
            ):
                attachment.evidence = self._read(attachment)
        if classification.accepted is None:
            count("document_processing_skipped")
            return ProcessingResult(
                classification, attachments, None, ["Check category"]
            )
        if classification.accepted != "BL_COMPARISON":
            count("document_processing_skipped")
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

    @timed("classify")
    def _classify(
        self, case: CaseView, attachments: list[AttachmentView]
    ) -> Classification:
        if case.classification is not None and case.classification.source == "human":
            count("classification_reused")
            return case.classification
        saved = self._checkpoints.load("classification", _ClassificationCheckpoint)
        if (
            saved is not None
            and saved.implementation == self._classification_identity
            and (
                self._classification_profile is None
                or (saved.model, saved.policy_version) == self._classification_profile
            )
        ):
            count("classification_reused")
            return Classification.model_validate(
                saved.model_dump(exclude={"implementation"})
            )
        # A changed provider profile invalidates only classification. Compatible
        # document checkpoints remain available, and human decisions take priority.
        classification = self._intelligence.classify(
            case.subject,
            case.body,
            attachment_filenames=tuple(
                attachment.filename
                for attachment in case.attachments
                if not attachment.superseded
            ),
            load_attachment_previews=lambda: self._classification_previews(attachments),
        )
        self._checkpoints.save(
            "classification",
            _ClassificationCheckpoint(
                **classification.model_dump(),
                implementation=self._classification_identity,
            ),
        )
        return classification

    def _classification_previews(
        self, attachments: list[AttachmentView]
    ) -> tuple[AttachmentPreview, ...]:
        """Prepare copied attachments once; extraction reuses these checkpoints.

        Full format/resource limits still apply to reading. Only bounded reliable
        text is exposed to classification, and prepared evidence stays in Sources
        even when the resulting category is not a shipment comparison.
        """
        active = [attachment for attachment in attachments if not attachment.superseded]
        if len(active) > MAX_CLASSIFICATION_DOCUMENTS:
            return ()
        previews: list[AttachmentPreview] = []
        for attachment in active:
            attachment.evidence = self._read(attachment)
            previews.append(
                AttachmentPreview.from_evidence(
                    attachment.filename, attachment.evidence
                )
            )
        count("classification_preview_documents", len(previews))
        return tuple(previews)

    @staticmethod
    def _decode_overrides(saved: dict[str, object]) -> dict[str, Reading]:
        try:
            return TypeAdapter(dict[str, Reading]).validate_python(saved)
        except ValidationError as exc:
            raise InvalidCheckpoint("Saved reviewer readings are invalid") from exc

    @timed("read_document")
    def _read(self, attachment: AttachmentView) -> DocumentEvidence:
        key = f"document:{attachment.id}"
        saved = self._checkpoints.load(key, _DocumentCheckpoint)
        if saved is not None:
            # Unversioned resumable checkpoints cannot be reused.
            if (
                saved.version != CHECKPOINT_VERSION
                or saved.reader_version != self._reader_version
                or saved.ocr_profile != self._ocr_profile
            ):
                raise InvalidCheckpoint(
                    "Saved document reading uses an incompatible reader profile"
                )
            if saved.evidence.document_id != attachment.id:
                raise InvalidCheckpoint("Saved document reading has wrong identity")
            count("document_reading_reused")
            return saved.evidence
        if (
            attachment.evidence is not None
            and attachment.evidence.reader_version == self._reader_version
            and attachment.evidence.ocr_profile == self._ocr_profile
        ):
            # Legacy evidence without a fingerprint is fingerprinted from its
            # stored contents without claiming a newer parser produced it.
            try:
                fingerprint = evidence_fingerprint(attachment.evidence)
            except Exception:  # noqa: BLE001 - fingerprint never blocks reading
                fingerprint = None
            if attachment.evidence.evidence_fingerprint is None and fingerprint:
                attachment.evidence.evidence_fingerprint = fingerprint
            count("document_reading_reused")
            return attachment.evidence
        content = self._load_document(attachment.id)
        available = self._remaining() - self._provider_time_reserve
        if available <= 0:
            raise TimeoutError("application_deadline")
        with measure("parser"):
            evidence = self._reader(
                attachment.id,
                attachment.filename,
                content,
                timeout_seconds=min(PARSER_TIMEOUT_SECONDS, available),
            )
        count("documents_parsed")
        count("ocr_blocks", sum(block.method == "ocr" for block in evidence.blocks))
        count("native_blocks", sum(block.method != "ocr" for block in evidence.blocks))
        try:
            fingerprint = evidence_fingerprint(evidence)
        except Exception:  # noqa: BLE001 - fingerprint never blocks reading
            fingerprint = None
        self._checkpoints.save(
            key,
            _DocumentCheckpoint(
                version=CHECKPOINT_VERSION,
                evidence=evidence,
                reader_version=self._reader_version,
                ocr_profile=self._ocr_profile,
                evidence_fingerprint=fingerprint or evidence.evidence_fingerprint,
            ),
        )
        return evidence

    @timed("extract")
    def _extract(self, evidence: DocumentEvidence) -> _ExtractionCheckpoint | None:
        key = f"extraction:{evidence.document_id}"
        saved = self._checkpoints.load(key, _ExtractionCheckpoint)
        if saved is not None:
            if (
                saved.version != CHECKPOINT_VERSION
                or saved.implementation != self._extraction_profile
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
            count("extraction_reused")
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
            if proposal.numeric_selection is not None:
                reading = bind_numeric_selection(
                    evidence,
                    proposal.field,
                    proposal.numeric_selection,
                    proposal.confidence,
                    proposal.selection_model,
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
            implementation=self._extraction_profile,
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

    @timed("compare")
    def _compare(
        self,
        documents: list[_PreparedDocument],
        inputs: ProcessingInput,
    ) -> tuple[Report | None, list[str]]:
        """Establish source-bound pairing, then compare independently read fields."""

        sis = [document for document in documents if document.attachment.role == "SI"]
        bls = [document for document in documents if document.attachment.role == "BL"]
        if len(sis) != 1 or len(bls) != 1:
            return None, [_pair_selection_reason(documents, len(sis), len(bls))]
        si, bl = sis[0], bls[0]
        if (
            si.fields is None
            or bl.fields is None
            or si.attachment.evidence is None
            or bl.attachment.evidence is None
        ):
            return None, ["Unreadable comparison documents"]
        valid, pairing_evidence = self._pair(
            si.attachment.evidence, bl.attachment.evidence, inputs
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
        report.pairing_evidence = pairing_evidence
        # Detailed issues stay typed in the report. Assessment decides whether
        # they block the selected comparison; do not duplicate them as strings.
        extra: list[str] = []
        if any(finding.outcome == "unresolved" for finding in report.findings):
            extra.append("Some fields need review")
        return report, extra

    @timed("pair")
    def _pair(
        self, si: DocumentEvidence, bl: DocumentEvidence, inputs: ProcessingInput
    ) -> tuple[bool, PairingEvidence | None]:
        if not validate_pair(si, bl, human_selected=True):
            return False, None
        manually_paired = inputs.accepted_pair == [si.document_id, bl.document_id]
        if validate_pair(si, bl, manually_paired):
            return True, None
        if self._pairing_judge is None:
            return False, None
        request = prepare_pairing(inputs.case.subject, inputs.case.body, si, bl)
        if request is None:
            return False, None
        model = (
            self._classification_profile[0] if self._classification_profile else None
        )
        fingerprint = request.fingerprint(self._pairing_profile or model)
        saved = self._checkpoints.load("pairing", _PairingCheckpoint)
        if saved is None or saved.fingerprint != fingerprint:
            if self._remaining() <= PROVIDER_TIME_RESERVE_SECONDS:
                raise TimeoutError("application_deadline")
            proposal = self._pairing_judge(request)
            # Validate before saving. Malformed provider output must not become
            # a durable accepted judgment or a silent abstention.
            accept_pairing(request, proposal)
            saved = _PairingCheckpoint(fingerprint=fingerprint, proposal=proposal)
            self._checkpoints.save("pairing", saved)
        evidence = accept_pairing(request, saved.proposal)
        return evidence is not None, evidence
