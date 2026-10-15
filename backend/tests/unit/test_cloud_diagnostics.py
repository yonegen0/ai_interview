"""Public failures are finite codes, never raw values or success receipts."""

from types import SimpleNamespace

import pytest
from test_cloud_ci import environment, parent
from test_p4_tools import tool


@pytest.mark.parametrize("stage", ("toolchain", "state-before", "terraform-plan", "state-after"))
def test_round_trip_and_first_failure_wins(stage, capsys):
    module = tool("cloud_diagnostics")
    module.checkpoint(stage)
    module.emit(ValueError("PlanS3ScopeOrCountMismatch"))
    module.emit(ValueError("CloudPlanFailed"))
    text = capsys.readouterr().out
    assert text.count("::error") == 1
    assert module.parse(text.split("::")[-1].strip()) == {
        "stage": stage,
        "reason_code": "PlanS3ScopeOrCountMismatch",
    }


def test_unknown_exception_never_stringified_or_exported(capsys):
    module = tool("cloud_diagnostics")

    class SecretError(Exception):
        def __str__(self):
            pytest.fail("Raw exception string accessed")

    module.emit(SecretError("FAKE_TOKEN", {"State": "FAKE_STATE"}))
    text = capsys.readouterr().out
    assert "ExternalOrScopeFailure" in text and "FAKE" not in text


def test_hostile_exception_property_cannot_leak_chained_exception(capsys):
    module = tool("cloud_diagnostics")

    class SecretError(Exception):
        @property
        def reason_code(self):
            raise ValueError("FAKE_PRIVATE_VALUE")

    module.emit(SecretError("FAKE_TOKEN"))
    text = capsys.readouterr().out
    assert "ExternalOrScopeFailure" in text and "FAKE" not in text


@pytest.mark.parametrize(
    "text",
    (
        "P4D1|stage=state-before|reason=FAKE_TOKEN",
        "P4D1|stage=FAKE|reason=CloudPlanFailed",
        "P4D1|stage=state-before|reason=CloudPlanFailed\nFAKE_TOKEN",
        None,
        {},
    ),
)
def test_unknown_or_injected_annotation_is_ignored(text):
    assert tool("cloud_diagnostics").parse(text) is None


def test_cloud_entry_exception_is_fail_closed_and_safe(monkeypatch, capsys):
    module = tool("cloud_ci")
    diag = tool("cloud_diagnostics")
    monkeypatch.setattr(module, "diagnostic", diag)

    def prepare(_):
        diag.checkpoint("parent-binding")
        raise ValueError("FAKE_SECRET_INPUT")

    monkeypatch.setattr(module, "prepare", prepare)
    assert module.main() == 1
    text = capsys.readouterr()
    assert "parent-binding" in text.out and "ExternalOrScopeFailure" in text.out
    assert "FAKE" not in text.out + text.err


def test_deploy_preflight_failure_records_earliest_stage(monkeypatch, capsys):
    module = tool("ci_deploy")
    import cloud_diagnostics as diag

    monkeypatch.setattr(diag, "REPORTED", False)
    monkeypatch.setenv("P4_CLOUD_ACTIVE", "true")

    def refuse(_):
        raise ValueError("ClosedInitialDeploymentRequired")

    monkeypatch.setattr(module, "preflight", refuse)
    assert module.main() == 1
    assert (
        "stage=deploy-preflight|reason=ClosedInitialDeploymentRequired" in capsys.readouterr().out
    )


def test_new_publication_base_preserves_historical_baseline():
    import hashlib
    import json
    from datetime import UTC, datetime

    module = tool("cloud_ci")
    p = parent() | {
        "base_commit": "2c6bf56d8de898554385c3cbc41e8fd1c2270a00",
        "baseline_base_commit": parent()["base_commit"],
    }
    raw = json.dumps(p)
    assert (
        module.validate_parent(
            raw,
            hashlib.sha256(raw.encode()).hexdigest(),
            environment(),
            "b" * 40,
            datetime(2026, 10, 14, 13, tzinfo=UTC),
        )
        == p
    )
    p["baseline_base_commit"] = "f" * 40
    raw = json.dumps(p)
    with pytest.raises(ValueError, match="CloudSourceMismatch"):
        module.validate_parent(
            raw,
            hashlib.sha256(raw.encode()).hexdigest(),
            environment(),
            "b" * 40,
            datetime(2026, 10, 14, 13, tzinfo=UTC),
        )


def test_allowlisted_reason_uses_field_without_private_message():
    assert (
        tool("cloud_diagnostics").code(SimpleNamespace(reason_code="PlanProcessFailed"))
        == "PlanProcessFailed"
    )
