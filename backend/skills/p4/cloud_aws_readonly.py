"""Frozen-credential read-only SDK boundary. No client is created on import."""

import json
from pathlib import Path

from cloud_controller_core import ACCOUNT, REGION, Refusal, digest, require

ALLOWED = {
    "s3": {
        "head_bucket",
        "get_bucket_location",
        "get_bucket_versioning",
        "get_bucket_encryption",
        "get_bucket_policy",
        "get_bucket_tagging",
        "get_public_access_block",
        "head_object",
        "get_object",
        "list_objects_v2",
        "list_object_versions",
    },
    "iam": {
        "get_role",
        "get_role_policy",
        "list_role_policies",
        "list_attached_role_policies",
        "get_policy",
        "get_policy_version",
        "list_policy_tags",
        "get_open_id_connect_provider",
        "list_roles",
    },
    "lambda": {
        "get_alias",
        "get_function_configuration",
        "get_function_concurrency",
        "get_policy",
        "get_event_source_mapping",
        "list_functions",
        "list_event_source_mappings",
    },
    "apigatewayv2": {
        "get_api",
        "get_apis",
        "get_stage",
        "get_stages",
        "get_routes",
        "get_integrations",
        "get_authorizers",
    },
    "dynamodb": {"describe_table", "describe_time_to_live", "list_tables"},
    "sqs": {"get_queue_attributes", "list_queues"},
    "sns": {"get_topic_attributes", "list_topics", "list_subscriptions_by_topic"},
    "cognito-idp": {
        "describe_user_pool",
        "describe_user_pool_client",
        "get_group",
        "list_user_pools",
    },
    "scheduler": {"get_schedule", "get_schedule_group", "list_schedules"},
    "logs": {"describe_log_groups"},
    "cloudwatch": {"describe_alarms"},
    "ses": {"get_identity_verification_attributes"},
    "budgets": {
        "describe_budget",
        "describe_notifications_for_budget",
        "describe_subscribers_for_notification",
    },
    "sts": {"get_caller_identity"},
}


class CachedIdentity:
    def __init__(self, identity, journal):
        self.identity, self.j = identity, journal

    def get_caller_identity(self):
        self.j.record("same-frozen-session-identity-cache-used")
        return self.identity


class SessionView:
    def __init__(self, session, scope):
        self.session, self.scope = session, scope
        self.identity = None
        self.events = session.events
        self.clients = {}

    def client(self, service, region_name=None, config=None):
        require(region_name in {None, REGION}, "ReaderRegionMismatch")
        if service == "sts" and self.identity is not None:
            return CachedIdentity(self.identity, self.scope.j)
        require(service in ALLOWED, "ReaderServiceForbidden")
        if service not in self.clients:
            from botocore.config import Config

            opts = Config(
                retries={"total_max_attempts": 1},
                connect_timeout=5,
                read_timeout=15,
                ignore_configured_endpoint_urls=True,
            )
            client = self.session.client(service, region_name=REGION, config=opts)
            require(client.meta.endpoint_url.startswith("https://"), "AwsTlsRequired")
            reverse = {v: k for k, v in client.meta.method_to_api_mapping.items()}

            def guard(params, model, context, **kwargs):
                if service == "s3" and "Bucket" in params:
                    params.setdefault("ExpectedBucketOwner", ACCOUNT)
                operation = reverse.get(model.name, "")
                self.scope.check(service, operation, params)
                context["approved_read_params"] = dict(params)

            client.meta.events.register("before-parameter-build.*.*", guard)

            def observe(parsed, model, context, **kwargs):
                self.scope.observe(
                    service, reverse.get(model.name, ""), context["approved_read_params"], parsed
                )

            client.meta.events.register("after-call.*.*", observe)
            self.clients[service] = client
        return self.clients[service]

    def fresh_identity(self):
        old = self.identity
        self.identity = None
        try:
            actual = self.client("sts").get_caller_identity()
        finally:
            self.identity = old
        expected = (
            f"arn:aws:sts::{ACCOUNT}:assumed-role/ai-interview-ci-plan/p4-{self.scope.run_id}-plan"
        )
        require(
            actual["Account"] == ACCOUNT
            and actual["Arn"] == expected
            and actual["UserId"].endswith(f":p4-{self.scope.run_id}-plan"),
            "CloudActorMismatch",
        )
        self.identity = actual
        return actual


class ReadonlyReader:
    def __init__(self, session, scope, source):
        self.scope = scope
        self.session = SessionView(session, scope)
        self.source = Path(source)
        self.batches = set()

    def verify_no_alarms(self):
        client = self.session.client("cloudwatch")
        request = {
            "AlarmNamePrefix": "ai-interview-dev-",
            "AlarmTypes": ["MetricAlarm", "CompositeAlarm", "LogAlarm"],
            "MaxRecords": 100,
        }
        seen = set()
        while True:
            page = client.describe_alarms(**request)
            require(
                not any(page.get(key) for key in ("MetricAlarms", "CompositeAlarms", "LogAlarms")),
                "UnexpectedDevAlarm",
            )
            token = page.get("NextToken")
            if token is None:
                return
            require(
                isinstance(token, str) and token and token not in seen, "AlarmPaginationIncomplete"
            )
            seen.add(token)
            request["NextToken"] = token

    def versions(self, key):
        s3 = self.session.client("s3")
        request = {
            "Bucket": f"ai-interview-state-{ACCOUNT}-{REGION}",
            "ExpectedBucketOwner": ACCOUNT,
            "Prefix": key,
            "MaxKeys": 1000,
        }
        rows = []
        seen = set()
        while True:
            page = s3.list_object_versions(**request)
            require(type(page.get("IsTruncated")) is bool, "VersionPaginationIncomplete")
            for group in ["Versions", "DeleteMarkers"]:
                for row in page.get(group, []):
                    require(row["Key"].startswith(key), "VersionPrefixMismatch")
                    require(
                        isinstance(row.get("VersionId"), str)
                        and row["VersionId"] not in {"", "null"}
                        and (
                            group != "Versions" or type(row.get("Size")) is int and row["Size"] >= 0
                        ),
                        "InvalidStateVersionEntry",
                    )
                    if row["Key"] == key:
                        rows.append(
                            {"kind": group, "version_id": row["VersionId"], "size": row.get("Size")}
                        )
            if not page["IsTruncated"]:
                break
            token = (page.get("NextKeyMarker"), page.get("NextVersionIdMarker"))
            require(
                all(isinstance(v, str) and v for v in token) and token not in seen,
                "VersionPaginationCycle",
            )
            seen.add(token)
            request.update(KeyMarker=token[0])
            if token[1]:
                request["VersionIdMarker"] = token[1]
            else:
                request.pop("VersionIdMarker", None)
        require(
            rows and len({(v["kind"], v["version_id"]) for v in rows}) == len(rows),
            "VersionInventoryIncomplete",
        )
        return sorted(rows, key=lambda r: (r["kind"], r["version_id"]))

    def snapshot_key(self, key, expected):
        from botocore.exceptions import ClientError
        from deployment_guards import exact_key_absent

        s3 = self.session.client("s3")
        args = {
            "Bucket": f"ai-interview-state-{ACCOUNT}-{REGION}",
            "Key": key,
            "ExpectedBucketOwner": ACCOUNT,
        }
        lock = args | {"Key": key + ".tflock"}

        def absent():
            try:
                s3.head_object(**lock)
            except ClientError as e:
                code = e.response["Error"]["Code"]
                if code in {"403", "Forbidden", "AccessDenied"}:
                    require(exact_key_absent(s3, lock), "ActiveLock")
                else:
                    require(code in {"404", "NoSuchKey", "NotFound"}, "LockReadUnknown")
            else:
                raise Refusal("ActiveLock")

        absent()
        head = s3.head_object(**args)
        require(
            head.get("VersionId") == expected["version_id"]
            and head.get("ServerSideEncryption") == "AES256"
            and head["ContentLength"] <= 32 * 1024 * 1024,
            "HistoricalStateVersionChanged",
        )
        obj = s3.get_object(**args, VersionId=expected["version_id"])
        with obj["Body"] as body:
            raw = body.read(32 * 1024 * 1024 + 1)
        require(
            len(raw) == head["ContentLength"] == obj["ContentLength"]
            and obj["VersionId"] == expected["version_id"]
            and obj.get("ServerSideEncryption") == "AES256"
            and digest(raw) == expected["sha256"],
            "StateHashOrVersionMismatch",
        )
        state = json.loads(raw)
        identity = {
            "lineage": state["lineage"],
            "serial": state["serial"],
            "version_id": expected["version_id"],
            "sha256": digest(raw),
        }
        require(identity == expected, "StateIdentityMismatch")
        self.scope.bind(state)
        versions = self.versions(key)
        require(
            any(
                v["kind"] == "Versions"
                and v["version_id"] == expected["version_id"]
                and v["size"] == len(raw)
                for v in versions
            ),
            "CurrentStateVersionInventoryMissing",
        )
        require(
            s3.head_object(**args)["VersionId"] == expected["version_id"], "StateChangedDuringRead"
        )
        absent()
        if hasattr(self.scope.j, "path"):
            with (
                self.scope.j.path / f"state-{self.active_label}-{key.split('/')[0]}.raw.private"
            ).open("xb") as stream:
                stream.write(raw)
        return {"identity": identity, "state": state, "versions": versions}
