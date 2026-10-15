"""Pure full-plan audit shared with the separate audit process."""

import hashlib
import json
import os

ACCOUNT = "835384817629"
REGION = "ap-northeast-1"
MAIN = os.environ.get("GITHUB_SHA", "")
ARTIFACT = "cc067d535699792204e4ec038b45a19b0d018536355a49b4e0f8ce4377a8ef6d"
FLAGS = ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
LIMITS = {"plan": 3, "artifact": 2}
BUDGETS = {"oidc": 20, "sts": 25, "put": 60, "build": 600, "init": 300, "plan": 1200}


class Refusal(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def check_snapshot(s, approval):
    require(
        s["closed"] is True
        and s["active_lock"] is False
        and s["managed_manifest_live_verified"] is True,
        "StateClosedLockOrLiveMismatch",
    )
    require(
        s["dev"]["identity"] == approval.x["dev_state_identity"], "PinnedDevStateIdentityMismatch"
    )
    require(
        len(s["dev"]["versions"]) == 1
        and s["dev"]["versions"][0]["version_id"] == approval.x["dev_state_identity"]["version_id"],
        "PinnedCurrentVersionProofMissing",
    )
    require(
        s["bootstrap_state_and_live"].startswith("UNCONFIRMED")
        and s["outside_dev_resource_inventory"].startswith("UNCONFIRMED"),
        "BroaderQualificationMustNotBeClaimed",
    )


def audit_plan(plan, binding, envelope, binary, approval, run_id, state_before):
    check_snapshot(state_before, approval)
    require(
        digest(binary) == envelope["plan_sha256"] == binding["plan_sha256"], "SavedPlanHashMismatch"
    )
    require(
        envelope["operation"] == "plan"
        and envelope["code_sha"] == binding["code_sha"] == MAIN
        and envelope["run_id"] == str(run_id)
        and envelope["run_attempt"] == "1",
        "PlanRunBindingMismatch",
    )
    require(
        binding["account_id"] == ACCOUNT
        and binding["region"] == REGION
        and binding["state_key"] == "dev/terraform.tfstate"
        and binding["state_bucket"] == f"ai-interview-state-{ACCOUNT}-{REGION}"
        and binding["terraform_version"] == "1.14.9",
        "BackendOrRuntimeMismatch",
    )
    require(
        binding["lock_sha256"] == approval.x["dev_provider_lock_sha256"]
        and binding["state_identity"] == state_before["dev"]["identity"],
        "PlanStateOrProviderBindingMismatch",
    )
    package = envelope["package"]
    require(
        package["artifact_bucket"] == f"ai-interview-artifacts-{ACCOUNT}-{REGION}"
        and package["artifact_key"] == f"lambda/{MAIN}/{run_id}/1/app.zip"
        and package["artifact_version"] not in {"", "null", None},
        "PlanArtifactBindingMismatch",
    )
    import base64

    require(
        package["artifact_sha256_base64"] == base64.b64encode(bytes.fromhex(ARTIFACT)).decode(),
        "PlanArtifactDigestMismatch",
    )
    inputs = approval.x["configuration"] | package
    expected_input = json.dumps(inputs, sort_keys=True).encode()
    require(binding["inputs_sha256"] == digest(expected_input), "SavedInputsHashMismatch")
    require(not plan.get("errored") and not plan.get("deferred_changes"), "ErroredOrDeferredPlan")
    require(not plan.get("resource_drift"), "UnexpectedPlanDrift")
    require(plan.get("terraform_version") == "1.14.9", "SavedPlanTerraformVersionMismatch")
    require(
        all(plan["variables"][k]["value"] is False for k in FLAGS), "PlannedEnablementForbidden"
    )
    from decimal import Decimal

    from cloud_configuration_contract import normalize_configuration

    normalized_inputs = normalize_configuration(
        approval.x["configuration"], package, approval.x["configuration_contract"]
    )
    for key, value in normalized_inputs.items():
        require(key in plan["variables"], "ActualPlanVariableBindingMismatch")
        actual = plan["variables"][key]["value"]
        if key == "monthly_budget_usd":
            require(
                type(actual) in {int, float} and Decimal(str(actual)) == Decimal(value),
                "ActualMonthlyBudgetMismatch",
            )
        else:
            require(
                actual == value and (type(actual) is bool if type(value) is bool else True),
                "ActualPlanVariableBindingMismatch",
            )
    require(
        plan["variables"]["account_id"]["value"] == ACCOUNT
        and plan["variables"]["region"]["value"] == REGION,
        "ActualPlanAccountRegionMismatch",
    )

    def addresses(state):
        found = set()
        for resource in state.get("resources", []):
            if resource.get("mode") != "managed":
                continue
            for instance in resource["instances"]:
                address = (
                    (resource.get("module", "") + "." if resource.get("module") else "")
                    + resource["type"]
                    + "."
                    + resource["name"]
                )
                if "index_key" in instance:
                    address += "[" + json.dumps(instance["index_key"]) + "]"
                require(address not in found, "DuplicateStateAddress")
                found.add(address)
        return found

    expected_addresses = addresses(state_before["dev"]["state"])
    actual_addresses = {
        r["address"]
        for r in plan["resource_changes"]
        if r.get("mode") == "managed" and r["change"]["before"] is not None
    }
    require(actual_addresses == expected_addresses, "FullBaselineResourceReviewRequired")
    from cloud_plan_semantics import walk_values

    prior = {
        r["address"]
        for r in walk_values(plan["prior_state"].get("values", {}).get("root_module", {}))
        if r.get("mode") == "managed"
    }
    require(prior == expected_addresses, "SavedPriorStateResourceInventoryMismatch")
    from cloud_plan_semantics import audit_semantics

    report = audit_semantics(
        plan,
        package,
        retention_policy=approval.x["retention_exception"],
        state_before=state_before["dev"]["state"],
    )
    report["plan_sha256"] = digest(binary)
    return report
