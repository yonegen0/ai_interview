"""Offline candidate bootstrap preflight, NEVER an AWS/Plan/Apply authorization.

The opt-in 1.16.7 candidate must use a new execution namespace and fresh
bindings. This module intentionally has NO execution entrypoint, AWS SDK,
backend, Terraform subprocess or credential access. An independently reviewed
runner must later verify authentic source/approval/journal evidence before
performing any side effect.
"""

import hashlib
import json
import re

from offline_terraform import parse_lock

CLI = "1.16.7"
PROVIDER = "6.70.0"
PLATFORM = "linux_amd64"
NAMESPACE = "p4-bootstrap-candidate-1.16.7-aws-6.70.0-linux_amd64-v2"
AWS = "registry.terraform.io/hashicorp/aws"
ROOTS = {
    "bootstrap": "main.tf",
    "environments/dev": "main.tf",
    "environments/test": "main.tf",
    "environments/web": "main.tf",
    "modules/frontend": "main.tf",
    "modules/service": "versions.tf",
}
OPERATIONS = {"maintenance-plan", "maintenance-apply", "recovery-apply"}
PLAN_FIELDS = {
    "schema_version", "kind", "operation", "namespace", "source_sha",
    "terraform_version", "provider_version", "platform", "terraform_sha256",
    "lock_sha256", "state_identity", "plan_sha256", "plan_approval_sha256",
}
BASE_FIELDS = {
    "schema_version", "kind", "operation", "namespace", "source_sha",
    "terraform_version", "provider_version", "platform", "terraform_sha256",
    "configuration_sha256", "lock_sha256", "state_identity",
    "approval_sha256",
}
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def state_identity(value):
    require(
        type(value) is dict
        and set(value) == {"lineage", "serial", "version_id", "sha256"}
        and isinstance(value["lineage"], str)
        and bool(value["lineage"])
        and type(value["serial"]) is int
        and value["serial"] >= 0
        and isinstance(value["version_id"], str)
        and value["version_id"] not in {"", "null"}
        and digest(value["sha256"]),
        "CandidateStateIdentityInvalid",
    )


def configuration_digest(configurations):
    """Bind the twelve candidate requirements/locks; never inspect remote State."""
    names = {
        path
        for scope, filename in ROOTS.items()
        for path in (f"terraform/{scope}/{filename}", f"terraform/{scope}/.terraform.lock.hcl")
    }
    require(type(configurations) is dict and set(configurations) == names, "CandidateScopeMismatch")
    selections = []
    for scope, filename in ROOTS.items():
        prefix = f"terraform/{scope}/"
        hcl, lock = (configurations[prefix + filename],
                     configurations[prefix + ".terraform.lock.hcl"])
        require(type(hcl) is bytes and type(lock) is bytes, "CandidateFileBytesRequired")
        text = hcl.decode("utf-8")
        require(
            re.findall(r'required_version\s*=\s*"([^"]+)"', text) == [f"= {CLI}"]
            and re.findall(
                r'aws\s*=\s*\{\s*source\s*=\s*"hashicorp/aws"\s*,\s*version\s*=\s*"([^"]+)"\s*\}',
                text,
            ) == [f"= {PROVIDER}"],
            "CandidateHclVersionMismatch",
        )
        selection = parse_lock(lock.decode("utf-8"))
        require(set(selection) == {AWS}, "CandidateProviderSelection")
        provider = selection[AWS]
        require(
            provider["version"] == PROVIDER
            and provider["constraints"] == PROVIDER
            and len([x for x in provider["hashes"] if x.startswith("h1:")]) >= 2
            and any(x.startswith("zh:") for x in provider["hashes"]),
            "CandidateProviderLockMismatch",
        )
        selections.append(provider)
    require(all(x == selections[0] for x in selections), "CandidateLockDivergence")
    return (
        sha(canonical({name: sha(raw) for name, raw in sorted(configurations.items())})),
        sha(canonical({scope: sha(configurations[f"terraform/{scope}/.terraform.lock.hcl"])
                      for scope in sorted(ROOTS)})),
    )


def verify(bundle, version_json, configurations, *, binary, approval, journal, saved_plan=None):
    """Evaluate synthetic/local bytes only; SUCCESS means *offline preflight*, not permission.

    Callers MUST separately authenticate source, approval, immutable journal,
    Terraform binary and real State. This function cannot grant/retry an attempt.
    """
    require(type(bundle) is dict and set(bundle) == BASE_FIELDS, "CandidateManifestFields")
    require(
        type(bundle["schema_version"]) is int and bundle["schema_version"] == 2
        and bundle["kind"] == "p4-bootstrap-candidate-preflight"
        and bundle["operation"] in OPERATIONS
        and bundle["namespace"] == NAMESPACE
        and bundle["terraform_version"] == CLI
        and bundle["provider_version"] == PROVIDER
        and bundle["platform"] == PLATFORM
        and isinstance(bundle["source_sha"], str)
        and REVISION.fullmatch(bundle["source_sha"]) is not None,
        "CandidateExecutionNamespaceMismatch",
    )
    for key in ("terraform_sha256", "configuration_sha256", "lock_sha256", "approval_sha256"):
        require(digest(bundle[key]), "CandidateManifestDigest")
    state_identity(bundle["state_identity"])
    require(type(binary) is bytes and sha(binary) == bundle["terraform_sha256"],
            "CandidateBinaryHashMismatch")
    require(
        type(version_json) is dict
        and version_json.get("terraform_version") == CLI
        and version_json.get("platform") == PLATFORM
        and version_json.get("format_version", "1.0") == "1.0",
        "CandidateCliPlatformMismatch",
    )
    source_digest, locks_digest = configuration_digest(configurations)
    require(
        source_digest == bundle["configuration_sha256"]
        and locks_digest == bundle["lock_sha256"],
        "CandidateConfigurationBindingMismatch",
    )
    require(
        type(approval) is dict
        and set(approval) == {
            "schema_version", "kind", "operation", "namespace", "source_sha",
            "terraform_version", "provider_version", "platform", "state_identity",
            "terraform_sha256", "configuration_sha256", "lock_sha256", "approval_id",
        }
        and type(approval["schema_version"]) is int
        and approval["schema_version"] == 2
        and approval["kind"] == "p4-bootstrap-candidate-approval-v2"
        and isinstance(approval["approval_id"], str)
        and REVISION.fullmatch(approval["approval_id"]) is not None
        and all(approval[key] == bundle[key] for key in (
            "operation", "namespace", "source_sha", "terraform_version",
            "provider_version", "platform", "state_identity", "terraform_sha256",
            "configuration_sha256", "lock_sha256",
        ))
        and sha(canonical(approval)) == bundle["approval_sha256"],
        "CandidateFreshApprovalRequired",
    )
    require(
        type(journal) is dict
        and set(journal) == {"namespace", "state", "attempt_id"}
        and journal["namespace"] == NAMESPACE
        and journal["state"] == "NEW"
        and isinstance(journal["attempt_id"], str)
        and REVISION.fullmatch(journal["attempt_id"]) is not None,
        "CandidateAttemptNotNew",
    )
    if bundle["operation"] == "maintenance-plan":
        require(saved_plan is None, "CandidatePlanNotExpected")
    else:
        require(type(saved_plan) is dict and set(saved_plan) == PLAN_FIELDS,
                "CandidateSavedPlanBindingMissing")
        require(
            type(saved_plan["schema_version"]) is int
            and saved_plan["schema_version"] == 2
            and saved_plan["kind"] == "p4-bootstrap-candidate-plan-v2"
            and saved_plan["operation"] in {"maintenance-plan", "recovery-plan"}
            and (bundle["operation"] != "maintenance-apply"
                 or saved_plan["operation"] == "maintenance-plan")
            and all(saved_plan[key] == bundle[key] for key in (
                "namespace", "source_sha", "terraform_version", "provider_version",
                "platform", "terraform_sha256", "lock_sha256", "state_identity",
            ))
            and digest(saved_plan["plan_sha256"])
            and digest(saved_plan["plan_approval_sha256"])
            and saved_plan["plan_approval_sha256"] != bundle["approval_sha256"],
            "CandidateHistoricalPlanOrApprovalRejected",
        )
    return {"status": "OFFLINE_CANDIDATE_PREFLIGHT_ONLY", "authorized": False,
            "aws_operations": 0, "operation": bundle["operation"], "namespace": NAMESPACE}
