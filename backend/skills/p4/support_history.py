"""Extract an owner-bound support summary from an existing private exact-item snapshot."""

import argparse
import json
from pathlib import Path

from interview_backend.repositories.codec import decode, from_wire
from interview_backend.support_history import summarize_evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--record", required=True, help="Private DynamoDB GetItem JSON; never a scan"
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    if not output.is_relative_to(private) or not output.parent.is_dir():
        raise ValueError("ExistingPrivateOutputDirectoryRequired")
    raw = json.loads(Path(args.record).read_text(encoding="utf-8"))
    row = from_wire(raw["Item"])
    evaluation, _ = decode(row)
    summary = summarize_evaluation(evaluation, owner=args.owner, evaluation_id=args.evaluation_id)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False)


if __name__ == "__main__":
    main()
