"""Environment App capability and bounded API reads; all HTTP is synthetic."""

import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
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
    with pytest.raises(DeploymentError):
        api.g.environment_variables("dev-plan", api.env)
    assert len(api.calls) == 2


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "GitHubEnvironmentAuthenticationFailed"),
        (403, "GitHubEnvironmentVariablesReadDenied"),
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
    with pytest.raises(DeploymentError):
        api.g.verify_environment_access(api.env)
    assert len(api.calls) == 1


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_standard_capability_refusal_precedes_all_aws_or_terraform_work(
    api, monkeypatch, operation
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
    assert c.main() == 1  # Missing App credential: fail before any AWS path.


def test_terraform_and_git_children_never_receive_app_token(api, monkeypatch, tmp_path):
    import terraform_dev as t

    monkeypatch.setenv("P4_STANDARD_ACTIVE", "false")

    def run(command, **kwargs):
        assert "P4_ENV_READ_TOKEN" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout=b"ok")

    monkeypatch.setattr(t.subprocess, "run", run)
    assert t.run(["git", "status"], cwd=tmp_path, env=api.env) == b"ok"
    assert api.env["P4_ENV_READ_TOKEN"] == "app_token"
