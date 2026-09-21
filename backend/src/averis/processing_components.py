"""Explicit, versioned component bindings; no provider or parser implementation."""

from collections.abc import Callable
from dataclasses import dataclass

from averis.intelligence import Intelligence
from averis.pairing import PairingJudge
from averis.pipeline import DocumentReader


@dataclass(frozen=True)
class RunIntelligence:
    intelligence: Intelligence
    pairing_judge: PairingJudge | None = None


@dataclass(frozen=True)
class Components:
    """One selected implementation set, including all checkpoint identities.

    Versions describe behavior, not class names. Change the relevant identity
    whenever a provider, prompt, reader or acceptance policy changes.
    Factories construct budgeted clients per run, never during module import.
    """

    create_intelligence: Callable[[str, str], RunIntelligence]
    reader: DocumentReader
    reader_profile: tuple[str, str]
    extraction_profile: str
    classification_profile: tuple[str, str] | None
    acceptance_profile: str
    pairing_profile: str
    provider_time_reserve: float = 45
    classification_identity: str = ""

    def __post_init__(self) -> None:
        identities = (
            *self.reader_profile,
            self.extraction_profile,
            self.acceptance_profile,
            self.pairing_profile,
        )
        if any(not value.strip() for value in identities):
            raise ValueError("Component identities must be nonempty")
        if self.provider_time_reserve <= 0:
            raise ValueError("Provider time reserve must be positive")
