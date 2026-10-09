"""Extract an owner-bound support summary from an existing private exact-item snapshot."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from bootstrap_state import private_path
from deployment_guards import approved_json

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
    parser.add_argument("--identity-proof", required=True)
    parser.add_argument("--identity-proof-sha256", required=True)
    args = parser.parse_args()
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    output = private_path(args.output, private)
    record = private_path(args.record, private)
    if not output.parent.is_dir():
        raise ValueError("ExistingPrivateOutputDirectoryRequired")
    _, identity = approved_json(args.identity_proof, args.identity_proof_sha256, private)
    if (
        identity.get("status") != "IDENTITY_VERIFIED"
        or identity.get("owner") != args.owner
        or identity.get("evaluation_id") != args.evaluation_id
        or identity.get("verification_method")
        not in {"authenticated_subject", "reviewed_support_ticket"}
        or not identity.get("verified_by")
        or type(identity.get("issued_at_epoch")) is not int
        or type(identity.get("expires_at_epoch")) is not int
        or not identity["issued_at_epoch"] <= int(time.time()) < identity["expires_at_epoch"]
        or not 0 < identity["expires_at_epoch"] - identity["issued_at_epoch"] <= 900
    ):
        raise ValueError("VerifiedSupportIdentityRequired")
    raw = json.loads(record.read_text(encoding="utf-8"))
    if "Item" not in raw:
        raise ValueError("SupportEvaluationUnavailable")
    row = from_wire(raw["Item"])
    evaluation, _ = decode(row)
    summary = summarize_evaluation(evaluation, owner=args.owner, evaluation_id=args.evaluation_id)
    with os.fdopen(
        os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8"
    ) as stream:
        json.dump(summary, stream, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("SupportHistoryFailed", file=sys.stderr)
        raise SystemExit(1) from None
