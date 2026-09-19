"""Bounded evaluation preparation and execution; never imports ground truth."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete

from averis.budget import BudgetAuthority
from averis.config import Settings
from averis.dataset import data_root, load_emails
from averis.domain import CaseView
from averis.exporting import adapt_case
from averis.intake import import_email
from averis.intelligence import CLASSIFICATION_POLICY_VERSION, Intelligence
from averis.persistence import Budget, Case, Database, Outbox, Run, Workspace, utcnow
from averis.processing import Processor
from averis.storage import Storage

POLICY_VERSION = "averis-evaluation-v1"
MAX_IMPORTS_PER_WORKSPACE = 100
MAX_LIMIT = 1_000
HOLDOUT_MODULUS = 5
HOLDOUT_REMAINDER = 0
EVALUATION_NAMESPACE = "https://averis.example/evaluation/"

IntelligenceFactory = Callable[[str, str], Intelligence]


def _split(source_id: str) -> str:
    bucket = int(sha256(source_id.encode()).hexdigest()[:8], 16) % HOLDOUT_MODULUS
    return "holdout" if bucket == HOLDOUT_REMAINDER else "development"


def _workspace_id(selection: str, chunk: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"{EVALUATION_NAMESPACE}{selection}/{chunk}"))


def _require_evaluation_mode(settings: Settings, *, running: bool) -> None:
    if settings.env not in {"evaluation", "test"}:
        raise RuntimeError("Evaluation requires AVERIS_ENV=evaluation and a dedicated database")
    if settings.tasks_queue:
        raise RuntimeError("Evaluation requires an empty AVERIS_TASKS_QUEUE")
    if not running and settings.live_enabled:
        raise RuntimeError("Preparation refuses live inference")



def _policy(settings: Settings, selection: str, limit: int) -> dict[str, object]:
    return {
        "version": POLICY_VERSION,
        "frozen": True,
        "purpose": "development",
        "source_key": "email_id",
        "database_fingerprint": sha256(settings.database_url.encode()).hexdigest(),
        "split": {
            "algorithm": "sha256-email-id-modulo",
            "modulus": HOLDOUT_MODULUS,
            "holdout_remainder": HOLDOUT_REMAINDER,
        },
        "selected_split": selection,
        "limit": limit,
        "max_imports_per_workspace": MAX_IMPORTS_PER_WORKSPACE,
        "thresholds": {
            "category": settings.category_threshold,
            "spam": settings.spam_threshold,
            "field": settings.field_threshold,
        },
        "model": settings.jev_model,
        "classification_policy": CLASSIFICATION_POLICY_VERSION,
    }


def _safe_attachment(root: Path, attachment: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / attachment).resolve()
    if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
        raise ValueError(f"Attachment is outside the source bundle: {attachment}")
    return candidate


def _ensure_workspace(db: Database, workspace_id: str) -> None:
    with db.session() as session, session.begin():
        if session.get(Workspace, workspace_id) is None:
            session.add(Workspace(
                id=workspace_id,
                expires_at=utcnow() + timedelta(days=3650),
            ))


def _hold_run(db: Database, run_id: str) -> None:
    """Keep prepared runs out of normal outbox/reconciler delivery."""
    with db.session() as session, session.begin():
        run = session.get(Run, run_id)
        if run is not None and run.status == "queued":
            run.status = "held"
            session.execute(delete(Outbox).where(Outbox.run_id == run_id))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _case_snapshot(
    db: Database,
    records: list[dict[str, object]],
    run_outcomes: dict[str, str] | None = None,
) -> dict[str, object]:
    run_outcomes = run_outcomes or {}
    cases: dict[str, object] = {}
    case_metadata: dict[str, object] = {}
    predictions: dict[str, object] = {}
    diagnostics: dict[str, object] = {}
    blocker_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter(str(record["split"]) for record in records)
    completed = 0
    with db.session() as session:
        for record in records:
            source_id = str(record["source_id"])
            case_id = str(record["case_id"])
            row = session.get(Case, case_id)
            run = session.get(Run, str(record["run_id"])) if record.get("run_id") else None
            if row is None or row.workspace_id != record["workspace_id"]:
                blocker_counts["case_missing"] += 1
                diagnostics[source_id] = {"reviewer_assisted": False, "reviewer_actions": [], "blockers": []}
                continue
            view = CaseView.model_validate(row.state)
            cases[source_id] = view.model_dump(mode="json")
            case_metadata[source_id] = {
                "case_id": case_id,
                "workspace_id": row.workspace_id,
                "run_id": record.get("run_id"),
                "run_status": run.status if run else None,
                "run_outcome": run_outcomes.get(source_id),
            }
            decision = adapt_case(view)
            diagnostics[source_id] = decision.diagnostics.model_dump(mode="json")
            for blocker in decision.diagnostics.blockers:
                blocker_counts[blocker] += 1
            if decision.prediction is not None:
                predictions[source_id] = decision.prediction.model_dump(mode="json")
            if view.processing == "completed":
                completed += 1
    total = len(records)
    return {
        "schema_version": 1,
        "cases": cases,
        "case_metadata": case_metadata,
        "official_adapter": {
            "predictions": predictions,
            "diagnostics": diagnostics,
            "coverage": {
                "records": total,
                "case_snapshots": len(cases),
                "completed": completed,
                "predictions": len(predictions),
                "blocked": total - len(predictions),
                "by_split": dict(split_counts),
                "blockers": dict(sorted(blocker_counts.items())),
            },
        },
        "run_outcomes": run_outcomes,
    }


def _manifest_records(manifest: dict[str, object]) -> list[dict[str, object]]:
    value = manifest.get("records")
    if not isinstance(value, list):
        raise TypeError("Evaluation manifest records are invalid")
    records: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise TypeError("Evaluation manifest records are invalid")
        records.append(cast(dict[str, object], item))
    return records


def prepare_evaluation(
    settings: Settings,
    source_root: Path,
    output_dir: Path,
    *,
    limit: int = 100,
    split: str = "all",
    overwrite: bool = False,
) -> dict[str, object]:
    """Import a bounded source selection and write a no-provider snapshot."""
    _require_evaluation_mode(settings, running=False)
    if not overwrite and (output_dir / "manifest.json").exists():
        raise FileExistsError("Evaluation manifest exists; pass overwrite explicitly")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    if split not in {"all", "development", "holdout"}:
        raise ValueError("split must be all, development, or holdout")
    records = load_emails(source_root)
    selected = [record for record in records if split == "all" or _split(record["email_id"]) == split][:limit]
    if not selected:
        raise ValueError("No source emails match the selected split and limit")
    db = Database(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        db.create_local_schema()
    storage = Storage(settings)
    manifest_records: list[dict[str, object]] = []
    for offset in range(0, len(selected), MAX_IMPORTS_PER_WORKSPACE):
        workspace_id = _workspace_id(split, offset // MAX_IMPORTS_PER_WORKSPACE)
        _ensure_workspace(db, workspace_id)
        for source in selected[offset:offset + MAX_IMPORTS_PER_WORKSPACE]:
            attachments = [
                (Path(path).name, _safe_attachment(source_root, path).read_bytes())
                for path in source["attachments"]
            ]
            result = import_email(
                db,
                storage,
                workspace_id,
                "evaluation",
                source["subject"],
                source["from"],
                source["body"],
                attachments,
            )
            if result.run_id:
                _hold_run(db, result.run_id)
            manifest_records.append({
                "source_id": source["email_id"],
                "split": _split(source["email_id"]),
                "workspace_id": workspace_id,
                "case_id": result.view.id,
                "run_id": result.run_id or result.view.processing_run_id,
                "attachments": list(source["attachments"]),
            })
    manifest = {
        "schema_version": 1,
        "policy": _policy(settings, split, limit),
        "records": manifest_records,
    }
    _write_json(output_dir / "manifest.json", manifest)
    snapshot = _case_snapshot(db, manifest_records)
    snapshot["manifest"] = manifest
    _write_json(output_dir / "snapshot.json", snapshot)
    return snapshot


def _validate_manifest_policy(settings: Settings, manifest: dict[str, object]) -> None:
    policy_value = manifest.get("policy")
    if not isinstance(policy_value, dict):
        raise TypeError("Evaluation manifest policy is missing")
    policy = cast(dict[str, object], policy_value)
    if policy.get("version") != POLICY_VERSION or policy.get("frozen") is not True:
        raise ValueError("Evaluation manifest policy is not frozen")
    if policy.get("database_fingerprint") != sha256(settings.database_url.encode()).hexdigest():
        raise ValueError("Evaluation database does not match the frozen manifest")
    if policy.get("model") != settings.jev_model:
        raise ValueError("Jev model differs from the frozen manifest")
    if policy.get("classification_policy") != CLASSIFICATION_POLICY_VERSION:
        raise ValueError("Classification policy differs from the frozen manifest")
    thresholds_value = policy.get("thresholds")
    expected = {"category": settings.category_threshold, "spam": settings.spam_threshold, "field": settings.field_threshold}
    if not isinstance(thresholds_value, dict):
        raise TypeError("Inference thresholds are missing from the frozen manifest")
    thresholds = cast(dict[str, object], thresholds_value)
    if any(thresholds.get(key) != value for key, value in expected.items()):
        raise ValueError("Inference thresholds differ from the frozen manifest")


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation manifest not found: {path}; run prepare first")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("records"), list):
        raise ValueError("Unsupported evaluation manifest")
    return manifest


def run_evaluation(
    settings: Settings,
    output_dir: Path,
    *,
    split: str = "development",
    budget_database_url: str | None = None,
    intelligence_factory: IntelligenceFactory | None = None,
) -> dict[str, object]:
    """Execute existing manifest runs sequentially after the paid-call gate."""
    _require_evaluation_mode(settings, running=True)
    if not settings.live_enabled or not settings.budget_verified:
        raise RuntimeError("--run requires live_enabled and budget_verified")
    if settings.env == "evaluation" and not budget_database_url:
        raise RuntimeError("--run requires the authoritative budget database URL")
    if settings.env == "evaluation" and budget_database_url and not budget_database_url.startswith("postgresql"):
        raise RuntimeError("The authoritative budget database must be PostgreSQL")
    if split not in {"all", "development", "holdout"}:
        raise ValueError("split must be all, development, or holdout")
    db = Database(settings.database_url)
    budget_db = Database(budget_database_url or settings.database_url)
    with budget_db.session() as session:
        if session.get(Budget, 1) is None:
            raise RuntimeError("--run requires an existing verified budget ledger")
    manifest = _load_manifest(output_dir / "manifest.json")
    _validate_manifest_policy(settings, manifest)
    all_records = _manifest_records(manifest)
    records = [record for record in all_records if split == "all" or record["split"] == split]
    storage = Storage(settings)
    budget = BudgetAuthority(budget_db, settings)
    if intelligence_factory is None:
        from averis.intelligence import Jev

        def live_factory(run_id: str, purpose: str) -> Intelligence:
            return Jev(settings, budget, run_id, purpose)

        factory: IntelligenceFactory = live_factory
    else:
        factory = intelligence_factory
    processor = Processor(db, settings, storage, factory=factory)
    outcomes: dict[str, str] = {}

    def save_progress() -> dict[str, object]:
        snapshot = _case_snapshot(db, all_records, outcomes)
        snapshot["manifest"] = manifest
        snapshot["run_selection"] = split
        _write_json(output_dir / "snapshot.json", snapshot)
        _write_json(output_dir / "run-results.json", {
            "policy_version": cast(dict[str, object], manifest["policy"])["version"],
            "split": split,
            "outcomes": outcomes,
        })
        return snapshot

    for record in records:
        run_id = record.get("run_id")
        if not run_id:
            outcomes[str(record["source_id"])] = "missing_run"
            continue
        outcomes[str(record["source_id"])] = processor.execute(str(run_id))
        save_progress()
    return save_progress()


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Prepare or explicitly run bounded Averis evaluation")
    parser.add_argument("--data", type=Path, default=data_root())
    parser.add_argument("--output", type=Path, default=Path("outputs/evaluation"))
    parser.add_argument("--database-url", help="Dedicated evaluation database URL (defaults to output/evaluation.db)")
    parser.add_argument("--budget-database-url", help="Authoritative application budget database URL (required by --run)")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--split", choices=("all", "development", "holdout"), default="all")
    parser.add_argument("--run-split", choices=("all", "development", "holdout"), default="development")
    parser.add_argument("--run", action="store_true", help="Execute existing manifest runs; requires verified live budget")
    parser.add_argument("--dry-run", action="store_true", help="Prepare only; this is the default")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing prepared manifest")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.run and args.dry_run:
        parser.error("--run and --dry-run cannot be combined")
    if args.run and not args.database_url:
        parser.error("--run requires --database-url for the isolated evaluation case database")
    if args.run and not args.budget_database_url:
        parser.error("--run requires --budget-database-url for the authoritative application ledger")
    base_settings = Settings()
    database_url = args.database_url or f"sqlite:///{(args.output / 'evaluation.db').resolve().as_posix()}"
    settings = base_settings.model_copy(update={
        "env": "evaluation",
        "database_url": database_url,
        "tasks_queue": "",
        "live_enabled": base_settings.live_enabled if args.run else False,
    })
    if args.run:
        result = run_evaluation(
            settings,
            args.output,
            split=args.run_split,
            budget_database_url=args.budget_database_url,
        )
        mode = "run"
    else:
        result = prepare_evaluation(
            settings,
            args.data,
            args.output,
            limit=args.limit,
            split=args.split,
            overwrite=args.overwrite,
        )
        mode = "prepare"
    adapter = cast(dict[str, object], result["official_adapter"])
    coverage = adapter["coverage"]
    print(json.dumps({"mode": mode, "output": str(args.output), "coverage": coverage}, indent=2))


if __name__ == "__main__":
    main()
