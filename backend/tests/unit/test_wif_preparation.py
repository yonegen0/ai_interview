"""Worker subject verification and non-generating WIF Smoke with synthetic tokens."""

import base64
import hashlib
import json
from time import time
from types import SimpleNamespace

import pytest
from test_provider_validation_tools import tool

from interview_backend.evaluation.openai_auth import AWSFederation
from interview_backend.evaluation.openai_provider import ProviderFailure
from interview_backend.evaluation.selection import checked_provider_environment
from interview_backend.evaluation.wif_smoke import smoke, verify_claims

ACCOUNT = "123456789012"
ISSUER = "https://synthetic-issuer.tokens.sts.global.api.aws"


def jwt(*, now=None, **changes):
    now = int(time()) if now is None else now
    claims = {
        "iss": ISSUER,
        "sub": f"arn:aws:iam::{ACCOUNT}:role/ai-interview-dev-worker-runtime",
        "aud": "https://api.openai.com/v1",
        "iat": now,
        "exp": now + 300,
    } | changes
    parts = [
        base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip("=")
        for x in ({"alg": "ES384"}, claims)
    ]
    return ".".join(parts + ["synthetic-signature"])


def environment():
    return {
        "INTERVIEW_AI_PROVIDER": "fake",
        "INTERVIEW_VALIDATION_ONLY": "true",
        "INTERVIEW_WIF_SMOKE_ENABLED": "true",
        "INTERVIEW_WIF_SMOKE_RUN_ID": "offline-wif",
        "INTERVIEW_OPENAI_AWS_ISSUER": ISSUER,
        "INTERVIEW_OPENAI_AUTH": "wif",
        "INTERVIEW_OPENAI_ENABLED": "true",
        "INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID": "idp-synthetic",
        "INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID": "sa-synthetic",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "unknown"},
        {"sub": "another-role"},
        {"aud": "other"},
        {"exp": 999},
        {"exp": 1301},
        {"iat": True},
    ],
)
def test_claim_mismatch_rejected(changes):
    with pytest.raises(ValueError):
        verify_claims(jwt(now=1000, **changes), ISSUER, ACCOUNT, now=1000)


@pytest.mark.parametrize("bad", ["flag", "run", "provider", "issuer", "component"])
def test_smoke_gates_prevent_auth_or_model_send(bad):
    settings = SimpleNamespace(
        component="worker",
        function_name="ai-interview-dev-worker",
        region="ap-northeast-1",
        account=ACCOUNT,
    )
    env = environment()
    event = {"operation": "wif_smoke", "run_id": "offline-wif"}
    if bad == "flag":
        env.pop("INTERVIEW_WIF_SMOKE_ENABLED")
    elif bad == "run":
        event["run_id"] = "other"
    elif bad == "provider":
        env["INTERVIEW_AI_PROVIDER"] = "openai"
    elif bad == "issuer":
        env["INTERVIEW_OPENAI_AWS_ISSUER"] = "unknown"
    else:
        settings.component = "api"

    def forbidden(*args, **kwargs):
        pytest.fail("No auth request permitted")

    with pytest.raises(ValueError):
        smoke(settings, env, event, authentication_factory=forbidden)


def test_actual_auth_exchange_observes_worker_claims_without_responses():
    from test_openai_provider import Transport

    exchange = Transport(
        value={
            "token_type": "Bearer",
            "access_token": "synthetic-access",
            "expires_at": time() + 900,
        }
    )
    calls = []

    def factory(*args, **kwargs):
        def get(**values):
            calls.append(values)
            return {"WebIdentityToken": jwt()}

        return AWSFederation(
            *args,
            **kwargs,
            client_factory=lambda deadline: SimpleNamespace(get_web_identity_token=get),
            transport=exchange,
        )

    settings = SimpleNamespace(
        component="worker",
        function_name="ai-interview-dev-worker",
        region="ap-northeast-1",
        account=ACCOUNT,
    )
    evidence = smoke(
        settings,
        environment(),
        {"operation": "wif_smoke", "run_id": "offline-wif"},
        authentication_factory=factory,
    )
    assert evidence["paid_responses_calls"] == 0 and evidence["openai_exchange_verified"] is True
    assert len(calls) == 1 and calls[0]["DurationSeconds"] == 300
    assert [r[:2] for r in exchange.requests] == [("auth.openai.com", "/oauth/token")]
    assert "synthetic-access" not in json.dumps(evidence)


def test_fake_smoke_config_and_shared_boundary_stay_narrow():
    assert checked_provider_environment(environment(), ACCOUNT, "ap-northeast-1") == environment()
    with pytest.raises(ValueError):
        checked_provider_environment(
            environment() | {"INTERVIEW_OPENAI_SECRET_ARN": "secret"}, ACCOUNT, "ap-northeast-1"
        )
    tool("provider_eval")
    policy = tool("wif_policy")
    baseline = tool("bootstrap_contract")
    before = baseline.boundary_policy(ACCOUNT, "ap-northeast-1")
    after = baseline.boundary_policy(ACCOUNT, "ap-northeast-1", worker_wif_enabled=True)
    assert after["Statement"][:-1] == before["Statement"]
    assert after["Statement"][-1] == policy.worker_statement(ACCOUNT, boundary=True)
    assert after["Statement"][-1]["Condition"]["ArnEquals"]["aws:PrincipalArn"].endswith(
        "-worker-runtime"
    )


def test_wrong_worker_subject_prevents_openai_exchange():
    from test_openai_provider import Transport

    from interview_backend.evaluation.openai_provider import Deadline

    exchange = Transport()
    auth = AWSFederation(
        "ap-northeast-1",
        "idp",
        "sa",
        client_factory=lambda d: SimpleNamespace(
            get_web_identity_token=lambda **kw: {"WebIdentityToken": jwt(sub="other")}
        ),
        transport=exchange,
        subject_observer=lambda token: verify_claims(token, ISSUER, ACCOUNT),
    )
    with pytest.raises(ProviderFailure, match="AUTHENTICATION"):
        auth.token(Deadline(40, lambda: 0))
    assert exchange.requests == []


def test_scenarios_are_separate_and_exact_owner_only():
    tool("coaching_binding")
    module = tool("suite_binding")
    approval = {
        "provider": "fake",
        "expected_rounds": 3,
        "scenario": "fake_three",
        "subjects": {"USER_A": "a"},
    }
    env = {
        "INTERVIEW_FAKE_SCENARIO": "coaching_three",
        "INTERVIEW_VALIDATION_ONLY": "true",
        "INTERVIEW_VALIDATION_OWNER_HASHES": hashlib.sha256(b"a").hexdigest(),
    }
    module.validate_scenario(approval, env)
    with pytest.raises(ValueError):
        module.validate_scenario(approval, {})
    with pytest.raises(ValueError):
        module.validate_scenario(
            approval,
            env | {"INTERVIEW_VALIDATION_OWNER_HASHES": hashlib.sha256(b"other").hexdigest()},
        )


def test_failure_suite_retries_under_same_approved_failure_configuration():
    from test_provider_validation_tools import LocalApi

    from interview_backend.bootstrap import build_runtime
    from interview_backend.evaluation.validation_scenarios import ValidationScenario

    live = tool("coaching_live")
    runtime = build_runtime(
        provider=ValidationScenario("provider_failure", [hashlib.sha256(b"a").hexdigest()])
    )

    def wait(api, eid):
        runtime.worker.run("a", eid)
        return api.call("GET", f"/evaluations/{eid}")[1]

    run = live.Run("failure-offline")
    live.coaching_flow(
        LocalApi(runtime, "a"), LocalApi(runtime, "b"), run, expected_failure=True, wait=wait
    )
    assert all(row["status"] == "passed" for row in run.rows)
    assert any(row["check"] == "same-failure-config-retry-terminal" for row in run.rows)


def test_eval_auth_binds_separate_observed_role_and_project():
    tool("provider_eval")
    budget = tool("eval_budget")
    auth = AWSFederation("ap-northeast-1", "idp", "sa")
    expected = {
        "mode": "wif",
        "status": "AUTHENTICATION_READBACK_VERIFIED",
        "gpt6_luna_access_verified": True,
        "region": "ap-northeast-1",
        "project_id": "project-synthetic",
        "permissions": ["api.model.request"],
        "identity_provider_id": "idp",
        "service_account_id": "sa",
        "issuer": ISSUER,
        "subject": f"arn:aws:iam::{ACCOUNT}:role/ai-interview-dev-worker-runtime",
    }
    budget.bind_authentication(auth, expected)
    auth.subject_observer(jwt())
    with pytest.raises(ValueError, match="LocalWIFClaimsMismatch"):
        auth.subject_observer(jwt(sub="other"))
    with pytest.raises(ValueError):
        budget.bind_authentication(auth, expected | {"project_id": ""})
    with pytest.raises(ValueError):
        budget.bind_authentication(
            auth, expected | {"service_account_id": "worker-mapping-must-not-be-reused"}
        )
