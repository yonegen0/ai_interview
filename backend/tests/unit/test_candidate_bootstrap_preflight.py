"""Fail-closed synthetic-only candidate bootstrap preflight contracts.

No AWS, Terraform process, backend init, State read, credentials or Plan/Apply.
"""

from copy import deepcopy

import pytest
from test_p4_tools import tool

AWS = "registry.terraform.io/hashicorp/aws"


@pytest.fixture
def fixture():
    m = tool("candidate_bootstrap_preflight")
    binary = b"synthetic-not-a-real-terraform-binary"
    locks = (
        'provider "registry.terraform.io/hashicorp/aws" { '
        'version = "6.70.0" constraints = "6.70.0" '
        'hashes = ["h1:' + "a" * 43 + '=", "h1:' + "b" * 43 + '=", "zh:' + "c" * 64 + '"] }'
    ).encode()
    configurations = {}
    for scope, filename in m.ROOTS.items():
        configurations[f"terraform/{scope}/{filename}"] = (
            b'terraform { required_version = "= 1.16.7" '
            b'required_providers { aws = { source = "hashicorp/aws", '
            b'version = "= 6.70.0" } } }'
        )
        configurations[f"terraform/{scope}/.terraform.lock.hcl"] = locks
    source_hash, locks_hash = m.configuration_digest(configurations)
    state = {
        "lineage": "synthetic-lineage",
        "serial": 1,
        "version_id": "synthetic-version",
        "sha256": "d" * 64,
    }
    bundle = {
        "schema_version": 2,
        "kind": "p4-bootstrap-candidate-preflight",
        "operation": "maintenance-plan",
        "namespace": m.NAMESPACE,
        "source_sha": "a" * 40,
        "terraform_version": m.CLI,
        "provider_version": m.PROVIDER,
        "platform": m.PLATFORM,
        "terraform_sha256": m.sha(binary),
        "configuration_sha256": source_hash,
        "lock_sha256": locks_hash,
        "state_identity": state,
        "approval_sha256": "",
    }
    approval = {
        **{
            k: bundle[k]
            for k in (
                "operation",
                "namespace",
                "source_sha",
                "terraform_version",
                "provider_version",
                "platform",
                "state_identity",
                "terraform_sha256",
                "configuration_sha256",
                "lock_sha256",
            )
        },
        "schema_version": 2,
        "kind": "p4-bootstrap-candidate-approval-v2",
        "approval_id": "c" * 40,
        "attempt_id": "b" * 40,
    }
    bundle["approval_sha256"] = m.sha(m.canonical(approval))
    journal = {"namespace": m.NAMESPACE, "state": "NEW", "attempt_id": "b" * 40}
    version = {"terraform_version": m.CLI, "platform": m.PLATFORM, "format_version": "1.0"}
    return m, bundle, version, configurations, binary, approval, journal


def run(f, *, saved_plan=None, saved_plan_binary=None, saved_plan_approval=None):
    m, bundle, version, configurations, binary, approval, journal = f
    return m.verify(
        bundle,
        version,
        configurations,
        binary=binary,
        approval=approval,
        journal=journal,
        saved_plan=saved_plan,
        saved_plan_binary=saved_plan_binary,
        saved_plan_approval=saved_plan_approval,
    )


def test_valid_candidate_preflight_never_authorizes_aws_or_apply(fixture):
    result = run(fixture)
    assert result["status"] == "OFFLINE_CANDIDATE_PREFLIGHT_ONLY"
    assert result["authorized"] is False
    assert result["aws_operations"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 1),
        ("schema_version", True),
        ("kind", "p4-bootstrap-maintenance-plan"),
        ("namespace", "p4-bootstrap-maintenance-legacy"),
        ("terraform_version", "1.14.9"),
        ("terraform_version", "1.17.0"),
        ("provider_version", "6.64.0"),
        ("platform", "windows_amd64"),
        ("operation", "apply"),
        ("source_sha", "x"),
        ("lock_sha256", "x"),
    ],
)
def test_cross_version_legacy_and_unknown_contracts_rejected(fixture, field, value):
    mutated = (fixture[0],) + deepcopy(fixture[1:])
    mutated[1][field] = value
    with pytest.raises(ValueError):
        run(mutated)


@pytest.mark.parametrize(
    "field,value",
    [
        ("terraform_version", "1.17.0"),
        ("platform", "windows_amd64"),
        ("format_version", "2.0"),
    ],
)
def test_version_json_mismatch_fails_closed(fixture, field, value):
    fixture[2][field] = value
    with pytest.raises(ValueError, match="CandidateCliPlatformMismatch"):
        run(fixture)


@pytest.mark.parametrize(
    "change",
    [
        "hcl",
        "hcl-extra",
        "old-lock",
        "lock-mutated",
        "different-lock",
        "missing-scope",
        "extra-scope",
        "non-bytes",
    ],
)
def test_candidate_hcl_and_provider_locks_must_match(fixture, change):
    m, bundle, _, configurations, *_ = fixture
    hcl = "terraform/bootstrap/main.tf"
    lock = "terraform/bootstrap/.terraform.lock.hcl"
    if change == "hcl":
        configurations[hcl] = configurations[hcl].replace(b"1.16.7", b"1.14.9")
    elif change == "hcl-extra":
        configurations[hcl] += b' required_version = "= 1.14.9"'
    elif change == "old-lock":
        configurations[lock] = configurations[lock].replace(b"6.70.0", b"6.64.0")
    elif change == "lock-mutated":
        configurations[lock] = configurations[lock].replace(b"c" * 64, b"d" * 64)
    elif change == "different-lock":
        configurations[lock] = configurations[lock].replace(b"c" * 64, b"d" * 64)
    elif change == "missing-scope":
        del configurations[hcl]
    elif change == "extra-scope":
        configurations["terraform/bootstrap/terraform.tfstate"] = b"{}"
    elif change == "non-bytes":
        configurations[lock] = "invalid"
    with pytest.raises((ValueError, UnicodeError)):
        run(fixture)
    assert bundle["terraform_version"] == m.CLI


@pytest.mark.parametrize(
    "change",
    [
        "binary",
        "approval",
        "approval-old",
        "approval-unknown",
        "state",
        "state-bool-serial",
        "state-missing",
        "journal-failed",
        "journal-unknown",
        "journal-missing",
        "journal-replay",
        "manifest-extra",
    ],
)
def test_untrusted_or_partial_evidence_rejected(fixture, change):
    m, bundle, version, configurations, binary, approval, journal = fixture
    if change == "binary":
        fixture = m, bundle, version, configurations, b"other binary", approval, journal
    elif change == "approval":
        approval["source_sha"] = "f" * 40
    elif change == "approval-old":
        approval["schema_version"] = 1
    elif change == "approval-unknown":
        approval["extra"] = "not-reviewed"
    elif change == "state":
        bundle["state_identity"]["lineage"] = ""
    elif change == "state-bool-serial":
        bundle["state_identity"]["serial"] = True
    elif change == "state-missing":
        del bundle["state_identity"]["sha256"]
    elif change == "journal-failed":
        journal["state"] = "FAILED"
    elif change == "journal-unknown":
        journal["state"] = "UNKNOWN"
    elif change == "journal-missing":
        del journal["attempt_id"]
    elif change == "journal-replay":
        journal["attempt_id"] = "a" * 40
    elif change == "manifest-extra":
        bundle["old_approval"] = "unsafe"
    with pytest.raises(ValueError):
        run(fixture)


def candidate_saved_plan(fixture, operation):
    m, bundle, *_ = fixture
    bundle["operation"] = operation
    fixture[5]["operation"] = operation
    bundle["approval_sha256"] = m.sha(m.canonical(fixture[5]))
    plan_binary = b"synthetic-offline-candidate-saved-plan-bytes"
    plan = {
        "schema_version": 2,
        "kind": "p4-bootstrap-candidate-plan-v2",
        "operation": "maintenance-plan" if operation == "maintenance-apply" else "recovery-plan",
        **{
            k: bundle[k]
            for k in (
                "namespace",
                "source_sha",
                "terraform_version",
                "provider_version",
                "platform",
                "terraform_sha256",
                "configuration_sha256",
                "lock_sha256",
                "state_identity",
            )
        },
        "plan_sha256": m.sha(plan_binary),
        "plan_approval_sha256": "",
    }
    plan_approval = {
        "schema_version": 2,
        "kind": "p4-bootstrap-candidate-plan-approval-v2",
        "approval_id": "e" * 40,
        **{
            k: plan[k]
            for k in (
                "namespace",
                "source_sha",
                "terraform_version",
                "provider_version",
                "platform",
                "state_identity",
                "terraform_sha256",
                "configuration_sha256",
                "lock_sha256",
                "plan_sha256",
            )
        },
    }
    plan["plan_approval_sha256"] = m.sha(m.canonical(plan_approval))
    return plan, plan_binary, plan_approval


@pytest.mark.parametrize("operation", ["maintenance-apply", "recovery-apply"])
def test_separate_candidate_plan_binding_is_required(fixture, operation):
    plan, binary, approval = candidate_saved_plan(fixture, operation)
    assert (
        run(fixture, saved_plan=plan, saved_plan_binary=binary, saved_plan_approval=approval)[
            "authorized"
        ]
        is False
    )
    for mutation in (
        "old-cli",
        "old-namespace",
        "old-state",
        "old-config",
        "same-approval",
        "missing",
    ):
        altered = deepcopy(plan)
        if mutation == "old-cli":
            altered["terraform_version"] = "1.14.9"
        elif mutation == "old-namespace":
            altered["namespace"] = "p4-bootstrap-legacy"
        elif mutation == "old-state":
            altered["state_identity"]["serial"] = 99
        elif mutation == "old-config":
            altered["configuration_sha256"] = "0" * 64
        elif mutation == "same-approval":
            altered["plan_approval_sha256"] = fixture[1]["approval_sha256"]
        elif mutation == "missing":
            del altered["plan_sha256"]
        with pytest.raises(ValueError):
            run(fixture, saved_plan=altered, saved_plan_binary=binary, saved_plan_approval=approval)
    with pytest.raises(ValueError, match="CandidateSavedPlanBinaryMismatch"):
        run(
            fixture,
            saved_plan=plan,
            saved_plan_binary=b"legacy-binary",
            saved_plan_approval=approval,
        )
    with pytest.raises(ValueError, match="CandidateFreshPlanApprovalRequired"):
        run(
            fixture,
            saved_plan=plan,
            saved_plan_binary=binary,
            saved_plan_approval={**approval, "approval_id": "0" * 40},
        )
    with pytest.raises(ValueError, match="CandidateSavedPlanBindingMissing"):
        run(fixture)


def test_legacy_maintenance_pin_is_independent_of_held_execution_proposal(fixture):
    assert tool("maintenance_contract").TF_VERSION == tool("bootstrap_maintenance").TF_VERSION
    assert tool("maintenance_contract").TF_VERSION == "1.14.9"
    cloud = tool("cloud_toolchain")
    assert cloud.EXPECTED_TERRAFORM_VERSION == cloud.NEW_EXECUTION_TERRAFORM_VERSION == "1.16.7"
    assert fixture[0].CLI == "1.16.7"
    assert fixture[0].NAMESPACE != "p4-bootstrap-maintenance-legacy"


@pytest.mark.parametrize(
    "operation,wrong_plan_operation",
    [
        ("maintenance-apply", "recovery-plan"),
        ("recovery-apply", "maintenance-plan"),
    ],
)
def test_apply_operation_must_match_its_own_saved_plan(fixture, operation, wrong_plan_operation):
    plan, binary, approval = candidate_saved_plan(fixture, operation)
    plan["operation"] = wrong_plan_operation
    with pytest.raises(ValueError, match="CandidateHistoricalPlanOrApprovalRejected"):
        run(fixture, saved_plan=plan, saved_plan_binary=binary, saved_plan_approval=approval)
