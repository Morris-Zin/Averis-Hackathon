"""Jev provider implementation behind the shared intelligence boundary.

This module owns Jev prompts, question construction, SDK decoding, request
limits and usage interpretation. Provider-neutral contracts, proposal
validation and the acceptance policy live in :mod:`averis.intelligence`.

Confidence is distribution concentration, not measured accuracy; preserve
uncertainty and source evidence. See https://docs.typesafe.ai/confidence.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast, get_args

from typesafe_sdk import (
    Choice,
    ChoiceAnswer,
    JSONContent,
    RetryPolicy,
    SystemOneResponse,
    TypeSafeClient,
    TypeSafeError,
)

from averis.budget import BudgetAuthority, BudgetUnavailable
from averis.config import Settings
from averis.contracts import FIELDS, Category, Field
from averis.domain import Classification, DocumentEvidence, Reading
from averis.intelligence import (
    MAX_CLASSIFICATION_DOCUMENTS,
    AttachmentLoader,
    ExtractionResult,
    Intelligence,
    ProviderCapacityError,
    ProviderPermanentError,
    validate_extraction_proposal,
)
from averis.jev_classification import prepare_email
from averis.jev_prompts import DEFAULT_PROMPTS, JevPrompts
from averis.numeric_evidence import (
    bind_numeric_selection,
    can_repair,
    numeric_candidates,
)
from averis.pairing import PairingProposal, PairingRequest
from averis.source_regions import complete_party_selection
from averis.timing import measure, timed
from averis.verification import normalize, reading_from_evidence
from averis.versions import (
    ACCEPTANCE_PROFILE,
    CLASSIFICATION_POLICY_VERSION,
    CLASSIFICATION_PROMPT_VERSION,
    EXTRACTION_PROMPT_VERSION,
)

_TYPED_FIELDS = cast(tuple[Field, ...], FIELDS)
_CATEGORIES = cast(tuple[Category, ...], get_args(Category))
JEV_MODEL_DEFAULT = "jev-1.13.0"


def validate_choice_answer(
    answer: ChoiceAnswer,
    allowed: frozenset[str],
) -> tuple[str, float, dict[str, float]]:
    """Reject malformed provider state rather than converting it into a decision."""

    if answer.choice not in allowed:
        raise ValueError(f"Invalid choice response: {answer.choice}")
    if not math.isfinite(answer.confidence) or not 0 <= answer.confidence <= 1:
        raise ValueError("Invalid choice confidence")
    probabilities = dict(answer.probabilities)
    if set(probabilities) != set(allowed):
        raise ValueError("Choice probabilities do not match the requested criteria")
    if any(
        not math.isfinite(probability) or not 0 <= probability <= 1
        for probability in probabilities.values()
    ):
        raise ValueError("Invalid choice probabilities")
    if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02):
        raise ValueError("Choice probabilities do not sum to one")
    if probabilities[answer.choice] < max(probabilities.values()):
        raise ValueError("Selected choice is not the highest-probability criterion")
    return answer.choice, answer.confidence, probabilities


def estimate_request(payload_bytes: int, questions: int) -> tuple[int, int]:
    """Validate the bounded envelope and return conservative token bounds.

    The ledger never estimates provider usage; this adapter supplies validated
    conservative bounds and the ledger reserves their cost atomically.
    """

    if not 0 <= payload_bytes <= 100_000 or not 1 <= questions <= 10:
        raise BudgetUnavailable("Request exceeds the bounded inference envelope")
    input_bound = payload_bytes * (questions + 1) * 2 + 32768
    output_bound = 32768
    return input_bound, output_bound


@dataclass(frozen=True, slots=True)
class JevMetadata:
    provider: str = "typesafe-jev"
    model: str = JEV_MODEL_DEFAULT
    classification_prompt: str = CLASSIFICATION_PROMPT_VERSION
    extraction_prompt: str = EXTRACTION_PROMPT_VERSION
    acceptance_profile: str = ACCEPTANCE_PROFILE


class Jev:
    """Jev provider implementing the shared Intelligence protocol."""

    def __init__(
        self,
        settings: Settings,
        budget: BudgetAuthority,
        run_id: str,
        purpose: str,
        prompts: JevPrompts = DEFAULT_PROMPTS,
    ) -> None:
        self.prompts = prompts
        self.settings = settings
        self.budget = budget
        self.run_id = run_id
        self.purpose = purpose
        self.metadata = JevMetadata(model=settings.jev_model)

    @timed("jev_request")
    def _ask(
        self,
        state: Mapping[str, object],
        questions: Mapping[str, Choice],
    ) -> SystemOneResponse:
        payload_size = len(
            json.dumps(
                {
                    "state": state,
                    "questions": {key: str(value) for key, value in questions.items()},
                },
                ensure_ascii=False,
            ).encode()
        )
        # Validated conservative estimates go to the shared ledger; the ledger
        # never owns provider estimation.
        input_bound, output_bound = estimate_request(payload_size, len(questions))
        # Client construction validates local configuration; it makes no API call.
        # Do not reserve money for a request that cannot even be constructed.
        client_context = TypeSafeClient(
            api_key=self.settings.typesafe_api_key.get_secret_value() or None,
            retry=RetryPolicy(max_retries=0),
            timeout=40,
        )
        with client_context as client:
            estimator = getattr(self.budget, "reserve_estimate", None)
            reservation_id: str
            if callable(estimator):
                raw_reservation = estimator(
                    self.run_id, self.purpose, input_bound, output_bound
                )
                assert isinstance(raw_reservation, str)
                reservation_id = raw_reservation
            else:
                # Legacy doubles expose only the envelope-based reserve.
                raw_legacy = self.budget.reserve(
                    self.run_id, self.purpose, payload_size, len(questions)
                )
                assert isinstance(raw_legacy, str)
                reservation_id = raw_legacy
            try:
                with measure("http"):
                    response = client.system_one(  # pyright: ignore[reportUnknownMemberType]
                        state=cast(JSONContent, state),
                        questions=questions,
                        model=self.settings.jev_model,
                    )
            except Exception:
                self.budget.retain_for_reconciliation(
                    reservation_id,
                    "Provider call did not return a validated response",
                )
                # Preserve the original failure for the shared vocabulary:
                # permanent config/malformed stops visibly (ValueError), transient
                # transport/service uses bounded retries, capacity becomes a
                # visible unsupported-input outcome via the caller.
                raise
        try:
            request_id = response.request_id
        except TypeSafeError:
            request_id = None
        self.budget.settle_success(
            reservation_id,
            response.usage.input_tokens,
            response.usage.output_tokens,
            request_id,
        )
        return response

    def judge_pair(self, request: PairingRequest) -> PairingProposal:
        criteria: dict[str, object] = {
            candidate.id: candidate.criteria() for candidate in request.candidates
        }
        criteria["NONE"] = (
            "No single supported shipment-identity reference establishes this pair, or conflicting identity / uncertainty."
        )
        response = self._ask(
            request.state,
            {
                "pair_reference": Choice(
                    instructions=self.prompts.pairing,
                    criteria=cast(Mapping[str, JSONContent | None], criteria),
                )
            },
        )
        answer = response.choices.get("pair_reference")
        if answer is None:
            raise ProviderPermanentError("Missing pairing response")
        selected, confidence, probabilities = validate_choice_answer(
            answer, frozenset(criteria)
        )
        try:
            request_id = response.request_id
        except TypeSafeError:
            request_id = None
        return PairingProposal(
            selected=selected,
            confidence=confidence,
            probabilities=probabilities,
            model=self.settings.jev_model,
            request_id=request_id,
        )

    def classify(
        self,
        subject: str,
        body: str,
        *,
        attachment_filenames: tuple[str, ...] = (),
        load_attachment_previews: AttachmentLoader | None = None,
    ) -> Classification:
        """Classify intent; consult names only for General or uncertain decisions.

        Filenames are context, never document evidence. Accepted specific categories
        bypass the supplement. Only an uncertain supplement requests document context;
        callers without a document loader retain the filename-only behaviour.
        Provider failures remain visible through the ordinary processing retry path.
        """
        state = prepare_email(subject, body)
        baseline = self._classify_state(state, self.prompts.classification)
        if not attachment_filenames or (
            baseline.accepted is not None and baseline.suggested != "GENERAL"
        ):
            return baseline
        supplemented = self._classify_state(
            {**state, "attachment_filenames": list(attachment_filenames)},
            self.prompts.filename_classification,
        )
        if supplemented.accepted is not None:
            return supplemented
        if load_attachment_previews is None:
            return baseline
        # Uncertainty is now explicit: do not restore a confident General label
        # after conflicting evidence. Unsupported preview scope needs human review.
        if len(attachment_filenames) > MAX_CLASSIFICATION_DOCUMENTS:
            return supplemented
        previews = load_attachment_previews()
        if not previews or any(not preview.text.strip() for preview in previews):
            return supplemented
        return self._classify_state(
            {
                **state,
                "attachment_previews": [
                    {"filename": p.filename, "text": p.text, "truncated": p.truncated}
                    for p in previews
                ],
            },
            self.prompts.content_classification,
        )

    def _classify_state(
        self, state: Mapping[str, object], question: Choice
    ) -> Classification:
        response = self._ask(
            state,
            {"category": question},
        )
        answer = response.choices.get("category")
        if answer is None:
            raise ProviderPermanentError("Missing category response")
        try:
            category_text, confidence, probabilities = validate_choice_answer(
                answer, frozenset(_CATEGORIES)
            )
        except ValueError as exc:
            raise ProviderPermanentError(str(exc)) from exc
        category = cast(Category, category_text)
        threshold = (
            self.settings.spam_threshold
            if category == "SPAM"
            else self.settings.category_threshold
        )
        return Classification(
            suggested=category,
            accepted=category if confidence >= threshold else None,
            confidence=confidence,
            probabilities=probabilities,
            model=self.settings.jev_model,
            policy_version=CLASSIFICATION_POLICY_VERSION,
        )

    def extract(self, document: DocumentEvidence) -> ExtractionResult:
        if len(document.blocks) > 240:
            raise ProviderCapacityError(
                "Too many evidence candidates; manual review required"
            )
        criteria = {block.id: block.text for block in document.blocks}
        criteria["NONE"] = "The complete value is absent or ambiguous"
        questions = {name: self.prompts.field(name, criteria) for name in _TYPED_FIELDS}
        questions["role"] = self.prompts.document_role
        response = self._ask(
            {"blocks": {block.id: block.text for block in document.blocks}},
            questions,
        )
        role_answer = response.choices.get("role")
        if role_answer is None:
            raise ProviderPermanentError("Missing document role response")
        try:
            role, role_confidence, _ = validate_choice_answer(
                role_answer, frozenset({"SI", "BL", "unknown"})
            )
        except ValueError as exc:
            raise ProviderPermanentError(str(exc)) from exc

        candidate_ids = frozenset(criteria)
        selections: dict[str, tuple[str, float]] = {}
        for name in _TYPED_FIELDS:
            answer = response.choices.get(name)
            if answer is None:
                raise ProviderPermanentError(f"Missing field response: {name}")
            try:
                selected, confidence, _ = validate_choice_answer(answer, candidate_ids)
            except ValueError as exc:
                raise ProviderPermanentError(str(exc)) from exc
            selections[name] = (selected, confidence)
        # Shared boundary validates proposals, applies the acceptance policy,
        # copies source text and produces validated domain readings. Providers
        # cannot supply authoritative normalized values or comparison outcomes.
        try:
            validated = validate_extraction_proposal(
                document.document_id, selections, candidate_ids
            )
        except ValueError as exc:
            raise ProviderPermanentError(str(exc)) from exc
        readings: dict[str, Reading] = {}
        for name in _TYPED_FIELDS:
            selected, confidence = validated[name]
            readings[name] = reading_from_evidence(
                name,
                document,
                complete_party_selection(document, name, selected),
                confidence,
                self.settings.field_threshold,
            )
        return ExtractionResult(
            role=role if role_confidence >= 0.8 else "unknown",
            role_confidence=role_confidence,
            fields=readings,
        )

    def repair_numeric(
        self, document: DocumentEvidence, readings: dict[str, Reading]
    ) -> dict[str, Reading]:
        repairable = {
            name
            for name, reading in readings.items()
            if can_repair(document, reading, self.settings.field_threshold)
        }
        if not repairable:
            return readings
        candidates = numeric_candidates(document)
        questions: dict[str, Choice] = {}
        allowed: dict[str, frozenset[str]] = {}
        for field in ("container_count", "gross_weight_kg"):
            criteria: dict[str, object] = {
                item.id: {
                    "block_id": item.selection.block_id,
                    "value": item.value,
                    "line": item.line,
                    "unit": item.unit,
                }
                for item in candidates
                if normalize(cast(Field, field), item.source_value) is not None
            }
            criteria["NONE"] = (
                "The field cannot be reliably read from these candidates."
            )
            if len(criteria) > 1:
                allowed[field] = frozenset(criteria)
                questions[field] = Choice(
                    instructions=self.prompts.numeric.format(field=field),
                    criteria=cast(Mapping[str, JSONContent | None], criteria),
                )
        if not questions:
            return readings
        try:
            response = self._ask(
                {
                    "blocks": [
                        {"id": block.id, "text": block.text}
                        for block in document.blocks
                    ]
                },
                questions,
            )
            repaired = dict(readings)
            for name in sorted(repairable & questions.keys()):
                answer = response.choices.get(name)
                if answer is None:
                    raise ProviderPermanentError("Missing numeric selection response")
                selected, confidence, _ = validate_choice_answer(answer, allowed[name])
                if selected == "NONE" or confidence < self.settings.field_threshold:
                    continue
                candidate = next(item for item in candidates if item.id == selected)
                repaired[name] = bind_numeric_selection(
                    document,
                    cast(Field, name),
                    candidate.selection,
                    confidence,
                    self.settings.jev_model,
                    self.settings.field_threshold,
                )
            return repaired
        except (TypeSafeError, BudgetUnavailable, ProviderPermanentError, ValueError):
            # Optional assistance cannot erase the original uncertainty or useful fields.
            return {
                name: reading.model_copy(
                    update={"assistance_error": "numeric_provider_unavailable"}
                )
                if name in repairable
                else reading
                for name, reading in readings.items()
            }


def validate_answer(
    answer: ChoiceAnswer, allowed: frozenset[str]
) -> tuple[str, float, dict[str, float]]:
    """Jev SDK decoding owned here; shared validation lives in intelligence."""

    if answer.choice not in allowed:
        raise ProviderPermanentError(f"Invalid choice response: {answer.choice}")
    if not math.isfinite(answer.confidence) or not 0 <= answer.confidence <= 1:
        raise ProviderPermanentError("Invalid choice confidence")
    probabilities = dict(answer.probabilities)
    if set(probabilities) != set(allowed):
        raise ProviderPermanentError("Choice probabilities do not match criteria")
    return answer.choice, answer.confidence, probabilities


class NumericAssistedIntelligence:
    """Repair unresolved native numeric readings after the existing providers."""

    def __init__(self, primary: Intelligence, judge: Jev):
        self._primary = primary
        self._judge = judge

    def classify(
        self,
        subject: str,
        body: str,
        *,
        attachment_filenames: tuple[str, ...] = (),
        load_attachment_previews: AttachmentLoader | None = None,
    ) -> Classification:
        return self._primary.classify(
            subject,
            body,
            attachment_filenames=attachment_filenames,
            load_attachment_previews=load_attachment_previews,
        )

    def extract(self, document: DocumentEvidence) -> ExtractionResult:
        original = self._primary.extract(document)
        return ExtractionResult(
            original.role,
            original.role_confidence,
            self._judge.repair_numeric(document, original.fields),
        )
