"""Environment App capability and bounded API reads; all HTTP is synthetic."""

import io
import json
import ssl
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import build_opener

import pytest

from interview_backend.deployment import DeploymentError


@pytest.fixture
def api(monkeypatch):
    import github_control as g

    env = {
        "GITHUB_REPOSITORY": g.REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1361325921",
        "P4_OPERATION": "plan",
        "GH_TOKEN": "job_token",
        "P4_ENV_READ_TOKEN": "app_token",
        "P4_ENV_TOKEN_STARTED_AT": "1000",
    }
    calls, responses = [], []
    monkeypatch.setattr(g.time, "time", lambda: 1000)

    def open_request(request, **kwargs):
        calls.append(request)
        assert kwargs == {"timeout": 15}
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return io.BytesIO(
            response if isinstance(response, bytes) else json.dumps(response).encode()
        )

    monkeypatch.setattr(g, "build_opener", lambda *a: SimpleNamespace(open=open_request))
    return SimpleNamespace(g=g, env=env, calls=calls, responses=responses)


def rows(flag="true"):
    return [{"name": k, "value": flag} for k in ("P4_STANDARD_READY", "P4_AWS_EXECUTION_READY")]


def repository():
    return {
        "total_count": 1,
        "repositories": [{"id": 1361325921, "full_name": "yonegen0/ai_interview"}],
    }


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_capability_requires_both_environments_and_keeps_job_token_separate(api, operation):
    h = api
    h.env["P4_OPERATION"] = operation
    h.responses.extend(
        [repository()]
        + [
            {"total_count": 2, "variables": rows("true" if name == operation else "false")}
            for name in ("plan", "apply")
        ]
        + [{"object": {"sha": "a" * 40}}]
    )
    h.g.verify_environment_access(h.env)
    h.g.github_json("git/ref/heads/main", h.env)
    assert [r.get_header("Authorization") for r in h.calls] == ["Bearer app_token"] * 3 + [
        "Bearer job_token"
    ]
    assert h.calls[0].full_url == (
        "https://api.github.com/installation/repositories?per_page=30&page=1"
    )


def test_all_pages_have_exact_counts_and_boundaries(api):
    variables = rows() + [{"name": f"EXTRA_{i}", "value": "private"} for i in range(298)]
    api.responses.extend(
        {"total_count": 300, "variables": variables[start : start + 30]}
        for start in range(0, 300, 30)
    )
    assert len(api.g.environment_variables("dev-plan", api.env)) == 300
    assert len(api.calls) == 10
    assert [r.full_url.split("?")[1] for r in api.calls] == [
        f"per_page=30&page={page}" for page in range(1, 11)
    ]


@pytest.mark.parametrize(
    "response",
    [
        [],
        None,
        {},
        {"total_count": -1, "variables": []},
        {"total_count": True, "variables": []},
        {"total_count": "2", "variables": rows()},
        {"total_count": 301, "variables": rows()},
        {"total_count": 2, "variables": {}},
        {"total_count": 2, "variables": []},
        {"total_count": 1, "variables": rows()},
        {"total_count": 2, "variables": [rows()[0]] * 2},
        {
            "total_count": 2,
            "variables": [rows()[0], {"name": "p4_standard_ready", "value": "true"}],
        },
        {"total_count": 1, "variables": [None]},
        {"total_count": 1, "variables": [{"name": [], "value": "true"}]},
        {"total_count": 1, "variables": [{"name": "A", "value": True}]},
        {"total_count": 1, "variables": [{"name": "A"}]},
        b'{"total_count":2,"total_count":0,"variables":[]}',
        b'{"total_count":1,"variables":[{"name":"A","value":"a","value":"b"}]}',
        b"private-invalid-json",
        pytest.param(b"x" * 1048577, id="oversized-body"),
    ],
)
def test_malformed_or_incomplete_variables_fail_closed(api, response):
    api.responses.append(response)
    with pytest.raises(DeploymentError) as failure:
        api.g.environment_variables("dev-plan", api.env)
    assert failure.value.reason_code == "GitHubEnvironmentResponseInvalid"
    assert failure.value.failure_phase == "dev-plan-variables"
    assert len(api.calls) == 1


@pytest.mark.parametrize("fault", ["missing-page", "changed-count", "duplicate-next-page"])
def test_partial_or_inconsistent_pagination_never_returns_partial_result(api, fault):
    first = rows() + [{"name": f"EXTRA_{i}", "value": "private"} for i in range(28)]
    second = [] if fault == "missing-page" else [{"name": "LAST", "value": "private"}]
    if fault == "duplicate-next-page":
        second = [first[0]]
    api.responses.extend(
        [
            {"total_count": 31, "variables": first},
            {"total_count": 32 if fault == "changed-count" else 31, "variables": second},
        ]
    )
    with pytest.raises(DeploymentError) as failure:
        api.g.environment_variables("dev-plan", api.env)
    assert failure.value.failure_phase == "dev-plan-variables"
    assert len(api.calls) == 2


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "GitHubEnvironmentAuthenticationFailed"),
        (403, "GitHubEnvironmentHttpRejected"),
        (404, "GitHubEnvironmentNotFound"),
        (429, "GitHubEnvironmentRateLimited"),
        (500, "GitHubEnvironmentServiceUnavailable"),
        (503, "GitHubEnvironmentServiceUnavailable"),
        (301, "GitHubEnvironmentRedirectRejected"),
        (302, "GitHubEnvironmentRedirectRejected"),
        (307, "GitHubEnvironmentRedirectRejected"),
        (308, "GitHubEnvironmentRedirectRejected"),
    ],
)
def test_http_errors_are_finite_secret_free_and_never_retried(api, capsys, status, reason):
    from standard_diagnostics import Diagnostic

    api.responses.append(
        HTTPError("https://private.invalid", status, "private", {}, io.BytesIO(b"private"))
    )
    with pytest.raises(DeploymentError) as failure:
        api.g.environment_variables("dev-apply", api.env)
    assert failure.value.reason_code == reason
    Diagnostic().emit(failure.value)
    output = capsys.readouterr()
    assert "private" not in output.out + output.err
    assert "token" not in output.out + output.err
    assert reason in output.out
    assert len(api.calls) == 1


def test_real_redirect_handler_refuses_redirect_before_second_request(api, monkeypatch):
    from urllib.request import BaseHandler

    seen = []

    class Redirect(BaseHandler):
        handler_order = 100

        def https_open(self, request):
            seen.append(request.full_url)
            result = io.BytesIO(b"private")
            result.code, result.msg = 302, "private"
            result.info = lambda: {"Location": "https://private.invalid/target"}
            return result

    monkeypatch.setattr(api.g, "build_opener", lambda *a: build_opener(*a, Redirect()))
    with pytest.raises(DeploymentError) as failure:
        api.g.environment_variables("dev-plan", api.env)
    assert failure.value.reason_code == "GitHubEnvironmentRedirectRejected"
    assert len(seen) == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"P4_ENV_READ_TOKEN": ""}, "GitHubEnvironmentAuthenticationFailed"),
        ({"P4_ENV_READ_TOKEN": "bad\nheader"}, "GitHubEnvironmentAuthenticationFailed"),
        ({"P4_ENV_TOKEN_STARTED_AT": ""}, "GitHubEnvironmentAuthenticationFailed"),
        ({"P4_ENV_TOKEN_STARTED_AT": "1001"}, "GitHubEnvironmentTokenExpired"),
        ({"P4_ENV_TOKEN_STARTED_AT": "0"}, "GitHubEnvironmentTokenExpired"),
        ({"GITHUB_REPOSITORY": "other/repo"}, "GitHubEnvironmentScopeMismatch"),
        ({"GITHUB_REPOSITORY_ID": "1"}, "GitHubEnvironmentScopeMismatch"),
    ],
)
def test_invalid_scope_or_expiry_never_uses_job_token(api, change, reason, monkeypatch):
    if change == {"P4_ENV_TOKEN_STARTED_AT": "0"}:
        monkeypatch.setattr(api.g.time, "time", lambda: 3270)
    api.env.update(change)
    with pytest.raises(DeploymentError) as failure:
        api.g.environment_variables("dev-plan", api.env)
    assert failure.value.reason_code == reason
    assert api.calls == []


def test_token_expiry_between_pages_is_refused(api, monkeypatch):
    clock = iter([1000, 4270])
    monkeypatch.setattr(api.g.time, "time", lambda: next(clock))
    api.responses.append(
        {"total_count": 31, "variables": [{"name": f"A_{i}", "value": "x"} for i in range(30)]}
    )
    with pytest.raises(DeploymentError) as failure:
        api.g.environment_variables("dev-plan", api.env)
    assert failure.value.reason_code == "GitHubEnvironmentTokenExpired"
    assert failure.value.failure_phase == "dev-plan-variables"
    assert len(api.calls) == 1


@pytest.mark.parametrize("name", ["dev", "prod", "dev-plan/../dev-apply", "dev-plan?x=y"])
def test_only_exact_environment_names_are_allowed(api, name):
    with pytest.raises(DeploymentError):
        api.g.environment_variables(name, api.env)
    assert api.calls == []


@pytest.mark.parametrize(
    "suffix",
    [
        "environments/other/variables?per_page=30&page=1",
        "environments/dev-plan/variables?per_page=100",
        "environments/dev-plan/variables?per_page=30&page=11",
        "environments/dev-plan/variables?per_page=30&page=0",
        "environments/dev-plan/variables?per_page=30&page=1&other=private",
    ],
)
def test_wrong_variable_paths_cannot_use_any_token(api, suffix):
    with pytest.raises(DeploymentError):
        api.g.github_json(suffix, api.env)
    assert api.calls == []


@pytest.mark.parametrize("fault", ["missing", "wrong", "both-true", "second-denied"])
def test_readiness_partial_success_and_missing_flags_are_failures(api, fault):
    first, second = rows(), rows("false")
    if fault == "missing":
        first.pop()
    elif fault == "wrong":
        first = rows("false")
    elif fault == "both-true":
        second = rows()
    api.responses.extend(
        [
            {"total_count": len(first), "variables": first},
            HTTPError("private", 403, "private", {}, None)
            if fault == "second-denied"
            else {"total_count": len(second), "variables": second},
        ]
    )
    with pytest.raises(DeploymentError):
        api.g.verify_readiness(api.env)


@pytest.mark.parametrize(
    "result",
    [
        {"total_count": True, "repositories": repository()["repositories"]},
        {"total_count": 2, "repositories": repository()["repositories"] * 2},
        {"total_count": 1, "repositories": []},
        {"total_count": 1, "repositories": [{"id": 1, "full_name": "yonegen0/ai_interview"}]},
        {"total_count": 1, "repositories": [{"id": 1361325921, "full_name": "other/repo"}]},
    ],
)
def test_capability_rejects_wrong_or_excess_repositories(api, result):
    api.responses.append(result)
    with pytest.raises(DeploymentError) as failure:
        api.g.verify_environment_access(api.env)
    assert failure.value.failure_phase == "repository-scope"
    assert len(api.calls) == 1


@pytest.mark.parametrize("operation", ["plan", "apply"])
@pytest.mark.parametrize("fault", ["missing", "repository", "dev-plan", "dev-apply", "readiness"])
def test_standard_capability_refusal_precedes_all_aws_or_terraform_work(
    api, monkeypatch, operation, fault
):
    import ci_deploy as c

    monkeypatch.setenv("P4_STANDARD_ACTIVE", "true")
    monkeypatch.setenv("P4_OPERATION", operation)
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("P4_PLAN_HASH", "a" * 64)
    monkeypatch.setattr(
        c, "preflight", lambda *a: ("123456789012", "ap-northeast-1", operation, {})
    )
    monkeypatch.setattr(
        c, "initialize", lambda *a: SimpleNamespace(package={}, fail=lambda *a: None)
    )
    monkeypatch.setattr(c, "checked_git", lambda *a: "a" * 40)
    import plan_authorization

    monkeypatch.setattr(plan_authorization, "verify_run_history", lambda *a: None)
    monkeypatch.setattr(c, "role_session", lambda *a: pytest.fail("AWS credentials reached"))
    monkeypatch.setattr(c, "plan_state_preflight", lambda *a: pytest.fail("State read reached"))
    monkeypatch.setattr(c, "execute", lambda *a: pytest.fail("Terraform reached"))
    for key, value in api.env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("P4_OPERATION", operation)
    first = {"total_count": 2, "variables": rows("true" if operation == "plan" else "false")}
    denied = HTTPError("private", 403, "private", {}, None)
    if fault == "missing":
        monkeypatch.delenv("P4_ENV_READ_TOKEN", raising=False)
    elif fault == "repository":
        api.responses.append(denied)
    elif fault == "dev-plan":
        api.responses.extend([repository(), denied])
    elif fault == "dev-apply":
        api.responses.extend([repository(), first, denied])
    else:
        api.responses.extend([repository(), {"total_count": 0, "variables": []}])
    assert c.main() == 1  # Every gate failure stops before AWS credentials/State/Terraform.


def test_terraform_and_git_children_never_receive_app_token(api, monkeypatch, tmp_path):
    import terraform_dev as t

    monkeypatch.setenv("P4_STANDARD_ACTIVE", "false")

    def run(command, **kwargs):
        assert "P4_ENV_READ_TOKEN" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout=b"ok")

    monkeypatch.setattr(t.subprocess, "run", run)
    assert t.run(["git", "status"], cwd=tmp_path, env=api.env) == b"ok"
    assert api.env["P4_ENV_READ_TOKEN"] == "app_token"


PHASES = ("repository-scope", "dev-plan-variables", "dev-apply-variables")
SENTINEL = "PRIVATE_SENTINEL https://private.invalid Authorization: Bearer ghp_private PEM"


def queue_failure(api, phase, response):
    before = {
        "repository-scope": [],
        "dev-plan-variables": [repository()],
        "dev-apply-variables": [repository(), {"total_count": 2, "variables": rows()}],
    }[phase]
    api.responses.extend([*before, response])
    return len(before) + 1


def failure_result(api, capsys):
    assert api.g.main(api.env) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert SENTINEL not in captured.out
    assert "private.invalid" not in captured.out
    assert "app_token" not in captured.out
    assert "job_token" not in captured.out
    assert len(captured.out.splitlines()) == 1
    value = json.loads(captured.out)
    assert set(value) == {
        "schema_version",
        "failure_phase",
        "reason_code",
        "http_status",
        "capability_result",
    }
    assert value["schema_version"] == 1
    assert value["capability_result"] == "FAIL"
    return value


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize(
    "status,kind",
    [
        (401, "AuthenticationFailed"),
        (403, "HttpRejected"),
        (404, "NotFound"),
        (418, "HttpRejected"),
        (429, "RateLimited"),
        (500, "ServiceUnavailable"),
        (503, "ServiceUnavailable"),
        (301, "RedirectRejected"),
        (302, "RedirectRejected"),
        (307, "RedirectRejected"),
        (308, "RedirectRejected"),
    ],
)
def test_cli_http_matrix_retains_stage_without_retry_or_private_data(
    api, capsys, phase, status, kind
):
    calls = queue_failure(
        api, phase, HTTPError(SENTINEL, status, SENTINEL, {}, io.BytesIO(SENTINEL.encode()))
    )
    value = failure_result(api, capsys)
    prefix = "GitHubRepository" if phase == "repository-scope" else "GitHubEnvironment"
    assert value["failure_phase"] == phase
    assert value["reason_code"] == prefix + kind
    assert value["http_status"] == status
    assert len(api.calls) == calls


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize(
    "headers,kind",
    [
        ({"X-RateLimit-Remaining": "0"}, "RateLimited"),
        ({"Retry-After": "60"}, "RateLimited"),
        ({"X-RateLimit-Remaining": "1"}, "HttpRejected"),
        ({"Retry-After": SENTINEL}, "HttpRejected"),
        ({"Retry-After": "0"}, "HttpRejected"),
        ({"Retry-After": "9" * 1000}, "HttpRejected"),
        ({}, "HttpRejected"),
    ],
)
def test_403_needs_numeric_rate_evidence_and_never_claims_permission_cause(
    api, capsys, phase, headers, kind
):
    queue_failure(api, phase, HTTPError(SENTINEL, 403, SENTINEL, headers, None))
    value = failure_result(api, capsys)
    assert value["failure_phase"] == phase
    assert value["reason_code"].endswith(kind)
    assert value["http_status"] == 403


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize(
    "fault,kind",
    [
        (TimeoutError(SENTINEL), "TransportFailed"),
        (URLError(SENTINEL), "TransportFailed"),
        (ssl.SSLError(SENTINEL), "TransportFailed"),
        (ConnectionError(SENTINEL), "TransportFailed"),
        (SENTINEL.encode(), "ResponseInvalid"),
        (b'{"total_count":1,"total_count":0}', "ResponseInvalid"),
        (b"\xff", "ResponseInvalid"),
        ([], "ResponseInvalid"),
        (pytest.param(b"x" * 1048577, "ResponseInvalid", id="oversized")),
        (RuntimeError(SENTINEL), "UNKNOWN"),
    ],
)
def test_cli_transport_schema_and_unknown_failures_are_distinct(api, capsys, phase, fault, kind):
    calls = queue_failure(api, phase, fault)
    value = failure_result(api, capsys)
    assert value["failure_phase"] == phase
    assert value["http_status"] is None
    assert value["reason_code"].endswith(kind)
    assert len(api.calls) == calls


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"P4_ENV_READ_TOKEN": ""}, "GitHubEnvironmentAuthenticationFailed"),
        ({"P4_ENV_READ_TOKEN": SENTINEL}, "GitHubEnvironmentAuthenticationFailed"),
        ({"P4_ENV_TOKEN_STARTED_AT": "1000\\n"}, "GitHubEnvironmentAuthenticationFailed"),
        ({"P4_ENV_TOKEN_STARTED_AT": "1001"}, "GitHubEnvironmentTokenExpired"),
        ({"GITHUB_REPOSITORY": SENTINEL}, "GitHubEnvironmentScopeMismatch"),
        ({"GITHUB_REPOSITORY_ID": "1"}, "GitHubEnvironmentScopeMismatch"),
    ],
)
def test_cli_token_preflight_has_no_http_fallback(api, capsys, change, reason):
    api.env.update(change)
    value = failure_result(api, capsys)
    assert value["failure_phase"] == "token-preflight"
    assert value["reason_code"] == reason
    assert value["http_status"] is None
    assert api.calls == []


@pytest.mark.parametrize("phase", ("dev-plan-variables", "dev-apply-variables"))
def test_cli_expiry_between_api_requests_keeps_actual_phase(api, monkeypatch, capsys, phase):
    calls = queue_failure(api, phase, {})
    # One token check before repository GET, then one before each variables GET.
    clock = iter([1000] * (calls - 1) + [4270])
    monkeypatch.setattr(api.g.time, "time", lambda: next(clock))
    value = failure_result(api, capsys)
    assert value["failure_phase"] == phase
    assert value["reason_code"] == "GitHubEnvironmentTokenExpired"
    assert len(api.calls) == calls - 1


@pytest.mark.parametrize("fault", ("missing", "false", "mixed", "both-true", "invalid"))
def test_cli_readiness_failures_keep_readiness_phase(api, capsys, fault):
    first, second = rows(), rows("false")
    if fault == "missing":
        first.pop()
    elif fault == "false":
        first = rows("false")
    elif fault == "mixed":
        first[0]["value"] = "false"
    elif fault == "invalid":
        first[0]["value"] = SENTINEL
    else:
        second = rows()
    api.responses.extend(
        [
            repository(),
            {"total_count": len(first), "variables": first},
            {"total_count": len(second), "variables": second},
        ]
    )
    value = failure_result(api, capsys)
    assert value["failure_phase"] == "readiness"
    assert value["reason_code"] == "GitHubEnvironmentReadinessMismatch"


@pytest.mark.parametrize("status", [True, False, "403", -1, 0, 99, 600, None, SENTINEL])
def test_projection_never_coerces_invalid_http_status_or_unsafe_fields(api, status):
    failure = api.g.CapabilityFailure(SENTINEL, SENTINEL, status)
    assert api.g.capability_projection(failure) == {
        "schema_version": 1,
        "failure_phase": "unknown",
        "reason_code": "UNKNOWN",
        "http_status": None,
        "capability_result": "FAIL",
    }


def test_unknown_hostile_exception_and_broken_stdout_fail_without_stringification(
    api, monkeypatch, capsys
):
    class Hostile(Exception):
        @property
        def reason_code(self):
            pytest.fail("Unknown exception properties must not be accessed")

        def __str__(self):
            pytest.fail("Private exception must not be stringified")

    def broken(*args):
        raise Hostile(SENTINEL)

    monkeypatch.setattr(api.g, "verify_environment_access", broken)
    assert failure_result(api, capsys)["failure_phase"] == "unknown"
    monkeypatch.setattr("builtins.print", lambda *a, **k: (_ for _ in ()).throw(OSError(SENTINEL)))
    assert api.g.main(api.env) == 1


@pytest.mark.parametrize("operation", ("plan", "apply"))
def test_cli_success_has_only_fixed_marker_and_exact_three_reads(api, capsys, operation):
    api.env["P4_OPERATION"] = operation
    api.responses.extend(
        [repository()]
        + [
            {"total_count": 2, "variables": rows("true" if name == operation else "false")}
            for name in ("plan", "apply")
        ]
    )
    assert api.g.main(api.env) == 0
    captured = capsys.readouterr()
    assert captured.out == "GitHubEnvironmentCapabilityPassed\n"
    assert captured.err == ""
    assert len(api.calls) == 3


def test_success_marker_output_failure_also_exits_without_traceback(api, monkeypatch):
    api.responses.extend(
        [
            repository(),
            {"total_count": 2, "variables": rows()},
            {"total_count": 2, "variables": rows("false")},
        ]
    )
    monkeypatch.setattr("builtins.print", lambda *a, **k: (_ for _ in ()).throw(OSError(SENTINEL)))
    assert api.g.main(api.env) == 1


@pytest.mark.parametrize("phase", ("dev-plan-variables", "dev-apply-variables"))
def test_unknown_errors_outside_transport_keep_environment_phase(api, monkeypatch, capsys, phase):
    original = api.g.environment_variables

    def injected(name, environment):
        if name + "-variables" == phase:
            raise RuntimeError(SENTINEL)
        return original(name, environment)

    api.responses.extend([repository(), {"total_count": 2, "variables": rows()}])
    monkeypatch.setattr(api.g, "environment_variables", injected)
    value = failure_result(api, capsys)
    assert value["failure_phase"] == phase
    assert value["reason_code"] == "UNKNOWN"


def test_actual_cli_process_returns_nonzero_and_no_traceback(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(backend / "skills/p4/github_control.py")],
        cwd=tmp_path,
        env={
            "SYSTEMROOT": os.environ["SYSTEMROOT"] if os.name == "nt" else "/",
            "PYTHONPATH": str(backend / "src"),
            "GITHUB_REPOSITORY": "yonegen0/ai_interview",
            "GITHUB_REPOSITORY_ID": "1361325921",
            "GH_TOKEN": SENTINEL,
            "P4_ENV_READ_TOKEN": SENTINEL,
        },
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr == ""
    assert SENTINEL not in result.stdout
    value = json.loads(result.stdout)
    assert value["failure_phase"] == "token-preflight"
    assert value["reason_code"] == "GitHubEnvironmentAuthenticationFailed"


# Synthetic shapes only: these are neither issued credentials nor verified JWTs.
OPAQUE_INSTALLATION_TOKENS = [
    pytest.param("ghs_" + "a" * 36, id="classic"),
    pytest.param("ghs_123456_header.payload.fake-signature", id="stateless"),
    pytest.param(
        "ghs_123456_" + "a" * 180 + "." + "b" * 380 + ".fake-signature_", id="long-stateless"
    ),
]


@pytest.mark.parametrize("token", OPAQUE_INSTALLATION_TOKENS)
def test_opaque_installation_tokens_reach_all_three_checks(api, capsys, token):
    api.env["P4_ENV_READ_TOKEN"] = token
    api.responses.extend(
        [
            repository(),
            {"total_count": 2, "variables": rows()},
            {"total_count": 2, "variables": rows("false")},
            {"object": {"sha": "a" * 40}},
        ]
    )
    assert api.g.main(api.env) == 0
    output = capsys.readouterr()
    assert output.out == "GitHubEnvironmentCapabilityPassed\n"
    assert output.err == ""
    assert token not in output.out
    api.g.github_json("git/ref/heads/main", api.env)
    assert [r.get_header("Authorization") for r in api.calls] == ["Bearer " + token] * 3 + [
        "Bearer job_token"
    ]


@pytest.mark.parametrize("suffix", ["\r", "\n", "\t", " ", "\0", "\x7f", ":", "/", "+", "=", "é"])
def test_stateless_shape_still_rejects_header_unsafe_characters(api, capsys, suffix):
    api.env["P4_ENV_READ_TOKEN"] = "ghs_123456_header.payload.fake-signature" + suffix
    value = failure_result(api, capsys)
    assert value["failure_phase"] == "token-preflight"
    assert value["reason_code"] == "GitHubEnvironmentAuthenticationFailed"
    assert value["http_status"] is None
    assert api.calls == []


@pytest.mark.parametrize("token", OPAQUE_INSTALLATION_TOKENS)
def test_opaque_token_keeps_expiry_scope_and_no_fallback(api, capsys, monkeypatch, token):
    api.env["P4_ENV_READ_TOKEN"] = token
    monkeypatch.setattr(api.g.time, "time", lambda: 4270)
    value = failure_result(api, capsys)
    assert value["reason_code"] == "GitHubEnvironmentTokenExpired"
    assert api.calls == []
    monkeypatch.setattr(api.g.time, "time", lambda: 1000)
    api.env["GITHUB_REPOSITORY_ID"] = "1"
    value = failure_result(api, capsys)
    assert value["reason_code"] == "GitHubEnvironmentScopeMismatch"
    assert api.calls == []


@pytest.mark.parametrize("token", OPAQUE_INSTALLATION_TOKENS)
def test_opaque_token_repository_http_rejection_has_no_retry_or_job_token(api, capsys, token):
    api.env["P4_ENV_READ_TOKEN"] = token
    api.responses.append(HTTPError("https://synthetic.invalid", 403, "synthetic", {}, None))
    value = failure_result(api, capsys)
    assert value["failure_phase"] == "repository-scope"
    assert value["reason_code"] == "GitHubRepositoryHttpRejected"
    assert value["http_status"] == 403
    assert len(api.calls) == 1
    assert api.calls[0].get_header("Authorization") == "Bearer " + token
