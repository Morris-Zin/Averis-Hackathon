"""Source-bound review decisions, independent of HTTP and persistence.

Each action operates on a private copy and returns explicit persistence changes.
The workflow adapter owns transactions, versions and job scheduling.
"""

from dataclasses import dataclass
from typing import Literal

from averis.case_status import spam_status
from averis.contracts import FIELDS
from averis.domain import (
    REVIEWERS,
    Action,
    AssignAction,
    CaseView,
    CategoryAction,
    CorrectAction,
    PairAction,
    Reading,
    ReadingCorrection,
    WorkflowAction,
)
from averis.verification import compare, reading_from_evidence, validate_pair


@dataclass(frozen=True)
class ReviewDecision:
    """Explicit domain outcome; workflow owns the surrounding transaction."""

    view: CaseView
    next_input_revision: int
    input_changed: bool
    processing_intent: Literal["none", "queue"]
    history_detail: str
    accepted_pair: list[str] | None = None
    reading_override: tuple[str, Reading] | None = None
    correction: ReadingCorrection | None = None

    @property
    def needs_processing(self) -> bool:
        return self.processing_intent == "queue"


def review_case(
    original: CaseView, action: Action, *, controlled: bool
) -> ReviewDecision:
    # Determine the next input revision once; all branches use this value.
    input_changed = action.kind in {"category", "pair", "correct", "not_spam"}
    next_input = original.input_revision + (1 if input_changed else 0)
    view = original.model_copy(deep=True)
    if input_changed:
        view.input_revision = next_input
    detail = action.reason.strip() or f"Updated {action.kind}"
    pair = None
    override = None
    correction = None
    match action.kind:
        case "assign":
            assert isinstance(action, AssignAction)
            if action.assignee not in {*REVIEWERS, "Unassigned"}:
                raise ValueError("Unknown reviewer")
            view.assignee = action.assignee
        case "workflow":
            assert isinstance(action, WorkflowAction)
            view.workflow = action.workflow
        case "category":
            assert isinstance(action, CategoryAction)
            detail = _change_category(view, action, controlled, next_input)
        case "not_spam":
            if spam_status(view) is None or view.classification is None:
                raise ValueError("Only spam or suspected spam can be restored")
            # A human rejection is not acceptance of a replacement category.
            # The pipeline preserves human classifications, including abstentions.
            view.classification.accepted = None
            view.classification.source = "human"
            view.workflow = "open"
            view.processing, view.stage = "completed", "classification_required"
            view.review_reasons = list(
                dict.fromkeys(
                    [
                        *view.review_reasons,
                        "Not spam: choose the appropriate email category",
                    ]
                )
            )
            detail = "Marked not spam; returned to classification review"
        case "pair":
            assert isinstance(action, PairAction)
            pair = _select_pair(view, action, controlled, next_input)
        case "correct":
            assert isinstance(action, CorrectAction)
            override = _correct_reading(view, action, next_input)
            assert original.report is not None
            before = next(
                reading
                for finding in original.report.findings
                for reading in (finding.si, finding.bl)
                if reading.field == action.field
                and reading.document_id == action.document_id
            )
            correction = ReadingCorrection(
                before=before.model_copy(deep=True),
                after=override[1].model_copy(deep=True),
                input_revision=next_input,
            )
            detail = f"Corrected {action.field}: {before.text!r} → {override[1].text!r}. {detail}"
        case "retry":
            view.processing = "queued"
            view.stage = "retry_requested"
        case "revision":
            raise ValueError("Document revisions require the versioning workflow")
    processing_intent: Literal["none", "queue"] = (
        "queue"
        if view.processing == "queued" and action.kind in {"category", "pair", "retry"}
        else "none"
    )
    return ReviewDecision(
        view=view,
        next_input_revision=next_input,
        input_changed=input_changed,
        processing_intent=processing_intent,
        history_detail=detail,
        accepted_pair=pair,
        reading_override=override,
        correction=correction,
    )


def _change_category(
    view: CaseView, action: CategoryAction, controlled: bool, next_input: int
) -> str:
    if view.classification is None:
        raise ValueError("Choose a category after classification is available")
    previous_category = view.classification.accepted
    view.classification.accepted = action.category
    view.classification.source = "human"
    history_detail = f"Category changed from {previous_category or 'unaccepted'} to {action.category}"
    if action.reason.strip():
        history_detail += f": {action.reason.strip()}"
    view.review_reasons = []
    view.report = None
    if action.category == "BL_COMPARISON":
        if controlled:
            replay_saved_comparison(view)
        else:
            view.processing, view.stage = "queued", "classification_accepted"
    else:
        view.processing, view.stage = "completed", "category_changed"
    return history_detail


def _select_pair(
    view: CaseView, action: PairAction, controlled: bool, next_input: int
) -> list[str]:
    require_comparison_category(view)
    if action.si_id == action.bl_id:
        raise ValueError("Select different SI and BL documents")
    si = next((a for a in view.attachments if a.id == action.si_id), None)
    bl = next((a for a in view.attachments if a.id == action.bl_id), None)
    if (
        not si
        or not bl
        or si.superseded
        or bl.superseded
        or not si.evidence
        or not bl.evidence
        or not action.reason.strip()
    ):
        raise ValueError("Choose two read documents and explain the pairing")
    if not validate_pair(si.evidence, bl.evidence, human_selected=True):
        raise ValueError("Document shipment identifiers conflict")
    for attachment in view.attachments:
        attachment.role = (
            "SI"
            if attachment.id == si.id
            else "BL"
            if attachment.id == bl.id
            else "unknown"
        )
    view.report = None
    if controlled:
        replay_saved_comparison(view)
    else:
        view.processing, view.stage = "queued", "pair_accepted"
    return [si.id, bl.id]


def _correct_reading(
    view: CaseView, action: CorrectAction, next_input: int
) -> tuple[str, Reading]:
    from averis.domain import evidence_fingerprint

    require_comparison_category(view)
    # The report must be current against the pre-action input revision; the
    # correction advances to next_input exactly once (view already carries it).
    if (
        not view.report
        or not view.report.pair_valid
        or view.report.input_revision
        not in (view.input_revision - 1, view.input_revision)
        or not action.reason.strip()
    ):
        raise ValueError(
            "A current valid comparison, field and correction reason are required"
        )
    si_attachment = next(
        (
            item
            for item in view.attachments
            if item.role == "SI" and not item.superseded
        ),
        None,
    )
    bl_attachment = next(
        (
            item
            for item in view.attachments
            if item.role == "BL" and not item.superseded
        ),
        None,
    )
    if (
        si_attachment is None
        or bl_attachment is None
        or any(
            finding.si.document_id != si_attachment.id
            or finding.bl.document_id != bl_attachment.id
            for finding in view.report.findings
        )
    ):
        raise ValueError("Comparison evidence does not match the current document pair")
    attachment = next((a for a in view.attachments if a.id == action.document_id), None)
    if attachment is None or attachment.superseded or attachment.evidence is None:
        raise ValueError("Evidence does not belong to this case")
    selected_blocks = {
        block.id: block
        for block in attachment.evidence.blocks
        if block.id in action.evidence_ids
    }
    if (
        any(block.method == "ocr" for block in selected_blocks.values())
        and not action.verified
    ):
        raise ValueError("Verify OCR evidence against the original before saving")
    if action.transcription is not None and not action.verified:
        raise ValueError(
            "Verify the transcription against the original image before saving"
        )
    replacement = reading_from_evidence(
        action.field,
        attachment.evidence,
        action.evidence_ids,
        transcription=action.transcription,
        verified=action.verified,
    )
    if not replacement.evidence_ids:
        raise ValueError("Select evidence from this document")
    if action.transcription is None:
        replacement.provenance = "human_verified"
    # Bind the correction to the exact evidence set, not merely an ordinal ID.
    replacement.evidence_fingerprint = evidence_fingerprint(attachment.evidence)
    assert view.report is not None
    si = {f.field: f.si for f in view.report.findings}
    bl = {f.field: f.bl for f in view.report.findings}
    target = si if attachment.role == "SI" else bl if attachment.role == "BL" else None
    if target is None:
        raise ValueError("Document is not in the accepted pair")
    target[action.field] = replacement
    pairing_evidence = view.report.pairing_evidence
    view.report = compare(si, bl, next_input, True, view.report.issues)
    # Correcting a field changes our reading, not the document identity.
    view.report.pairing_evidence = pairing_evidence
    unresolved = [
        finding for finding in view.report.findings if finding.outcome == "unresolved"
    ]
    unresolved_issues = {
        issue
        for finding in unresolved
        for issue in (finding.si.issue, finding.bl.issue)
        if issue
    }
    if any(not finding.si.issue and not finding.bl.issue for finding in unresolved):
        unresolved_issues.add("Unresolved field")

    def _text(issue: str | object) -> str:
        if isinstance(issue, str):
            return issue
        code = getattr(issue, "code", "unknown_issue")
        detail = getattr(issue, "detail", "")
        return f"{code}:{detail}" if detail else str(code)

    view.review_reasons = sorted(
        {_text(issue) for issue in view.report.issues} | unresolved_issues
    )
    view.processing, view.stage = "completed", "reading_corrected"
    view.processing_error = None
    return f"{attachment.id}:{action.field}", replacement


def require_comparison_category(view: CaseView) -> None:
    if not view.classification or view.classification.accepted != "BL_COMPARISON":
        raise ValueError(
            "Accept the BL comparison category before reviewing shipment documents"
        )


def replay_saved_comparison(view: CaseView) -> None:
    """Replay explicitly labelled fixture readings, without pretending to run AI."""
    si = next(
        (a for a in view.attachments if a.role == "SI" and not a.superseded), None
    )
    bl = next(
        (a for a in view.attachments if a.role == "BL" and not a.superseded), None
    )
    view.processing, view.stage = "completed", "saved_demo"
    if not si or not bl or not si.evidence or not bl.evidence:
        view.report = None
        view.review_reasons = ["Select the correct SI and draft BL"]
        return
    readings = [
        {field: reading_from_evidence(field, a.evidence, [field]) for field in FIELDS}
        for a in (si, bl)
        if a.evidence
    ]
    view.report = compare(
        readings[0],
        readings[1],
        view.input_revision,
        validate_pair(si.evidence, bl.evidence, True),
    )
    view.review_reasons = (
        ["Some fields need review"]
        if any(f.outcome == "unresolved" for f in view.report.findings)
        else []
    )
