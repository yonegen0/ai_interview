"""Disposable backend-free CLI/Provider probe inside an isolated Linux netns.

Requires separately supplied digest pins; those pins do not authenticate official
signers. Only version/init(-backend=false)/validate/schema are permitted. Never
uses repository configuration, backend, State, Plan, credentials or AWS clients.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from offline_terraform import parse_lock


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def require_isolation() -> None:
    require(
        sys.platform == "linux"
        and os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net")
        and {name for _, name in socket.if_nameindex()} == {"lo"},
        "CandidateProbeNetworkIsolationRequiredHOLD",
    )


def checked_bytes(path: Path, digest: str) -> bytes:
    require(
        path.is_absolute()
        and path.is_file()
        and all(not p.is_symlink() for p in (path, *path.parents)),
        "CandidateProbeBinaryPathHOLD",
    )
    raw = path.read_bytes()
    require(
        type(digest) is str and hashlib.sha256(raw).hexdigest() == digest,
        "CandidateProbeBinaryDigestHOLD",
    )
    return raw


def probe(
    cli: Path,
    provider: Path,
    *,
    version: str,
    cli_sha256: str,
    provider_sha256: str,
    provider_inventory_sha256: str,
    lock_bytes: bytes,
) -> dict[str, object]:
    require_isolation()
    require(type(version) is str and version in {"1.16.7", "1.17.0"}, "CandidateProbeVersionHOLD")
    cli_raw = checked_bytes(cli, cli_sha256)
    provider_raw = checked_bytes(provider, provider_sha256)
    names = {provider.name, "LICENSE.txt"}
    require({p.name for p in provider.parent.iterdir()} == names, "CandidateProbePackageHOLD")
    license_path = provider.parent / "LICENSE.txt"
    require(not license_path.is_symlink() and license_path.is_file(), "CandidateProbePackageHOLD")
    license_raw = license_path.read_bytes()
    inventory = {
        provider.name: provider_sha256,
        "LICENSE.txt": hashlib.sha256(license_raw).hexdigest(),
    }
    inventory_digest = hashlib.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    require(inventory_digest == provider_inventory_sha256, "CandidateProbePackageDigestHOLD")
    require(type(lock_bytes) is bytes, "CandidateProbeLockHOLD")
    selection = parse_lock(lock_bytes.decode("utf-8"))
    aws = "registry.terraform.io/hashicorp/aws"
    require(
        set(selection) == {aws}
        and selection[aws]["version"] == "6.70.0"
        and selection[aws]["constraints"] == "6.70.0",
        "CandidateProbeLockHOLD",
    )
    with tempfile.TemporaryDirectory(prefix="candidate-offline-probe-") as temporary:
        root = Path(temporary)
        binary = root / "terraform"
        binary.write_bytes(cli_raw)
        binary.chmod(0o700)
        mirror = root / "mirror"
        plugin = mirror / aws / "6.70.0/linux_amd64/terraform-provider-aws_v6.70.0_x5"
        plugin.parent.mkdir(parents=True)
        plugin.write_bytes(provider_raw)
        (plugin.parent / "LICENSE.txt").write_bytes(license_raw)
        plugin.chmod(0o700)
        home = root / "home"
        home.mkdir()
        config = root / "terraform.rc"
        config.write_text(
            f'provider_installation {{\n filesystem_mirror {{\n  path = "{mirror}"\n }}\n}}\n'
        )
        work = root / "configuration"
        work.mkdir()
        hcl = (
            f'terraform {{\n required_version = "= {version}"\n'
            ' required_providers { aws = { source = "hashicorp/aws", version = "= 6.70.0" } }\n}\n'
        ).encode()
        (work / "main.tf").write_bytes(hcl)
        (work / ".terraform.lock.hcl").write_bytes(lock_bytes)
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "TF_CLI_CONFIG_FILE": str(config),
            "CHECKPOINT_DISABLE": "1",
            "TF_IN_AUTOMATION": "true",
            "AWS_EC2_METADATA_DISABLED": "true",
        }

        def run(*args):
            result = subprocess.run(
                [str(binary), *args],
                cwd=work,
                env=env,
                capture_output=True,
                timeout=120,
            )
            require(result.returncode == 0, f"CandidateProbeCommandFailedHOLD:{args[0]}")
            return result.stdout

        actual = json.loads(run("version", "-json"))
        require(
            actual["terraform_version"] == version and actual["platform"] == "linux_amd64",
            "CandidateProbeVersionOrPlatformHOLD",
        )
        run("init", "-backend=false", "-input=false", "-lockfile=readonly", "-get=false")
        validation = json.loads(run("validate", "-json"))
        require(validation.get("valid") is True, "CandidateProbeValidateHOLD")
        schema = json.loads(run("providers", "schema", "-json"))
        require(set(schema.get("provider_schemas", {})) == {aws}, "CandidateProbeProviderHOLD")
        checked_bytes(binary, cli_sha256)
        checked_bytes(plugin, provider_sha256)
        require(
            (work / "main.tf").read_bytes() == hcl
            and (work / ".terraform.lock.hcl").read_bytes() == lock_bytes
            and not list(work.glob("*.tfstate*")),
            "CandidateProbeSourceOrStateHOLD",
        )
    return {
        "status": "OFFLINE_CLI_PROVIDER_OBSERVED_HOLD",
        "terraform_version": version,
        "provider_version": "6.70.0",
        "platform": "linux_amd64",
        "terraform_sha256": cli_sha256,
        "provider_sha256": provider_sha256,
        "provider_inventory_sha256": inventory_digest,
        "validate_valid": True,
        "provider_schema_observed": True,
        "official_signer_authenticated": False,
        "immutable_execution_toolchain_verified": False,
        "state_compatibility_verified": False,
        "authorized": False,
        "aws_operations": 0,
    }
