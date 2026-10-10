"""Pure contracts for the one canonical bootstrap IAM correction; no AWS calls."""

import hashlib
import json
import re
from datetime import UTC, datetime

from bootstrap_contract import canonical_policy

from interview_backend.deployment import DeploymentError

KEY = "bootstrap/terraform.tfstate"
REGION = "ap-northeast-1"
TF_VERSION = "1.14.9"
UPDATES = frozenset({'aws_iam_role_policy.state["plan"]', 'aws_iam_role_policy.state["deploy"]'})
INPUT_KEYS = frozenset(
    {
        "account_id",
        "region",
        "oidc_provider_arn",
        "oidc_subjects",
        "ses_identity_type",
        "ses_from_email",
        "ses_domain",
        "worker_wif_enabled",
    }
)


def require(condition, code):
    if not condition:
        raise DeploymentError(code)


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def backend(account, region):
    require(
        bool(re.fullmatch(r"[0-9]{12}", account)) and region == REGION, "MaintenanceAccountRegion"
    )
    return {
        "bucket": f"ai-interview-state-{account}-{region}",
        "key": KEY,
        "region": region,
        "encrypt": True,
        "use_lockfile": True,
        "allowed_account_ids": [account],
    }


def identity(raw, version):
    state = json.loads(raw)
    require(
        state.get("version") == 4
        and state.get("terraform_version") == TF_VERSION
        and isinstance(state.get("lineage"), str)
        and bool(state["lineage"])
        and type(state.get("serial")) is int
        and state["serial"] >= 0
        and isinstance(version, str)
        and version not in {"", "null"},
        "MaintenanceStateIdentity",
    )
    return {
        "lineage": state["lineage"],
        "serial": state["serial"],
        "version_id": version,
        "sha256": hashed(raw),
    }


def state_instances(state):
    result = {}
    require(isinstance(state.get("resources"), list), "MaintenanceStateResources")
    for resource in state["resources"]:
        require(
            resource.get("mode") == "managed"
            and not resource.get("module")
            and resource.get("type", "").startswith("aws_"),
            "MaintenanceStateNamespace",
        )
        for item in resource["instances"]:
            require(not item.get("deposed"), "MaintenanceDeposedResource")
            address = resource["type"] + "." + resource["name"]
            if "index_key" in item:
                address += "[" + json.dumps(item["index_key"], separators=(",", ":")) + "]"
            require(
                address not in result and isinstance(item["attributes"], dict),
                "MaintenanceDuplicateResource",
            )
            result[address] = item["attributes"]
    require(len(result) == 32 and UPDATES <= result.keys(), "MaintenanceStateResources")
    return result


def check_snapshot(snapshot, approval):
    require(snapshot["identity"] == approval["state_identity"], "MaintenanceStateChanged")
    resources = state_instances(snapshot["state"])
    require(sorted(resources) == approval["addresses"], "MaintenanceStateAddresses")
    require(snapshot["backend"] == approval["backend"], "MaintenanceBackendMismatch")
    return resources


def validate_inputs(values, state, account, region):
    require(
        set(values) == INPUT_KEYS
        and values["account_id"] == account
        and values["region"] == region,
        "MaintenanceInputs",
    )
    resources = state_instances(state)
    require(
        values["worker_wif_enabled"] is False
        and values["oidc_provider_arn"] == ""
        and values["ses_identity_type"] == "email"
        and values["ses_domain"] == "",
        "MaintenanceInputsWouldChangeBaseline",
    )
    require(
        "aws_iam_openid_connect_provider.github[0]" in resources, "MaintenanceOwnedProviderRequired"
    )
    require(
        resources["aws_ses_email_identity.sender[0]"]["email"] == values["ses_from_email"],
        "MaintenanceSesInputMismatch",
    )
    require(
        set(values["oidc_subjects"]) == {"plan", "deploy", "test", "artifact"},
        "MaintenanceSubjects",
    )
    for role, subject in values["oidc_subjects"].items():
        trust = json.loads(resources[f'aws_iam_role.ci["{role}"]']["assume_role_policy"])
        require(
            trust["Statement"][0]["Condition"]["StringEquals"][
                "token.actions.githubusercontent.com:sub"
            ]
            == subject,
            "MaintenanceTrustInputMismatch",
        )


def validate_approval(value, operation, account, region, now=None):
    fields = {
        "schema_version",
        "kind",
        "approved",
        "expires_at",
        "account_id",
        "region",
        "source_sha",
        "backend",
        "workspace",
        "state_identity",
        "addresses",
        "inputs_path",
        "inputs_sha256",
        "provider_lock_sha256",
        "adoption_path",
        "adoption_sha256",
        "receipt_path",
        "receipt_sha256",
        "principal_role_arn",
        "normal_lockfile_writes_approved",
        "canonical_state_writes_approved",
        "iam_policy_updates_approved",
        "cost_cap_usd",
    }
    if operation == "apply":
        fields |= {"run_path", "plan_sha256", "binding_sha256", "plan_approval_sha256"}
    require(
        set(value) == fields
        and value["schema_version"] == 1
        and value["kind"] == f"p4-bootstrap-maintenance-{operation}"
        and type(value["approved"]) is bool,
        "MaintenanceApprovalSchema",
    )
    require(
        value["cost_cap_usd"] == "0.05"
        and all(
            type(value[k]) is bool
            for k in (
                "normal_lockfile_writes_approved",
                "canonical_state_writes_approved",
                "iam_policy_updates_approved",
            )
        ),
        "MaintenanceApprovalWriteScope",
    )
    if value["approved"]:
        require(
            value["normal_lockfile_writes_approved"] is True
            and value["canonical_state_writes_approved"] is (operation == "apply")
            and value["iam_policy_updates_approved"] is (operation == "apply"),
            "MaintenanceApprovalWriteScope",
        )
    require(
        value["account_id"] == account
        and value["region"] == region
        and value["backend"] == backend(account, region)
        and value["workspace"] == "default",
        "MaintenanceApprovalNamespace",
    )
    require(bool(re.fullmatch(r"[0-9a-f]{40}", value["source_sha"])), "MaintenanceSourceSha")
    state = value["state_identity"]
    require(
        set(state) == {"lineage", "serial", "version_id", "sha256"}
        and type(state["serial"]) is int
        and state["serial"] == 1
        and isinstance(state["lineage"], str)
        and bool(state["lineage"])
        and isinstance(state["version_id"], str)
        and state["version_id"] not in {"", "null"},
        "MaintenanceApprovalStateIdentity",
    )
    digests = [
        state["sha256"],
        value["inputs_sha256"],
        value["provider_lock_sha256"],
        value["adoption_sha256"],
        value["receipt_sha256"],
    ]
    if operation == "apply":
        digests += [value["plan_sha256"], value["binding_sha256"], value["plan_approval_sha256"]]
    require(
        all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) for x in digests),
        "MaintenanceApprovalDigest",
    )
    require(
        isinstance(value["addresses"], list)
        and len(value["addresses"]) == 32
        and value["addresses"] == sorted(set(value["addresses"])),
        "MaintenanceApprovalAddresses",
    )
    require(
        isinstance(value["principal_role_arn"], str)
        and value["principal_role_arn"].startswith(f"arn:aws:iam::{account}:role/"),
        "MaintenancePrincipal",
    )
    expiry = datetime.fromisoformat(value["expires_at"])
    now = datetime.now(UTC) if now is None else now
    require(
        expiry.tzinfo is not None and 0 < (expiry - now).total_seconds() <= 86400,
        "MaintenanceApprovalExpired",
    )


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    # Unknown masks contain only booleans and nested containers. Fail closed
    # for malformed scalars (including 0/null), rather than treating them as false.
    return value is not False


def addition(account, region):
    return {
        "Sid": "DevVersionedStateRead",
        "Effect": "Allow",
        "Action": ["s3:GetObjectVersion"],
        "Resource": [f"arn:aws:s3:::ai-interview-state-{account}-{region}/dev/terraform.tfstate"],
    }


def policy_after(before, account, region):
    document = json.loads(before)
    require(
        isinstance(document["Statement"], list)
        and not any(x.get("Sid") == "DevVersionedStateRead" for x in document["Statement"]),
        "MaintenanceAlreadyPatched",
    )
    document["Statement"].append(addition(account, region))
    return document


def plan_values(module):
    require(not module.get("child_modules"), "MaintenanceModuleAddressChange")
    rows = module.get("resources", [])
    require(len({r["address"] for r in rows}) == len(rows), "MaintenancePlanDuplicate")
    return {r["address"]: r["values"] for r in rows if r["mode"] == "managed"}


def same_attributes(a, b):
    a, b = dict(a), dict(b)
    for field in ("policy", "assume_role_policy"):
        if field in a and field in b:
            a[field], b[field] = canonical_policy(a[field]), canonical_policy(b[field])
    return encoded(a) == encoded(b)


def audit_variables(actual, expected):
    """Only the disabled WIF flag may use Terraform's literal env representation."""
    require(set(actual) == set(expected) == INPUT_KEYS, "MaintenancePlanInputs")
    require(expected["worker_wif_enabled"] is False, "MaintenancePlanInputs")
    values = {k: v["value"] for k, v in actual.items()}
    flag = values["worker_wif_enabled"]
    require(flag is False or type(flag) is str and flag == "false", "MaintenancePlanInputs")
    values["worker_wif_enabled"] = False
    require(encoded(values) == encoded(expected), "MaintenancePlanInputs")


def audit_outputs(review, state, values):
    """Preserve every output; permit only an omitted, known null SES-domain output."""
    expected = {k: v["value"] for k, v in state["outputs"].items()}
    prior = {k: v["value"] for k, v in review["prior_state"]["values"]["outputs"].items()}
    require(encoded(prior) == encoded(expected), "MaintenanceOutputsChanged")
    planned = {k: v["value"] for k, v in review["planned_values"]["outputs"].items()}
    nullable = "ses_domain_verification"
    if nullable not in expected and nullable in planned:
        require(
            values["ses_identity_type"] == "email"
            and values["ses_domain"] == ""
            and planned[nullable] is None,
            "MaintenanceOutputsChanged",
        )
        expected[nullable] = None
    require(encoded(planned) == encoded(expected), "MaintenanceOutputsChanged")
    changes = review["output_changes"]
    require(set(changes) == set(expected), "MaintenanceOutputsChanged")
    for name, change in changes.items():
        require(
            {"actions", "before", "after", "after_unknown"} <= change.keys()
            and change["actions"] == ["no-op"]
            and encoded(change["before"]) == encoded(expected[name])
            and encoded(change["after"]) == encoded(expected[name])
            and change["after_unknown"] is False,
            "MaintenanceOutputsChanged",
        )


def audit_plan(review, state, values, account, region):
    before = state_instances(state)
    require(
        review.get("errored") is not True
        and review.get("applyable") is True
        and review.get("complete") is True
        and not review.get("resource_drift")
        and not review.get("deferred_changes"),
        "MaintenanceIncompleteOrDriftedPlan",
    )
    changes = review.get("resource_changes", [])
    require(
        len(changes) == len(before) and {r["address"] for r in changes} == before.keys(),
        "MaintenancePlanAddresses",
    )
    require(review.get("terraform_version") == TF_VERSION, "MaintenancePlanTerraformVersion")
    audit_variables(review["variables"], values)
    prior = plan_values(review["prior_state"]["values"]["root_module"])
    planned = plan_values(review["planned_values"]["root_module"])
    require(prior.keys() == before.keys() == planned.keys(), "MaintenancePlanValuesAddresses")
    for row in changes:
        address, change = row["address"], row["change"]
        require(
            row.get("mode") == "managed"
            and not row.get("previous_address")
            and not change.get("importing")
            and not change.get("replace_paths")
            and not unknown(change.get("after_unknown", {})),
            "MaintenanceUnapprovedChange",
        )
        require(
            same_attributes(change["before"], before[address])
            and same_attributes(prior[address], before[address]),
            "MaintenancePlanBeforeMismatch",
        )
        expected = dict(before[address])
        if address in UPDATES:
            require(change["actions"] == ["update"], "MaintenanceExpectedTwoUpdates")
            expected["policy"] = json.dumps(policy_after(expected["policy"], account, region))
        else:
            require(change["actions"] == ["no-op"], "MaintenanceUnapprovedChange")
        require(
            same_attributes(change["after"], expected)
            and same_attributes(planned[address], expected),
            "MaintenanceUnexpectedIamOrResource",
        )
    audit_outputs(review, state, values)
    require(
        all(x.get("status") == "pass" for x in review.get("checks", [])), "MaintenanceChecksFailed"
    )
    return {"create": 0, "update": 2, "replace": 0, "destroy": 0, "no_op": 30}


def check_applied(before, after, account, region):
    require(
        after["lineage"] == before["lineage"]
        and after["serial"] > before["serial"]
        and after["outputs"] == before["outputs"],
        "MaintenanceApplyStateIdentity",
    )
    old, new = state_instances(before), state_instances(after)
    require(old.keys() == new.keys(), "MaintenanceApplyAddresses")
    for address, attrs in old.items():
        expected = dict(attrs)
        if address in UPDATES:
            expected["policy"] = json.dumps(policy_after(attrs["policy"], account, region))
        require(same_attributes(new[address], expected), "MaintenanceApplyUnexpectedChange")
