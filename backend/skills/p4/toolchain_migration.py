"""Explicit offline qualification only; never authorizes a deployed toolchain change."""

import argparse
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from offline_terraform import (
    copy_configuration,
    isolated_environment,
    parse_lock,
    tracked_snapshot,
)

BASELINE_CLI = "1.14.9"
CANDIDATE_CLIS = ("1.16.7", "1.17.0")
CANDIDATE_PROVIDER = "6.70.0"
AWS = "registry.terraform.io/hashicorp/aws"
# Explicit inventory, independent of the normal additive-checksum validator.
SCOPES = {
    "bootstrap": ("main.tf", "6.64.0"),
    "environments/dev": ("main.tf", "6.65.0"),
    "environments/test": ("main.tf", "6.64.0"),
    "environments/web": ("main.tf", "6.65.0"),
    "modules/frontend": ("main.tf", "6.65.0"),
    "modules/service": ("versions.tf", "6.64.0"),
}


def candidate_configuration(before, candidate):
    """Only the six literal CLI/provider requirements may change; retain every other byte."""
    if candidate not in CANDIDATE_CLIS:
        raise ValueError("UnreviewedMigrationCandidate")
    expected = dict(before)
    for scope, (filename, _) in SCOPES.items():
        name = f"terraform/{scope}/{filename}"
        raw = before[name]
        cli = b'required_version = "= 1.14.9"'
        provider = b'aws = { source = "hashicorp/aws", version = "~> 6.0" }'
        if raw.count(cli) != 1 or raw.count(provider) != 1:
            raise ValueError("MigrationBaselineRequirementsMismatch")
        expected[name] = raw.replace(cli, f'required_version = "= {candidate}"'.encode()).replace(
            provider, b'aws = { source = "hashicorp/aws", version = "= 6.70.0" }'
        )
    return expected


def assert_migration(before, after, candidate):
    """Check generated locks and exact version-only HCL changes, not AWS/State safety."""
    if before.keys() != after.keys():
        raise ValueError("MigrationFileInventoryChanged")
    expected = candidate_configuration(before, candidate)
    locks = {f"terraform/{scope}/.terraform.lock.hcl" for scope in SCOPES}
    if {name for name in before if name.endswith(".terraform.lock.hcl")} != locks:
        raise ValueError("MigrationScopeMismatch")
    generated = None
    for scope, (_, old_version) in SCOPES.items():
        name = f"terraform/{scope}/.terraform.lock.hcl"
        old, new = parse_lock(before[name].decode()), parse_lock(after[name].decode())
        if set(old) != {AWS} or set(new) != {AWS}:
            raise ValueError("MigrationProviderSelectionChanged")
        if old[AWS]["version"] != old_version or old[AWS]["constraints"] != "~> 6.0":
            raise ValueError("MigrationBaselineProviderMismatch")
        if new[AWS]["version"] != CANDIDATE_PROVIDER or new[AWS]["constraints"] != "6.70.0":
            raise ValueError("MigrationCandidateProviderMismatch")
        hashes = new[AWS]["hashes"]
        if sum(h.startswith("h1:") for h in hashes) < 2 or not any(
            h.startswith("zh:") for h in hashes
        ):
            raise ValueError("MigrationPlatformChecksumsRequired")
        if generated is not None and generated != new:
            raise ValueError("MigrationGeneratedLocksDiffer")
        generated = new
    if any(after[name] != raw for name, raw in expected.items() if name not in locks):
        raise ValueError("MigrationUnrelatedConfigurationChanged")


def assert_version_json(value, expected, expected_platform):
    """Accept the documented optional 1.17 format field, reject unknown formats/platforms."""
    if (
        not isinstance(value, dict)
        or value.get("terraform_version") != expected
        or value.get("platform") != expected_platform
        or ("format_version" in value and value["format_version"] != "1.0")
    ):
        raise ValueError("MigrationTerraformVersionMismatch")


def configuration_bytes(copied):
    return {
        path.relative_to(copied).as_posix(): path.read_bytes()
        for path in copied.rglob("*")
        if path.is_file() and ".terraform" not in path.relative_to(copied).parts
    }


def qualify(repository, temp_parent, executable, candidate):
    """Official registry downloads + backend-disabled validate + existing mocked tests.

    Use a separately checksum-verified absolute binary path. No formal plan/apply,
    credentials, backend initialization, saved-plan reuse or runtime version changes.
    All work products stay in a fresh directory; tracked source is rechecked on failure.
    """
    executable = Path(executable)
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("ExplicitTerraformBinaryRequired")
    if candidate not in CANDIDATE_CLIS:
        raise ValueError("UnreviewedMigrationCandidate")
    repository = Path(repository).resolve()
    binary_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    snapshot = tracked_snapshot(repository)
    work = Path(tempfile.mkdtemp(prefix=f"p4-qualify-{candidate}-", dir=temp_parent)).resolve()
    copied = work / "checkout"
    try:
        copy_configuration(repository, copied, snapshot)
        env = isolated_environment(work)
        logs = work / "logs"
        logs.mkdir()
        sequence = 0

        def terraform(directory, *args):
            nonlocal sequence
            sequence += 1
            process = subprocess.run(
                [str(executable), *args],
                cwd=directory,
                env=env,
                check=False,
                capture_output=True,
                timeout=600,
            )
            (logs / f"{sequence:03d}.stdout").write_bytes(process.stdout)
            (logs / f"{sequence:03d}.stderr").write_bytes(process.stderr)
            if process.returncode:
                # Only public copied configuration and synthetic mock output can enter here.
                print(
                    (process.stdout + process.stderr).decode(errors="replace")[-12000:], flush=True
                )
            process.check_returncode()
            return process.stdout

        expected_platform = {"Windows": "windows_amd64", "Linux": "linux_amd64"}.get(
            platform.system()
        )
        if expected_platform is None or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise ValueError("MigrationPlatformUnsupported")
        version = json.loads(terraform(copied, "version", "-json"))
        assert_version_json(version, candidate, expected_platform)
        before = configuration_bytes(copied)
        prepared = candidate_configuration(before, candidate)
        for name, raw in prepared.items():
            if raw != before[name]:
                (copied / name).write_bytes(raw)
        for scope in SCOPES:
            print(f"Locking {candidate} / {expected_platform} / {scope}", flush=True)
            root = copied / "terraform" / scope
            # Delete only the disposable copied lock; the source/historical lock is retained.
            (root / ".terraform.lock.hcl").unlink()
            terraform(root, "get", "-no-color")
            terraform(root, "providers", "lock", "-platform=linux_amd64", "-platform=windows_amd64")
        assert_migration(before, configuration_bytes(copied), candidate)
        terraform(copied, "fmt", "-check", "-recursive", "terraform")
        for scope in SCOPES:
            print(f"Qualifying {candidate} / {expected_platform} / {scope}", flush=True)
            root = copied / "terraform" / scope
            terraform(root, "init", "-backend=false", "-input=false", "-lockfile=readonly")
            terraform(root, "validate", "-no-color")
        tests = {}
        for scope in ("bootstrap", "modules/service", "modules/frontend"):
            tests[scope] = terraform(copied / "terraform" / scope, "test", "-no-color").decode()
        assert_migration(before, configuration_bytes(copied), candidate)
        report = {
            "status": "OFFLINE_QUALIFIED_NOT_DEPLOYMENT_APPROVAL",
            "version": version,
            "provider": CANDIDATE_PROVIDER,
            "scopes": list(SCOPES),
            "mock_tests": tests,
            "aws_operations": 0,
            "formal_plan_apply": False,
            "binary_sha256": binary_sha256,
            "source_configuration_sha256": snapshot,
        }
    finally:
        if tracked_snapshot(repository) != snapshot:
            raise ValueError("OriginalTerraformChanged")
        if hashlib.sha256(executable.read_bytes()).hexdigest() != binary_sha256:
            raise ValueError("MigrationTerraformBinaryChanged")
    (work / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--temp-parent", required=True)
    parser.add_argument("--terraform", required=True)
    parser.add_argument("--candidate", required=True, choices=CANDIDATE_CLIS)
    args = parser.parse_args()
    print(qualify(args.repository, args.temp_parent, args.terraform, args.candidate))


if __name__ == "__main__":
    main()
