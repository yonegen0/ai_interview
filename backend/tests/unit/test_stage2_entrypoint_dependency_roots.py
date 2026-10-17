"""Hosted dependency placement preserves source checks and import restrictions."""

import json
from pathlib import Path

import pytest

from skills.p4.stage2_development import ci_entrypoint, entrypoints


@pytest.fixture
def installed(tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    backend.mkdir()
    site = backend / ".venv/lib/python3.14/site-packages"
    site.mkdir(parents=True)
    monkeypatch.setattr(entrypoints.sysconfig, "get_path", lambda name: str(site))
    return backend, site


def test_nested_installed_dependency_is_not_application_source(installed):
    backend, site = installed
    (backend / "layout_app.py").write_text("import layout_dependency\n")
    (site / "layout_dependency.py").write_text(
        "if False:\n    import optional_dependency_not_installed\n"
    )
    result = entrypoints.inspect([backend], ["layout_app"])
    assert result["passed"]
    assert {row["module"] for row in result["files"]} == {"layout_app"}
    assert result["import_passed"] is True


def test_missing_application_import_remains_an_error(installed):
    backend, _ = installed
    (backend / "missing_app.py").write_text("import mandatory_module_not_installed\n")
    result = entrypoints.inspect([backend], ["missing_app"])
    assert not result["passed"]
    assert any(issue["code"] == "ImportMissing" for issue in result["issues"])


def test_sibling_dependency_name_does_not_exclude_application_source(installed):
    backend, site = installed
    sibling = Path(str(site) + "-app")
    sibling.mkdir()
    (sibling / "sibling_app.py").write_text("import mandatory_module_not_installed\n")
    result = entrypoints.inspect([backend, sibling], ["sibling_app"])
    assert not result["passed"]
    assert any(issue["code"] == "ImportMissing" for issue in result["issues"])


def test_installed_dependency_side_effect_is_still_denied(installed):
    backend, site = installed
    target = backend / "unexpected-write.txt"
    (backend / "side_effect_app.py").write_text("import side_effect_dependency\n")
    (site / "side_effect_dependency.py").write_text(f"open({str(target)!r}, 'w').write('denied')\n")
    result = entrypoints.inspect([backend], ["side_effect_app"])
    assert result["static_passed"]
    assert not result["passed"]
    assert any("open-write" in issue.get("denied_events", []) for issue in result["issues"])
    assert not target.exists()


def test_qualification_failure_exports_existing_bound_finite_schema(tmp_path, monkeypatch):
    import cloud_failure_json

    from skills.p4 import cloud_diagnostics

    for key, value in {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "P4_CLOUD_PARENT_SHA256": "b" * 64,
        "P4_CLOUD_FAILURE_JSON": "true",
        "P4_CLOUD_FAILURE_JSON_SCHEMA": "2",
    }.items():
        monkeypatch.setenv(key, value)
    backend = Path(__file__).resolve().parents[2]
    ci_entrypoint.persist_failure(backend)
    result = json.loads((tmp_path / "p4-public-diagnostic/diagnostic.json").read_bytes())
    assert result["schema_version"] == 2 and result["process_failure"] is None
    assert result["stage"] in cloud_diagnostics.STAGES
    assert result["reason_code"] == "ModuleLoadFailed"
    assert result["source_sha"] == "a" * 40
    assert result["command_kind"] == "unknown"
    assert "issues" not in result and "exception" not in result
    assert callable(cloud_failure_json.persist)


def test_qualification_diagnostic_rejects_missing_binding(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    backend = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="BindingInvalid"):
        ci_entrypoint.persist_failure(backend)
    assert not (tmp_path / "p4-public-diagnostic").exists()


def test_ci_failure_persists_diagnostic_and_exports_only_codes(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ci_entrypoint", "."])
    monkeypatch.setenv("P4_CLOUD_FAILURE_JSON", "true")
    monkeypatch.setattr(
        ci_entrypoint,
        "qualify_ci",
        lambda backend: {
            "passed": False,
            "issues": [{"code": "ImportMissing", "module": "PRIVATE_IMPORT_DETAIL"}],
        },
    )
    calls = []
    monkeypatch.setattr(ci_entrypoint, "persist_failure", lambda backend: calls.append(backend))
    assert ci_entrypoint.main() == 1 and calls == [Path(".")]
    output = capsys.readouterr().out
    assert "PRIVATE_IMPORT_DETAIL" not in output
    assert json.loads(output) == {
        "passed": False,
        "READY": False,
        "issue_codes": ["ImportMissing"],
    }


def test_ci_diagnostic_failure_preserves_failed_status(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ci_entrypoint", "."])
    monkeypatch.setenv("P4_CLOUD_FAILURE_JSON", "true")
    monkeypatch.setattr(
        ci_entrypoint,
        "qualify_ci",
        lambda backend: {"passed": False, "issues": [{"code": "ImportMissing"}]},
    )

    def unavailable(backend):
        raise ValueError("PRIVATE_EXCEPTION_DETAIL")

    monkeypatch.setattr(ci_entrypoint, "persist_failure", unavailable)
    assert ci_entrypoint.main() == 1
    output = capsys.readouterr().out
    assert "PRIVATE_EXCEPTION_DETAIL" not in output
    assert json.loads(output)["issue_codes"] == [
        "EntrypointDiagnosticUnavailable",
        "ImportMissing",
    ]
