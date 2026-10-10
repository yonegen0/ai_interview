"""Version-pinned bootstrap snapshots and managed-resource readback; SDK writes forbidden."""

import json

from bootstrap_contract import canonical_policy
from bootstrap_state import verify_created_resources
from botocore.config import Config
from botocore.exceptions import ClientError
from deployment_guards import exact_key_absent
from maintenance_contract import (
    addition,
    backend,
    encoded,
    hashed,
    identity,
    require,
    state_instances,
)

CONFIG = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=15)


class BootstrapAWS:
    def __init__(self, session, account, region):
        self.session, self.account, self.region = session, account, region
        self.backend = backend(account, region)
        self.operations = []

        def readonly(model, **kwargs):
            require(
                model.name.startswith(("Get", "Head", "List", "Describe", "Simulate")),
                "MaintenanceSdkWriteForbidden",
            )
            self.operations.append(model.name)

        session.events.register("before-call.*.*", readonly)
        self.s3 = session.client("s3", region_name=region, config=CONFIG)
        self.iam = session.client("iam", config=CONFIG)

    def diagnose(self):
        """Observe heads after uncertainty; never remove a remaining lock."""
        args = {
            "Bucket": self.backend["bucket"],
            "Key": self.backend["key"],
            "ExpectedBucketOwner": self.account,
        }
        result = {"repair_attempted": False}
        for name, request in (("state", args), ("lock", args | {"Key": args["Key"] + ".tflock"})):
            try:
                head = self.s3.head_object(**request)
                result[name] = {
                    "present": True,
                    "version_id": head.get("VersionId"),
                    "size": head.get("ContentLength"),
                }
            except ClientError as error:
                code = error.response["Error"]["Code"]
                result[name] = {
                    "error_code": code,
                    "absence_proven": code in {"404", "NoSuchKey", "NotFound"},
                }
        return result

    def absent_lock(self):
        args = {
            "Bucket": self.backend["bucket"],
            "Key": self.backend["key"] + ".tflock",
            "ExpectedBucketOwner": self.account,
        }
        try:
            self.s3.head_object(**args)
        except ClientError as error:
            code = error.response["Error"]["Code"]
            if code in {"403", "AccessDenied", "Forbidden"}:
                require(exact_key_absent(self.s3, args), "MaintenanceActiveLock")
            else:
                require(code in {"404", "NoSuchKey", "NotFound"}, "MaintenanceLockUnavailable")
        else:
            require(False, "MaintenanceActiveLock")

    def inventory(self):
        args = {
            "Bucket": self.backend["bucket"],
            "Prefix": self.backend["key"],
            "ExpectedBucketOwner": self.account,
            "MaxKeys": 1000,
        }
        records, seen = [], set()
        while True:
            page = self.s3.list_object_versions(**args)
            require(type(page.get("IsTruncated")) is bool, "MaintenanceVersionInventory")
            for kind in ("Versions", "DeleteMarkers"):
                require(isinstance(page.get(kind, []), list), "MaintenanceVersionInventory")
                for item in page.get(kind, []):
                    require(
                        isinstance(item.get("Key"), str)
                        and item["Key"].startswith(self.backend["key"]),
                        "MaintenanceVersionInventory",
                    )
                    if item["Key"] == self.backend["key"]:
                        require(
                            isinstance(item.get("VersionId"), str)
                            and item["VersionId"] not in {"", "null"},
                            "MaintenanceVersionInventory",
                        )
                        records.append(
                            {
                                "kind": kind,
                                "version_id": item["VersionId"],
                                "size": item.get("Size"),
                            }
                        )
            if page["IsTruncated"] is False:
                break
            token = (page.get("NextKeyMarker"), page.get("NextVersionIdMarker"))
            require(
                all(isinstance(x, str) and x for x in token) and token not in seen,
                "MaintenanceVersionInventory",
            )
            seen.add(token)
            args.update(KeyMarker=token[0], VersionIdMarker=token[1])
        require(
            records and len({(x["kind"], x["version_id"]) for x in records}) == len(records),
            "MaintenanceVersionInventory",
        )
        return sorted(records, key=lambda x: (x["kind"], x["version_id"]))

    def snapshot(self):
        self.absent_lock()
        bucket = {"Bucket": self.backend["bucket"], "ExpectedBucketOwner": self.account}
        self.s3.head_bucket(**bucket)
        require(
            self.s3.get_bucket_location(**bucket).get("LocationConstraint") == self.region
            and self.s3.get_bucket_versioning(**bucket).get("Status") == "Enabled",
            "MaintenanceBucketOwnerRegionVersioning",
        )
        encryption = self.s3.get_bucket_encryption(**bucket)["ServerSideEncryptionConfiguration"]
        require(
            len(encryption["Rules"]) == 1
            and encryption["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
            == "AES256",
            "MaintenanceBucketEncryption",
        )
        args = bucket | {"Key": self.backend["key"]}
        head = self.s3.head_object(**args)
        version = head.get("VersionId")
        require(
            isinstance(version, str) and version not in {"", "null"},
            "MaintenanceVersionedStateRequired",
        )
        response = self.s3.get_object(**args, VersionId=version)
        with response["Body"] as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
        require(
            len(raw) <= 32 * 1024 * 1024
            and response.get("ContentLength") == len(raw)
            and head.get("ContentLength") == len(raw)
            and response.get("VersionId") == version
            and response.get("ServerSideEncryption")
            == head.get("ServerSideEncryption")
            == "AES256",
            "MaintenanceStateReadback",
        )
        inventory = self.inventory()
        require(
            self.s3.head_object(**args).get("VersionId") == version,
            "MaintenanceStateReadbackChanged",
        )
        self.absent_lock()
        state = json.loads(raw)
        state_instances(state)
        return {
            "identity": identity(raw, version),
            "state": state,
            "backend": self.backend,
            "versions": inventory,
            "versions_sha256": hashed(encoded(inventory)),
        }

    def actor(self, expected_arn):
        actual = self.session.client("sts", config=CONFIG).get_caller_identity()
        require(actual["Account"] == self.account, "MaintenanceActorAccount")
        if ":assumed-role/" in actual["Arn"]:
            role_name = actual["Arn"].split("/")[-2]
            role = self.iam.get_role(RoleName=role_name)["Role"]["Arn"]
        else:
            role = actual["Arn"]
        require(role == expected_arn, "MaintenanceActorMismatch")
        arn = f"arn:aws:s3:::{self.backend['bucket']}"
        requests = [
            ("s3:GetObject", arn + "/" + self.backend["key"]),
            ("s3:GetObjectVersion", arn + "/" + self.backend["key"]),
            ("s3:ListBucket", arn),
            ("s3:ListBucketVersions", arn),
            *[
                (action, arn + "/" + self.backend["key"] + ".tflock")
                for action in ("s3:GetObject", "s3:PutObject", "s3:DeleteObject")
            ],
        ]
        for action, resource in requests:
            simulation = self.iam.simulate_principal_policy(
                PolicySourceArn=role,
                ActionNames=[action],
                ResourceArns=[resource],
                ContextEntries=[
                    {
                        "ContextKeyName": "s3:prefix",
                        "ContextKeyValues": [self.backend["key"]],
                        "ContextKeyType": "string",
                    },
                    {
                        "ContextKeyName": "aws:SecureTransport",
                        "ContextKeyValues": ["true"],
                        "ContextKeyType": "boolean",
                    },
                ],
            )
            require(
                [v["EvalDecision"] for v in simulation["EvaluationResults"]] == ["allowed"],
                "MaintenanceActorPermissions",
            )
        return {
            "role_arn": role,
            "identity_arn": actual["Arn"],
            "permissions_checked": len(requests),
        }

    def verify_resources(self, state, values):
        resources = state_instances(state)
        outputs = {k: v["value"] for k, v in state["outputs"].items()}
        verify_created_resources(self.session, outputs, self.account, self.region, values)
        for address, attrs in resources.items():
            kind = address.split(".")[0]
            if kind == "aws_iam_role_policy":
                doc = self.iam.get_role_policy(RoleName=attrs["role"], PolicyName=attrs["name"])
                require(
                    canonical_policy(doc["PolicyDocument"]) == canonical_policy(attrs["policy"]),
                    "MaintenanceLiveIamDrift",
                )
            elif kind == "aws_iam_role":
                role = self.iam.get_role(RoleName=attrs["name"])["Role"]
                require(
                    role["Arn"] == attrs["arn"]
                    and role["RoleId"] == attrs["unique_id"]
                    and role["MaxSessionDuration"] == attrs["max_session_duration"]
                    and role.get("PermissionsBoundary") is None
                    and canonical_policy(role["AssumeRolePolicyDocument"])
                    == canonical_policy(attrs["assume_role_policy"])
                    and {t["Key"]: t["Value"] for t in role.get("Tags", [])} == attrs["tags_all"],
                    "MaintenanceLiveRoleDrift",
                )
                observed = set()
                for page in self.iam.get_paginator("list_role_policies").paginate(
                    RoleName=attrs["name"]
                ):
                    observed.update(page["PolicyNames"])
                expected = {
                    a["name"]
                    for key, a in resources.items()
                    if key.startswith("aws_iam_role_policy.") and a["role"] == attrs["name"]
                }
                require(observed == expected, "MaintenanceUnexpectedInlinePolicy")
                for page in self.iam.get_paginator("list_attached_role_policies").paginate(
                    RoleName=attrs["name"]
                ):
                    require(not page["AttachedPolicies"], "MaintenanceUnexpectedAttachedPolicy")
            elif kind == "aws_iam_policy":
                policy = self.iam.get_policy(PolicyArn=attrs["arn"])["Policy"]
                doc = self.iam.get_policy_version(
                    PolicyArn=attrs["arn"], VersionId=policy["DefaultVersionId"]
                )
                tags = self.iam.list_policy_tags(PolicyArn=attrs["arn"])["Tags"]
                require(
                    canonical_policy(doc["PolicyVersion"]["Document"])
                    == canonical_policy(attrs["policy"])
                    and {t["Key"]: t["Value"] for t in tags} == attrs["tags_all"],
                    "MaintenanceLiveBoundaryDrift",
                )
            elif kind == "aws_iam_openid_connect_provider":
                provider = self.iam.get_open_id_connect_provider(
                    OpenIDConnectProviderArn=attrs["arn"]
                )
                require(
                    provider["Url"] == attrs["url"].removeprefix("https://")
                    and sorted(provider["ClientIDList"]) == sorted(attrs["client_id_list"])
                    and {t["Key"]: t["Value"] for t in provider.get("Tags", [])}
                    == attrs["tags_all"],
                    "MaintenanceLiveOidcDrift",
                )
            elif kind.startswith("aws_s3_bucket"):
                self.verify_bucket(kind, attrs)
            else:
                require(kind == "aws_ses_email_identity", "MaintenanceUnsupportedResource")
        return {"verified_instances": len(resources)}

    def verify_bucket(self, kind, attrs):
        args = {"Bucket": attrs.get("bucket", attrs["id"]), "ExpectedBucketOwner": self.account}
        if kind == "aws_s3_bucket":
            self.s3.head_bucket(**args)
            tags = self.s3.get_bucket_tagging(**args)["TagSet"]
            require(
                self.s3.get_bucket_location(**args)["LocationConstraint"] == attrs["region"]
                and {t["Key"]: t["Value"] for t in tags} == attrs["tags_all"],
                "MaintenanceLiveBucketDrift",
            )
        elif kind == "aws_s3_bucket_policy":
            doc = json.loads(self.s3.get_bucket_policy(**args)["Policy"])
            require(
                canonical_policy(doc) == canonical_policy(attrs["policy"]),
                "MaintenanceLiveBucketPolicyDrift",
            )
        elif kind == "aws_s3_bucket_versioning":
            require(
                self.s3.get_bucket_versioning(**args)["Status"]
                == attrs["versioning_configuration"][0]["status"],
                "MaintenanceLiveBucketDrift",
            )
        elif kind == "aws_s3_bucket_server_side_encryption_configuration":
            rules = self.s3.get_bucket_encryption(**args)["ServerSideEncryptionConfiguration"][
                "Rules"
            ]
            require(
                len(rules) == 1
                and rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
                == attrs["rule"][0]["apply_server_side_encryption_by_default"][0]["sse_algorithm"],
                "MaintenanceLiveBucketDrift",
            )
        else:
            require(kind == "aws_s3_bucket_public_access_block", "MaintenanceUnsupportedResource")
            actual = self.s3.get_public_access_block(**args)["PublicAccessBlockConfiguration"]
            require(
                all(
                    actual[key] == attrs[name]
                    for key, name in (
                        ("BlockPublicAcls", "block_public_acls"),
                        ("IgnorePublicAcls", "ignore_public_acls"),
                        ("BlockPublicPolicy", "block_public_policy"),
                        ("RestrictPublicBuckets", "restrict_public_buckets"),
                    )
                ),
                "MaintenanceLiveBucketDrift",
            )

    def simulate_addition(self):
        statement = addition(self.account, self.region)
        for name in ("plan", "deploy"):
            role = self.iam.get_role(RoleName="ai-interview-ci-" + name)["Role"]["Arn"]
            result = self.iam.simulate_principal_policy(
                PolicySourceArn=role,
                ActionNames=statement["Action"],
                ResourceArns=statement["Resource"],
                PolicyInputList=[json.dumps({"Version": "2012-10-17", "Statement": [statement]})],
            )
            require(
                [x["EvalDecision"] for x in result["EvaluationResults"]] == ["allowed"],
                "MaintenanceProposalSimulation",
            )
        return {"plan": "allowed", "deploy": "allowed", "actual_iam_change": False}
