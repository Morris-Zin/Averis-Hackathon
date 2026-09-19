import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from averis.contracts import Prediction
from averis.dataset import data_root, load_emails
from averis.domain import CaseView
from averis.exporting import export_submission


def validate(path: Path, root: Path) -> dict[str, Prediction]:
    submission = TypeAdapter(dict[str, Prediction]).validate_json(path.read_text(encoding="utf-8-sig"))
    expected = {e["email_id"] for e in load_emails(root)}
    if set(submission) != expected:
        raise ValueError("Submission must contain exactly every dataset email ID")
    return submission



def export_cases(snapshot: Path, output: Path, diagnostics: Path, root: Path) -> bool:
    """Export a source-ID keyed snapshot; unknown rows remain explicit blockers."""
    cases = TypeAdapter(dict[str, CaseView]).validate_json(snapshot.read_text(encoding="utf-8-sig"))
    # Application UUIDs are unrelated to dataset IDs. The operator supplies the
    # mapping from the import manifest, never by guessing from shipment content.
    mapped = [case.model_copy(update={"id": source_id}) for source_id, case in cases.items()]
    expected = [email["email_id"] for email in load_emails(root)]
    result = export_submission(mapped, expected)
    count = len(expected)
    automatic = sum(not item.reviewer_assisted and not item.blockers for item in result.diagnostics.values())
    assisted = sum(item.reviewer_assisted and not item.blockers for item in result.diagnostics.values())
    sidecar = {
        "complete": result.complete,
        "global_blockers": result.global_blockers,
        "cases": result.diagnostics_payload(),
        "automatic_rows": automatic,
        "reviewer_assisted_rows": assisted,
        "abstentions": count - automatic - assisted,
        "automatic_coverage": automatic / count if count else 0,
    }
    if len({snapshot.resolve(), output.resolve(), diagnostics.resolve()}) != 3:
        raise ValueError("Snapshot, submission and diagnostics must be separate files")
    if output.exists() or diagnostics.exists():
        raise ValueError("Choose new output paths; existing evaluation artifacts are never overwritten")
    diagnostics.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    if not result.complete:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.official_payload(), indent=2) + "\n", encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Dataset and evaluation utilities")
    parser.add_argument("command", choices=["inspect", "validate", "score", "export"])
    parser.add_argument("submission", type=Path, nargs="?")
    parser.add_argument("--data", type=Path, default=data_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    args = parser.parse_args()
    if args.command == "export":
        if args.submission is None or args.output is None or args.diagnostics is None:
            parser.error("export requires a case snapshot, --output and --diagnostics")
        if not export_cases(args.submission, args.output, args.diagnostics, args.data):
            parser.exit(2, "Export blocked; diagnostics written, no official submission created.\n")
        print("Official submission and separate coverage diagnostics written")
        return
    if args.command == "inspect":
        emails = load_emails(args.data)
        attachments = list((args.data / "attachments").glob("*"))
        print(json.dumps({"emails": len(emails), "attachment_files": len(attachments),
                          "formats": dict(Counter(p.suffix for p in attachments))}, indent=2))
        return
    if args.submission is None:
        parser.error("validate and score require a submission path")
    validate(args.submission, args.data)
    if args.command == "validate":
        print("Submission contract and email coverage are valid")
        return
    scorer = Path("resources/official/docker/server/score_cli.py")
    if not scorer.is_file():
        parser.error("Download and extract the official Docker kit first; see README")
    subprocess.run([sys.executable, str(scorer), str(args.submission.resolve()), "--json"],
                   check=True)


if __name__ == "__main__":
    main()
