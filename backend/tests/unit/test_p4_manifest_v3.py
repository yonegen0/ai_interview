"""Keep legacy v2 readbacks; independently verify complete ADMIN v3 readbacks."""

import copy
import json

import pytest
import test_p4_manifest_v2 as v2_fixtures
from test_p4_tools import tool


@pytest.fixture
def admin_deployment(monkeypatch):
    m, data, session = v2_fixtures.deployment.__wrapped__(monkeypatch)
    m["schema_version"] = 3
    a, r, p = m["account_id"], m["region"], "ai-interview-dev"
    m["versions"]["admin"] = "1"
    m["aliases"]["admin"] = f"arn:aws:lambda:{r}:{a}:function:{p}-admin:live"
    m["log_groups"] = {role: f"/aws/lambda/{p}-{role}" for role in m["versions"]}
    config = copy.deepcopy(data["lambda", "get_function_configuration", p + "-api"])
    config.update(
        Handler="interview_backend.aws_runtime.admin_handler",
        Role=f"arn:aws:iam::{a}:role/{p}-admin-runtime",
    )
    config["Environment"]["Variables"].update(
        INTERVIEW_COMPONENT="admin", INTERVIEW_FUNCTION_NAME=p + "-admin"
    )
    data["lambda", "get_function_configuration", p + "-admin"] = config
    data["lambda", "get_alias", m["aliases"]["admin"]] = {
        "AliasArn": m["aliases"]["admin"],
        "FunctionVersion": "1",
    }
    data["lambda", "get_function_concurrency", p + "-admin"] = {}
    data["iam", "get_role", p + "-admin-runtime"] = copy.deepcopy(
        data["iam", "get_role", p + "-api-runtime"]
    )
    data["logs", "describe_log_groups", m["log_groups"]["admin"]] = {
        "logGroups": [{"logGroupName": m["log_groups"]["admin"], "retentionInDays": 7}]
    }
    integration = copy.deepcopy(data["apigatewayv2", "get_integrations", ""]["Items"][0])
    integration.update(
        IntegrationId="admin-integration",
        IntegrationUri=f"arn:aws:apigateway:{r}:lambda:path/2015-03-31/functions/{m['aliases']['admin']}/invocations",
    )
    data["apigatewayv2", "get_integrations", ""]["Items"].append(integration)
    for route, target in (
        ("GET /practice-options", "integration"),
        ("GET /admin/question-bank", "admin-integration"),
        ("POST /admin/question-bank", "admin-integration"),
    ):
        data["apigatewayv2", "get_routes", ""]["Items"].append(
            {
                "RouteKey": route,
                "Target": "integrations/" + target,
                "AuthorizationType": "JWT",
                "AuthorizerId": "auth",
            }
        )
    table = f"arn:aws:dynamodb:{r}:{a}:table/{p}-main"
    bank = {
        "ForAllValues:StringEquals": {"dynamodb:LeadingKeys": ["SYSTEM#QUESTION_BANK"]},
        "Null": {"dynamodb:LeadingKeys": "false"},
    }
    transaction = {"StringEquals": {"dynamodb:EnclosingOperation": "TransactWriteItems"}}
    user_key_attributes = {
        "ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["USER#*"]},
        "ForAllValues:StringEquals": {"dynamodb:Attributes": ["PK", "SK"]},
        "Null": {"dynamodb:LeadingKeys": "false", "dynamodb:Attributes": "false"},
    }
    for role in ("api", "admin"):
        name = p + "-" + role + "-runtime"
        statements = [
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [f"arn:aws:logs:{r}:{a}:log-group:/aws/lambda/{p}-{role}:*"],
            }
        ]
        if role == "admin":
            statements.extend(
                [
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:GetItem"],
                        "Resource": [table],
                        "Condition": bank,
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:PutItem", "dynamodb:ConditionCheckItem"],
                        "Resource": [table],
                        "Condition": bank | transaction,
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:GetItem"],
                        "Resource": [table],
                        "Condition": user_key_attributes
                        | {"StringEqualsIfExists": {"dynamodb:Select": "SPECIFIC_ATTRIBUTES"}},
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:ConditionCheckItem"],
                        "Resource": [table],
                        "Condition": user_key_attributes
                        | transaction
                        | {"StringEqualsIfExists": {"dynamodb:ReturnValues": "NONE"}},
                    },
                ]
            )
        else:
            statements.extend(
                [
                    {"Effect": "Allow", "Action": ["dynamodb:GetItem"], "Resource": [table]},
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:PutItem"],
                        "Resource": [table],
                        "Condition": transaction
                        | {
                            "ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["USER#*"]},
                            "Null": {"dynamodb:LeadingKeys": "false"},
                        },
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:ConditionCheckItem"],
                        "Resource": [table],
                        "Condition": bank | transaction,
                    },
                ]
            )
        data["iam", "list_role_policies", name] = {"PolicyNames": ["business"]}
        data["iam", "list_attached_role_policies", name] = {"AttachedPolicies": []}
        data["iam", "get_role_policy", name] = {
            "PolicyDocument": {"Version": "2012-10-17", "Statement": statements}
        }
    statements = [
        {
            "Sid": "OnlyThisAdmin" + method,
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": m["aliases"]["admin"],
            "Principal": {"Service": "apigateway.amazonaws.com"},
            "Condition": {
                "StringEquals": {"AWS:SourceAccount": a},
                "ArnLike": {
                    "AWS:SourceArn": (
                        f"arn:aws:execute-api:{r}:{a}:{m['api_id']}"
                        f"/dev/{method}/admin/question-bank"
                    )
                },
            },
        }
        for method in ("GET", "POST")
    ]
    data["lambda", "get_policy", p + "-admin"] = {
        "Policy": json.dumps({"Version": "2012-10-17", "Statement": statements})
    }
    return m, data, session


def test_v3_manifest_and_full_closed_readback(admin_deployment, tmp_path):
    m, _, session = admin_deployment
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(m))
    assert tool("manifest").read_manifest(path, m["account_id"], m["region"]) == m
    tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)


@pytest.mark.parametrize("mutation", ["admin_iam", "api_iam", "route", "invocation", "version"])
def test_v3_rejects_admin_privilege_and_route_drift(admin_deployment, mutation):
    m, data, session = admin_deployment
    if mutation in {"admin_iam", "api_iam"}:
        role = mutation.removesuffix("_iam")
        data["iam", "get_role_policy", f"ai-interview-dev-{role}-runtime"]["PolicyDocument"][
            "Statement"
        ].append({"Effect": "Allow", "Action": ["dynamodb:DeleteItem"], "Resource": ["*"]})
    elif mutation == "route":
        data["apigatewayv2", "get_routes", ""]["Items"][-1]["Target"] = "integrations/integration"
    elif mutation == "invocation":
        data["lambda", "get_policy", "ai-interview-dev-admin"]["Policy"] = '{"Statement":[]}'
    else:
        data["lambda", "get_alias", m["aliases"]["admin"]]["FunctionVersion"] = "999"
    with pytest.raises(ValueError, match="DeploymentReadbackFailed"):
        tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)


@pytest.mark.parametrize("mutation", ["attributes", "projection", "return_values", "user_write"])
def test_v3_rejects_expanded_admin_user_data_access(admin_deployment, mutation):
    m, data, session = admin_deployment
    statements = data["iam", "get_role_policy", "ai-interview-dev-admin-runtime"]["PolicyDocument"][
        "Statement"
    ]
    if mutation == "attributes":
        statements[3]["Condition"]["ForAllValues:StringEquals"]["dynamodb:Attributes"].append(
            "data"
        )
    elif mutation == "projection":
        statements[3]["Condition"].pop("StringEqualsIfExists")
    elif mutation == "return_values":
        statements[4]["Condition"]["StringEqualsIfExists"]["dynamodb:ReturnValues"] = "ALL_OLD"
    else:
        statements[4]["Action"].append("dynamodb:PutItem")
    with pytest.raises(ValueError, match="DeploymentReadbackFailed"):
        tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)
