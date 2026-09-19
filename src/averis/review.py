"""Source-bound review decisions, independent of HTTP and persistence.

Each action operates on a private copy and returns explicit persistence changes.
The workflow adapter owns transactions, quotas, versions and job scheduling.
"""

from dataclasses import dataclass

from averis.contracts import FIELDS
from averis.domain import REVIEWERS, Action, CaseView, Reading
from averis.verification import compare, reading_from_evidence, validate_pair


@dataclass(frozen=True)
class ReviewDecision:
    view: CaseView
    input_changed: bool
    needs_processing: bool
    history_detail: str
    accepted_pair: list[str] | None = None
    reading_override: tuple[str, Reading] | None = None


def review_case(
    original: CaseView, action: Action, *, controlled: bool
) -> ReviewDecision:
    view = original.model_copy(deep=True)
    detail = action.reason.strip() or f"Updated {action.kind}"
    pair = None
    override = None
    match action.kind:
        case "assign":
            if action.assignee not in {*REVIEWERS, "Unassigned"}:
                raise ValueError("Unknown reviewer")
            assert action.assignee is not None
            view.assignee = action.assignee
        case "workflow":
            if action.workflow is None:
                raise ValueError("Select a workflow state")
            view.workflow = action.workflow
        case "category":
            detail = _change_category(view, action, controlled)
        case "pair":
            pair = _select_pair(view, action, controlled)
        case "correct":
            override = _correct_reading(view, action)
        case "retry":
            view.processing = "queued"
            view.stage = "retry_requested"
        case "revision":
            raise ValueError("Document revisions require the versioning workflow")
    return ReviewDecision(
        view=view,
        input_changed=action.kind in {"category", "pair", "correct"},
        needs_processing=view.processing == "queued"
        and action.kind in {"category", "pair", "retry"},
        history_detail=detail,
        accepted_pair=pair,
        reading_override=override,
    )


def _change_category(view: CaseView, action: Action, controlled: bool) -> str:
    if action.category is None or view.classification is None:
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


def _select_pair(view: CaseView, action: Action, controlled: bool) -> list[str]:
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


def _correct_reading(view: CaseView, action: Action) -> tuple[str, Reading]:
    require_comparison_category(view)
    if (
        not view.report
        or not view.report.pair_valid
        or not action.field
        or not action.reason.strip()
    ):
        raise ValueError("A valid comparison, field and correction reason are required")
    attachment = next((a for a in view.attachments if a.id == action.document_id), None)
    if attachment is None or attachment.superseded or attachment.evidence is None:
        raise ValueError("Evidence does not belong to this case")
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
    si = {f.field: f.si for f in view.report.findings}
    bl = {f.field: f.bl for f in view.report.findings}
    target = si if attachment.role == "SI" else bl if attachment.role == "BL" else None
    if target is None:
        raise ValueError("Document is not in the accepted pair")
    target[action.field] = replacement
    view.report = compare(si, bl, view.input_revision + 1, True, view.report.issues)
    view.review_reasons = sorted(
        set(view.report.issues)
        | {
            f.si.issue or f.bl.issue or "Unresolved field"
            for f in view.report.findings
            if f.outcome == "unresolved"
        }
    )
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
