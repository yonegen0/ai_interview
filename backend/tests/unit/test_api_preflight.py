"""Offline HTTP API CORS preflight gate regression; no AWS or network access."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_p4_runtime import ACCOUNT, REGION, context, environment, http_api_event

from interview_backend.aws_runtime import ApiEntry
from interview_backend.aws_settings import AwsSettings


def _entry(role="api", *, values=None):
    handled = []
    settings = AwsSettings.load(values or environment(role), role)
    entry = ApiEntry(settings, lambda req: handled.append(req) or {"statusCode": 200})
    return entry, handled


def _preflight(route_key="OPTIONS /{proxy+}", path="/dev/practice-options"):
    request = http_api_event("OPTIONS", path, route_key)
    request["requestContext"].pop("authorizer")
    request["headers"] = {
        "origin": "https://frontend.example.invalid",
        "access-control-request-method": "GET",
        "access-control-request-headers": "authorization",
    }
    return request


@pytest.mark.parametrize(
    ("route_key", "path"),
    [
        ("OPTIONS /{proxy+}", "/dev/practice-options"),
        ("OPTIONS /{proxy+}", "/dev/star-assist/options"),
        ("OPTIONS /{proxy+}", "/dev/unknown"),
        ("OPTIONS /", "/dev"),
        ("OPTIONS /", "/dev/"),
    ],
)
def test_exact_unauthenticated_gateway_preflight_returns_empty_204(route_key, path):
    entry, handled = _entry()
    request = _preflight(route_key, path)
    original = deepcopy(request)
    reply = entry(request, context())
    assert reply == {
        "statusCode": 204,
        "headers": {"Cache-Control": "no-store"},
        "body": "",
    }
    assert request == original
    assert handled == []
    # Origin restrictions and allow-* response headers belong to API Gateway.
    assert not any(key.lower().startswith("access-control-") for key in reply["headers"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accountId", "000000000000"),
        ("apiId", "other-api"),
        ("stage", "other"),
    ],
)
def test_preflight_rejects_wrong_gateway_identity(field, value):
    entry, handled = _entry()
    request = _preflight()
    request["requestContext"][field] = value
    assert entry(request, context())["statusCode"] == 401
    assert handled == []


@pytest.mark.parametrize("version", ["1.0", "3.0", None])
def test_preflight_rejects_wrong_payload_version(version):
    entry, handled = _entry()
    request = _preflight()
    request["version"] = version
    assert entry(request, context())["statusCode"] == 401
    assert handled == []


@pytest.mark.parametrize(
    "route_key", ["$default", "OPTIONS /other", "GET /practice-options", ""]
)
def test_preflight_rejects_unrecognized_route_key(route_key):
    entry, handled = _entry()
    request = _preflight(route_key)
    assert entry(request, context())["statusCode"] == 401
    assert handled == []


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"])
def test_preflight_does_not_bypass_non_options_methods(method):
    entry, handled = _entry()
    request = _preflight()
    request["requestContext"]["http"]["method"] = method
    assert entry(request, context())["statusCode"] == 401
    assert handled == []


@pytest.mark.parametrize(
    "alter",
    [
        "route_context_missing",
        "route_context_mismatch",
        "route_event_missing",
        "http_missing",
    ],
)
def test_preflight_requires_matching_gateway_route_and_http_method(alter):
    entry, handled = _entry()
    request = _preflight()
    if alter == "route_context_missing":
        request["requestContext"].pop("routeKey")
    elif alter == "route_context_mismatch":
        request["requestContext"]["routeKey"] = "GET /practice-options"
    elif alter == "route_event_missing":
        request.pop("routeKey")
    else:
        request["requestContext"].pop("http")
    assert entry(request, context())["statusCode"] == 401
    assert handled == []


def test_preflight_wrong_lambda_alias_is_not_authorized():
    entry, handled = _entry()
    assert entry(_preflight(), context(alias="unexpected"))["statusCode"] == 500
    assert handled == []


def test_preflight_not_an_anonymous_admin_route():
    entry, handled = _entry("admin")
    assert entry(_preflight(), context("admin"))["statusCode"] == 401
    assert handled == []


@pytest.mark.parametrize(
    ("method", "route_key"),
    [
        ("GET", "GET /practice-options"),
        ("POST", "POST /sessions"),
        ("PUT", "PUT /answer-drafts/{draftId}"),
        ("DELETE", "$default"),
    ],
)
def test_business_methods_continue_to_require_jwt(method, route_key):
    entry, handled = _entry()
    request = _preflight(route_key)
    request["requestContext"]["http"]["method"] = method
    assert entry(request, context())["statusCode"] == 401
    assert handled == []


def test_invite_generation_preflight_isolated_from_other_lambda_functions():
    values = {
        k: v.replace("ai-interview-dev", "ai-interview-invite-g1")
        for k, v in environment("api").items()
    }
    entry, handled = _entry(values=values)
    live_context = SimpleNamespace(
        invoked_function_arn=(
            f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:ai-interview-invite-g1-api:live"
        ),
        get_remaining_time_in_millis=lambda: 60000,
    )
    assert entry(_preflight(), live_context)["statusCode"] == 204
    assert handled == []
    assert entry(_preflight(), context())["statusCode"] == 500
    assert handled == []
