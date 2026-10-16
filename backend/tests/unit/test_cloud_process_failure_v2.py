"""Finite v2 diagnostics have no arbitrary text and stay informational."""

import json

import pytest


def metadata():
    return {
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "P4_CLOUD_PARENT_SHA256": "b" * 64,
    }


def context():
    from process_failure_contract import build_context

    return build_context(
        {
            "returncode": 1,
            "diagnostic_hints": ["authorization-denied-marker"],
            "classification_complete": True,
        },
        metadata(),
        "plan",
        4,
    )


def test_v2_writer_exports_only_bound_finite_context(tmp_path, monkeypatch):
    import cloud_failure_json
    from cloud_process_output import ProcessFailure

    for key, value in {
        **metadata(),
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "P4_CLOUD_FAILURE_JSON_SCHEMA": "2",
    }.items():
        monkeypatch.setenv(key, value)
    cloud_failure_json.persist(
        "terraform-plan", "PlanProcessFailed", "plan", ProcessFailure(context())
    )
    value = json.loads((tmp_path / "p4-public-diagnostic/diagnostic.json").read_bytes())
    assert value["schema_version"] == 2 and value["process_failure"] == context()
    assert value["process_failure"]["hints_are_root_cause_proof"] is False


@pytest.mark.parametrize(
    "field,value",
    (
        ("returncode", True),
        ("returncode", 0),
        ("diagnostic_hints", ["PRIVATE_ERROR"]),
        ("diagnostic_id", "a" * 64),
        ("private_event_sequence", 5),
    ),
)
def test_context_change_or_arbitrary_text_is_rejected(field, value):
    from process_failure_contract import validate_context

    item = context()
    item[field] = value
    binding = {
        "run_id": "123",
        "run_attempt": "1",
        "source_sha": "a" * 40,
        "parent_sha256": "b" * 64,
    }
    with pytest.raises(ValueError):
        validate_context(item, binding, "plan")


def test_v2_nonzero_failure_requires_context(tmp_path, monkeypatch):
    import cloud_failure_json

    for key, value in {
        **metadata(),
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "P4_CLOUD_FAILURE_JSON_SCHEMA": "2",
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="ShapeInvalid"):
        cloud_failure_json.persist(
            "terraform-plan", "PlanProcessFailed", "plan", ValueError("PRIVATE_ERROR")
        )
    assert not (tmp_path / "p4-public-diagnostic").exists()
