"""The pinned crypto wheel's exact test stub is omitted; safety rules remain."""

import zipfile

import pytest
from test_p4_offline_ci import build, package  # noqa: F401

STUB = "cryptography/hazmat/bindings/_rust/test_support.pyi"


def test_crypto_test_stub_and_record_entry_are_excluded(package):  # noqa: F811
    _, _, deps, _, output = package
    stub = deps / STUB
    stub.parent.mkdir(parents=True)
    stub.write_text("# synthetic non-runtime typing stub")
    name = "annotated_types-1.0.dist-info/RECORD"
    (deps / name).write_text(f"{STUB},sha256=omitted,1\n{name},,\n")
    first = build(package)
    second = build(package, output.with_name("second.zip"))
    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(output) as archive:
        assert STUB not in archive.namelist()
        assert archive.read(name).decode() == f"{name},,\n"


@pytest.mark.parametrize("kind", ["executable", "sibling", "source", "symlink"])
def test_crypto_exclusion_never_allows_other_test_code_or_links(package, monkeypatch, kind):  # noqa: F811
    module, source, deps, _, _ = package
    name = STUB
    root = deps
    if kind == "executable":
        name = name.replace(".pyi", ".py")
    elif kind == "sibling":
        name = name.replace("test_support.pyi", "test_other.pyi")
    elif kind == "source":
        root = source
    file = root / name
    file.parent.mkdir(parents=True)
    file.write_text("# synthetic")
    if kind == "symlink":
        original = type(file).is_symlink
        monkeypatch.setattr(type(file), "is_symlink", lambda path: path == file or original(path))
    with pytest.raises(
        module.PackageBuildError,
        match="SymlinksNotAllowed" if kind == "symlink" else "UnsafePackageContent",
    ):
        build(package)
