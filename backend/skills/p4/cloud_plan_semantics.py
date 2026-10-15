"""Complete row classification; only reviewed closed Lambda-code updates pass."""

from cloud_controller_core import require


def walk_values(root):
    yield from root.get("resources", [])
    for child in root.get("child_modules", []):
        yield from walk_values(child)


def audit_semantics(plan, package, *, retention_policy=None, state_before=None):
    rows = []
    violations = []
    risks = []
    retention_approved = set()
    if retention_policy is not None:
        from cloud_retention_exception import changes

        retention_risks = changes(plan, retention_policy, state_before)
        retention_approved = {r["address"] for r in retention_risks}
        risks.extend(retention_risks)
    categories = {
        ("create",): "create",
        ("update",): "update",
        ("delete",): "destroy",
        ("delete", "create"): "replace",
        ("create", "delete"): "replace",
        ("read",): "read",
        ("no-op",): "no_op",
    }
    counts = {k: 0 for k in ("create", "update", "replace", "destroy", "read", "no_op")}
    seen = set()
    planned = {r["address"]: r for r in walk_values(plan["planned_values"].get("root_module", {}))}
    computed = {
        "version",
        "qualified_arn",
        "qualified_invoke_arn",
        "last_modified",
        "code_sha256",
        "source_code_size",
        "signing_job_arn",
        "signing_profile_version_arn",
    }
    code_fields = computed | {"s3_bucket", "s3_key", "s3_object_version", "source_code_hash"}
    for entry in plan.get("resource_changes", []):
        address = entry["address"]
        require(address not in seen, "DuplicatePlanAddress")
        seen.add(address)
        change = entry["change"]
        actions = tuple(change["actions"])
        require(actions in categories, "UnsupportedPlanAction")
        category = categories[actions]
        counts[category] += 1
        before = change.get("before") or {}
        after = change.get("after") or {}
        unknown = change.get("after_unknown", {})
        row = {
            "address": address,
            "type": entry["type"],
            "category": category,
            "replace_paths": change.get("replace_paths", []),
            "after_unknown": unknown,
        }
        rows.append(row)
        if entry.get("previous_address") or change.get("importing") or entry.get("deposed"):
            violations.append({"address": address, "reason": "move/import/deposed"})
        if entry.get("mode") == "data":
            if category not in {"no_op", "read"}:
                violations.append({"address": address, "reason": "unexpected-data-action"})
            continue
        require(address in planned or category in {"destroy"}, "PlannedResourceMissing")
        if category == "no_op":
            require(before == after, "NoOpValuesChanged")
        elif address in retention_approved:
            # Full before/after/prior/planned values were independently bound
            # above, including all immutable name/ARN/tags/KMS/class attributes.
            require(
                category == "update" and entry["type"] == "aws_cloudwatch_log_group",
                "RetentionUpdateOnly",
            )
        elif category == "update" and entry["type"] == "aws_lambda_function":
            delta = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            extra_unknown = {k for k, v in unknown.items() if v and k not in computed}
            if not delta <= code_fields or extra_unknown:
                violations.append(
                    {
                        "address": address,
                        "reason": "lambda-non-code-change",
                        "fields": sorted(delta - code_fields | extra_unknown),
                    }
                )
            if after.get("runtime") != "python3.14" or after.get("architectures") != ["x86_64"]:
                violations.append({"address": address, "reason": "runtime/architecture"})
            expected = {
                "s3_bucket": package["artifact_bucket"],
                "s3_key": package["artifact_key"],
                "s3_object_version": package["artifact_version"],
                "source_code_hash": package["artifact_sha256_base64"],
            }
            if any(after.get(k) != v for k, v in expected.items()):
                violations.append({"address": address, "reason": "artifact-binding"})
            risks.append(
                {
                    "address": address,
                    "category": category,
                    "review": "CODE_VERSION_UPDATE_REQUIRES_SEPARATE_APPLY_APPROVAL",
                }
            )
        elif category == "update" and entry["type"] == "aws_lambda_alias":
            delta = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            if not delta <= {"function_version"} or any(
                v for k, v in unknown.items() if k != "function_version"
            ):
                violations.append({"address": address, "reason": "alias-non-version-change"})
            risks.append(
                {
                    "address": address,
                    "category": category,
                    "review": "ALIAS_VERSION_UPDATE_REQUIRES_SEPARATE_APPLY_APPROVAL",
                }
            )
        else:
            violations.append(
                {
                    "address": address,
                    "reason": "outside-reviewed-code-update-whitelist",
                    "category": category,
                }
            )
            risks.append(
                {
                    "address": address,
                    "category": category,
                    "review": "UNEXPECTED_CHANGE_NO_APPLY_AUTHORIZATION",
                }
            )
        t = entry["type"]
        if t == "aws_lambda_function":
            expected = {
                "s3_bucket": package["artifact_bucket"],
                "s3_key": package["artifact_key"],
                "s3_object_version": package["artifact_version"],
                "source_code_hash": package["artifact_sha256_base64"],
            }
            if (
                after.get("runtime") != "python3.14"
                or after.get("architectures") != ["x86_64"]
                or any(after.get(k) != v for k, v in expected.items())
            ):
                violations.append(
                    {"address": address, "reason": "planned-lambda-runtime-or-artifact"}
                )
        if t == "aws_apigatewayv2_api" and after.get("disable_execute_api_endpoint") is not True:
            violations.append({"address": address, "reason": "api-not-closed"})
        if t == "aws_lambda_event_source_mapping":
            if after.get("enabled") is not False:
                violations.append({"address": address, "reason": "mapping-enabled"})
            if address.endswith(".worker") and after.get("scaling_config") != [
                {"maximum_concurrency": 2}
            ]:
                violations.append({"address": address, "reason": "worker-concurrency"})
        if t == "aws_scheduler_schedule" and after.get("state") != "DISABLED":
            violations.append({"address": address, "reason": "scheduler-enabled"})
        if t == "aws_cloudwatch_metric_alarm" and category != "destroy":
            violations.append({"address": address, "reason": "validation-alarm-present"})
        if (
            t == "aws_cloudwatch_log_group"
            and address not in retention_approved
            and before.get("retention_in_days") != after.get("retention_in_days")
        ):
            violations.append({"address": address, "reason": "log-retention-change"})
    require(set(planned) <= seen, "PlannedResourceNotReviewed")
    return {
        "counts": counts,
        "entries": rows,
        "risks": risks,
        "violations": violations,
        "passed": not violations,
        "output_changes": plan["output_changes"],
        "apply_authorized": False,
    }
