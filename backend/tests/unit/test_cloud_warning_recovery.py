"""Finite warning diagnostics; no real Terraform, services, or operator keys."""

import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("kind", ("version", "init", "plan", "show"))
def test_warning_json_has_only_finite_metadata(tmp_path, monkeypatch, capsys, kind):
    import cloud_diagnostics as diag
    import cloud_process_output as output

    monkeypatch.setattr(diag, "REPORTED", False)
    monkeypatch.setattr(diag, "CURRENT", "terraform-plan")
    for key, value in {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_RUN_ID": "7",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "P4_CLOUD_PARENT_SHA256": "b" * 64,
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "P4_CLOUD_FAILURE_JSON": "true",
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(output.OutputRefusal) as caught:
        output.inspect(
            SimpleNamespace(directory=tmp_path, sequence=1),
            kind,
            b"Warning: FAKE_PRIVATE_WARNING\n",
            b"FAKE_PRIVATE_STDERR",
        )
    diag.emit(caught.value)
    raw = (tmp_path / "p4-public-diagnostic/diagnostic.json").read_text()
    value = json.loads(raw)
    assert value["command_kind"] == kind and value["warning_count"] == 1
    assert value["warning_class"] == "Unclassified"
    assert value["status"] == "FAILURE_DIAGNOSTIC_ONLY"
    assert "FAKE" not in raw + capsys.readouterr().out
    assert len(list(tmp_path.glob("*.private.raw"))) == 2


def test_no_warning_returns_and_preserves_private_bytes(tmp_path):
    import cloud_process_output as output

    output.inspect(SimpleNamespace(directory=tmp_path, sequence=1), "init", b"FAKE_PRIVATE", b"")
    assert (tmp_path / "process-0001-init-stdout.private.raw").read_bytes() == b"FAKE_PRIVATE"


def test_masked_identifier_is_rejected_without_reconstruction():
    import cloud_diagnostics as diag

    assert (
        diag.parse("P***D1|stage=terraform-plan|reason=CloudImportantWarningUnclassified") is None
    )


def test_json_save_failure_and_broken_stdout_cannot_leak(monkeypatch):
    import cloud_diagnostics as diag
    import cloud_failure_json as writer

    monkeypatch.setattr(diag, "REPORTED", False)
    monkeypatch.setenv("P4_CLOUD_FAILURE_JSON", "true")

    def refuse(*args, **kwargs):
        raise OSError("FAKE_PRIVATE_ERROR")

    monkeypatch.setattr(writer, "persist", refuse)
    monkeypatch.setattr("builtins.print", refuse)
    assert diag.emit(ValueError("FAKE_PRIVATE_ORIGINAL")) is None
