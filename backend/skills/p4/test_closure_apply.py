"""Private saved-plan-only test Alarm closure, with live preflight and no retry.

Requires explicit AWS readiness. Codex Cloud exercises only the guard's mocks.
This does not enable test writers or change their concurrency settings.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from bootstrap_state import private_path, write_record
from deployment_guards import read_state_snapshot, sha256
from manifest import read_manifest, verify_live_manifest
from test_closure_guard import apply_once, guard

from interview_backend.deployment import (
    checked_session,
    credential_environment,
    require_aws_execution,
    terraform_environment,
)

PROJECT = Path(__file__).resolve().parents[3]


class Driver:
    def __init__(self, session, manifest, plan, plan_hash, directory, source_sha):
        self.session, self.manifest = session, manifest
        self.plan, self.plan_hash, self.directory, self.source_sha = (
            plan,
            plan_hash,
            directory,
            source_sha,
        )
        self.root = PROJECT / "terraform/environments/test"
        self.env = credential_environment(
            session,
            terraform_environment(
                self.root, os.environ, manifest["account_id"], manifest["region"]
            ),
        )
        self.env["TF_DATA_DIR"] = str(directory / ".terraform")
        self.env["TF_WORKSPACE"] = "default"
        self.check_source()
        if json.loads(self.command("version", "-json"))["terraform_version"] != "1.14.9":
            raise ValueError("TerraformVersionMismatch")
        self.command(
            "init",
            "-input=false",
            "-lockfile=readonly",
            f"-backend-config=bucket=ai-interview-state-{manifest['account_id']}-{manifest['region']}",
            f"-backend-config=key=test/{manifest['run_id']}/terraform.tfstate",
            f"-backend-config=region={manifest['region']}",
            '-backend-config=allowed_account_ids=["' + manifest["account_id"] + '"]',
            "-backend-config=encrypt=true",
            "-backend-config=use_lockfile=true",
        )

    @staticmethod
    def sleep(seconds):
        import time

        time.sleep(seconds)

    def command(self, *args):
        result = subprocess.run(
            ["terraform", *args], cwd=self.root, env=self.env, capture_output=True, check=False
        )
        if result.returncode:
            raise ValueError("TestTerraformOperationFailed")
        return result.stdout

    def check_source(self):
        head = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, check=True
            )
            .stdout.decode()
            .strip()
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=PROJECT,
            capture_output=True,
            check=True,
        ).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_sha) or head != self.source_sha or dirty:
            raise ValueError("ApprovedCleanCommittedSourceRequired")

    def review(self):
        if sha256(self.plan.read_bytes()) != self.plan_hash:
            raise ValueError("ApprovedSavedTestPlanHashRequired")
        return json.loads(self.command("show", "-json", str(self.plan)))

    def snapshot(self):
        return read_state_snapshot(
            self.session,
            self.manifest["account_id"],
            self.manifest["region"],
            f"test/{self.manifest['run_id']}/terraform.tfstate",
        )

    def apply(self, review):
        self.check_source()
        if self.review() != review:
            raise ValueError("TestSavedPlanChangedBeforeApply")
        self.command("apply", "-input=false", "-lock-timeout=60s", str(self.plan))

    def verify(self, expected):
        if json.loads(self.command("output", "-json", "manifest")) != expected:
            raise ValueError("TestTerraformOutputMismatch")
        verify_live_manifest(self.session, expected, require_api_enabled=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("preflight", "apply"))
    for name in (
        "manifest",
        "account",
        "region",
        "directory",
        "plan",
        "plan-hash",
        "proof",
        "proof-hash",
        "source-sha",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    require_aws_execution()
    private = PROJECT / ".p4-artifacts"
    directory = private_path(args.directory, private.resolve())
    plan = private_path(args.plan, private.resolve())
    proof = private_path(args.proof, private.resolve())
    manifest = read_manifest(
        private_path(args.manifest, private.resolve()), args.account, args.region, require_test=True
    )
    if not directory.is_dir() or not re.fullmatch(r"[0-9a-f]{64}", args.plan_hash):
        raise ValueError("ExistingPrivateTestRunAndPlanRequired")
    if (directory / "test-apply-attempt.json").exists():
        raise ValueError("TestApplyAlreadyAttempted")
    driver = Driver(
        checked_session(args.account, args.region),
        manifest,
        plan,
        args.plan_hash,
        directory,
        args.source_sha,
    )
    review = driver.review()
    binding = {
        "source_sha": args.source_sha,
        "plan_sha256": args.plan_hash,
        "proof_sha256": args.proof_hash,
        "account_id": args.account,
        "region": args.region,
        "run_id": manifest["run_id"],
    }
    receipt = directory / "test-plan-preflight.json"
    if args.operation == "preflight":
        snapshot = driver.snapshot()
        guard(driver.session, manifest, snapshot, review, proof, args.proof_hash, private.resolve())
        if driver.snapshot() != snapshot:
            raise ValueError("TestStateChangedDuringPlanPreflight")
        write_record(receipt, binding | {"state_identity": snapshot["identity"]})
    else:
        previous = json.loads(receipt.read_text())
        if previous != binding | {"state_identity": driver.snapshot()["identity"]}:
            raise ValueError("TestPlanPreflightBindingMismatch")
        apply_once(driver, directory, manifest, review, proof, args.proof_hash, private.resolve())
    print(json.dumps({"status": "test_" + args.operation + "_verified"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("TestClosureGuardFailed", file=sys.stderr)
        raise SystemExit(1) from None
