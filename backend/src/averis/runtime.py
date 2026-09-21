"""Application composition: select concrete readers and budgeted AI adapters here."""

import hashlib
import json
from collections.abc import Callable

from averis.budget import BudgetAuthority
from averis.components import Components, RunIntelligence
from averis.config import Settings
from averis.deepseek import MODEL, PROFILE, PROMPT, AssistedIntelligence
from averis.documents import read_document_bounded
from averis.fields import FIELD_MEANINGS
from averis.intelligence import Intelligence
from averis.jev import Jev, NumericAssistedIntelligence
from averis.jev_prompts import DEFAULT_PROMPTS, JevPrompts
from averis.persistence import Database
from averis.pipeline import DocumentReader
from averis.versions import (
    ACCEPTANCE_PROFILE,
    CLASSIFICATION_POLICY_VERSION,
    EXTRACTION_PROMPT_VERSION,
    OCR_PROFILE,
    READER_VERSION,
)


def application_components(
    db: Database, settings: Settings, *, prompts: JevPrompts = DEFAULT_PROMPTS
) -> Components:
    """Build the shipped adapter combination without executing any paid calls."""

    def create(run_id: str, purpose: str) -> RunIntelligence:
        budget = BudgetAuthority(db, settings)
        primary = Jev(settings, budget, run_id, purpose, prompts)
        intelligence: Intelligence = primary
        if settings.deepseek_fields_enabled:
            intelligence = AssistedIntelligence(
                primary,
                settings.deepseek_api_key.get_secret_value(),
                budget,
                run_id,
                purpose,
            )
        return RunIntelligence(
            NumericAssistedIntelligence(intelligence, primary), primary.judge_pair
        )

    identity = [
        "typesafe-jev",
        settings.jev_model,
        EXTRACTION_PROMPT_VERSION,
        str(settings.field_threshold),
        prompts.numeric,
        prompts.document_role.model_dump_json(),
        *[prompts.field(name, {}).model_dump_json() for name in FIELD_MEANINGS],
    ]
    if settings.deepseek_fields_enabled:
        identity.extend(["deepseek", MODEL, PROFILE, PROMPT])
    extraction = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    pairing = hashlib.sha256(
        json.dumps([settings.jev_model, prompts.pairing]).encode()
    ).hexdigest()
    return Components(
        create,
        read_document_bounded,
        (READER_VERSION, OCR_PROFILE),
        extraction,
        (settings.jev_model, CLASSIFICATION_POLICY_VERSION),
        PROFILE if settings.deepseek_fields_enabled else ACCEPTANCE_PROFILE,
        pairing,
        140 if settings.deepseek_fields_enabled else 45,
        hashlib.sha256(
            json.dumps(
                [
                    settings.jev_model,
                    CLASSIFICATION_POLICY_VERSION,
                    settings.category_threshold,
                    settings.spam_threshold,
                    *[
                        q.model_dump_json()
                        for q in (
                            prompts.classification,
                            prompts.filename_classification,
                            prompts.content_classification,
                        )
                    ],
                ]
            ).encode()
        ).hexdigest(),
    )


def injected_components(
    factory: Callable[[str, str], Intelligence], reader: DocumentReader
) -> Components:
    """Legacy offline-test seam; replacements must use explicit Components.

    Preserve fixture checkpoint compatibility. This helper is not the production
    plugin interface and never attaches a hidden paid pairing judge.
    """
    return Components(
        lambda run, purpose: RunIntelligence(factory(run, purpose)),
        reader,
        (READER_VERSION, OCR_PROFILE),
        "legacy-unspecified",
        None,
        ACCEPTANCE_PROFILE,
        "legacy-unspecified",
        classification_identity="legacy-unspecified",
    )
