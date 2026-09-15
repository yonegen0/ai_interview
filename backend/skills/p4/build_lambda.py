"""Build a deterministic Lambda ZIP from explicitly staged Linux dependencies."""

import argparse
import base64
import hashlib
import importlib.metadata
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path


def build(source, dependencies, lock, output, code_sha):
    if re.fullmatch(r"[0-9a-f]{40}", code_sha) is None:
        raise ValueError("FullCodeShaRequired")
    source, dependencies, lock, output = map(Path, (source, dependencies, lock, output))
    source = source.resolve(strict=True)
    dependencies = dependencies.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(source) or output.is_relative_to(dependencies) or output.exists():
        raise ValueError("FreshSeparateOutputRequired")
    locked = tomllib.loads(lock.read_text(encoding="utf-8"))
    versions = {p["name"]: p["version"] for p in locked["package"]}
    installed = {}
    for distribution in importlib.metadata.distributions(path=[str(dependencies)]):
        name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"]).lower()
        if name not in versions or distribution.version != versions[name]:
            raise ValueError("DependencyLockMismatch")
        if name in {"pytest", "ruff", "hatchling", "interview-backend"}:
            raise ValueError("NonRuntimeDependency")
        installed[name] = distribution.version
    if not {"boto3", "botocore", "pydantic", "pydantic-core"} <= installed.keys():
        raise ValueError("RuntimeDependenciesMissing")
    native = list(dependencies.glob("pydantic_core/*.so"))
    if (
        len(native) != 1
        or "x86_64-linux-gnu" not in native[0].name
        or "cpython-314" not in native[0].name
    ):
        raise ValueError("CPython314LinuxX86WheelRequired")
    files = {}
    for root, prefix in ((source, "interview_backend"), (dependencies, "")):
        for file in root.rglob("*"):
            if file.is_symlink():
                raise ValueError("SymlinksNotAllowed")
            if not file.is_file():
                continue
            relative = file.relative_to(root)
            if (
                any(p in {"__pycache__", "bin", "Scripts"} for p in relative.parts)
                or file.suffix == ".pyc"
            ):
                continue
            if any(
                p in {"tests", "test_support", "fault_injection", ".venv", ".aws", ".git"}
                or p.startswith((".env", "hard_stop", "test_"))
                for p in relative.parts
            ) or file.suffix in {".pyd", ".dll"}:
                raise ValueError("UnsafePackageContent")
            name = (Path(prefix) / relative).as_posix()
            if name in files:
                raise ValueError("DuplicatePackagePath")
            files[name] = file.read_bytes()
            if root == source and any(
                marker in files[name]
                for marker in (
                    b"P4_HARD_STOP",
                    b"P4_FAULT_INJECTION",
                    b"-----BEGIN PRIVATE KEY-----",
                )
            ):
                raise ValueError("UnsafePackageContent")
    if "interview_backend/assets/questions.json" not in files:
        raise ValueError("QuestionAssetMissing")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(output.read_bytes()).digest()
    return {
        "schema_version": 1,
        "code_sha": code_sha,
        "sha256": digest.hex(),
        "sha256_base64": base64.b64encode(digest).decode(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "runtime": "python3.14",
        "architecture": "x86_64",
        "dependencies": installed,
    }


def main():
    parser = argparse.ArgumentParser()
    for flag in ("source", "dependencies", "lock", "output", "code-sha", "manifest"):
        parser.add_argument(f"--{flag}", required=True)
    args = parser.parse_args()
    try:
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            raise ValueError("FreshManifestRequired")
        result = build(args.source, args.dependencies, args.lock, args.output, args.code_sha)
        manifest_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except Exception:
        print("PackageBuildFailed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
