"""Validate tracked Terraform in a fresh copy; allow only additive lock checksums."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOTS = ("bootstrap", "environments/dev", "environments/test", "modules/service")
TOKEN = re.compile(
    r'\s+|\#[^\n]*|//[^\n]*|/\*[\s\S]*?\*/|"(?:[^"\\\x00-\x1f]|\\.)*"'
    r"|[A-Za-z_][A-Za-z_0-9]*|[{}\[\]=,]"
)


def parse_lock(text):
    """Parse the deliberately limited provider-lock grammar, consuming every byte."""
    tokens = []
    position = 0
    while position < len(text):
        match = TOKEN.match(text, position)
        if match is None:
            raise ValueError("InvalidProviderLock")
        token = match.group()
        position = match.end()
        if not token.isspace() and not token.startswith(("#", "//", "/*")):
            tokens.append(token)
    cursor = 0

    def take(expected=None):
        nonlocal cursor
        if cursor == len(tokens):
            raise ValueError("InvalidProviderLock")
        value = tokens[cursor]
        cursor += 1
        if expected is not None and value != expected:
            raise ValueError("InvalidProviderLock")
        return value

    def string():
        value = take()
        if not value.startswith('"'):
            raise ValueError("InvalidProviderLock")
        decoded = json.loads(value)
        if "${" in decoded or "%{" in decoded:
            raise ValueError("InvalidProviderLock")
        return decoded

    providers = {}
    while cursor < len(tokens):
        take("provider")
        address = string()
        if not re.fullmatch(r"registry\.terraform\.io/[a-z0-9-]+/[a-z0-9-]+", address):
            raise ValueError("InvalidProviderLock")
        if address in providers:
            raise ValueError("InvalidProviderLock")
        take("{")
        fields = {}
        while cursor < len(tokens) and tokens[cursor] != "}":
            key = take()
            if key not in {"version", "constraints", "hashes"} or key in fields:
                raise ValueError("InvalidProviderLock")
            take("=")
            if key != "hashes":
                fields[key] = string()
                continue
            take("[")
            hashes = set()
            while cursor < len(tokens) and tokens[cursor] != "]":
                hashed = string()
                if not re.fullmatch(r"(?:h1:[A-Za-z0-9+/]{43}=|zh:[0-9a-f]{64})", hashed):
                    raise ValueError("InvalidProviderLock")
                if hashed in hashes:
                    raise ValueError("InvalidProviderLock")
                hashes.add(hashed)
                if cursor < len(tokens) and tokens[cursor] == ",":
                    take(",")
                elif cursor < len(tokens) and tokens[cursor] != "]":
                    raise ValueError("InvalidProviderLock")
            take("]")
            fields[key] = hashes
        take("}")
        if set(fields) != {"version", "constraints", "hashes"} or not fields["hashes"]:
            raise ValueError("InvalidProviderLock")
        providers[address] = fields
    if not providers:
        raise ValueError("InvalidProviderLock")
    return providers


def assert_additive(before, after):
    old, new = parse_lock(before), parse_lock(after)
    if old.keys() != new.keys():
        raise ValueError("ProviderSelectionChanged")
    for address, fields in old.items():
        candidate = new[address]
        if any(fields[key] != candidate[key] for key in ("version", "constraints")):
            raise ValueError("ProviderSelectionChanged")
        if not fields["hashes"] <= candidate["hashes"]:
            raise ValueError("ProviderChecksumsRemoved")


def tracked_snapshot(repository):
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "terraform/"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    snapshot = {}
    for name in result.stdout.decode("utf-8").split("\0"):
        if not name:
            continue
        relative = Path(name)
        path = repository / relative
        if relative.is_absolute() or ".." in relative.parts or not path.is_file():
            raise ValueError("InvalidTrackedTerraformPath")
        if any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)()
            for p in (path, *path.parents)
        ):
            raise ValueError("InvalidTrackedTerraformPath")
        snapshot[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not snapshot:
        raise ValueError("TrackedTerraformRequired")
    return snapshot


def copy_configuration(repository, destination, snapshot):
    destination.mkdir(exist_ok=False)
    for name in snapshot:
        relative = Path(name)
        if not (
            name.endswith((".tf", ".tf.json", ".tftest.hcl"))
            or relative.name == ".terraform.lock.hcl"
        ):
            continue
        if any(p in {".terraform", ".git", ".p4-artifacts"} for p in relative.parts):
            raise ValueError("InvalidTrackedTerraformPath")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write((repository / relative).read_bytes())


def isolated_environment(work):
    # Ignore implicit CLI config, credentials, plugin caches and command injection knobs.
    config = work / "terraform.rc"
    config.write_text("provider_installation {\n  direct {}\n}\n", encoding="utf-8")
    empty = work / "empty-aws-config"
    empty.write_text("", encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith(("AWS_", "TF_", "TERRAFORM_"))
    }
    env.update(
        TF_CLI_CONFIG_FILE=str(config),
        TF_IN_AUTOMATION="true",
        CHECKPOINT_DISABLE="1",
        AWS_EC2_METADATA_DISABLED="true",
        AWS_CONFIG_FILE=str(empty),
        AWS_SHARED_CREDENTIALS_FILE=str(empty),
    )
    return env


def validate(repository, temp_parent):
    repository = Path(repository).resolve()
    snapshot = tracked_snapshot(repository)
    work = Path(tempfile.mkdtemp(prefix="p4-offline-", dir=temp_parent)).resolve()
    copied = work / "checkout"
    try:
        copy_configuration(repository, copied, snapshot)
        env = isolated_environment(work)

        def terraform(root, *args):
            subprocess.run(
                ["terraform", *args], cwd=copied / "terraform" / root, env=env, check=True
            )

        for root in ROOTS:
            print("Validating " + root, flush=True)
            lock = copied / "terraform" / root / ".terraform.lock.hcl"
            before = lock.read_text(encoding="utf-8")
            # providers lock needs the local module manifest, but not a backend/provider init.
            terraform(root, "get", "-no-color")
            terraform(root, "providers", "lock", "-platform=linux_amd64")
            assert_additive(before, lock.read_text(encoding="utf-8"))
            terraform(root, "init", "-backend=false", "-input=false", "-lockfile=readonly")
            terraform(root, "validate", "-no-color")
        for root in ("modules/service", "bootstrap"):
            terraform(root, "test", "-no-color")
    finally:
        if tracked_snapshot(repository) != snapshot:
            raise ValueError("OriginalTerraformChanged")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=".")
    parser.add_argument("--temp-parent", required=True)
    args = parser.parse_args()
    validate(args.repository, args.temp_parent)


if __name__ == "__main__":
    main()
