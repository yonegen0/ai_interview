"""Synthetic OIDC HTTP diagnostics must never serialize a response or token."""

import json
from email.message import Message
from urllib.error import HTTPError

import pytest


class UnreadableBody:
    def read(self, *args):
        pytest.fail("OIDC error body must not be read")

    def close(self):
        pass


def error(code, headers=None):
    return HTTPError(
        "https://test.actions.githubusercontent.com/SECRET-url",
        code,
        "SECRET-reason",
        headers,
        UnreadableBody(),
    )


@pytest.mark.parametrize("code", [True, "403", None, -1, 99, 600, 10**9])
def test_invalid_status_is_not_serialized(code):
    from ci_identity import oidc_http_diagnostic

    assert oidc_http_diagnostic(error(code)) == {
        "http_status": None,
        "request_ids": {},
        "raw_response_preserved": False,
    }


def test_diagnostic_uses_only_status_and_shaped_correlation_ids():
    from ci_identity import oidc_http_diagnostic

    headers = Message()
    headers["X-GitHub-Request-Id"] = "3A75:105007:1D8F698:2F32F6B:6ADF3C99"
    headers["X-VSS-E2EID"] = "01234567-89ab-cdef-0123-456789abcdef"
    headers["X-TFS-Session"] = "abcdef01-2345-6789-abcd-ef0123456789"
    for key in ("Authorization", "Set-Cookie", "Location", "X-Unknown", "Retry-After"):
        headers[key] = "SECRET"
    result = oidc_http_diagnostic(error(403, headers))
    assert result["http_status"] == 403
    assert len(result["request_ids"]) == 3
    assert "SECRET" not in json.dumps(result)
    assert set(result) == {"http_status", "request_ids", "raw_response_preserved"}


@pytest.mark.parametrize(
    "value",
    ["SECRET", "Bearer SECRET", "a" * 10000, "01234567-89ab-cdef-0123-456789abcdef SECRET"],
)
def test_unrecognized_identifier_omitted(value):
    from ci_identity import oidc_http_diagnostic

    headers = Message()
    for name in ("X-GitHub-Request-Id", "X-VSS-E2EID", "X-TFS-Session"):
        headers[name] = value
    assert oidc_http_diagnostic(error(429, headers))["request_ids"] == {}
