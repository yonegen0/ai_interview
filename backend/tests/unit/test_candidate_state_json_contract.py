"""Synthetic API Gateway identity and SNS computed State/Plan regression coverage.

No remote State, provider downloads or AWS access. A synthetic no-op is not an
adoption/Apply approval, even if all assertions pass.
"""

from copy import deepcopy

import pytest
from test_p4_tools import tool

AWS = "registry.terraform.io/hashicorp/aws"
API = "aws_api_gateway_rest_api"
SNS = "aws_sns_topic"
ADDR_API = "aws_api_gateway_rest_api.main"
ADDR_SNS = "aws_sns_topic.main"


def schema():
    return {
        "format_version": "1.0",
        "provider_schemas": {
            AWS: {
                "resource_schemas": {
                    API: {
                        "version": 0,
                        "block": {
                            "attributes": {
                                "id": {"type": "string", "computed": True},
                                "name": {"type": "string", "required": True},
                            }
                        },
                    },
                    SNS: {
                        "version": 0,
                        "block": {
                            "attributes": {
                                "id": {"type": "string", "computed": True},
                                "name": {"type": "string", "required": True},
                            }
                        },
                    },
                }
            }
        },
    }


def synthetic_plan(version):
    resources = [
        {
            "address": ADDR_API,
            "mode": "managed",
            "type": API,
            "name": "main",
            "values": {"id": "synthetic-api-identity", "name": "synthetic"},
        },
        {
            "address": ADDR_SNS,
            "mode": "managed",
            "type": SNS,
            "name": "main",
            "values": {
                "id": "synthetic-topic-identity",
                "name": "synthetic",
                "maximum_message_size": 262144,
            },
        },
    ]
    return {
        "format_version": "1.0",
        "terraform_version": version,
        "complete": True,
        "errored": False,
        "applyable": True,
        "checks": [],
        "variables": {},
        "prior_state": {"values": {"root_module": {"resources": deepcopy(resources)}}},
        "planned_values": {"root_module": {"resources": deepcopy(resources)}},
        "resource_changes": [
            {
                "address": row["address"],
                "mode": "managed",
                "change": {
                    "actions": ["no-op"],
                    "before": deepcopy(row["values"]),
                    "after": deepcopy(row["values"]),
                    "after_unknown": {},
                },
            }
            for row in resources
        ],
        "output_changes": {},
    }


def test_synthetic_api_gateway_and_sns_noop_does_not_authorize_apply():
    checker = tool("toolchain_compatibility")
    before, after = synthetic_plan("1.14.9"), synthetic_plan("1.16.7")
    assert checker.assert_noop_plan_pair(before, after, "1.16.7") == {
        "status": "SYNTHETIC_NOOP_COMPATIBLE_NOT_APPLY_APPROVAL",
        "resources": 2,
    }


@pytest.mark.parametrize(
    "address,attribute,changed",
    [
        (ADDR_API, "id", "replaced-api-identity"),
        (ADDR_SNS, "maximum_message_size", 2048),
        (ADDR_SNS, "id", "replaced-sns-identity"),
    ],
)
def test_synthetic_default_and_resource_identity_drift_rejected(
    address, attribute, changed
):
    checker = tool("toolchain_compatibility")
    before, after = synthetic_plan("1.14.9"), synthetic_plan("1.16.7")
    for row in after["planned_values"]["root_module"]["resources"]:
        if row["address"] == address:
            row["values"][attribute] = changed
    with pytest.raises(ValueError, match="MigrationDefaultOrStateValuesChanged"):
        checker.assert_noop_plan_pair(before, after, "1.16.7")


@pytest.mark.parametrize(
    "change",
    ["moved-address", "create", "sns-computed-unknown", "api-id-unknown"],
)
def test_plan_change_or_unknown_requires_review(change):
    checker = tool("toolchain_compatibility")
    before, after = synthetic_plan("1.14.9"), synthetic_plan("1.16.7")
    row = after["resource_changes"][0 if change == "api-id-unknown" else 1]
    if change == "moved-address":
        row["previous_address"] = "aws_sns_topic.old"
    elif change == "create":
        row["change"]["actions"] = ["create"]
    elif change == "sns-computed-unknown":
        row["change"]["after_unknown"]["maximum_message_size"] = True
    else:
        row["change"]["after_unknown"]["id"] = True
    with pytest.raises(ValueError, match="MigrationResourceChangeOrUnknown"):
        checker.assert_noop_plan_pair(before, after, "1.16.7")


def test_sns_optional_computed_addition_does_not_prove_default_or_upgrader():
    checker = tool("toolchain_compatibility")
    original = schema()
    candidate = deepcopy(original)
    candidate["provider_schemas"][AWS]["resource_schemas"][SNS]["block"]["attributes"][
        "maximum_message_size"
    ] = {"type": "number", "optional": True, "computed": True}
    result = checker.compare_schemas(original, candidate, {API, SNS})
    assert result["additions"] == {SNS: "attributes.maximum_message_size"}
    assert result["defaults_and_state_upgraders_proven"] is False


@pytest.mark.parametrize("change", ["api-identity-schema", "state-upgrader", "sns-not-computed"])
def test_unreviewed_provider_schema_requires_manual_upgrade_evidence(change):
    checker = tool("toolchain_compatibility")
    original, candidate = schema(), schema()
    api = candidate["provider_schemas"][AWS]["resource_schemas"][API]
    sns = candidate["provider_schemas"][AWS]["resource_schemas"][SNS]
    if change == "api-identity-schema":
        api["block"]["attributes"]["id"]["optional"] = True
    elif change == "state-upgrader":
        api["version"] = 1
    else:
        sns["block"]["attributes"]["maximum_message_size"] = {
            "type": "number",
            "optional": True,
            "computed": False,
        }
    with pytest.raises(ValueError):
        checker.compare_schemas(original, candidate, {API, SNS})
