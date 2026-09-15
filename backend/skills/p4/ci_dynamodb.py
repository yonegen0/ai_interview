"""Explicit real-DynamoDB CI entry; never invoked by collection or ordinary pytest."""

import json
import os
import sys

from ci_identity import assume
from terraform_dev import PROJECT, checked_git

from interview_backend.deployment import account_settings


def main():
    import subprocess

    journal = None
    account = region = None
    outcome = 1
    try:
        account, region = account_settings(PROJECT)
        checked_git(PROJECT, os.environ)
        run_id = os.environ["GITHUB_RUN_ID"]
        attempt = os.environ["GITHUB_RUN_ATTEMPT"]
        if not run_id.isdecimal() or not attempt.isdecimal():
            raise ValueError("InvalidRunIdentity")
        directory = PROJECT / ".p4-artifacts" / f"db-{run_id}-{attempt}"
        directory.mkdir(parents=True, exist_ok=False)
        journal = directory / "tables.jsonl"
        assume("test", account, region, expected_subject=os.environ["P4_OIDC_SUBJECT"])
        env = dict(os.environ)
        env.update(
            {
                "INTERVIEW_TEST_MODE": "aws",
                "INTERVIEW_TEST_AWS_REGION": region,
                "INTERVIEW_TEST_TABLE_PREFIX": "interview-p3-test-ci",
                "INTERVIEW_TEST_MANIFEST": str(journal),
            }
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "dynamodb"],
            cwd=PROJECT / "backend",
            env=env,
            capture_output=True,
            check=False,
        )
        # Do not forward SDK exceptions, assertion bodies or user data into CI logs.
        print(
            json.dumps(
                {
                    "suite": "dynamodb",
                    "code_sha": os.environ["GITHUB_SHA"],
                    "status": "success" if result.returncode == 0 else "failed",
                }
            )
        )
        outcome = 0 if result.returncode == 0 else 1
    except Exception:
        print("DynamoDbCiFailed", file=sys.stderr)
    finally:
        if journal is not None and journal.exists():
            try:
                from ci_deploy import put

                session = assume(
                    "artifact", account, region, expected_subject=os.environ["P4_OIDC_SUBJECT"]
                )
                put(
                    session.client("s3"),
                    f"ai-interview-artifacts-{account}-{region}",
                    f"plans/db-{run_id}/{attempt}/tables.jsonl",
                    journal.read_bytes(),
                )
            except Exception:
                print("TestManifestUploadFailed", file=sys.stderr)
                outcome = 1
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            os.environ.pop(key, None)
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
