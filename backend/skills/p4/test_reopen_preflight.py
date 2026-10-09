"""Read back all 39 test alarms while entry paths remain disabled, before reenablement."""

import argparse
import sys
from pathlib import Path

from bootstrap_state import private_path
from cost_controls import FLAGS
from deployment_guards import read_state_snapshot
from manifest import read_manifest, verify_live_manifest
from test_closure_guard import require_reopen

from interview_backend.deployment import checked_session, require_aws_execution


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    require_aws_execution()
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    manifest = read_manifest(
        private_path(args.manifest, private), args.account, args.region, require_test=True
    )
    if any(manifest["configuration"][flag] for flag in FLAGS):
        raise ValueError("RestoreAlarmsBeforeTestEnablement")
    session = checked_session(args.account, args.region)
    snapshot = read_state_snapshot(
        session, args.account, args.region, f"test/{manifest['run_id']}/terraform.tfstate"
    )
    if snapshot["manifest"] != manifest:
        raise ValueError("CurrentTestManifestRequired")
    require_reopen(snapshot, enabling=True)
    verify_live_manifest(session, manifest, require_api_enabled=False)
    if (
        read_state_snapshot(
            session, args.account, args.region, f"test/{manifest['run_id']}/terraform.tfstate"
        )
        != snapshot
    ):
        raise ValueError("TestStateChangedDuringReopenPreflight")
    print("Test39AlarmReadbackVerified")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("TestReopenPreflightFailed", file=sys.stderr)
        raise SystemExit(1) from None
