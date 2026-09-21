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
from contextvars import ContextVar
from pathlib import Path

STAGE = ContextVar("package_stage", default="arguments")
REASONS = frozenset(
    "FullCodeShaRequired FreshSeparateOutputRequired DependencyLockMismatch "
    "NonRuntimeDependency RuntimeDependenciesMissing CPython314LinuxX86WheelRequired "
    "SymlinksNotAllowed UnsafePackageContent DuplicatePackagePath QuestionAssetMissing "
    "FreshManifestRequired UnexpectedPackageBuildFailure".split()
)


class PackageBuildError(ValueError):
    """Only fixed classifications may cross the CLI boundary."""

    def __init__(self, reason):
        self.reason_code = reason if reason in REASONS else "UnexpectedPackageBuildFailure"
        self.stage = STAGE.get()
        super().__init__(self.reason_code)


def build(source, dependencies, lock, output, code_sha):
    token = STAGE.set("arguments")
    try:
        return _build(source, dependencies, lock, output, code_sha)
    except PackageBuildError:
        raise
    except Exception:
        raise PackageBuildError("UnexpectedPackageBuildFailure") from None
    finally:
        STAGE.reset(token)


def _build(source, dependencies, lock, output, code_sha):
    if re.fullmatch(r"[0-9a-f]{40}", code_sha) is None:
        raise PackageBuildError("FullCodeShaRequired")
    STAGE.set("paths")
    source, dependencies, lock, output = map(Path, (source, dependencies, lock, output))
    source = source.resolve(strict=True)
    dependencies = dependencies.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(source) or output.is_relative_to(dependencies) or output.exists():
        raise PackageBuildError("FreshSeparateOutputRequired")
    STAGE.set("lock")
    locked = tomllib.loads(lock.read_text(encoding="utf-8"))
    versions = {p["name"]: p["version"] for p in locked["package"]}
    STAGE.set("dependencies")
    installed = {}
    for distribution in importlib.metadata.distributions(path=[str(dependencies)]):
        name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"]).lower()
        if name not in versions or distribution.version != versions[name]:
            raise PackageBuildError("DependencyLockMismatch")
        if name in {"pytest", "ruff", "hatchling", "interview-backend"}:
            raise PackageBuildError("NonRuntimeDependency")
        installed[name] = distribution.version
    if not {"boto3", "botocore", "pydantic", "pydantic-core"} <= installed.keys():
        raise PackageBuildError("RuntimeDependenciesMissing")
    STAGE.set("native")
    native = list(dependencies.glob("pydantic_core/*.so"))
    if len(native) != 1 or native[0].name != "_pydantic_core.cpython-314-x86_64-linux-gnu.so":
        raise PackageBuildError("CPython314LinuxX86WheelRequired")
    STAGE.set("contents")
    files = {}
    for root, prefix in ((source, "interview_backend"), (dependencies, "")):
        for file in root.rglob("*"):
            if file.is_symlink() or file.is_junction():
                raise PackageBuildError("SymlinksNotAllowed")
            if not file.is_file():
                continue
            relative = file.relative_to(root)
            # The locked annotated-types wheel ships a test helper, not runtime code.
            # Exclude this exact dependency path; never allow arbitrary test_* files.
            if root == dependencies and relative.as_posix() == "annotated_types/test_cases.py":
                continue
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
                raise PackageBuildError("UnsafePackageContent")
            name = (Path(prefix) / relative).as_posix()
            if name in files:
                raise PackageBuildError("DuplicatePackagePath")
            files[name] = file.read_bytes()
            if root == source and any(
                marker in files[name]
                for marker in (
                    b"P4_HARD_STOP",
                    b"P4_FAULT_INJECTION",
                    b"-----BEGIN PRIVATE KEY-----",
                )
            ):
                raise PackageBuildError("UnsafePackageContent")
    if "interview_backend/assets/questions.json" not in files:
        raise PackageBuildError("QuestionAssetMissing")
    STAGE.set("archive")
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
        STAGE.set("manifest")
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            raise PackageBuildError("FreshManifestRequired")
        result = build(args.source, args.dependencies, args.lock, args.output, args.code_sha)
        with manifest_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    except Exception as error:
        failure = (
            error
            if isinstance(error, PackageBuildError)
            else PackageBuildError("UnexpectedPackageBuildFailure")
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "failure": "PackageBuildFailed",
                    "stage": failure.stage,
                    "reason_code": failure.reason_code,
                }
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
