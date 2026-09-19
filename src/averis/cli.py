import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from averis.contracts import Prediction
from averis.dataset import data_root, load_emails


def validate(path: Path, root: Path) -> dict:
    submission = json.loads(path.read_text(encoding="utf-8-sig"))
    expected = {e["email_id"] for e in load_emails(root)}
    if not isinstance(submission, dict) or set(submission) != expected:
        raise ValueError("Submission must contain exactly every dataset email ID")
    for record in submission.values():
        Prediction.model_validate(record)
    return submission


def main():
    parser = argparse.ArgumentParser(description="Dataset and evaluation utilities")
    parser.add_argument("command", choices=["inspect", "validate", "score"])
    parser.add_argument("submission", type=Path, nargs="?")
    parser.add_argument("--data", type=Path, default=data_root())
    args = parser.parse_args()
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
