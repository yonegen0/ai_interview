"""STAR deployment readback: complete routes and bounded transaction permissions."""

import re
from pathlib import Path

import pytest
from test_p4_cost_controls import cost_deployment as cost_deployment
from test_p4_manifest_v3 import admin_deployment as admin_deployment
from test_p4_tools import tool


@pytest.mark.parametrize(
    "mutation",
    ["missing", "unexpected", "jwt", "authorizer", "target", "duplicate"],
)
def test_schema4_rejects_star_route_drift(cost_deployment, mutation):
    manifest, data, session = cost_deployment
    routes = data["apigatewayv2", "get_routes", ""]["Items"]
    route = next(r for r in routes if r["RouteKey"] == "GET /star-assist/quota")
    if mutation == "missing":
        routes.remove(route)
    elif mutation == "unexpected":
        routes.append(dict(route, RouteKey="DELETE /star-assist/quota"))
    elif mutation == "jwt":
        route["AuthorizationType"] = "NONE"
    elif mutation == "authorizer":
        route["AuthorizerId"] = "other-auth"
    elif mutation == "target":
        route["Target"] = "integrations/admin-integration"
    else:
        routes.append(dict(route))
    with pytest.raises(ValueError, match="ApiRoutesMismatch|DeploymentAttributeMismatch"):
        tool("manifest_checks").verify_api(
            session.client("apigatewayv2"), manifest, "ai-interview-dev"
        )


@pytest.mark.parametrize("mutation", ["put", "header", "wildcard", "extra_method"])
def test_schema4_rejects_missing_or_expanded_star_cors(cost_deployment, mutation):
    manifest, data, session = cost_deployment
    cors = data["apigatewayv2", "get_api", ""]["CorsConfiguration"]
    if mutation == "put":
        cors["AllowMethods"].remove("PUT")
    elif mutation == "header":
        cors["AllowHeaders"].remove("X-Star-Application-Id")
    elif mutation == "wildcard":
        cors["AllowHeaders"].append("*")
    else:
        cors["AllowMethods"].append("DELETE")
    with pytest.raises(ValueError, match="CorsMismatch"):
        tool("manifest_checks").verify_api(
            session.client("apigatewayv2"), manifest, "ai-interview-dev"
        )


@pytest.mark.parametrize(
    "mutation",
    ["missing_user_check", "missing_quota", "resource", "keys", "null", "transaction", "delete"],
)
def test_schema4_rejects_missing_or_expanded_star_iam(cost_deployment, mutation):
    manifest, data, session = cost_deployment
    statements = data["iam", "get_role_policy", "ai-interview-dev-api-runtime"]["PolicyDocument"][
        "Statement"
    ]
    quota = statements[-1]
    if mutation == "missing_user_check":
        statements[2]["Action"].remove("dynamodb:ConditionCheckItem")
    elif mutation == "missing_quota":
        statements.remove(quota)
    elif mutation == "resource":
        quota["Resource"] = ["*"]
    elif mutation == "keys":
        quota["Condition"]["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"] = ["USER#*"]
    elif mutation == "null":
        quota["Condition"].pop("Null")
    elif mutation == "transaction":
        quota["Condition"].pop("StringEquals")
    else:
        quota["Action"].append("dynamodb:DeleteItem")
    with pytest.raises(ValueError, match="QuestionPermissionsMismatch"):
        tool("manifest_checks").verify_question_permissions(
            session.client("iam"), session.client("lambda"), manifest, "ai-interview-dev"
        )


def test_schema4_route_fixture_covers_terraform_contract(cost_deployment):
    _, data, _ = cost_deployment
    source = Path(__file__).resolve().parents[3] / "terraform/modules/service/auth.tf"
    declaration = re.search(
        r"star_routes\s*=\s*\[([\s\S]*?)\n\s*\]", source.read_text(encoding="utf-8")
    )
    assert declaration is not None
    routes = set(re.findall(r'"((?:GET|POST|PUT) /[^\"]+)"', declaration[1]))
    observed = {r["RouteKey"] for r in data["apigatewayv2", "get_routes", ""]["Items"]}
    assert len(routes) == 16
    assert routes <= observed
