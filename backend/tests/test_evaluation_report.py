"""Offline evaluation reporting never turns abstentions into predictions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from scripts.report_evaluation import FIELDS, build_evaluation_report


def _row(
    category: str,
    *,
    status: str = "OK",
    defect_fields: list[str] | None = None,
) -> dict[str, object]:
    fields = defect_fields or []
    return {
        "category": category,
        "status": status,
        "review_reason": None,
        "has_defect": status == "MISMATCH",
        "defect_fields": fields,
    }


def _case(
    processing: str,
    accepted: str | None,
    suggested: str,
    *,
    report: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "processing": processing,
        "classification": {
            "accepted": accepted,
            "suggested": suggested,
        },
        "report": report,
    }


def _comparison_report(mismatches: set[str]) -> dict[str, object]:
    return {
        "pair_valid": True,
        "findings": [
            {
                "field": field,
                "outcome": "mismatch" if field in mismatches else "match",
            }
            for field in FIELDS
        ],
    }


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.fixture
def scorer_stub(tmp_path: Path) -> Path:
    """Exercise the external CLI boundary without an ignored organizer download."""
    path = tmp_path / "scorer_stub.py"
    path.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('predictions')\n"
        "p.add_argument('--ground-truth', required=True)\n"
        "p.add_argument('--json', action='store_true', required=True)\n"
        "a = p.parse_args()\n"
        "truth = json.loads(Path(a.ground_truth).read_text())\n"
        "predictions = json.loads(Path(a.predictions).read_text())\n"
        "assert set(predictions) <= set(truth)\n"
        "print(json.dumps({'n_emails': len(truth), 'test_double': True}))\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def evaluation_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    records = [
        {"source_id": "auto", "split": "development"},
        {"source_id": "assisted", "split": "development"},
        {"source_id": "blocked", "split": "development"},
        {"source_id": "failed", "split": "development"},
        {"source_id": "email_001", "split": "holdout"},
        {"source_id": "email_002", "split": "holdout"},
        {"source_id": "email_025", "split": "holdout"},
        {"source_id": "email_030", "split": "holdout"},
    ]
    manifest = {"schema_version": 1, "records": records}
    snapshot = {
        "manifest": manifest,
        "cases": {
            "auto": _case("completed", "GENERAL", "GENERAL"),
            "assisted": _case(
                "completed",
                "BL_COMPARISON",
                "BL_COMPARISON",
                report=_comparison_report({"shipper"}),
            ),
            "blocked": _case("completed", None, "SI_REQUEST"),
            "failed": _case("failed", "GENERAL", "GENERAL"),
            "email_030": _case("running", None, "SPAM"),
        },
        "case_metadata": {
            "auto": {"run_status": "completed", "run_outcome": "completed"},
            "assisted": {
                "run_status": "completed",
                "run_outcome": "completed",
            },
            "blocked": {"run_status": "completed", "run_outcome": "completed"},
            # The misleading execute return must not hide the persisted failure.
            "failed": {"run_status": "failed", "run_outcome": "completed"},
            "email_030": {"run_status": "running"},
        },
        "official_adapter": {
            "predictions": {
                "auto": _row("GENERAL"),
                "assisted": _row(
                    "BL_COMPARISON",
                    status="MISMATCH",
                    defect_fields=["shipper"],
                ),
            },
            "diagnostics": {
                "auto": {"reviewer_assisted": False, "blockers": []},
                "assisted": {"reviewer_assisted": True, "blockers": []},
                "blocked": {
                    "reviewer_assisted": False,
                    "blockers": ["category_unresolved"],
                },
                "failed": {
                    "reviewer_assisted": False,
                    "blockers": ["processing_incomplete"],
                },
                "email_030": {
                    "reviewer_assisted": False,
                    "blockers": ["processing_incomplete"],
                },
            },
        },
    }
    truth = {
        "auto": _row("GENERAL"),
        "assisted": _row("BL_COMPARISON", status="MISMATCH", defect_fields=["shipper"]),
        "blocked": _row("SI_REQUEST"),
        "failed": _row("GENERAL"),
        "email_001": _row("GENERAL"),
        "email_002": _row("GENERAL"),
        "email_025": _row("GENERAL"),
        "email_030": _row("SPAM"),
    }
    return (
        _write(tmp_path / "snapshot.json", snapshot),
        _write(tmp_path / "manifest.json", manifest),
        _write(tmp_path / "ground-truth.json", truth),
    )


def test_report_separates_automatic_assisted_blocked_and_failed(
    evaluation_files: tuple[Path, Path, Path], tmp_path: Path, scorer_stub: Path
) -> None:
    snapshot, manifest, truth = evaluation_files
    artifacts = tmp_path / "report"

    report = build_evaluation_report(
        snapshot,
        manifest,
        truth,
        artifacts,
        split="development",
        scorer_path=scorer_stub,
    )

    assert report["selection"]["selected_total"] == 4
    assert report["processing"] == {"terminal": 4, "failed": 1, "incomplete": 0}
    assert report["export"]["automatic"] == {"count": 1, "coverage": 0.25}
    assert report["export"]["reviewer_assisted"] == {
        "selected": 1,
        "exported": 1,
        "abstained": 0,
        "coverage": 0.25,
    }
    assert report["export"]["abstentions"] == 2
    assert report["export"]["blockers"] == {
        "category_unresolved": 1,
        "processing_incomplete": 1,
    }
    assert report["category"]["accepted"] == {
        "correct": 3,
        "count": 3,
        "accuracy": 1.0,
    }
    assert report["category"]["suggested"] == {
        "correct": 4,
        "count": 4,
        "accuracy": 1.0,
    }
    assert report["exact_rows"]["all_exported"]["correct"] == 2
    assert report["exact_rows"]["automatic"]["count"] == 1
    assert report["exact_rows"]["reviewer_assisted"]["count"] == 1
    assert report["field_comparison"]["all"]["representable_cases"] == 1
    assert report["field_comparison"]["all"]["exact_cases"] == 1
    assert report["field_comparison"]["automatic"]["representable_cases"] == 0
    assert report["field_comparison"]["reviewer_assisted"]["representable_cases"] == 1

    automatic = json.loads(
        (artifacts / "automatic-partial-predictions.json").read_text()
    )
    inclusive = json.loads(
        (artifacts / "reviewer-inclusive-partial-predictions.json").read_text()
    )
    assert set(automatic) == {"auto"}
    assert set(inclusive) == {"auto", "assisted"}
    assert "blocked" not in inclusive
    scorer = report["official_scorer_diagnostics"]
    assert scorer["is_full_submission"] is False
    assert "defaults missing prediction categories to GENERAL" in scorer["warning"]
    assert scorer["automatic_partial"]["missing_rows_defaulted_by_scorer"] == 3
    assert scorer["automatic_partial"]["result"]["n_emails"] == 4


def test_holdout_selection_applies_explicit_exclusions_and_keeps_incomplete(
    evaluation_files: tuple[Path, Path, Path], tmp_path: Path, scorer_stub: Path
) -> None:
    snapshot, manifest, truth = evaluation_files

    report = build_evaluation_report(
        snapshot,
        manifest,
        truth,
        tmp_path / "holdout-report",
        split="holdout",
        excluded_ids=("email_001", "email_002", "email_025"),
        scorer_path=scorer_stub,
    )

    assert report["selection"]["selected_ids"] == ["email_030"]
    assert report["selection"]["excluded_ids_applied"] == [
        "email_001",
        "email_002",
        "email_025",
    ]
    assert report["processing"] == {"terminal": 0, "failed": 0, "incomplete": 1}
    assert report["export"]["automatic"]["count"] == 0
    assert report["export"]["abstentions"] == 1
    assert (
        json.loads(
            (tmp_path / "holdout-report/automatic-partial-predictions.json").read_text()
        )
        == {}
    )


def test_blocked_row_with_prediction_is_rejected_instead_of_scored(
    evaluation_files: tuple[Path, Path, Path], tmp_path: Path, scorer_stub: Path
) -> None:
    snapshot_path, manifest, truth = evaluation_files
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["official_adapter"]["predictions"]["blocked"] = _row("SI_REQUEST")
    snapshot_path.write_text(json.dumps(snapshot))

    with pytest.raises(ValueError, match="Blocked row unexpectedly has a prediction"):
        build_evaluation_report(
            snapshot_path,
            manifest,
            truth,
            tmp_path / "invalid-report",
            split="development",
            scorer_path=scorer_stub,
        )
