"""Offline checks for bounded evaluation preparation and gated execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from averis.config import Settings
from averis.domain import Classification
from averis.persistence import Base, Budget, Database, Outbox, Run

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.evaluate import prepare_evaluation, run_evaluation


class DeterministicIntelligence:
    def classify(
        self, _subject: str, _body: str, *, attachment_filenames: tuple[str, ...] = ()
    ) -> Classification:
        return Classification(
            suggested="GENERAL",
            accepted="GENERAL",
            confidence=1,
            probabilities={"GENERAL": 1},
            source="model",
            model="offline-double",
        )


def make_bundle(root: Path, count: int = 3) -> Path:
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    for index in range(count):
        source_id = f"email_{index + 1:03d}"
        (inbox / f"{source_id}.json").write_text(
            json.dumps(
                {
                    "email_id": source_id,
                    "from": f"sender-{index}@example.test",
                    "subject": f"General request {index}",
                    "body": "Please confirm the delivery appointment.",
                    "attachments": [],
                }
            ),
            encoding="utf-8",
        )
    return root


@pytest.fixture
def evaluation(tmp_path):
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'evaluation.db'}",
        tasks_queue="",
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
    )
    return settings, make_bundle(tmp_path / "bundle"), tmp_path / "out"


def test_prepare_is_source_keyed_and_does_not_execute(evaluation):
    settings, source_root, output = evaluation

    snapshot = prepare_evaluation(settings, source_root, output, limit=3)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert [record["source_id"] for record in manifest["records"]] == [
        "email_001",
        "email_002",
        "email_003",
    ]
    assert {record["case_id"] for record in manifest["records"]}
    assert set(snapshot["cases"]) == {"email_001", "email_002", "email_003"}
    assert snapshot["official_adapter"]["coverage"]["completed"] == 0
    assert snapshot["official_adapter"]["coverage"]["blockers"] == {
        "processing_incomplete": 3,
    }
    db = Database(settings.database_url)
    with db.session() as session:
        assert {run.status for run in session.query(Run).all()} == {"held"}
        assert session.query(Outbox).count() == 0


def test_run_requires_verified_ledger(evaluation):
    settings, source_root, output = evaluation
    prepare_evaluation(settings, source_root, output, limit=1)

    settings.live_enabled = True
    settings.budget_verified = True
    settings.env = "evaluation"
    with pytest.raises(RuntimeError, match="authoritative budget database"):
        run_evaluation(
            settings,
            output,
            intelligence_factory=lambda *_: DeterministicIntelligence(),
        )


def test_gated_run_uses_offline_double_and_writes_predictions(evaluation):
    settings, source_root, output = evaluation
    prepare_evaluation(settings, source_root, output, limit=3)
    settings.live_enabled = True
    settings.budget_verified = True
    budget_url = f"sqlite:///{output.parent / 'authoritative-budget.db'}"
    budget_db = Database(budget_url)
    Base.metadata.create_all(budget_db.engine)
    with budget_db.session() as session, session.begin():
        session.add(Budget(id=1, prior_spend=0, development=0, demo=0))
    case_db = Database(settings.database_url)
    with case_db.session() as session:
        assert session.get(Budget, 1) is None

    snapshot = run_evaluation(
        settings,
        output,
        split="all",
        budget_database_url=budget_url,
        intelligence_factory=lambda *_: DeterministicIntelligence(),
    )

    assert snapshot["run_outcomes"] == {
        "email_001": "completed",
        "email_002": "completed",
        "email_003": "completed",
    }
    assert set(snapshot["official_adapter"]["predictions"]) == {
        "email_001",
        "email_002",
        "email_003",
    }
    assert snapshot["official_adapter"]["coverage"]["completed"] == 3


def test_changed_classification_policy_cannot_reuse_frozen_manifest(evaluation):
    from scripts.evaluate import _validate_manifest_policy

    settings, source_root, output = evaluation
    prepare_evaluation(settings, source_root, output, limit=1)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["policy"]["classification_policy"] = "older-policy"
    with pytest.raises(ValueError, match="Classification policy differs"):
        _validate_manifest_policy(settings, manifest)


def test_interruption_preserves_completed_evaluation_progress(evaluation, monkeypatch):
    from scripts.evaluate import Processor

    settings, source_root, output = evaluation
    prepare_evaluation(settings, source_root, output, limit=3)
    settings.live_enabled = True
    settings.budget_verified = True
    budget_url = f"sqlite:///{output.parent / 'budget.db'}"
    budget_db = Database(budget_url)
    Base.metadata.create_all(budget_db.engine)
    with budget_db.session() as session, session.begin():
        session.add(Budget(id=1, prior_spend=0, development=0, demo=0))
    execute = Processor.execute
    calls = 0

    def interrupt_second(processor, run_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return execute(processor, run_id)

    monkeypatch.setattr(Processor, "execute", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        run_evaluation(
            settings,
            output,
            split="all",
            budget_database_url=budget_url,
            intelligence_factory=lambda *_: DeterministicIntelligence(),
        )
    snapshot = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["official_adapter"]["coverage"]["completed"] == 1
    assert snapshot["run_outcomes"] == {"email_001": "completed"}
