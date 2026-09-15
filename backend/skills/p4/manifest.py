"""Validate deployment identity before obtaining AWS clients or sending HTTP tokens."""

import json
import re
import time
from pathlib import Path

from interview_backend.deployment import checked_session as checked_session
from interview_backend.deployment import validate_target


def wait_for_manifest(
    session, manifest, *, approved_inputs, timeout=60, clock=time.monotonic, sleep=time.sleep
):
    deadline = clock() + timeout
    while True:
        try:
            verify_live_manifest(
                session, manifest, require_api_enabled=False, approved_inputs=approved_inputs
            )
            return
        except ValueError:
            remaining = deadline - clock()
            if remaining <= 0:
                raise ValueError("DeploymentReadbackDeadlineExceeded") from None
            sleep(min(2, remaining))


def read_manifest(path, account, region, *, require_test=False):
    validate_target(account, region)
    try:
        return _read_manifest(path, account, region, require_test=require_test)
    except OSError, ValueError, TypeError, AttributeError, KeyError:
        raise ValueError("InvalidDeploymentManifest") from None


def _read_manifest(path, account, region, *, require_test=False):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "manifest" in data and isinstance(data["manifest"], dict) and "value" in data["manifest"]:
        data = data["manifest"]["value"]
    if type(data.get("schema_version")) is not int or data["schema_version"] != 2:
        raise ValueError("InvalidManifest")
    if (
        not re.fullmatch(r"[0-9]{12}", account)
        or data.get("account_id") != account
        or data.get("region") != region
    ):
        raise ValueError("ManifestAccountMismatch")
    run = data.get("run_id", "")
    if run and not re.fullmatch(r"[a-z0-9-]{1,24}", run):
        raise ValueError("InvalidRunId")
    if require_test and (not run or data.get("environment") != "test"):
        raise ValueError("DedicatedTestStackRequired")
    if data.get("environment") != ("test" if run else "dev"):
        raise ValueError("InvalidManifestEnvironment")
    prefix = f"ai-interview-test-{run}" if run else "ai-interview-dev"
    if data.get("table_name") != f"{prefix}-main":
        raise ValueError("InvalidManifestTable")
    for key, role, alias in (
        ("api", "api", "live"),
        ("worker", "worker", "live"),
        ("streams", "dispatcher", "streams"),
        ("recovery", "dispatcher", "recovery"),
    ):
        if (
            data.get("aliases", {}).get(key)
            != f"arn:aws:lambda:{region}:{account}:function:{prefix}-{role}:{alias}"
        ):
            raise ValueError("InvalidManifestAlias")
    api_id = data.get("api_id", "")
    if (
        not re.fullmatch(r"[a-z0-9]+", api_id)
        or data.get("api_endpoint") != f"https://{api_id}.execute-api.{region}.amazonaws.com/dev"
    ):
        raise ValueError("InvalidManifestEndpoint")
    if (
        data.get("queue_arn") != f"arn:aws:sqs:{region}:{account}:{prefix}-main"
        or data.get("queue_url") != f"https://sqs.{region}.amazonaws.com/{account}/{prefix}-main"
    ):
        raise ValueError("InvalidManifestQueue")
    for key, suffix in (("worker_dlq_url", "worker-dlq"), ("stream_failure_url", "stream-failure")):
        if data.get(key) != f"https://sqs.{region}.amazonaws.com/{account}/{prefix}-{suffix}":
            raise ValueError("InvalidManifestQueue")
    if not re.fullmatch(
        re.escape(region) + r"_[A-Za-z0-9]+", data.get("user_pool_id", "")
    ) or not re.fullmatch(r"[A-Za-z0-9]{1,128}", data.get("client_id", "")):
        raise ValueError("InvalidManifestIdentity")
    if not all(
        re.fullmatch(r"[1-9][0-9]*", str(data.get("versions", {}).get(k, "")))
        for k in ("api", "worker", "dispatcher")
    ):
        raise ValueError("InvalidManifestVersions")
    configuration = data["configuration"]
    if not isinstance(configuration, dict) or set(configuration) != {
        "boundary_arn",
        "ses_email",
        "ses_identity_arn",
        "alarm_email",
        "monthly_budget_usd",
        "cors_origins",
        "worker_enabled",
        "streams_enabled",
        "scheduler_enabled",
        "api_enabled",
    }:
        raise ValueError("InvalidManifestConfiguration")
    if any(
        type(configuration[key]) is not bool
        for key in ("worker_enabled", "streams_enabled", "scheduler_enabled", "api_enabled")
    ):
        raise ValueError("InvalidManifestConfiguration")
    return data


def verify_live_manifest(session, manifest, *, require_api_enabled=True, approved_inputs=None):
    """Read known resources, never enumerate or trust a self-reported endpoint alone."""
    from botocore.config import Config

    config = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=5)
    try:
        account, region = manifest["account_id"], manifest["region"]
        validate_target(account, region)
        if session.client("sts", config=config).get_caller_identity()["Account"] != account:
            raise ValueError
        if manifest["schema_version"] != 2:
            raise ValueError
        if approved_inputs is not None:
            expected = {key: approved_inputs[key] for key in manifest["configuration"]}
            expected["monthly_budget_usd"] = str(expected["monthly_budget_usd"])
            if manifest["configuration"] != expected:
                raise ValueError
        api = session.client("apigatewayv2", config=config).get_api(ApiId=manifest["api_id"])
        if api["ApiEndpoint"] + "/dev" != manifest["api_endpoint"]:
            raise ValueError
        if require_api_enabled and api.get("DisableExecuteApiEndpoint"):
            raise ValueError
        table = session.client("dynamodb", config=config).describe_table(
            TableName=manifest["table_name"]
        )["Table"]
        if (
            table["TableArn"]
            != (f"arn:aws:dynamodb:{region}:{account}:table/{manifest['table_name']}")
            or table["LatestStreamArn"] != manifest["stream_arn"]
        ):
            raise ValueError
        if table["StreamSpecification"] != {
            "StreamEnabled": True,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        }:
            raise ValueError
        indexes = table.get("GlobalSecondaryIndexes", [])
        if (
            len(indexes) != 1
            or indexes[0]["IndexName"] != "WorkIndex"
            or (indexes[0]["Projection"]["ProjectionType"] != "KEYS_ONLY")
        ):
            raise ValueError
        queue = session.client("sqs", config=config).get_queue_attributes(
            QueueUrl=manifest["queue_url"],
            AttributeNames=[
                "QueueArn",
                "VisibilityTimeout",
                "MessageRetentionPeriod",
                "SqsManagedSseEnabled",
                "RedrivePolicy",
            ],
        )["Attributes"]
        if any(
            queue.get(key) != expected
            for key, expected in {
                "QueueArn": manifest["queue_arn"],
                "VisibilityTimeout": "360",
                "MessageRetentionPeriod": "345600",
                "SqsManagedSseEnabled": "true",
            }.items()
        ):
            raise ValueError
        if int(json.loads(queue["RedrivePolicy"])["maxReceiveCount"]) != 5:
            raise ValueError
        cognito = session.client("cognito-idp", config=config)
        pool = cognito.describe_user_pool(UserPoolId=manifest["user_pool_id"])["UserPool"]
        if pool["Arn"] != (
            f"arn:aws:cognito-idp:{region}:{account}:userpool/{manifest['user_pool_id']}"
        ):
            raise ValueError
        client = cognito.describe_user_pool_client(
            UserPoolId=manifest["user_pool_id"], ClientId=manifest["client_id"]
        )["UserPoolClient"]
        if client.get("ClientSecret") or client["ClientId"] != manifest["client_id"]:
            raise ValueError
        lambdas = session.client("lambda", config=config)
        for name, arn in manifest["aliases"].items():
            function, alias = arn.rsplit(":", 1)
            observed = lambdas.get_alias(FunctionName=function, Name=alias)
            component = "dispatcher" if name in {"streams", "recovery"} else name
            if observed["AliasArn"] != arn or observed["FunctionVersion"] != str(
                manifest["versions"][component]
            ):
                raise ValueError
            if observed.get("RoutingConfig", {}).get("AdditionalVersionWeights"):
                raise ValueError
            deployed = lambdas.get_function_configuration(
                FunctionName=function, Qualifier=observed["FunctionVersion"]
            )
            if deployed["CodeSha256"] != manifest["artifact"]["sha256_base64"]:
                raise ValueError
            if deployed["Version"] != str(manifest["versions"][component]):
                raise ValueError
            if deployed["Runtime"] != "python3.14" or deployed["Architectures"] != ["x86_64"]:
                raise ValueError
            if (
                deployed["MemorySize"] != 512
                or deployed["Timeout"] != {"api": 15, "worker": 60, "dispatcher": 30}[component]
            ):
                raise ValueError
        from manifest_checks import verify_configuration

        verify_configuration(session, manifest, config)
    except Exception:
        raise ValueError("DeploymentReadbackFailed") from None
