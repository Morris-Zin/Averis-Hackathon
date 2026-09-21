"""Honest adapter from rich case state to the unchanged organizer contract."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from averis.contracts import FIELDS, Field, Prediction
from averis.domain import CaseView, Finding, Report, normalize_issue

ExportBlocker = Literal[
    "processing_incomplete",
    "illustrative_demo",
    "pairing_unresolved",
    "category_unresolved",
    "comparison_missing",
    "report_incomplete",
    "report_issue_unrepresentable",
    "mixed_outcomes_unrepresentable",
    "review_reason_unrepresentable",
    "multiple_review_reasons_unrepresentable",
]
ReviewReason = Literal[
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
]

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
_FIELD_SET = frozenset(_TYPED_FIELDS)
_REVIEW_ACTIONS = frozenset({"category", "pair", "correct"})
_MISSING_READING_ISSUES = frozenset({"missing_value", "missing_or_ambiguous_value"})
_SELECTION_UNCERTAINTY = frozenset(
    {"low_field_confidence", "low_ocr_confidence", "provider_disagreement"}
)


class ExportBlocked(ValueError):
    """Raised when a complete scorer payload would require fabricated state."""


def _empty_blockers() -> list[ExportBlocker]:
    return []


class ExportDiagnostics(BaseModel):
    """Sidecar metadata; never embedded in the official scorer payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer_assisted: bool = False
    reviewer_actions: list[str] = PydanticField(default_factory=list)
    blockers: list[ExportBlocker] = PydanticField(default_factory=_empty_blockers)
    known_mismatches: list[Field] = PydanticField(default_factory=lambda: list[Field]())
    unresolved_fields: list[Field] = PydanticField(
        default_factory=lambda: list[Field]()
    )
    review_reasons: list[str] = PydanticField(default_factory=list)


class ExportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction: Prediction | None = None
    diagnostics: ExportDiagnostics


class SubmissionExport(BaseModel):
    """Official predictions plus diagnostics kept outside the scorer schema."""

    model_config = ConfigDict(extra="forbid")

    predictions: dict[str, Prediction] = PydanticField(default_factory=dict)
    diagnostics: dict[str, ExportDiagnostics] = PydanticField(default_factory=dict)
    global_blockers: list[str] = PydanticField(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.global_blockers and all(
            not diagnostic.blockers for diagnostic in self.diagnostics.values()
        )

    def official_payload(self) -> dict[str, dict[str, object]]:
        """Return only the organizer fields, refusing partial or invented rows."""

        if not self.complete:
            blockers = [*self.global_blockers]
            blockers.extend(
                f"{case_id}:{blocker}"
                for case_id, diagnostic in self.diagnostics.items()
                for blocker in diagnostic.blockers
            )
            raise ExportBlocked("Export blocked: " + ", ".join(blockers))
        return {
            case_id: cast(dict[str, object], prediction.model_dump(mode="json"))
            for case_id, prediction in self.predictions.items()
        }

    def diagnostics_payload(self) -> dict[str, dict[str, object]]:
        """Serialize the reviewer marker and blockers as a separate sidecar."""

        return {
            case_id: cast(dict[str, object], diagnostic.model_dump(mode="json"))
            for case_id, diagnostic in self.diagnostics.items()
        }


def adapt_case(case: CaseView) -> ExportDecision:
    """Adapt one final case without collapsing an unknown into a false outcome."""

    reviewer_actions = _reviewer_actions(case)
    reviewer_assisted = bool(reviewer_actions) or _has_human_reading(case)

    if case.processing != "completed":
        return _blocked(reviewer_assisted, reviewer_actions, "processing_incomplete")
    classification = case.classification
    if classification is None or classification.accepted is None:
        return _blocked(reviewer_assisted, reviewer_actions, "category_unresolved")

    if classification.source == "fixture" or any(
        entry.actor == "Demo setup" for entry in case.history
    ):
        return _blocked(reviewer_assisted, reviewer_actions, "illustrative_demo")

    category = classification.accepted
    if category != "BL_COMPARISON":
        return ExportDecision(
            prediction=Prediction(
                category=category,
                status="OK",
                review_reason=None,
                has_defect=False,
                defect_fields=[],
            ),
            diagnostics=ExportDiagnostics(
                reviewer_assisted=reviewer_assisted,
                reviewer_actions=reviewer_actions,
            ),
        )

    report = case.report
    if report is None:
        reason, blocker = _reason_without_report(case)
        if blocker is not None:
            return _blocked(reviewer_assisted, reviewer_actions, blocker)
        assert reason is not None
        return _review_decision(case, reviewer_assisted, reviewer_actions, reason)

    decision = _adapt_comparison(case, report, reviewer_assisted, reviewer_actions)
    if any(
        blocker in {"pairing_unresolved", "comparison_missing", "report_incomplete"}
        for blocker in decision.diagnostics.blockers
    ):
        return decision
    # The official schema has no place for simultaneous findings and unknowns.
    # Preserve both in the sidecar even when the official row needs review.
    from averis.case_status import assess_case

    assessment = assess_case(case)
    return decision.model_copy(
        update={
            "diagnostics": decision.diagnostics.model_copy(
                update={
                    "known_mismatches": assessment.mismatches,
                    "unresolved_fields": assessment.unresolved,
                    "review_reasons": assessment.blocking_issues,
                }
            )
        }
    )


def _adapt_comparison(
    case: CaseView, report: Report, reviewer_assisted: bool, reviewer_actions: list[str]
) -> ExportDecision:
    if not report.pair_valid:
        return _blocked(reviewer_assisted, reviewer_actions, "pairing_unresolved")
    if report.input_revision != case.input_revision:
        return _blocked(reviewer_assisted, reviewer_actions, "comparison_missing")

    by_field = {finding.field: finding for finding in report.findings}
    if len(report.findings) != len(_FIELD_SET) or frozenset(by_field) != _FIELD_SET:
        return _blocked(reviewer_assisted, reviewer_actions, "report_incomplete")

    mismatches: list[Field] = [
        field for field in _TYPED_FIELDS if by_field[field].outcome == "mismatch"
    ]
    unresolved = [
        by_field[field]
        for field in _TYPED_FIELDS
        if by_field[field].outcome == "unresolved"
    ]
    reasons, unrepresentable = _review_reasons(case, unresolved)
    # Report issues may be legacy strings or typed Issue records; only the
    # benign pair marker is representable. Any other selected-pair issue makes
    # the row unrepresentable, and an unexplained blocking reason can never
    # emit OK.
    report_texts = [
        issue if isinstance(issue, str) else f"{issue.code}:{issue.detail}".rstrip(":")
        for issue in report.issues
        if normalize_issue(issue).blocking
        and normalize_issue(issue).scope != "unused_attachment"
    ]
    if report_texts and report_texts != ["pair_requires_review"]:
        unrepresentable = True
    from averis.case_status import assess_case

    assessment = assess_case(case)
    if assessment.blocking_issues and not unresolved and not reasons:
        # A blocking issue with no representable official reason (for example an
        # unknown legacy string or a conflicting identifier) must block export.
        unrepresentable = True

    if mismatches and (unresolved or reasons or unrepresentable):
        if any(
            issue != "Some fields need review" for issue in assessment.blocking_issues
        ):
            return _blocked(
                reviewer_assisted, reviewer_actions, "mixed_outcomes_unrepresentable"
            )
        if reasons == {"missing_value"}:
            # The organizer explicitly treats missing required values as review,
            # even if other fields differ. Known findings survive in diagnostics.
            return _review_decision(
                case, reviewer_assisted, reviewer_actions, "missing_value"
            )
        if reasons or not _only_selection_uncertainty(unresolved):
            return _blocked(
                reviewer_assisted, reviewer_actions, "mixed_outcomes_unrepresentable"
            )
        # A dependable discrepancy answers whether at least one field differs.
        # Unrelated selection uncertainty does not turn it into a match or erase
        # it. Only known fields are exported; the app and sidecar retain review.
        return _mismatch_decision(mismatches, reviewer_assisted, reviewer_actions)
    if unresolved or reasons or unrepresentable:
        if unrepresentable:
            return _blocked(
                reviewer_assisted,
                reviewer_actions,
                "review_reason_unrepresentable",
            )
        if len(reasons) != 1:
            reason_blocker: ExportBlocker = (
                "multiple_review_reasons_unrepresentable"
                if reasons
                else "review_reason_unrepresentable"
            )
            return _blocked(reviewer_assisted, reviewer_actions, reason_blocker)
        return _review_decision(
            case,
            reviewer_assisted,
            reviewer_actions,
            next(iter(reasons)),
        )

    if mismatches:
        return _mismatch_decision(mismatches, reviewer_assisted, reviewer_actions)
    return ExportDecision(
        prediction=Prediction(
            category="BL_COMPARISON",
            status="OK",
            review_reason=None,
            has_defect=False,
            defect_fields=[],
        ),
        diagnostics=ExportDiagnostics(
            reviewer_assisted=reviewer_assisted,
            reviewer_actions=reviewer_actions,
        ),
    )


def _mismatch_decision(
    fields: list[Field], reviewer_assisted: bool, reviewer_actions: list[str]
) -> ExportDecision:
    return ExportDecision(
        prediction=Prediction(
            category="BL_COMPARISON",
            status="MISMATCH",
            review_reason=None,
            has_defect=True,
            defect_fields=fields,
        ),
        diagnostics=ExportDiagnostics(
            reviewer_assisted=reviewer_assisted,
            reviewer_actions=reviewer_actions,
        ),
    )


def _only_selection_uncertainty(findings: list[Finding]) -> bool:
    if not findings:
        return False
    issues = [
        reading.issue
        for finding in findings
        for reading in (finding.si, finding.bl)
        if reading.issue is not None or reading.normalized is None
    ]
    return bool(issues) and all(issue in _SELECTION_UNCERTAINTY for issue in issues)


def export_submission(
    cases: Iterable[CaseView], expected_ids: Iterable[str]
) -> SubmissionExport:
    """Build an exact-ID submission and retain blockers instead of placeholders."""

    case_list = list(cases)
    expected_list = list(expected_ids)
    case_counts = Counter(case.id for case in case_list)
    expected_counts = Counter(expected_list)
    global_blockers: list[str] = []
    global_blockers.extend(
        f"duplicate_case_id:{case_id}"
        for case_id, count in sorted(case_counts.items())
        if count > 1
    )
    global_blockers.extend(
        f"duplicate_expected_id:{case_id}"
        for case_id, count in sorted(expected_counts.items())
        if count > 1
    )
    case_by_id = {case.id: case for case in case_list}
    expected = set(expected_list)
    actual = set(case_by_id)
    global_blockers.extend(
        f"missing_expected_case:{case_id}" for case_id in sorted(expected - actual)
    )
    global_blockers.extend(
        f"unexpected_case:{case_id}" for case_id in sorted(actual - expected)
    )

    predictions: dict[str, Prediction] = {}
    diagnostics: dict[str, ExportDiagnostics] = {}
    for case_id in expected_list:
        case = case_by_id.get(case_id)
        if case is None or case_id in diagnostics:
            continue
        decision = adapt_case(case)
        diagnostics[case_id] = decision.diagnostics
        if decision.prediction is not None:
            predictions[case_id] = decision.prediction
    return SubmissionExport(
        predictions=predictions,
        diagnostics=diagnostics,
        global_blockers=global_blockers,
    )


def _reviewer_actions(case: CaseView) -> list[str]:
    actions = {
        entry.action
        for entry in case.history
        if entry.action in _REVIEW_ACTIONS and entry.actor != "Processing"
    }
    if case.classification is not None and case.classification.source == "human":
        actions.add("category")
    return sorted(actions)


def _has_human_reading(case: CaseView) -> bool:
    if case.report is None:
        return False
    return any(
        reading.provenance != "machine"
        for finding in case.report.findings
        for reading in (finding.si, finding.bl)
    )


def _reason_without_report(
    case: CaseView,
) -> tuple[ReviewReason | None, ExportBlocker | None]:
    attachments = [
        attachment for attachment in case.attachments if not attachment.superseded
    ]
    if len(attachments) < 2:
        return "missing_attachment", None
    if any(
        attachment.evidence is None
        or not attachment.evidence.blocks
        or bool(attachment.evidence.issues)
        for attachment in attachments
    ):
        return "unreadable", None
    si_count = sum(attachment.role == "SI" for attachment in attachments)
    bl_count = sum(attachment.role == "BL" for attachment in attachments)
    if si_count != 1 or bl_count != 1:
        return "wrong_doc_type", None
    return None, "comparison_missing"


def _selected_pair_ids(case: CaseView) -> set[str] | None:
    current = [a for a in case.attachments if not a.superseded]
    sis = [a.id for a in current if a.role == "SI" and a.evidence is not None]
    bls = [a.id for a in current if a.role == "BL" and a.evidence is not None]
    if len(sis) == 1 and len(bls) == 1:
        return {sis[0], bls[0]}
    return None


def _review_reasons(
    case: CaseView, unresolved: list[Finding]
) -> tuple[set[ReviewReason], bool]:
    reasons: set[ReviewReason] = set()
    unrepresentable = False
    selected = _selected_pair_ids(case)
    # An explicitly selected SI/BL pair is assessed using its own evidence.
    # Problems in unused attachments remain visible elsewhere as warnings and
    # do not decide the selected-pair export outcome. Without a selection the
    # handling stays conservative and every readable problem blocks.
    relevant = [
        attachment
        for attachment in case.attachments
        if not attachment.superseded and (selected is None or attachment.id in selected)
    ]
    if any(
        attachment.evidence is not None
        and any(normalize_issue(issue).blocking for issue in attachment.evidence.issues)
        for attachment in relevant
    ):
        reasons.add("unreadable")
    for finding in unresolved:
        for reading in (finding.si, finding.bl):
            if reading.issue in _MISSING_READING_ISSUES:
                reasons.add("missing_value")
            elif reading.issue is not None or reading.normalized is None:
                unrepresentable = True
    return reasons, unrepresentable


def _review_decision(
    case: CaseView,
    reviewer_assisted: bool,
    reviewer_actions: list[str],
    reason: ReviewReason,
) -> ExportDecision:
    return ExportDecision(
        prediction=Prediction(
            category="BL_COMPARISON",
            status="NEEDS_REVIEW",
            review_reason=reason,
            has_defect=False,
            defect_fields=[],
        ),
        diagnostics=ExportDiagnostics(
            reviewer_assisted=reviewer_assisted,
            reviewer_actions=reviewer_actions,
        ),
    )


def _blocked(
    reviewer_assisted: bool,
    reviewer_actions: list[str],
    blocker: ExportBlocker,
) -> ExportDecision:
    return ExportDecision(
        diagnostics=ExportDiagnostics(
            reviewer_assisted=reviewer_assisted,
            reviewer_actions=reviewer_actions,
            blockers=[blocker],
        )
    )
