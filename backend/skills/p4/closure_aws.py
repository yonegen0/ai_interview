"""Concrete read-only AWS snapshots and saved Terraform plan/apply transport."""

import hashlib
import json
import os
from pathlib import Path

from botocore.config import Config
from botocore.exceptions import ClientError
from closure_adapter import digest, state_addresses
from manifest import verify_live_manifest, wait_for_manifest
from terraform_dev import TF_VERSION, run

from interview_backend.deployment import (
    checked_session,
    credential_environment,
    require_aws_execution,
    terraform_environment,
)


def require_clean_source(root, environment):
    """Root-anchored checks include untracked runtime and Terraform overlays."""
    paths = [":(top)backend/src", ":(top)backend/skills/p4", ":(top)terraform"]
    for arguments in (
        ["diff", "--name-only", "HEAD", "--", *paths],
        ["ls-files", "--others", "--exclude-standard", "--", *paths],
    ):
        if run(["git", *arguments], cwd=root, env=environment).strip():
            raise ValueError("CleanApprovedExecutionSourceRequired")


class TerraformAWS:
    def __init__(self, root, approval, environment=None):
        require_aws_execution(environment or os.environ)
        self.root, self.approval = Path(root).resolve(), approval
        self.account, self.region = approval["account_id"], approval["region"]
        if (
            self.region != "ap-northeast-1"
            or self.root.name != "dev"
            or self.root.parent.name != "environments"
        ):
            raise ValueError("CanonicalDevRootRequired")
        self.env = terraform_environment(
            self.root, environment or os.environ, self.account, self.region
        )
        if digest((self.root / ".terraform.lock.hcl").read_bytes()) != approval["lock_sha256"]:
            raise ValueError("ProviderLockMismatch")
        source = run(["git", "rev-parse", "HEAD"], cwd=self.root, env=self.env).decode().strip()
        if source != approval["code_sha"]:
            raise ValueError("ApprovedSourceRequired")
        require_clean_source(self.root, self.env)
        version = json.loads(run(["terraform", "version", "-json"], cwd=self.root, env=self.env))
        if version["terraform_version"] != TF_VERSION:
            raise ValueError("TerraformVersionMismatch")
        self.session = checked_session(self.account, self.region, environment=self.env)

        def readonly(model, **kwargs):
            if not model.name.startswith(("Get", "Head", "List", "Describe")):
                raise ValueError("ClosureAWSMutationForbidden")

        self.session.events.register("before-call.*.*", readonly)
        self.env = credential_environment(self.session, self.env)
        self.config = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=15)
        self.backend = {
            "bucket": f"ai-interview-state-{self.account}-{self.region}",
            "key": "dev/terraform.tfstate",
        }
        metadata = json.loads((self.root / ".terraform/terraform.tfstate").read_bytes())["backend"]
        expected = self.backend | {
            "region": self.region,
            "encrypt": True,
            "use_lockfile": True,
            "allowed_account_ids": [self.account],
        }
        if (
            metadata["type"] != "s3"
            or any(metadata["config"].get(k) != v for k, v in expected.items())
            or any(
                metadata["config"].get(k)
                for k in ("access_key", "secret_key", "token", "profile", "endpoint")
            )
        ):
            raise ValueError("CanonicalBackendRequired")

    def client(self, service):
        return self.session.client(service, region_name=self.region, config=self.config)

    def snapshot(self, manifest):
        s3 = self.client("s3")
        args = {
            "Bucket": self.backend["bucket"],
            "Key": self.backend["key"],
            "ExpectedBucketOwner": self.account,
        }
        head = s3.head_object(**args)
        obj = s3.get_object(**args, VersionId=head["VersionId"])
        with obj["Body"] as body:
            raw = body.read()
        state = json.loads(raw)
        try:
            s3.head_object(**(args | {"Key": args["Key"] + ".tflock"}))
            raise ValueError("ActiveStateLock")
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
                raise
        if (
            obj["VersionId"] != head["VersionId"]
            or obj.get("ServerSideEncryption") != "AES256"
            or state["outputs"]["manifest"]["value"] != manifest
        ):
            raise ValueError("StateManifestMismatch")
        # Full configuration checks enforce flags, exact Lambda code/environment,
        # runtime/architecture/concurrency and aliases, including expected alarm set.
        if all(
            manifest["configuration"].get(k) is False
            for k in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
        ):
            approved = manifest["configuration"] | {
                "worker_ai_environment": manifest.get("worker_ai_environment", {})
            }
            wait_for_manifest(self.session, manifest, approved_inputs=approved)
        else:
            verify_live_manifest(self.session, manifest, require_api_enabled=False)
        self.namespace(state)
        if s3.head_object(**args)["VersionId"] != head["VersionId"]:
            raise ValueError("StateChangedDuringRead")
        return {
            "state": state,
            "identity": {
                "lineage": state["lineage"],
                "serial": state["serial"],
                "version_id": head["VersionId"],
                "sha256": hashlib.sha256(raw).hexdigest(),
            },
            "manifest": manifest,
            "active_lock": False,
            "state_outside_dev_resources": 0,
        }

    def namespace(self, state):
        """Compare all managed dev instances against paginated service inventories."""
        expected = {}
        for resource in state["resources"]:
            if resource.get("mode") == "managed":
                expected.setdefault(resource["type"], []).extend(
                    i["attributes"] for i in resource["instances"]
                )
        prefix = "ai-interview-dev"
        from bootstrap_contract import canonical_policy

        iam = self.client("iam")
        for role in expected["aws_iam_role"]:
            name = role["name"]
            policies = [p for p in expected.get("aws_iam_role_policy", []) if p["role"] == name]
            actual_names = {
                p
                for page in iam.get_paginator("list_role_policies").paginate(RoleName=name)
                for p in page["PolicyNames"]
            }
            if actual_names != {p["name"] for p in policies}:
                raise ValueError("UntrackedRuntimeInlinePolicy")
            for policy in policies:
                live = iam.get_role_policy(RoleName=name, PolicyName=policy["name"])[
                    "PolicyDocument"
                ]
                if canonical_policy(live) != canonical_policy(policy["policy"]):
                    raise ValueError("RuntimePolicyStateMismatch")
            attached = {
                p["PolicyArn"]
                for page in iam.get_paginator("list_attached_role_policies").paginate(RoleName=name)
                for p in page["AttachedPolicies"]
            }
            wanted = {
                p["policy_arn"]
                for p in expected.get("aws_iam_role_policy_attachment", [])
                if p["role"] == name
            }
            if attached != wanted:
                raise ValueError("UntrackedRuntimeManagedPolicy")

        def paged(service, operation, field, **kwargs):
            return [
                item
                for page in self.client(service).get_paginator(operation).paginate(**kwargs)
                for item in page.get(field, [])
            ]

        checks = [
            (
                {
                    x["FunctionName"]
                    for x in paged("lambda", "list_functions", "Functions")
                    if x["FunctionName"].startswith(prefix + "-")
                },
                {x["function_name"] for x in expected["aws_lambda_function"]},
            ),
            (
                {
                    x["UUID"]
                    for x in paged("lambda", "list_event_source_mappings", "EventSourceMappings")
                    if x["FunctionArn"].split(":function:")[-1].startswith(prefix + "-")
                },
                {x["id"] for x in expected["aws_lambda_event_source_mapping"]},
            ),
            (
                {
                    x
                    for x in paged("dynamodb", "list_tables", "TableNames")
                    if x.startswith(prefix + "-")
                },
                {x["name"] for x in expected["aws_dynamodb_table"]},
            ),
            (
                set(paged("sqs", "list_queues", "QueueUrls", QueueNamePrefix=prefix + "-")),
                {x["url"] for x in expected["aws_sqs_queue"]},
            ),
            (
                {
                    x["ApiId"]
                    for x in paged("apigatewayv2", "get_apis", "Items")
                    if x["Name"].startswith(prefix + "-")
                },
                {x["id"] for x in expected["aws_apigatewayv2_api"]},
            ),
            (
                {
                    x["Arn"]
                    for x in paged("scheduler", "list_schedules", "Schedules", GroupName=prefix)
                },
                {x["arn"] for x in expected["aws_scheduler_schedule"]},
            ),
            (
                {
                    x["RoleName"]
                    for x in paged("iam", "list_roles", "Roles")
                    if x["RoleName"].startswith(prefix + "-")
                },
                {x["name"] for x in expected["aws_iam_role"]},
            ),
            (
                {
                    x["logGroupName"]
                    for x in paged(
                        "logs",
                        "describe_log_groups",
                        "logGroups",
                        logGroupNamePrefix="/aws/lambda/" + prefix + "-",
                    )
                },
                {
                    x["name"]
                    for x in expected["aws_cloudwatch_log_group"]
                    if x["name"].startswith("/aws/lambda/")
                },
            ),
            (
                {
                    x["TopicArn"]
                    for x in paged("sns", "list_topics", "Topics")
                    if x["TopicArn"].rsplit(":", 1)[-1].startswith(prefix + "-")
                },
                {x["arn"] for x in expected["aws_sns_topic"]},
            ),
            (
                {
                    x["Id"]
                    for x in paged("cognito-idp", "list_user_pools", "UserPools", MaxResults=60)
                    if x["Name"].startswith(prefix + "-")
                },
                {x["id"] for x in expected["aws_cognito_user_pool"]},
            ),
        ]
        alarms = self.client("cloudwatch").describe_alarms(AlarmNamePrefix=prefix + "-")
        if alarms.get("NextToken") or alarms.get("CompositeAlarms"):
            raise ValueError("UnaccountedAlarmInventory")
        checks.append(
            (
                {x["AlarmName"] for x in alarms["MetricAlarms"]},
                {x["alarm_name"] for x in expected.get("aws_cloudwatch_metric_alarm", [])},
            )
        )
        if any(actual != wanted for actual, wanted in checks):
            raise ValueError("StateOutsideDevResources")
        if len(state_addresses(state)) != sum(len(r["instances"]) for r in state["resources"]):
            raise ValueError("StateInstanceMismatch")

    def plan(self, inputs, directory):
        self.apply_env = dict(self.env)
        for key, value in inputs.items():
            self.apply_env["TF_VAR_" + key] = value if isinstance(value, str) else json.dumps(value)
        if any(k.startswith("TF_VAR_") and k[7:] not in inputs for k in self.apply_env):
            raise ValueError("UnexpectedTerraformInput")
        plan = directory / "closure.tfplan"
        run(
            ["terraform", "plan", "-input=false", "-lock-timeout=0s", "-out=" + str(plan)],
            cwd=self.root,
            env=self.apply_env,
            accepted=(0, 2),
        )
        review_raw = run(
            ["terraform", "show", "-json", str(plan)], cwd=self.root, env=self.apply_env
        )
        (directory / "review.private.json").write_bytes(review_raw)
        return plan, json.loads(review_raw)

    def apply(self, plan, approved_sha):
        if digest(plan.read_bytes()) != approved_sha:
            raise ValueError("SavedClosurePlanMismatch")
        run(
            ["terraform", "apply", "-input=false", "-lock-timeout=0s", str(plan)],
            cwd=self.root,
            env=self.apply_env,
        )
