"""Allowlisted Terraform plan summary; never copy before/after objects or IAM JSON."""

import math
import re

from interview_backend.deployment import DeploymentError

FIELDS = frozenset(
    {
        "timeout",
        "memory_size",
        "reserved_concurrent_executions",
        "enabled",
        "batch_size",
        "maximum_retry_attempts",
        "maximum_record_age_in_seconds",
        "visibility_timeout_seconds",
        "message_retention_seconds",
        "disable_execute_api_endpoint",
        "generate_secret",
        "access_token_validity",
        "id_token_validity",
        "refresh_token_validity",
    }
)
ACTIONS = frozenset({"no-op", "create", "read", "update", "delete", "forget"})


def summarize(plan):
    resources = []
    try:
        for item in plan.get("resource_changes", []):
            kind = item["type"]
            actions = item["change"]["actions"]
            if not re.fullmatch(r"aws_[a-z0-9_]{1,100}", kind):
                raise ValueError
            if not actions or any(action not in ACTIONS for action in actions):
                raise ValueError
            fields = {}
            before, after = item["change"].get("before") or {}, item["change"].get("after") or {}
            for key in sorted(FIELDS):
                sensitive = False
                for label in ("before_sensitive", "after_sensitive"):
                    marker = item["change"].get(label, {})
                    if marker is True or isinstance(marker, dict) and marker.get(key):
                        sensitive = True
                if sensitive:
                    continue
                old, new = before.get(key), after.get(key)
                if old == new:
                    continue
                if all(
                    value is None
                    or type(value) is bool
                    or (type(value) in {int, float} and math.isfinite(value))
                    for value in (old, new)
                ):
                    fields[key] = {"before": old, "after": new}
            resources.append({"resource_type": kind, "actions": actions, "settings": fields})
    except Exception:
        raise DeploymentError("UnsafePlanSummary") from None
    return {"resource_changes": resources, "scope": "allowlisted_numeric_settings_only"}
