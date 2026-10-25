"""Strict synthetic-only raw State/Plan JSON candidate compatibility checks."""

import json
from copy import deepcopy

import pytest
from test_candidate_state_json_contract import synthetic_plan
from test_p4_tools import tool


@pytest.fixture
def plans():
    before, candidate = synthetic_plan("1.14.9"), synthetic_plan("1.16.7")
    for document in (before, candidate):
        for stage in ("prior_state", "planned_values"):
            root = (
                document[stage]["values"]["root_module"]
                if stage == "prior_state"
                else document[stage]["root_module"]
            )
            for resource in root["resources"]:
                resource["schema_version"] = 0
                resource["sensitive_values"] = {"id": True}
    return before, candidate


def test_synthetic_plan_noop_with_sensitive_metadata_remains_non_authorizing(plans):
    result = tool("candidate_state_snapshot_review").compare_offline_plans(*plans)
    assert result == {
        "status": "CANDIDATE_SYNTHETIC_NOOP_NOT_APPLY_APPROVAL",
        "authorized": False,
        "resources": 2,
        "real_state_compatibility_proven": False,
    }


@pytest.mark.parametrize(
    "change",
    [
        "proposed-unknown",
        "proposed-malformed",
        "after-unknown",
        "malformed-after-unknown",
        "deferred",
        "malformed-deferred",
        "action-invocations",
        "resource-drift",
        "missing-schema",
        "schema-upgrade",
        "invalid-sensitive-mask",
        "deposed",
        "missing-prior",
    ],
)
def test_candidate_plan_risks_fail_closed(plans, change):
    module = tool("candidate_state_snapshot_review")
    before, candidate = plans
    if change == "proposed-unknown":
        candidate["proposed_unknown"] = {
            "root_module": {
                "resources": [{"address": "aws_api_gateway_rest_api.main", "values": {"id": True}}]
            }
        }
    elif change == "proposed-malformed":
        candidate["proposed_unknown"] = {
            "root_module": {
                "resources": [
                    {"address": "aws_api_gateway_rest_api.main", "values": {"id": "unknown"}}
                ]
            }
        }
    elif change == "after-unknown":
        candidate["resource_changes"][0]["change"]["after_unknown"] = {"id": True}
    elif change == "malformed-after-unknown":
        candidate["resource_changes"][0]["change"]["after_unknown"] = {"id": "unknown"}
    elif change == "deferred":
        candidate["deferred_changes"] = [{"reason": "instance_count_unknown"}]
    elif change == "malformed-deferred":
        candidate["deferred_changes"] = {}
    elif change == "action-invocations":
        candidate["action_invocations"] = [{"unapproved": True}]
    elif change == "resource-drift":
        candidate["resource_drift"] = [{"address": "aws_sns_topic.main"}]
    elif change == "missing-schema":
        del candidate["planned_values"]["root_module"]["resources"][0]["schema_version"]
    elif change == "schema-upgrade":
        candidate["planned_values"]["root_module"]["resources"][0]["schema_version"] = 1
    elif change == "invalid-sensitive-mask":
        candidate["prior_state"]["values"]["root_module"]["resources"][0]["sensitive_values"] = {
            "id": "private"
        }
    elif change == "deposed":
        candidate["resource_changes"][0]["deposed"] = "deadbeef"
    elif change == "missing-prior":
        del candidate["prior_state"]["values"]
    with pytest.raises(ValueError):
        module.compare_offline_plans(before, candidate)


def test_false_proposed_unknown_without_hidden_changes_is_reviewable(plans):
    before, candidate = plans
    candidate["proposed_unknown"] = {
        "root_module": {
            "resources": [{"address": "aws_api_gateway_rest_api.main", "values": {"id": False}}]
        }
    }
    result = tool("candidate_state_snapshot_review").compare_offline_plans(before, candidate)
    assert result["authorized"] is False


def test_minor_version_json_remains_reviewable_but_never_authorized(plans):
    before, candidate = plans
    before["format_version"] = "1.2"
    candidate["format_version"] = "1.2"
    assert tool("candidate_state_snapshot_review").compare_offline_plans(
        before, candidate
    )["authorized"] is False


def test_local_raw_state_bytes_never_prove_remote_version():
    module = tool("candidate_state_snapshot_review")
    raw = json.dumps(
        {
            "version": 4,
            "terraform_version": "1.14.9",
            "lineage": "local-synthetic-lineage",
            "serial": 8,
            "resources": [],
            "outputs": {},
        },
        sort_keys=True,
    ).encode()
    identity = {
        "lineage": "local-synthetic-lineage",
        "serial": 8,
        "version_id": "claimed-s3-version-id",
        "sha256": module.preflight.sha(raw),
    }
    result = module.inspect_raw_state(raw, identity)
    assert result["authorized"] is False
    assert result["remote_version_id_proven"] is False
    assert result["provider_upgrader_proven"] is False
    with pytest.raises(ValueError, match="CandidateRawStateDigestMismatch"):
        module.inspect_raw_state(raw + b" ", identity)
    with pytest.raises(ValueError, match="CandidateRawStateIdentityMismatch"):
        module.inspect_raw_state(raw, identity | {"serial": 9})
    invalid_raw = json.dumps({**json.loads(raw), "serial": True}).encode()
    with pytest.raises(ValueError, match="CandidateRawStateIdentityMismatch"):
        module.inspect_raw_state(
            invalid_raw, identity | {"sha256": module.preflight.sha(invalid_raw)}
        )


def test_legacy_candidate_json_comparison_is_not_an_approval(plans):
    before, candidate = deepcopy(plans)
    result = tool("candidate_state_snapshot_review").compare_offline_plans(before, candidate)
    assert result["status"] == "CANDIDATE_SYNTHETIC_NOOP_NOT_APPLY_APPROVAL"


@pytest.mark.parametrize("invalid_format", [None, "2.0", "1.0.0", True])
def test_show_json_major_version_or_missing_format_is_rejected(plans, invalid_format):
    before, candidate = plans
    if invalid_format is None:
        del candidate["format_version"]
    else:
        candidate["format_version"] = invalid_format
    with pytest.raises(ValueError, match="CandidatePlanFormatVersionUnsupported"):
        tool("candidate_state_snapshot_review").compare_offline_plans(before, candidate)


def test_raw_state_rejects_duplicate_keys_and_nonfinite_json():
    module = tool("candidate_state_snapshot_review")
    raw = b'{"version":4,"lineage":"synthetic","serial":1,"serial":1,"resources":[],"outputs":{}}'
    identity = {
        "lineage": "synthetic",
        "serial": 1,
        "version_id": "synthetic-id",
        "sha256": module.preflight.sha(raw),
    }
    with pytest.raises(ValueError, match="CandidateRawStateMalformed"):
        module.inspect_raw_state(raw, identity)
    raw = raw.replace(b'"serial":1,"serial":1', b'"serial":NaN')
    with pytest.raises(ValueError, match="CandidateRawStateMalformed"):
        module.inspect_raw_state(raw, identity | {"sha256": module.preflight.sha(raw)})
