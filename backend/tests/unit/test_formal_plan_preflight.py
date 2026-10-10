"""Authenticated absence and exact CI input mapping; synthetic objects, no live AWS."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from test_p4_artifact_inputs import valid_inputs
from test_p4_tools import tool


@pytest.fixture(autouse=True)
def tool_imports(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "skills/p4"))


@pytest.mark.parametrize(
    "pages,expected",
    [
        ([{"IsTruncated": False}], "pass"),
        (
            [{"IsTruncated": False, "Contents": [{"Key": "dev/terraform.tfstate.tflock-other"}]}],
            "pass",
        ),
        ([{"IsTruncated": True, "NextContinuationToken": "next"}, {"IsTruncated": False}], "pass"),
        (
            [{"IsTruncated": False, "Contents": [{"Key": "dev/terraform.tfstate.tflock"}]}],
            "ActiveStateLock",
        ),
        (
            [
                {"IsTruncated": True, "NextContinuationToken": "next"},
                {"IsTruncated": False, "Contents": [{"Key": "dev/terraform.tfstate.tflock"}]},
            ],
            "ActiveStateLock",
        ),
        ([{}], "StateLockReadUnavailable"),
        ([{"IsTruncated": "false"}], "StateLockReadUnavailable"),
        ([{"IsTruncated": False, "Contents": [{}]}], "StateLockReadUnavailable"),
        ([{"IsTruncated": False, "Contents": [{"Key": "other"}]}], "StateLockReadUnavailable"),
        ([{"IsTruncated": False, "Contents": {}}], "StateLockReadUnavailable"),
        ([{"IsTruncated": True}], "StateLockReadUnavailable"),
        (
            [
                {"IsTruncated": True, "NextContinuationToken": "next"},
                {"IsTruncated": True, "NextContinuationToken": "next"},
            ],
            "StateLockReadUnavailable",
        ),
        (["denied"], "StateLockReadUnavailable"),
    ],
)
def test_prefix_listing_proves_exact_lock_absence(pages, expected):
    requests = []
    state = {
        "lineage": "fixed",
        "serial": 12,
        "resources": [],
        "outputs": {
            "manifest": {
                "value": {"account_id": "123456789012", "region": "ap-northeast-1", "run_id": ""}
            }
        },
    }

    def head(**kw):
        if kw["Key"].endswith(".tflock"):
            raise ClientError({"Error": {"Code": "403"}}, "HeadObject")
        return {"VersionId": "immutable"}

    def listing(**kw):
        requests.append(kw)
        assert kw["ExpectedBucketOwner"] == "123456789012"
        assert kw["Prefix"] == "dev/terraform.tfstate.tflock"
        page = pages.pop(0)
        if page == "denied":
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectsV2")
        return page

    def get(**kw):
        assert kw["VersionId"] == "immutable"
        assert kw["ExpectedBucketOwner"] == "123456789012"
        return {
            "VersionId": "immutable",
            "ServerSideEncryption": "AES256",
            "Body": io.BytesIO(json.dumps(state).encode()),
        }

    session = SimpleNamespace(
        client=lambda *a, **kw: SimpleNamespace(
            head_object=head, get_object=get, list_objects_v2=listing
        )
    )

    def invoke():
        return tool("deployment_guards").read_state_snapshot(
            session, "123456789012", "ap-northeast-1", "dev/terraform.tfstate"
        )

    if expected == "pass":
        assert invoke()["state"] == state
    else:
        with pytest.raises(ValueError, match=expected):
            invoke()
    assert requests
    if len(requests) == 2:
        assert requests[1]["ContinuationToken"] == "next"


def test_prepared_19_variables_map_to_14_exact_inputs_plus_derived_and_defaults():
    module = tool("terraform_dev")
    values = valid_inputs()
    values.pop("jpy_per_usd")
    values.pop("budget_rate_date")
    values.update(log_usage="customer", monthly_budget_usd="10.00")
    normalized = module.validate_inputs(values, "123456789012", "ap-northeast-1")
    full = normalized | {"worker_ai_environment": {}, "worker_wif_enabled": False}
    assert len(values) == 14 and len(normalized) == 17 and len(full) == 19
    assert normalized["cors_origins"] == ["http://localhost:3000"]
    assert not module.valid_input_keys(full)
    configuration = {k: v for k, v in values.items() if k not in tool("ci_deploy").PACKAGE_KEYS}
    assert len(configuration) == 10 and module.valid_input_keys(
        configuration, without_artifact=True
    )
    assert all(
        normalized[k] is False
        for k in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("monthly_budget_usd", 10),
        ("cors_origins", ["https://example.invalid"]),
        ("account_id", "123456789012"),
        ("worker_ai_environment", {}),
        ("worker_wif_enabled", False),
    ],
)
def test_unaccepted_full_variables_cannot_silently_override_transport(key, value):
    values = valid_inputs()
    values.pop("jpy_per_usd")
    values.pop("budget_rate_date")
    values["monthly_budget_usd"] = "10.00"
    values[key] = value
    with pytest.raises(ValueError):
        tool("terraform_dev").validate_inputs(values, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize(
    "fault",
    [None, "state-denied", "state-changed", "get-mismatch", "put-timeout", "artifact-mismatch"],
)
def test_ci_plan_checks_state_before_upload_and_never_retries(monkeypatch, tmp_path, fault):
    module = tool("ci_deploy")
    counts = {"state": 0, "build": 0, "put": 0, "get": 0, "execute": 0}
    objects = {}
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(
        module, "preflight", lambda env: ("123456789012", "ap-northeast-1", "plan", {})
    )
    monkeypatch.setattr(module, "checked_git", lambda *a: "a" * 40)
    monkeypatch.setenv(
        "P4_PACKAGE_SHA256",
        module.hashlib.sha256(b"zip").hexdigest() if fault != "artifact-mismatch" else "a" * 64,
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")

    def state(*args):
        counts["state"] += 1
        if fault == "state-denied":
            raise ValueError("VersionedStateReadDenied")
        return {"serial": 12 + int(fault == "state-changed" and counts["state"] == 2)}

    monkeypatch.setattr(module, "plan_state_preflight", state)

    def build(directory, sha):
        counts["build"] += 1
        assert counts["state"] == 1
        path = directory / "app.zip"
        path.write_bytes(b"zip")
        return path, {
            "sha256_base64": module.base64.b64encode(
                module.hashlib.sha256(b"zip").digest()
            ).decode()
        }

    monkeypatch.setattr(module, "build_package", build)

    def put(**kw):
        counts["put"] += 1
        assert counts["state"] == 2
        assert kw["ExpectedBucketOwner"] == "123456789012"
        assert kw["IfNoneMatch"] == "*" and kw["ServerSideEncryption"] == "AES256"
        assert (
            kw["ChecksumSHA256"]
            == module.base64.b64encode(module.hashlib.sha256(kw["Body"]).digest()).decode()
        )
        if fault == "put-timeout":
            raise TimeoutError("uncertain")
        objects[kw["Key"]] = kw["Body"]
        return {"VersionId": "version"}

    def get(**kw):
        counts["get"] += 1
        assert kw["VersionId"] == "version" and kw["ExpectedBucketOwner"] == "123456789012"
        body = b"bad" if fault == "get-mismatch" else objects[kw["Key"]]
        return {
            "VersionId": "version",
            "ServerSideEncryption": "AES256",
            "ContentLength": len(body),
            "Body": io.BytesIO(body),
        }

    client = SimpleNamespace(put_object=put, get_object=get)
    session = SimpleNamespace(client=lambda *a, **kw: client)
    monkeypatch.setattr(module, "role_session", lambda *a: session)

    def execute(operation, input_path, directory):
        counts["execute"] += 1
        assert counts["put"] == counts["get"] == 1
        assert operation == "plan"
        directory.mkdir()
        for name in ["dev.tfplan", "plan.json", "summary.json", "review.private.json"]:
            (directory / name).write_bytes(b"private")
        return {"status": "planned", "plan_sha256": "b" * 64}

    monkeypatch.setattr(module, "execute", execute)
    assert module.main() == (0 if fault is None else 1)
    if fault is None:
        assert counts["put"] == counts["get"] == 6 and counts["execute"] == 1
        assert all(key.startswith(("lambda/", "plans/")) for key in objects)
    elif fault == "state-denied":
        assert counts["build"] == counts["put"] == counts["execute"] == 0
    elif fault in {"state-changed", "artifact-mismatch"}:
        assert counts["build"] == 1 and counts["put"] == counts["execute"] == 0
    else:
        assert counts["put"] == 1 and counts["execute"] == 0
    assert module.s3_client(session) is client
    # The client constructor explicitly disables SDK retries, including lost Put responses.
    configs = []
    module.s3_client(SimpleNamespace(client=lambda *a, **kw: configs.append(kw["config"])))
    assert configs[0].retries == {"total_max_attempts": 1}


@pytest.mark.parametrize("values", [{"api_enabled": True}, {}, {"api_enabled": None}])
def test_plan_state_preflight_rejects_unknown_or_active_flags(monkeypatch, values):
    module = tool("ci_deploy")
    import deployment_guards

    flags = dict.fromkeys(
        ["api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled"], False
    )
    if values:
        flags.update(values)
    else:
        flags = {}
    monkeypatch.setattr(module, "role_session", lambda *a: None)
    monkeypatch.setattr(
        deployment_guards,
        "read_state_snapshot",
        lambda *a, **kw: {"manifest": {"configuration": flags}},
    )
    with pytest.raises(ValueError, match="ClosedExistingStateRequired"):
        module.plan_state_preflight("123456789012", "ap-northeast-1")


@pytest.mark.parametrize(
    "flag", [None, "api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled"]
)
def test_ci_preflight_requires_closed_configuration_without_artifact_override(monkeypatch, flag):
    module = tool("ci_deploy")
    values = valid_inputs()
    values.pop("jpy_per_usd")
    values.pop("budget_rate_date")
    values["monthly_budget_usd"] = "10.00"
    values = {k: v for k, v in values.items() if k not in module.PACKAGE_KEYS}
    if flag:
        values[flag] = True
    monkeypatch.setattr(module, "account_settings", lambda *a: ("123456789012", "ap-northeast-1"))
    monkeypatch.setattr(module, "terraform_environment", lambda *a: {})
    environment = {
        "P4_AWS_EXECUTION_READY": "true",
        "P4_OPERATION": "plan",
        "P4_PACKAGE_SHA256": "a" * 64,
        "P4_DEPLOY_INPUTS": json.dumps(values),
    }
    if flag:
        with pytest.raises(ValueError, match="ClosedInitialDeploymentRequired"):
            module.preflight(environment)
    else:
        assert module.preflight(environment)[3] == values


def test_plan_object_cost_bound_rejects_before_put():
    module = tool("ci_deploy")
    client = SimpleNamespace(put_object=lambda **kw: pytest.fail("oversize object uploaded"))
    with pytest.raises(ValueError, match="PlanObjectSizeLimitExceeded"):
        module.put(
            client,
            "ai-interview-artifacts-123456789012-ap-northeast-1",
            "plans/123/1/review.private.json",
            b"x" * (module.PLAN_OBJECT_MAX_BYTES + 1),
        )


@pytest.mark.parametrize("digest", [None, "", "main", "A" * 64, "a" * 63])
def test_ci_plan_requires_explicit_approved_package_digest(monkeypatch, digest):
    module = tool("ci_deploy")
    values = valid_inputs()
    values = {k: v for k, v in values.items() if k not in module.PACKAGE_KEYS}
    monkeypatch.setattr(module, "account_settings", lambda *a: ("123456789012", "ap-northeast-1"))
    environment = {
        "P4_AWS_EXECUTION_READY": "true",
        "P4_OPERATION": "plan",
        "P4_DEPLOY_INPUTS": json.dumps(values),
    }
    if digest is not None:
        environment["P4_PACKAGE_SHA256"] = digest
    with pytest.raises(ValueError, match="ApprovedArtifactDigestRequired"):
        module.preflight(environment)
