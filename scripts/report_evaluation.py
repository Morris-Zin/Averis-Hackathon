"""Offline evaluation diagnostics over explicit, local evaluation artifacts.

This module is intentionally outside ``src/averis``. Ground truth is an
evaluation input and must never become a runtime inference dependency.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCORER = ROOT / "resources/official/docker/server/score_cli.py"
FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)
TERMINAL_PROCESSING = frozenset({"completed", "failed"})
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "superseded"})

JsonObject = dict[str, object]


def _load_json_object(path: Path, label: str) -> JsonObject:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    return _as_object(value, label)


def _as_object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    raw = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in raw):
        raise TypeError(f"{label} must be a JSON object")
    return cast(JsonObject, raw)


def _as_object_map(value: object, label: str) -> dict[str, JsonObject]:
    source = _as_object(value, label)
    result: dict[str, JsonObject] = {}
    for key, item in source.items():
        result[key] = _as_object(item, f"{label}.{key}")
    return result


def _manifest_records(manifest: JsonObject) -> list[JsonObject]:
    value = manifest.get("records")
    if not isinstance(value, list):
        raise TypeError("manifest.records must be a JSON array")
    records: list[JsonObject] = []
    seen: set[str] = set()
    for index, item in enumerate(cast(list[object], value)):
        record = _as_object(item, f"manifest.records[{index}]")
        source_id = record.get("source_id")
        split = record.get("split")
        if not isinstance(source_id, str) or not source_id:
            raise TypeError(f"manifest.records[{index}].source_id must be a string")
        if source_id in seen:
            raise ValueError(f"Duplicate manifest source_id: {source_id}")
        if split not in {"development", "holdout"}:
            raise ValueError(f"Invalid manifest split for {source_id}: {split}")
        seen.add(source_id)
        records.append(record)
    return records


def _metric(correct: int, count: int) -> JsonObject:
    return {
        "correct": correct,
        "count": count,
        "accuracy": correct / count if count else None,
    }


def _prediction_signature(row: JsonObject) -> tuple[object, ...]:
    fields = row.get("defect_fields")
    if not isinstance(fields, list):
        raise TypeError("Prediction defect_fields must be a list of strings")
    raw_fields = cast(list[object], fields)
    if any(not isinstance(field, str) for field in raw_fields):
        raise TypeError("Prediction defect_fields must be a list of strings")
    return (
        row.get("category"),
        row.get("status"),
        row.get("review_reason"),
        row.get("has_defect"),
        tuple(sorted(cast(list[str], fields))),
    )


def _reviewer_assisted(diagnostic: JsonObject) -> bool:
    value = diagnostic.get("reviewer_assisted", False)
    if not isinstance(value, bool):
        raise TypeError("diagnostic.reviewer_assisted must be boolean")
    return value


def _blockers(diagnostic: JsonObject) -> list[str]:
    value = diagnostic.get("blockers", [])
    if not isinstance(value, list):
        raise TypeError("diagnostic.blockers must be a list of strings")
    raw = cast(list[object], value)
    if any(not isinstance(item, str) for item in raw):
        raise TypeError("diagnostic.blockers must be a list of strings")
    return cast(list[str], value)


def _category_metrics(
    selected_ids: Sequence[str],
    cases: Mapping[str, JsonObject],
    truth: Mapping[str, JsonObject],
) -> JsonObject:
    accepted_correct = accepted_count = 0
    suggested_correct = suggested_count = 0
    for source_id in selected_ids:
        case = cases.get(source_id)
        if case is None:
            continue
        classification_value = case.get("classification")
        if classification_value is None:
            continue
        classification = _as_object(
            classification_value, f"cases.{source_id}.classification"
        )
        expected = truth[source_id].get("category")
        accepted = classification.get("accepted")
        if isinstance(accepted, str):
            accepted_count += 1
            accepted_correct += int(accepted == expected)
        suggested = classification.get("suggested")
        if isinstance(suggested, str):
            suggested_count += 1
            suggested_correct += int(suggested == expected)
    return {
        "accepted": _metric(accepted_correct, accepted_count),
        "suggested": _metric(suggested_correct, suggested_count),
    }


def _processing_metrics(
    selected_ids: Sequence[str],
    cases: Mapping[str, JsonObject],
    metadata: Mapping[str, JsonObject],
) -> JsonObject:
    terminal = failed = incomplete = 0
    for source_id in selected_ids:
        case = cases.get(source_id)
        meta = metadata.get(source_id, {})
        processing = case.get("processing") if case is not None else None
        run_status = meta.get("run_status")
        is_failed = processing == "failed" or run_status == "failed"
        is_terminal = (
            processing in TERMINAL_PROCESSING or run_status in TERMINAL_RUN_STATUSES
        )
        terminal += int(is_terminal)
        failed += int(is_failed)
        incomplete += int(not is_terminal)
    return {"terminal": terminal, "failed": failed, "incomplete": incomplete}


def _new_field_metrics() -> dict[str, object]:
    return {
        "representable_cases": 0,
        "exact_cases": 0,
        "outcomes": {"match": 0, "mismatch": 0, "unresolved": 0},
        "fields": {"correct": 0, "count": 0, "accuracy": None},
    }


def _record_field_comparison(
    target: dict[str, object], outcomes: dict[str, str], expected_mismatches: set[str]
) -> None:
    target["representable_cases"] = cast(int, target["representable_cases"]) + 1
    outcome_counts = cast(dict[str, int], target["outcomes"])
    correct = 0
    for field in FIELDS:
        outcome = outcomes[field]
        outcome_counts[outcome] += 1
        expected = "mismatch" if field in expected_mismatches else "match"
        correct += int(outcome == expected)
    if correct == len(FIELDS):
        target["exact_cases"] = cast(int, target["exact_cases"]) + 1
    fields = cast(dict[str, object], target["fields"])
    fields["correct"] = cast(int, fields["correct"]) + correct
    fields["count"] = cast(int, fields["count"]) + len(FIELDS)


def _field_metrics(
    selected_ids: Sequence[str],
    cases: Mapping[str, JsonObject],
    diagnostics: Mapping[str, JsonObject],
    truth: Mapping[str, JsonObject],
) -> JsonObject:
    groups = {
        "all": _new_field_metrics(),
        "automatic": _new_field_metrics(),
        "reviewer_assisted": _new_field_metrics(),
    }
    for source_id in selected_ids:
        expected = truth[source_id]
        if expected.get("category") != "BL_COMPARISON" or expected.get(
            "status"
        ) not in {
            "OK",
            "MISMATCH",
        }:
            continue
        case = cases.get(source_id)
        if case is None or not isinstance(case.get("report"), dict):
            continue
        report = _as_object(case["report"], f"cases.{source_id}.report")
        if report.get("pair_valid") is not True:
            continue
        findings_value = report.get("findings")
        if not isinstance(findings_value, list):
            continue
        outcomes: dict[str, str] = {}
        for item in cast(list[object], findings_value):
            finding = _as_object(item, f"cases.{source_id}.report.finding")
            field = finding.get("field")
            outcome = finding.get("outcome")
            if isinstance(field, str) and outcome in {
                "match",
                "mismatch",
                "unresolved",
            }:
                if field in outcomes:
                    outcomes = {}
                    break
                outcomes[field] = cast(str, outcome)
        if set(outcomes) != set(FIELDS):
            continue
        defect_fields = expected.get("defect_fields")
        if not isinstance(defect_fields, list):
            raise TypeError(f"ground_truth.{source_id}.defect_fields is invalid")
        raw_defect_fields = cast(list[object], defect_fields)
        if any(not isinstance(field, str) for field in raw_defect_fields):
            raise TypeError(f"ground_truth.{source_id}.defect_fields is invalid")
        mismatches = set(cast(list[str], raw_defect_fields))
        _record_field_comparison(groups["all"], outcomes, mismatches)
        diagnostic = diagnostics.get(source_id)
        if diagnostic is None:
            # The comparison itself is still representable, but a missing
            # adapter diagnostic cannot be truthfully assigned to either
            # automatic or reviewer-assisted output.
            continue
        group = "reviewer_assisted" if _reviewer_assisted(diagnostic) else "automatic"
        _record_field_comparison(groups[group], outcomes, mismatches)
    for target in groups.values():
        fields = cast(dict[str, object], target["fields"])
        count = cast(int, fields["count"])
        fields["accuracy"] = cast(int, fields["correct"]) / count if count else None
    return cast(JsonObject, groups)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _run_official_scorer(
    scorer: Path, truth_path: Path, predictions_path: Path
) -> JsonObject:
    if not scorer.is_file():
        raise FileNotFoundError(f"Official scorer not found: {scorer}")
    completed = subprocess.run(
        [
            sys.executable,
            str(scorer.resolve()),
            str(predictions_path.resolve()),
            "--ground-truth",
            str(truth_path.resolve()),
            "--json",
        ],
        cwd=scorer.resolve().parent,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    value = cast(object, json.loads(completed.stdout))
    return _as_object(value, "official scorer output")


def build_evaluation_report(
    snapshot_path: Path,
    manifest_path: Path,
    ground_truth_path: Path,
    artifact_dir: Path,
    *,
    split: str = "development",
    excluded_ids: Iterable[str] = (),
    scorer_path: Path = DEFAULT_SCORER,
) -> JsonObject:
    """Build source-keyed diagnostics and run the unchanged official scorer.

    The scorer receives filtered truth plus partial prediction objects. Its
    missing-row fallback is retained unchanged and prominently labelled in the
    returned report; this function never fills an abstained row.
    """

    if split not in {"development", "holdout", "all"}:
        raise ValueError("split must be development, holdout, or all")
    snapshot = _load_json_object(snapshot_path, "snapshot")
    manifest = _load_json_object(manifest_path, "manifest")
    truth_all = _as_object_map(
        _load_json_object(ground_truth_path, "ground truth"), "ground_truth"
    )
    records = _manifest_records(manifest)
    record_splits = {
        cast(str, record["source_id"]): cast(str, record["split"]) for record in records
    }

    embedded = snapshot.get("manifest")
    if embedded is not None:
        embedded_records = _manifest_records(_as_object(embedded, "snapshot.manifest"))
        embedded_splits = {
            cast(str, record["source_id"]): cast(str, record["split"])
            for record in embedded_records
        }
        if embedded_splits != record_splits:
            raise ValueError("Snapshot and explicit manifest select different records")

    requested_exclusions = sorted(set(excluded_ids))
    candidates = [
        source_id
        for source_id, record_split in record_splits.items()
        if split == "all" or record_split == split
    ]
    excluded_applied = sorted(set(candidates) & set(requested_exclusions))
    selected_ids = sorted(set(candidates) - set(requested_exclusions))
    if not selected_ids:
        raise ValueError("Selection is empty after split and exclusions")
    missing_truth = sorted(set(selected_ids) - set(truth_all))
    if missing_truth:
        raise ValueError(
            f"Ground truth is missing selected IDs: {', '.join(missing_truth)}"
        )
    truth = {source_id: truth_all[source_id] for source_id in selected_ids}

    cases = _as_object_map(snapshot.get("cases", {}), "snapshot.cases")
    metadata = _as_object_map(
        snapshot.get("case_metadata", {}), "snapshot.case_metadata"
    )
    adapter = _as_object(snapshot.get("official_adapter"), "snapshot.official_adapter")
    predictions = _as_object_map(adapter.get("predictions", {}), "predictions")
    diagnostics = _as_object_map(adapter.get("diagnostics", {}), "diagnostics")

    automatic_predictions: dict[str, JsonObject] = {}
    assisted_predictions: dict[str, JsonObject] = {}
    abstention_ids: list[str] = []
    blocker_counts: Counter[str] = Counter()
    assisted_selected = assisted_abstained = 0
    for source_id in selected_ids:
        stored_diagnostic = diagnostics.get(source_id)
        if stored_diagnostic is None:
            diagnostic: JsonObject = {
                "reviewer_assisted": False,
                "blockers": ["diagnostic_missing"],
            }
        else:
            diagnostic = stored_diagnostic
        blockers = _blockers(diagnostic)
        blocker_counts.update(
            blockers or ([] if source_id in predictions else ["prediction_missing"])
        )
        assisted = _reviewer_assisted(diagnostic)
        assisted_selected += int(assisted)
        prediction = predictions.get(source_id)
        if prediction is not None and blockers:
            raise ValueError(f"Blocked row unexpectedly has a prediction: {source_id}")
        if prediction is None:
            abstention_ids.append(source_id)
            assisted_abstained += int(assisted)
        elif assisted:
            assisted_predictions[source_id] = prediction
        else:
            automatic_predictions[source_id] = prediction

    all_predictions = {**automatic_predictions, **assisted_predictions}
    automatic_exact = assisted_exact = 0
    incorrect_exported: list[str] = []
    for source_id, prediction in all_predictions.items():
        exact = _prediction_signature(prediction) == _prediction_signature(
            truth[source_id]
        )
        if exact:
            if source_id in assisted_predictions:
                assisted_exact += 1
            else:
                automatic_exact += 1
        else:
            incorrect_exported.append(source_id)

    selected_total = len(selected_ids)
    truth_artifact = artifact_dir / "filtered-ground-truth.json"
    automatic_artifact = artifact_dir / "automatic-partial-predictions.json"
    inclusive_artifact = artifact_dir / "reviewer-inclusive-partial-predictions.json"
    _write_json(truth_artifact, truth)
    _write_json(automatic_artifact, automatic_predictions)
    _write_json(inclusive_artifact, all_predictions)
    automatic_score = _run_official_scorer(
        scorer_path, truth_artifact, automatic_artifact
    )
    inclusive_score = _run_official_scorer(
        scorer_path, truth_artifact, inclusive_artifact
    )

    report: JsonObject = {
        "schema_version": 1,
        "selection": {
            "split": split,
            "selected_total": selected_total,
            "selected_ids": selected_ids,
            "excluded_ids_requested": requested_exclusions,
            "excluded_ids_applied": excluded_applied,
        },
        "processing": _processing_metrics(selected_ids, cases, metadata),
        "export": {
            "automatic": {
                "count": len(automatic_predictions),
                "coverage": len(automatic_predictions) / selected_total,
            },
            "reviewer_assisted": {
                "selected": assisted_selected,
                "exported": len(assisted_predictions),
                "abstained": assisted_abstained,
                "coverage": len(assisted_predictions) / selected_total,
            },
            "exported_total": len(all_predictions),
            "abstentions": len(abstention_ids),
            "abstention_ids": abstention_ids,
            "blockers": dict(sorted(blocker_counts.items())),
        },
        "category": _category_metrics(selected_ids, cases, truth),
        "exact_rows": {
            "all_exported": _metric(
                automatic_exact + assisted_exact, len(all_predictions)
            ),
            "automatic": _metric(automatic_exact, len(automatic_predictions)),
            "reviewer_assisted": _metric(assisted_exact, len(assisted_predictions)),
            "incorrect_exported_ids": sorted(incorrect_exported),
        },
        "field_comparison": _field_metrics(selected_ids, cases, diagnostics, truth),
        "official_scorer_diagnostics": {
            "warning": (
                "Diagnostic only, not a full-submission score. The unchanged organizer "
                "scorer defaults missing prediction categories to GENERAL."
            ),
            "is_full_submission": False,
            "filtered_truth_rows": selected_total,
            "automatic_partial": {
                "prediction_rows": len(automatic_predictions),
                "missing_rows_defaulted_by_scorer": selected_total
                - len(automatic_predictions),
                "result": automatic_score,
            },
            "reviewer_inclusive_partial": {
                "prediction_rows": len(all_predictions),
                "missing_rows_defaulted_by_scorer": selected_total
                - len(all_predictions),
                "result": inclusive_score,
            },
        },
        "artifacts": {
            "filtered_ground_truth": str(truth_artifact),
            "automatic_partial_predictions": str(automatic_artifact),
            "reviewer_inclusive_partial_predictions": str(inclusive_artifact),
        },
    }
    _write_json(artifact_dir / "evaluation-report.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Report an existing evaluation without running inference"
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--scorer", type=Path, default=DEFAULT_SCORER)
    parser.add_argument(
        "--split", choices=("development", "holdout", "all"), default="development"
    )
    parser.add_argument(
        "--exclude-id",
        action="append",
        default=[],
        help="Explicit source ID to exclude; repeat for multiple IDs",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = build_evaluation_report(
        args.snapshot,
        args.manifest,
        args.ground_truth,
        args.artifacts,
        split=args.split,
        excluded_ids=args.exclude_id,
        scorer_path=args.scorer,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
