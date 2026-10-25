"""Explicit offline qualification only; never authorizes a deployed toolchain change."""

import argparse
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from offline_terraform import (
    assert_additive,
    copy_configuration,
    isolated_environment,
    parse_lock,
    tracked_snapshot,
)
from toolchain_compatibility import compare_schemas, resource_types

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


def export_candidate_bundle(repository, qualification, destination):
    """Export twelve reviewed candidate files, without editing the active checkout.

    The bundle is PR B input, never a complete or approved execution migration.
    Recheck source binding and every copied byte; never export State/Plan/credentials.
    """
    repository, qualification, destination = map(
        lambda value: Path(value).resolve(), (repository, qualification, destination)
    )
    if destination.is_relative_to(repository):
        raise ValueError("MigrationExportMustBeOutsideRepository")
    report = json.loads((qualification / "report.json").read_text(encoding="utf-8"))
    snapshot = tracked_snapshot(repository)
    if (
        report.get("status") != "OFFLINE_QUALIFIED_NOT_DEPLOYMENT_APPROVAL"
        or report.get("source_configuration_sha256") != snapshot
        or set(report.get("provider_schema_comparisons", {})) != {"6.64.0", "6.65.0"}
    ):
        raise ValueError("MigrationExportEvidenceMismatch")
    baseline = {
        name: (repository / name).read_bytes()
        for name in snapshot
        if name.endswith((".tf", ".tf.json", ".tftest.hcl", "/.terraform.lock.hcl"))
        or name == "terraform/modules/frontend/rewrite.js"
    }
    kinds = resource_types(baseline)
    for evidence in report["provider_schema_comparisons"].values():
        if (
            set(evidence.get("resource_types", [])) != kinds
            or set(evidence.get("schema_versions", {})) != kinds
            or evidence.get("defaults_and_state_upgraders_proven") is not False
            or any(
                not isinstance(evidence.get(field), str)
                or len(evidence[field]) != 64
                or any(c not in "0123456789abcdef" for c in evidence[field])
                for field in ("baseline_schema_sha256", "candidate_schema_sha256")
            )
        ):
            raise ValueError("MigrationExportEvidenceMismatch")
    candidate = report["version"]["terraform_version"]
    prepared = configuration_bytes(qualification / "checkout")
    assert_migration(baseline, prepared, candidate)
    if tracked_snapshot(repository) != snapshot:
        raise ValueError("OriginalTerraformChanged")
    changed = {name: raw for name, raw in prepared.items() if raw != baseline[name]}
    if len(changed) != 12:
        raise ValueError("MigrationExportInventoryMismatch")
    destination.mkdir(exist_ok=False)
    for name, raw in changed.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    manifest = {
        "status": "HOLD_INCOMPLETE_EXECUTION_MIGRATION_DO_NOT_MERGE",
        "candidate": candidate,
        "provider": CANDIDATE_PROVIDER,
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in changed.items()},
        "qualification_report_sha256": hashlib.sha256(
            (qualification / "report.json").read_bytes()
        ).hexdigest(),
        "remaining": [
            "new execution constant and all workflow pins must migrate together",
            "bootstrap future execution must remain separate from historical readers",
            "new saved Plans, bindings and approvals; no historical authorization reuse",
            "State/default/identity compatibility evidence and independent adoption review",
            "genuine required CI, approval and HOLD release before adoption merge",
        ],
    }
    with (destination / "UPGRADE_HOLD.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
    return destination


def qualify(repository, temp_parent, executable, candidate, *, compare_provider_schemas=False):
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
        baseline_schemas = {}
        if compare_provider_schemas:
            # Independent minimal roots: no repository backend, module, resource or State.
            for provider, scope in (("6.64.0", "bootstrap"), ("6.65.0", "environments/dev")):
                raw_lock = before[f"terraform/{scope}/.terraform.lock.hcl"]
                selection = parse_lock(raw_lock.decode("utf-8"))
                if (
                    set(selection) != {AWS}
                    or selection[AWS]["version"] != provider
                    or selection[AWS]["constraints"] != "~> 6.0"
                ):
                    raise ValueError("MigrationBaselineProviderMismatch")
                schema_root = work / f"schema-{provider}"
                schema_root.mkdir()
                (schema_root / "main.tf").write_text(
                    "terraform {\n  required_providers {\n"
                    '    aws = { source = "hashicorp/aws", version = "~> 6.0" }\n'
                    "  }\n}\n",
                    encoding="utf-8",
                )
                (schema_root / ".terraform.lock.hcl").write_bytes(raw_lock)
                # Baseline locks may contain Windows h1 only. Add the official native
                # package hash in this disposable root, preserving selection and hashes.
                terraform(schema_root, "providers", "lock", f"-platform={expected_platform}")
                assert_additive(
                    raw_lock.decode("utf-8"),
                    (schema_root / ".terraform.lock.hcl").read_text(encoding="utf-8"),
                )
                terraform(
                    schema_root, "init", "-backend=false", "-input=false", "-lockfile=readonly"
                )
                baseline_schemas[provider] = json.loads(
                    terraform(schema_root, "providers", "schema", "-json")
                )
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
        schema_comparisons = {}
        if compare_provider_schemas:
            candidate_schema = json.loads(
                terraform(copied / "terraform/bootstrap", "providers", "schema", "-json")
            )
            kinds = resource_types(before)
            for provider, schema in baseline_schemas.items():
                schema_comparisons[provider] = compare_schemas(schema, candidate_schema, kinds)
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
            "provider_schema_comparisons": schema_comparisons,
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
    parser.add_argument("--compare-provider-schemas", action="store_true")
    parser.add_argument("--export-directory")
    args = parser.parse_args()
    work = qualify(
        args.repository,
        args.temp_parent,
        args.terraform,
        args.candidate,
        compare_provider_schemas=args.compare_provider_schemas,
    )
    print(work)
    if args.export_directory:
        print(export_candidate_bundle(args.repository, work, args.export_directory))


if __name__ == "__main__":
    main()
