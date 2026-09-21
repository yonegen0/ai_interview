"""Offline CI lock augmentation and deterministic package safety contracts."""

import json
import sys
import zipfile
from pathlib import Path

import pytest
from test_p4_tools import tool


def lock_text(version="1.0.0", hashes=None, address="registry.terraform.io/hashicorp/aws"):
    hashes = hashes or ["zh:" + "a" * 64]
    return (
        f'provider "{address}" {{\nversion = "{version}"\n'
        'constraints = ">= 1.0.0"\nhashes = [' + ",".join(json.dumps(h) for h in hashes) + ",]\n}"
    )


def test_lock_allows_only_additive_hashes_and_formatting():
    module = tool("offline_terraform")
    before = lock_text()
    after = "/* comment */\n" + lock_text(hashes=["zh:" + "b" * 64, "zh:" + "a" * 64])
    module.assert_additive(before, before)
    module.assert_additive(before, after + "\n// trailing\n# comment")


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "constraints",
        "provider",
        "remove",
        "replace",
        "field",
        "trailing",
        "duplicate",
        "expression",
        "syntax",
    ],
)
def test_lock_rejects_non_additive_or_unknown_changes(change):
    before = lock_text()
    after = {
        "version": lock_text(version="2.0.0"),
        "constraints": before.replace(">= 1.0.0", ">= 2.0.0"),
        "provider": before + lock_text(address="registry.terraform.io/hashicorp/random"),
        "remove": "",
        "replace": lock_text(hashes=["zh:" + "b" * 64]),
        "field": before.replace("version =", 'extra = "x"\nversion ='),
        "trailing": before + "garbage",
        "duplicate": before + before,
        "expression": before.replace('"1.0.0"', '"${var.version}"'),
        "syntax": before.replace("hashes = [", "hashes = [!"),
    }[change]
    with pytest.raises(ValueError):
        tool("offline_terraform").assert_additive(before, after)


def test_copy_only_configuration_and_strip_environment(tmp_path, monkeypatch):
    module = tool("offline_terraform")
    repo, dest = tmp_path / "repo", tmp_path / "copy"
    names = [
        "terraform/bootstrap/main.tf",
        "terraform/bootstrap/.terraform.lock.hcl",
        "terraform/bootstrap/tests/contract.tftest.hcl",
        "terraform/bootstrap/settings.tfvars",
        "terraform/bootstrap/terraform.tfstate",
        "terraform/environments/dev/backend-dev.hcl",
    ]
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    module.copy_configuration(repo, dest, dict.fromkeys(names, "unused"))
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == sorted(
        names[:3]
    )
    for name in ("AWS_ACCESS_KEY_ID", "TF_CLI_ARGS", "TF_PLUGIN_CACHE_DIR", "TERRAFORM_CONFIG"):
        monkeypatch.setenv(name, "synthetic-secret")
    env = module.isolated_environment(tmp_path)
    assert "synthetic-secret" not in env.values()
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"


@pytest.mark.parametrize("failure", [None, "selection", "command", "original"])
def test_terraform_orchestration_preserves_original_and_checks_before_init(
    tmp_path, monkeypatch, failure
):
    module = tool("offline_terraform")
    repository = tmp_path / "repo"
    snapshot = {}
    for root in module.ROOTS:
        name = f"terraform/{root}/.terraform.lock.hcl"
        path = repository / name
        path.parent.mkdir(parents=True)
        path.write_text(lock_text())
        snapshot[name] = "original"
    reads = []

    def tracked(path):
        reads.append(path)
        return snapshot if len(reads) == 1 or failure != "original" else {}

    calls = []

    def run(command, *, cwd, env, check):
        calls.append(command[1:])
        assert cwd.is_relative_to(tmp_path) and not cwd.is_relative_to(repository)
        assert check and env["AWS_EC2_METADATA_DISABLED"] == "true"
        if command[1:3] == ["providers", "lock"]:
            if failure == "command":
                raise module.subprocess.CalledProcessError(1, command)
            (cwd / ".terraform.lock.hcl").write_text(
                lock_text(version="2.0.0")
                if failure == "selection"
                else lock_text(hashes=["zh:" + "a" * 64, "zh:" + "b" * 64])
            )

    monkeypatch.setattr(module, "tracked_snapshot", tracked)
    monkeypatch.setattr(module.subprocess, "run", run)
    if failure:
        with pytest.raises((ValueError, module.subprocess.CalledProcessError)):
            module.validate(repository, tmp_path)
    else:
        module.validate(repository, tmp_path)
        assert len(calls) == 18
        assert sum(c[0] == "test" for c in calls) == 2
    assert len(reads) == 2
    if failure in {"selection", "command"}:
        assert len(calls) == 2
        assert calls[0] == ["get", "-no-color"]
    assert all((repository / name).read_text() == lock_text() for name in snapshot)


@pytest.fixture
def package(tmp_path):
    module = tool("build_lambda")
    source, deps = tmp_path / "source", tmp_path / "deps"
    (source / "assets").mkdir(parents=True)
    (source / "assets/questions.json").write_text("[]")
    (source / "__init__.py").write_text("")
    deps.mkdir()
    names = ("boto3", "botocore", "pydantic", "pydantic-core", "annotated-types")
    for name in names:
        metadata = deps / (name.replace("-", "_") + "-1.0.dist-info")
        metadata.mkdir()
        (metadata / "METADATA").write_text(f"Name: {name}\nVersion: 1.0\n")
    (deps / "pydantic_core").mkdir()
    (deps / "pydantic_core/_pydantic_core.cpython-314-x86_64-linux-gnu.so").write_bytes(
        b"synthetic"
    )
    (deps / "annotated_types").mkdir()
    (deps / "annotated_types/test_cases.py").write_text("# wheel test helper")
    lock = tmp_path / "uv.lock"
    lock.write_text("\n".join(f'[[package]]\nname="{n}"\nversion="1.0"' for n in names))
    return module, source, deps, lock, tmp_path / "app.zip"


def build(package, output=None):
    module, source, deps, lock, default = package
    return module.build(source, deps, lock, output or default, "a" * 40)


def test_wheel_test_helper_is_excluded_and_zip_is_deterministic(package):
    first = build(package)
    second = build(package, package[-1].with_name("second.zip"))
    assert first == second
    with zipfile.ZipFile(package[-1]) as archive:
        assert "annotated_types/test_cases.py" not in archive.namelist()
        assert "interview_backend/assets/questions.json" in archive.namelist()


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("version", "DependencyLockMismatch"),
        ("missing", "RuntimeDependenciesMissing"),
        ("windows", "CPython314LinuxX86WheelRequired"),
        ("arm", "CPython314LinuxX86WheelRequired"),
        ("abi", "CPython314LinuxX86WheelRequired"),
        ("free_threaded", "CPython314LinuxX86WheelRequired"),
        ("unsafe", "UnsafePackageContent"),
        ("source_test", "UnsafePackageContent"),
        ("duplicate", "DuplicatePackagePath"),
        ("asset", "QuestionAssetMissing"),
        ("existing", "FreshSeparateOutputRequired"),
        ("symlink", "SymlinksNotAllowed"),
    ],
)
def test_package_safety_rejections(package, monkeypatch, kind, reason):
    module, source, deps, lock, output = package
    if kind == "version":
        lock.write_text(lock.read_text().replace('version="1.0"', 'version="2.0"'))
    elif kind == "missing":
        (deps / "boto3-1.0.dist-info/METADATA").write_text("Name: annotated-types\nVersion: 1.0\n")
    elif kind in {"windows", "arm", "abi", "free_threaded"}:
        native = next((deps / "pydantic_core").glob("*.so"))
        new = {
            "windows": "_pydantic_core.pyd",
            "arm": "_pydantic_core.cpython-314-aarch64-linux-gnu.so",
            "abi": "_pydantic_core.cpython-313-x86_64-linux-gnu.so",
            "free_threaded": "_pydantic_core.cpython-314t-x86_64-linux-gnu.so",
        }[kind]
        native.rename(native.with_name(new))
    elif kind == "unsafe":
        (deps / "test_other.py").write_text("synthetic")
    elif kind == "source_test":
        (source / "test_cases.py").write_text("synthetic")
    elif kind == "duplicate":
        (deps / "interview_backend").mkdir()
        (deps / "interview_backend/__init__.py").write_text("")
    elif kind == "asset":
        (source / "assets/questions.json").rename(source / "assets/other.json")
    elif kind == "existing":
        output.write_bytes(b"preserve")
    else:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "test_cases.py" or original(p))
    with pytest.raises(module.PackageBuildError, match=reason):
        build(package)


@pytest.mark.parametrize("unknown", [False, True])
def test_package_cli_failure_is_safe(package, monkeypatch, capsys, unknown):
    module, source, deps, lock, output = package
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_lambda",
            "--source",
            str(source),
            "--dependencies",
            str(deps),
            "--lock",
            str(lock),
            "--output",
            str(output),
            "--code-sha",
            "invalid",
            "--manifest",
            str(output.with_suffix(".json")),
        ],
    )
    if unknown:

        def fail(*args):
            raise RuntimeError("synthetic-secret")

        monkeypatch.setattr(module, "build", fail)
    assert module.main() == 1
    captured = capsys.readouterr()
    assert not captured.out and "synthetic-secret" not in captured.err
    failure = json.loads(captured.err)
    assert failure["failure"] == "PackageBuildFailed"
    assert failure["reason_code"] == (
        "UnexpectedPackageBuildFailure" if unknown else "FullCodeShaRequired"
    )


def test_package_cli_success_and_existing_manifest(package, monkeypatch):
    module, source, deps, lock, output = package
    manifest = output.with_suffix(".json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_lambda",
            "--source",
            str(source),
            "--dependencies",
            str(deps),
            "--lock",
            str(lock),
            "--output",
            str(output),
            "--code-sha",
            "a" * 40,
            "--manifest",
            str(manifest),
        ],
    )
    assert module.main() == 0
    before = manifest.read_bytes()
    assert json.loads(before)["schema_version"] == 1
    assert module.main() == 1
    assert manifest.read_bytes() == before
