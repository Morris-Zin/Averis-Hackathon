"""One interpretation of report completeness for all application views.

The pure :func:`assess_case` operation owns classification acceptance, report
currentness, complete/unique fields, valid pairing, mismatches, unresolved
findings and blocking issues. The screen summary, persisted queue flags and
export adapter all consume this assessment.
"""

from typing import Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField

from averis.contracts import FIELDS, Category, Field
from averis.domain import AttachmentView, CaseView, Issue, normalize_issue


def spam_status(case: CaseView) -> Literal["confirmed", "suspected"] | None:
    classification = case.classification
    if classification is None:
        return None
    if classification.accepted == "SPAM":
        return "confirmed"
    if (
        classification.accepted is None
        and classification.suggested == "SPAM"
        and classification.source != "human"
    ):
        return "suspected"
    return None


class Assessment(BaseModel):
    """Authoritative facts about one case; no HTTP or persistence details."""

    classification_accepted: Category | None = None
    report_present: bool = False
    report_current: bool = False
    fields_complete_unique: bool = False
    pair_valid: bool = False
    mismatches: list[Field] = PydanticField(default_factory=lambda: list[Field]())
    unresolved: list[Field] = PydanticField(default_factory=lambda: list[Field]())
    blocking_issues: list[str] = PydanticField(default_factory=lambda: list[str]())
    unused_warnings: list[str] = PydanticField(default_factory=lambda: list[str]())
    selected_pair: list[str] | None = None
    has_mismatch: bool = False
    needs_review: bool = True
    can_be_clear: bool = False


def _issue_text(issue: str | object) -> str:
    if isinstance(issue, str):
        return issue
    code = getattr(issue, "code", "unknown_issue")
    detail = getattr(issue, "detail", "")
    return f"{code}:{detail}" if detail else str(code)


def _current_attachments(case: CaseView) -> list[AttachmentView]:
    return [a for a in case.attachments if not a.superseded]


def _explicit_pair(current: list[AttachmentView]) -> list[str] | None:
    sis = [a for a in current if a.role == "SI" and a.evidence is not None]
    bls = [a for a in current if a.role == "BL" and a.evidence is not None]
    if len(sis) == 1 and len(bls) == 1:
        return [sis[0].id, bls[0].id]
    return None


def _evidence_texts(attachments: list[AttachmentView]) -> list[str | Issue]:
    texts: list[str | Issue] = []
    for attachment in attachments:
        if attachment.evidence is None:
            continue
        texts.extend(attachment.evidence.issues)
    return texts


def _split_selected_unused(
    current: list[AttachmentView], selected_pair: list[str] | None
) -> tuple[list[str | Issue], list[str | Issue]]:
    if selected_pair is None:
        # Conservative: without an explicit SI/BL selection every readable
        # problem blocks until a reviewer selects the comparison pair.
        return _evidence_texts(current), []
    selected_ids = set(selected_pair)
    selected = [a for a in current if a.id in selected_ids]
    unused = [a for a in current if a.id not in selected_ids]
    return _evidence_texts(selected), _evidence_texts(unused)


def _report_facts(case: CaseView, assessment: Assessment) -> list[str | Issue]:
    report = case.report
    assessment.report_present = report is not None
    if report is None:
        assessment.report_current = False
        assessment.pair_valid = False
        assessment.fields_complete_unique = False
        return []
    assessment.report_current = report.input_revision == case.input_revision
    assessment.pair_valid = bool(report.pair_valid)
    seen: set[str] = set()
    duplicate = False
    for finding in report.findings:
        if finding.field in seen:
            duplicate = True
        seen.add(finding.field)
        if finding.outcome == "mismatch":
            assessment.mismatches.append(finding.field)
        elif finding.outcome == "unresolved":
            assessment.unresolved.append(finding.field)
    assessment.fields_complete_unique = (
        not duplicate and seen == set(FIELDS) and len(report.findings) == len(FIELDS)
    )
    return list(report.issues)


def assess_case(case: CaseView) -> Assessment:
    """Pure assessment covering acceptance, currency, completeness and blocks.

    Attachment policy:
    - An explicitly selected SI/BL pair is assessed using its own evidence and
      issues; problems in unused attachments remain visible as warnings.
    - Conflicting identifiers within the selected pair still block comparison.
    - Without an explicit selection, ambiguous documents are handled
      conservatively (all readable issues block).
    - Unknown legacy issue strings remain blocking until scoped; they are never
      silently discarded.
    """

    assessment = Assessment()
    classification = case.classification
    assessment.classification_accepted = (
        classification.accepted if classification else None
    )
    current = _current_attachments(case)
    assessment.selected_pair = _explicit_pair(current)
    selected_texts, unused = _split_selected_unused(current, assessment.selected_pair)
    assessment.unused_warnings = [_issue_text(issue) for issue in unused]
    report_texts = _report_facts(case, assessment)

    # Blocking issues: selected evidence + report issues + explicit review
    # reasons. Legacy unknown strings stay blocking; unused warnings are visible
    # separately and do not decide the selected-pair comparison.
    blocking: list[str] = []
    for text in [*selected_texts, *report_texts]:
        parsed = normalize_issue(text)
        if parsed.scope == "unused_attachment":
            assessment.unused_warnings.append(_issue_text(text))
        elif parsed.blocking:
            blocking.append(_issue_text(text))
    # Unexplained review reasons always block a clear outcome; export retains
    # additional official-schema restrictions on top of this assessment.
    for reason in case.review_reasons:
        if reason not in blocking:
            blocking.append(reason)
    assessment.blocking_issues = sorted(set(blocking))
    assessment.has_mismatch = bool(assessment.mismatches)
    # A clear comparison needs an accepted BL_COMPARISON category, a current
    # complete valid report, no mismatches/unresolved and no blocking issues.
    assessment.can_be_clear = bool(
        assessment.classification_accepted == "BL_COMPARISON"
        and assessment.report_present
        and assessment.report_current
        and assessment.fields_complete_unique
        and assessment.pair_valid
        and not assessment.mismatches
        and not assessment.unresolved
        and not assessment.blocking_issues
    )
    # Non-comparison categories are review-free only when nothing blocks them.
    if assessment.classification_accepted not in (None, "BL_COMPARISON"):
        assessment.needs_review = bool(
            assessment.blocking_issues
            or case.review_reasons
            or case.processing == "failed"
        )
    else:
        assessment.needs_review = bool(
            case.review_reasons
            or case.processing == "failed"
            or assessment.blocking_issues
            or assessment.unused_warnings
            or not assessment.report_present
            or not assessment.report_current
            or not assessment.fields_complete_unique
            or not assessment.pair_valid
            or bool(assessment.unresolved)
            or assessment.has_mismatch
            or assessment.classification_accepted is None
        )
    return assessment


class CaseSummary(BaseModel):
    kind: Literal[
        "queued",
        "running",
        "failed",
        "unclassified",
        "categorized",
        "spam",
        "suspected_spam",
        "needs_review",
        "mismatch",
        "mismatch_review",
        "match",
    ]
    mismatches: int = 0


def summarize_case(case: CaseView) -> CaseSummary:
    """Screen summary derived from the shared assessment."""

    spam = spam_status(case)
    if spam:
        return CaseSummary(kind="spam" if spam == "confirmed" else "suspected_spam")
    if case.processing != "completed":
        return CaseSummary(kind=case.processing)  # type: ignore[arg-type]
    if case.classification is None:
        return CaseSummary(kind="unclassified")
    if case.classification.accepted is None:
        return CaseSummary(kind="needs_review")
    if case.classification.accepted != "BL_COMPARISON":
        assessment = assess_case(case)
        return CaseSummary(
            kind="needs_review" if assessment.needs_review else "categorized"
        )
    assessment = assess_case(case)
    if not assessment.report_present:
        return CaseSummary(kind="needs_review")
    blocked = (
        not assessment.pair_valid
        or not assessment.report_current
        or bool(assessment.blocking_issues)
        or bool(assessment.unused_warnings)
        or not assessment.fields_complete_unique
        or bool(assessment.unresolved)
    )
    if assessment.mismatches:
        return CaseSummary(
            kind="mismatch_review" if blocked else "mismatch",
            mismatches=len(assessment.mismatches),
        )
    return CaseSummary(kind="needs_review" if blocked else "match")
