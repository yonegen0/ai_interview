"""Gate B recovery boundaries with synthetic State/Plan/processes; sockets stay forbidden."""

import base64
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def state14_recovery(recovery):
    h = recovery
    h.snapshot["identity"]["serial"] = 14
    h.snapshot["identity"]["version_id"] = "pinned-state14"
    h.snapshot["identity"]["sha256"] = "4" * 64
    h.descriptor["state_identity"] = copy.deepcopy(h.snapshot["identity"])
    h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    return h


def test_fresh_state14_requires_exact_new_identity_and_snapshot(state14_recovery):
    h = state14_recovery
    h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")
    h.m.check_state(h.snapshot, h.descriptor)
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    for field, value in [("version_id", "old-state13"), ("sha256", "0" * 64)]:
        changed = copy.deepcopy(h.snapshot)
        changed["identity"][field] = value
        with pytest.raises(ValueError):
            h.m.check_state(changed, h.descriptor)


@pytest.mark.parametrize("serial", [12, 15, True, "14"])
def test_other_serials_remain_outside_fixed_stage_recovery(recovery, serial):
    h = recovery
    h.descriptor["state_identity"]["serial"] = serial
    with pytest.raises(ValueError):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")


@pytest.fixture
def state15_recovery(state14_recovery):
    """Synthetic 77-resource successor; no private State or CloudTrail fixtures."""
    h = state14_recovery
    before = copy.deepcopy(h.snapshot["identity"])
    h.snapshot["identity"].update(serial=15, version_id="pinned-state15", sha256="5" * 64)
    for index in range(75):
        kind = "aws_iam_role_policy" if index < 10 else "aws_cloudwatch_log_group"
        name = f"synthetic_{index}"
        address = f"module.service.{kind}.{name}"
        attributes = {"name": name, "synthetic": True}
        h.snapshot["state"]["resources"].append(
            dict(
                module="module.service",
                type=kind,
                name=name,
                instances=[dict(attributes=attributes)],
            )
        )
        h.plan["resource_changes"].append(
            dict(
                address=address,
                type=kind,
                mode="managed",
                change=dict(actions=["no-op"], before=attributes, after=attributes),
            )
        )
        h.plan["planned_values"]["root_module"]["resources"].append(
            dict(address=address, mode="managed", values=attributes)
        )
    h.descriptor.update(
        schema_version=2,
        state_identity=copy.deepcopy(h.snapshot["identity"]),
        state_snapshot_sha256=h.m.canonical_hash(h.snapshot),
        predecessor={
            "kind": "failed-apply010",
            "source_sha": "c25181ca3880825a9dffd59115bc79cb450c80c0",
            "apply_run_id": "40777680174",
            "apply_attempt": 1,
            "plan_run_id": "40776053053",
            "plan_sha256": "db294c872fb1b2b00a304112416af8f6100087fe4c0017548ce11a0591f7f1f6",
            "started_receipt_sha256": (
                "8e7a7a0b0572da1029d764d9fc405a21846ef8fb1a04d5ed590b4720fc6a7514"
            ),
            "completed_receipt_absent": True,
            "deployment_receipt_absent": True,
            "approval_consumed": True,
            "denied_action": "logs:ListLogDeliveries",
            "cloudtrail_correlation_sha256": "a" * 64,
            "state_before": before,
            "state_after": copy.deepcopy(h.snapshot["identity"]),
            "resource_attributes_sha256": h.m.canonical_hash(h.m.state_resources(h.snapshot)),
        },
    )
    return h


@pytest.fixture
def state16_recovery(state15_recovery):
    h = state15_recovery
    before = copy.deepcopy(h.snapshot["identity"])
    h.snapshot["identity"].update(serial=16, version_id="pinned-state16", sha256="6" * 64)
    h.descriptor.update(
        schema_version=3,
        state_identity=copy.deepcopy(h.snapshot["identity"]),
        state_snapshot_sha256=h.m.canonical_hash(h.snapshot),
    )
    h.descriptor["predecessor"].update(
        kind="failed-stage15-apply",
        source_sha="04ceae2d75a3ba2c36764012295085af86846cda",
        apply_run_id="40865048330",
        plan_run_id="40858452172",
        plan_sha256="c1efebbf04945233c96acc9454ca5d880ae305ffe5e26dc1dc5d53d6e1ae4a9c",
        started_receipt_sha256="cb8c1d0fceba7a42c6de54877816aea56076160baef7c2fab9d7426be5c88bb3",
        denied_action="logs:GetLogDelivery",
        state_before=before,
        state_after=copy.deepcopy(h.snapshot["identity"]),
    )
    return h


@pytest.fixture(params=["state15_recovery", "state16_recovery"])
def successor_recovery(request):
    return request.getfixturevalue(request.param)


def test_successor_requires_separate_schema_provenance_and_complete_unchanged_resources(
    successor_recovery,
):
    h = successor_recovery
    original = copy.deepcopy((h.descriptor, h.snapshot, h.plan))
    assert h.m.validate(h.descriptor, "123456789012", "ap-northeast-1") == h.descriptor
    h.m.check_state(h.snapshot, h.descriptor)
    assert len(h.m.state_resources(h.snapshot)) == 77
    assert sum(row["type"].startswith("aws_iam_") for row in h.plan["resource_changes"]) == 10
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    assert (h.descriptor, h.snapshot, h.plan) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "other"),
        ("source_sha", "0" * 40),
        ("apply_run_id", "other"),
        ("apply_attempt", 2),
        ("apply_attempt", True),
        ("plan_run_id", "other"),
        ("plan_sha256", "0" * 64),
        ("started_receipt_sha256", "0" * 64),
        ("completed_receipt_absent", False),
        ("completed_receipt_absent", 1),
        ("deployment_receipt_absent", False),
        ("approval_consumed", False),
        ("denied_action", "logs:UpdateLogDelivery"),
        ("cloudtrail_correlation_sha256", "not-a-hash"),
        ("resource_attributes_sha256", None),
    ],
)
def test_successor_rejects_wrong_predecessor_provenance(successor_recovery, field, value):
    h = successor_recovery
    h.descriptor["predecessor"][field] = value
    with pytest.raises(ValueError, match="StageRecoveryScopeMismatch"):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize(
    "fault", ["missing", "extra", "missing-field", "old-schema", "cache", "pins"]
)
def test_successor_cannot_inherit_old_recovery_exceptions(successor_recovery, fault):
    h = successor_recovery
    if fault == "missing":
        h.descriptor.pop("predecessor")
    elif fault == "extra":
        h.descriptor["predecessor"]["unknown"] = True
    elif fault == "missing-field":
        h.descriptor["predecessor"].pop("approval_consumed")
    elif fault == "old-schema":
        h.descriptor.pop("predecessor")
        h.descriptor["schema_version"] = 1
    elif fault == "cache":
        h.descriptor["api_role_policy_cache_refresh"] = True
    else:
        h.descriptor["stage"].update(
            deployment_id_before="cached1", observed_deployment_id="observed2"
        )
    with pytest.raises(ValueError, match="StageRecoveryScopeMismatch"):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize("serial", [13, 14, 16, True, 15.0, "15"])
def test_state15_schema_rejects_other_or_noninteger_serials(state15_recovery, serial):
    h = state15_recovery
    h.descriptor["state_identity"]["serial"] = serial
    h.descriptor["predecessor"]["state_after"] = copy.deepcopy(h.descriptor["state_identity"])
    with pytest.raises(ValueError, match="StageRecoveryScopeMismatch"):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize("serial", [13, 14, 15, 17, True, 16.0, "16"])
def test_state16_schema_rejects_other_or_noninteger_serials(state16_recovery, serial):
    h = state16_recovery
    h.descriptor["state_identity"]["serial"] = serial
    h.descriptor["predecessor"]["state_after"] = copy.deepcopy(h.descriptor["state_identity"])
    with pytest.raises(ValueError, match="StageRecoveryScopeMismatch"):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize(
    "fault", ["serial", "lineage", "version", "same-version", "hash", "same-hash", "extra", "after"]
)
def test_successor_predecessor_requires_exact_identity_transition(successor_recovery, fault):
    h = successor_recovery
    p = h.descriptor["predecessor"]
    before, after = p["state_before"], p["state_after"]
    if fault == "serial":
        before["serial"] = True
    elif fault == "lineage":
        before["lineage"] = "different"
    elif fault == "version":
        before["version_id"] = "null"
    elif fault == "same-version":
        before["version_id"] = after["version_id"]
    elif fault == "hash":
        before["sha256"] = "invalid"
    elif fault == "same-hash":
        before["sha256"] = after["sha256"]
    elif fault == "extra":
        before["extra"] = True
    else:
        after["version_id"] = "different"
    with pytest.raises(ValueError, match="StageRecoveryScopeMismatch"):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize("fault", ["resource", "count", "identity", "snapshot", "fingerprint"])
def test_successor_binds_snapshot_identity_and_all_77_resources(successor_recovery, fault):
    h = successor_recovery
    if fault == "resource":
        h.m.state_resources(h.snapshot)[h.m.ADDRESS]["tags"]["Project"] = "changed"
        h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    elif fault == "count":
        h.snapshot["state"]["resources"].pop()
        h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
        h.descriptor["predecessor"]["resource_attributes_sha256"] = h.m.canonical_hash(
            h.m.state_resources(h.snapshot)
        )
    elif fault == "identity":
        h.snapshot["identity"]["version_id"] = "changed"
    elif fault == "snapshot":
        h.descriptor["state_snapshot_sha256"] = "0" * 64
    else:
        h.descriptor["predecessor"]["resource_attributes_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="StageRecoveryScopeMismatch"):
        h.m.check_state(h.snapshot, h.descriptor)


@pytest.mark.parametrize(
    "fault", ["iam-update", "destroy", "replace", "unknown", "missing", "extra-drift"]
)
def test_successor_still_audits_stage_only_change_and_iam_noop(successor_recovery, fault):
    h = successor_recovery
    row = h.plan["resource_changes"][2]
    if fault == "iam-update":
        row["change"]["actions"] = ["update"]
    elif fault == "destroy":
        row["change"]["actions"] = ["delete"]
    elif fault == "replace":
        row["change"]["replace_paths"] = [["name"]]
    elif fault == "unknown":
        row["change"]["after_unknown"] = {"name": True}
    elif fault == "missing":
        h.plan["resource_changes"].pop()
    else:
        h.plan["resource_drift"].append(copy.deepcopy(row))
        h.plan["resource_drift"][-1]["change"]["after"] = {"name": "changed"}
    with pytest.raises(ValueError, match="StageRecoveryPlanRejected"):
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


@pytest.fixture
def policy_cache_recovery(recovery):
    h = recovery
    cached = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "synthetic:Read", "Resource": "fixed"}],
        }
    )
    current = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": "synthetic:Read", "Resource": "fixed"},
                {"Effect": "Deny", "Action": "synthetic:Write", "Resource": "fixed"},
            ],
        }
    )
    original = dict(
        name="fixed-api",
        inline_policy=[dict(name="runtime", policy=cached)],
        permissions_boundary="fixed-boundary",
        managed_policy_arns=[],
        assume_role_policy="fixed-trust",
    )
    refreshed = copy.deepcopy(original)
    refreshed["inline_policy"][0]["policy"] = current
    policy = dict(role="fixed-api", name="runtime", policy=current)
    for kind, name, attributes, before, after, address in [
        ("aws_iam_role", "lambda", original, refreshed, refreshed, h.m.API_ROLE),
        ("aws_iam_role_policy", "runtime", policy, policy, policy, h.m.API_POLICY),
    ]:
        h.snapshot["state"]["resources"].append(
            dict(
                module="module.service",
                type=kind,
                name=name,
                instances=[dict(index_key="api", attributes=attributes)],
            )
        )
        h.plan["resource_changes"].append(
            dict(
                address=address,
                type=kind,
                mode="managed",
                change=dict(actions=["no-op"], before=before, after=after),
            )
        )
        h.plan["planned_values"]["root_module"]["resources"].append(
            dict(address=address, mode="managed", values=after)
        )
    h.plan["resource_drift"].append(
        dict(
            address=h.m.API_ROLE, change=dict(actions=["update"], before=original, after=refreshed)
        )
    )
    h.descriptor["api_role_policy_cache_refresh"] = True
    h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    h.cached_role, h.refreshed_role, h.managed_policy = original, refreshed, policy
    return h


def test_only_exact_fixed_role_cache_can_follow_separately_managed_state_policy(
    policy_cache_recovery,
):
    h = policy_cache_recovery
    original = copy.deepcopy((h.snapshot, h.plan, h.descriptor))
    h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")
    h.m.check_state(h.snapshot, h.descriptor)
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    final = copy.deepcopy(h.snapshot)
    h.m.state_resources(final)[h.m.API_ROLE]["inline_policy"] = copy.deepcopy(
        h.refreshed_role["inline_policy"]
    )
    assert h.m.same_resource_states(h.snapshot, final, recovery=h.descriptor)
    assert not h.m.same_resource_states(h.snapshot, final)
    assert (h.snapshot, h.plan, h.descriptor) == original


@pytest.mark.parametrize(
    "fault",
    [
        "flag",
        "unapproved",
        "extra-policy",
        "policy",
        "boundary",
        "trust",
        "attached",
        "role-name",
        "unknown",
        "replace",
        "action",
        "drift-before",
        "drift-after",
        "no-drift",
        "policy-resource",
    ],
)
def test_cached_policy_rule_cannot_admit_iam_changes_or_unbound_refresh(
    policy_cache_recovery, fault
):
    h = policy_cache_recovery
    change = h.plan["resource_changes"][-2]["change"]
    drift = h.plan["resource_drift"][-1]["change"]
    if fault == "flag":
        h.descriptor["api_role_policy_cache_refresh"] = False
    elif fault == "unapproved":
        h.descriptor.pop("api_role_policy_cache_refresh")
    elif fault == "extra-policy":
        h.refreshed_role["inline_policy"].append(dict(name="unapproved", policy="{}"))
    elif fault == "policy":
        h.refreshed_role["inline_policy"][0]["policy"] = "{}"
    elif fault == "boundary":
        h.refreshed_role["permissions_boundary"] = "other"
    elif fault == "trust":
        h.refreshed_role["assume_role_policy"] = "other"
    elif fault == "attached":
        h.refreshed_role["managed_policy_arns"] = ["unapproved"]
    elif fault == "role-name":
        h.refreshed_role["name"] = "other"
    elif fault == "unknown":
        change["after_unknown"] = {"inline_policy": True}
    elif fault == "replace":
        change["replace_paths"] = [["inline_policy"]]
    elif fault == "action":
        change["actions"] = ["update"]
    elif fault == "drift-before":
        drift["before"] = dict(h.cached_role, permissions_boundary="other")
    elif fault == "drift-after":
        drift["after"] = dict(h.refreshed_role, permissions_boundary="other")
    elif fault == "no-drift":
        h.plan["resource_drift"].pop()
    else:
        h.plan["resource_changes"][-1]["change"] = dict(
            actions=["update"], before=h.managed_policy, after=dict(h.managed_policy, policy="{}")
        )
    with pytest.raises(ValueError):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


@pytest.mark.parametrize("fault", [None, "document", "role", "name"])
def test_live_policy_read_must_match_immutable_managed_policy(
    policy_cache_recovery, monkeypatch, fault
):
    import github_control

    h = policy_cache_recovery
    monkeypatch.setattr(github_control, "verify_readiness", lambda *a: None)
    response = dict(
        RoleName=h.managed_policy["role"],
        PolicyName=h.managed_policy["name"],
        PolicyDocument=json.loads(h.managed_policy["policy"]),
    )
    if fault:
        response[
            {"document": "PolicyDocument", "role": "RoleName", "name": "PolicyName"}[fault]
        ] = {} if fault == "document" else "other"
    calls = []

    def read_policy(**kwargs):
        calls.append(kwargs)
        return response

    client = SimpleNamespace(
        get_api=lambda **k: {"DisableExecuteApiEndpoint": True},
        get_event_source_mapping=lambda **k: {"State": "Disabled"},
        get_schedule=lambda **k: {"State": "DISABLED"},
        get_stage=lambda **k: {
            "AccessLogSettings": {
                "DestinationArn": "arn:synthetic:logs",
                "Format": h.descriptor["stage"]["format_before"],
            }
        },
        get_role_policy=read_policy,
    )
    args = (SimpleNamespace(client=lambda *a, **k: client), h.snapshot, h.descriptor, {})
    if fault:
        with pytest.raises(ValueError):
            h.m.check_live(*args)
    else:
        h.m.check_live(*args)
    assert calls == [dict(RoleName="fixed-api", PolicyName="runtime")]


@pytest.fixture
def deployment_recovery(recovery):
    h = recovery
    h.snapshot = copy.deepcopy(h.snapshot)
    h.plan = copy.deepcopy(h.plan)
    old = h.m.state_resources(h.snapshot)[h.m.ADDRESS]
    old["deployment_id"] = "cached1"
    h.descriptor["stage"].update(deployment_id_before="cached1", observed_deployment_id="observed2")
    h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    change = h.plan["resource_changes"][0]["change"]
    change["before"]["deployment_id"] = "observed2"
    change["after"]["deployment_id"] = "observed2"
    h.plan["planned_values"]["root_module"]["resources"][0]["values"] = copy.deepcopy(
        change["after"]
    )
    h.plan["resource_drift"][0]["change"].update(
        before=copy.deepcopy(old), after=copy.deepcopy(change["before"])
    )
    return h


def test_exact_observed_auto_deployment_pin_allows_cached_state_refresh_only(deployment_recovery):
    h = deployment_recovery
    original = copy.deepcopy((h.snapshot, h.plan, h.descriptor))
    h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")
    h.m.check_state(h.snapshot, h.descriptor)
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    final = copy.deepcopy(h.snapshot)
    h.m.state_resources(final)[h.m.ADDRESS]["deployment_id"] = "observed2"
    assert h.m.same_resource_states(h.snapshot, final, recovery=h.descriptor)
    assert not h.m.same_resource_states(h.snapshot, final)
    h.m.state_resources(final)[h.m.ADDRESS]["deployment_id"] = "third3"
    assert not h.m.same_resource_states(h.snapshot, final, recovery=h.descriptor)
    assert (h.snapshot, h.plan, h.descriptor) == original


@pytest.mark.parametrize("fault", ["missing", "same", "invalid", "unpaired", "old-state", "manual"])
def test_deployment_descriptor_or_snapshot_rejects_unbound_pointer(deployment_recovery, fault):
    h = deployment_recovery
    stage = h.descriptor["stage"]
    if fault == "missing":
        stage["observed_deployment_id"] = ""
    elif fault == "same":
        stage["observed_deployment_id"] = "cached1"
    elif fault == "invalid":
        stage["observed_deployment_id"] = "other/id"
    elif fault == "unpaired":
        stage.pop("deployment_id_before")
    elif fault == "old-state":
        stage["deployment_id_before"] = "another3"
    else:
        h.m.state_resources(h.snapshot)[h.m.ADDRESS]["auto_deploy"] = False
        h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    with pytest.raises(ValueError):
        h.m.validate(h.descriptor, "123456789012", "ap-northeast-1")
        h.m.check_state(h.snapshot, h.descriptor)


@pytest.mark.parametrize(
    "fault",
    [
        "unapproved",
        "service-write",
        "manual",
        "unknown",
        "replace",
        "drift-before",
        "drift-after",
        "destination",
    ],
)
def test_plan_rejects_deployment_changes_outside_exact_observed_pin(deployment_recovery, fault):
    h = deployment_recovery
    change = h.plan["resource_changes"][0]["change"]
    drift = h.plan["resource_drift"][0]["change"]
    if fault == "unapproved":
        change["before"]["deployment_id"] = change["after"]["deployment_id"] = "third3"
    elif fault == "service-write":
        change["before"]["deployment_id"] = "cached1"
    elif fault == "manual":
        change["before"]["auto_deploy"] = change["after"]["auto_deploy"] = False
    elif fault == "unknown":
        change["after_unknown"] = {"deployment_id": True}
    elif fault == "replace":
        change["replace_paths"] = [["deployment_id"]]
    elif fault == "drift-before":
        drift["before"]["deployment_id"] = "third3"
    elif fault == "drift-after":
        drift["after"]["deployment_id"] = "third3"
    else:
        drift["after"]["access_log_settings"][0]["destination_arn"] = "arn:other"
    h.plan["planned_values"]["root_module"]["resources"][0]["values"] = copy.deepcopy(
        change["after"]
    )
    with pytest.raises(ValueError):
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


@pytest.mark.parametrize("fault", [None, "deployment", "manual"])
def test_live_stage_must_still_match_observed_deployment_pin(
    deployment_recovery, monkeypatch, fault
):
    import github_control

    h = deployment_recovery
    monkeypatch.setattr(github_control, "verify_readiness", lambda *a: None)
    stage = dict(
        DeploymentId="third3" if fault == "deployment" else "observed2",
        AutoDeploy=fault != "manual",
        AccessLogSettings=dict(
            DestinationArn="arn:synthetic:logs", Format=h.descriptor["stage"]["format_before"]
        ),
    )
    client = SimpleNamespace(
        get_api=lambda **k: {"DisableExecuteApiEndpoint": True},
        get_event_source_mapping=lambda **k: {"State": "Disabled"},
        get_schedule=lambda **k: {"State": "DISABLED"},
        get_stage=lambda **k: stage,
    )
    args = (SimpleNamespace(client=lambda *a, **k: client), h.snapshot, h.descriptor, {})
    if fault:
        with pytest.raises(ValueError):
            h.m.check_live(*args)
    else:
        h.m.check_live(*args)


@pytest.mark.parametrize("fault", ["missing-drift", "missing-pin"])
def test_deployment_refresh_requires_both_explicit_pin_and_plan_drift(deployment_recovery, fault):
    h = deployment_recovery
    if fault == "missing-drift":
        h.plan["resource_drift"] = []
    else:
        h.descriptor["stage"].pop("deployment_id_before")
        h.descriptor["stage"].pop("observed_deployment_id")
    with pytest.raises(ValueError):
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


@pytest.fixture
def route_recovery(recovery):
    h = recovery
    address = 'module.service.aws_apigatewayv2_route.business["GET /synthetic"]'
    original = dict(
        id="route1",
        api_id="api1",
        route_key="GET /synthetic",
        authorization_type="JWT",
        authorizer_id="jwt1",
        target="integrations/fixed",
        authorization_scopes=None,
        request_models=None,
    )
    refreshed = copy.deepcopy(original)
    refreshed.update(authorization_scopes=[], request_models={})
    h.snapshot["state"]["resources"].append(
        dict(
            module="module.service",
            type="aws_apigatewayv2_route",
            name="business",
            instances=[dict(index_key="GET /synthetic", attributes=original)],
        )
    )
    h.plan["resource_changes"].append(
        dict(
            address=address,
            type="aws_apigatewayv2_route",
            mode="managed",
            change=dict(actions=["no-op"], before=refreshed, after=refreshed),
        )
    )
    h.plan["planned_values"]["root_module"]["resources"].append(
        dict(address=address, mode="managed", values=refreshed)
    )
    h.route_address, h.route_original, h.route_refreshed = address, original, refreshed
    return h


def test_plan_accepts_provider_route_absent_optional_collections_only(route_recovery):
    h = route_recovery
    original = copy.deepcopy((h.snapshot, h.plan))
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    assert (h.snapshot, h.plan) == original


@pytest.mark.parametrize(
    "fault",
    [
        "scope",
        "model",
        "auth",
        "authorizer",
        "target",
        "scope-type",
        "map-type",
        "missing",
        "unrelated-null",
    ],
)
def test_route_empty_comparison_rejects_permissions_identity_type_or_missing_fields(
    route_recovery, fault
):
    h = route_recovery
    current = h.route_refreshed
    if fault == "scope":
        current["authorization_scopes"] = ["unapproved"]
    elif fault == "model":
        current["request_models"] = {"application/json": "unapproved"}
    elif fault == "auth":
        current["authorization_type"] = "NONE"
    elif fault == "authorizer":
        current["authorizer_id"] = "another"
    elif fault == "target":
        current["target"] = "integrations/another"
    elif fault == "scope-type":
        current["authorization_scopes"] = {}
    elif fault == "map-type":
        current["request_models"] = []
    elif fault == "missing":
        current.pop("request_models")
    else:
        current["unrelated"] = None
    with pytest.raises(ValueError):
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


def test_route_empty_drift_and_final_state_remain_identity_bound(route_recovery):
    h = route_recovery
    h.plan["resource_drift"].append(
        dict(
            address=h.route_address,
            change=dict(actions=["update"], before=h.route_original, after=h.route_refreshed),
        )
    )
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    final = copy.deepcopy(h.snapshot)
    final["state"]["resources"][-1]["instances"][0]["attributes"] = copy.deepcopy(h.route_refreshed)
    assert h.m.same_resource_states(h.snapshot, final)
    final["state"]["resources"][-1]["instances"][0]["attributes"]["authorization_type"] = "NONE"
    assert not h.m.same_resource_states(h.snapshot, final)


def test_route_empty_rule_does_not_normalize_other_resource_types_or_names(route_recovery):
    h = route_recovery
    for address in [
        "module.service.aws_lambda_function.main",
        'module.service.aws_apigatewayv2_route.other["GET /synthetic"]',
    ]:
        assert not h.m.resource_state_equal(address, h.route_original, h.route_refreshed)


@pytest.fixture
def cors_recovery(recovery):
    h = recovery
    original = {
        "id": "synthetic-api",
        "disable_execute_api_endpoint": True,
        "cors_configuration": [
            {
                "allow_headers": ["Authorization", "Content-Type"],
                "expose_headers": ["allow"],
                "allow_methods": ["GET", "OPTIONS", "POST"],
                "allow_origins": ["https://synthetic.invalid"],
                "allow_credentials": False,
                "max_age": 300,
            }
        ],
    }
    refreshed = copy.deepcopy(original)
    refreshed["cors_configuration"][0]["allow_headers"] = ["content-type", "authorization"]
    refreshed["cors_configuration"][0]["allow_methods"] = ["POST", "GET", "OPTIONS"]
    address = "module.service.aws_apigatewayv2_api.main"
    h.snapshot["state"]["resources"].append(
        {
            "module": "module.service",
            "type": "aws_apigatewayv2_api",
            "name": "main",
            "instances": [{"attributes": original}],
        }
    )
    h.plan["resource_changes"].append(
        {
            "address": address,
            "type": "aws_apigatewayv2_api",
            "mode": "managed",
            "change": {"actions": ["no-op"], "before": refreshed, "after": refreshed},
        }
    )
    h.plan["planned_values"]["root_module"]["resources"].append(
        {
            "address": address,
            "mode": "managed",
            "values": refreshed,
        }
    )
    h.api_address, h.api_original, h.api_refreshed = address, original, refreshed
    return h


def test_plan_accepts_provider_cors_header_case_and_set_order_only(cors_recovery):
    h = cors_recovery
    original = copy.deepcopy((h.snapshot, h.plan))
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    assert (h.snapshot, h.plan) == original


@pytest.mark.parametrize(
    "fault",
    ["header", "method", "origin-case", "credentials", "max-age", "endpoint", "duplicate", "null"],
)
def test_cors_representation_comparison_rejects_substantive_changes(cors_recovery, fault):
    h = cors_recovery
    current = h.api_refreshed
    cors = current["cors_configuration"][0]
    if fault == "header":
        cors["allow_headers"].append("x-unapproved")
    elif fault == "method":
        cors["allow_methods"].append("DELETE")
    elif fault == "origin-case":
        cors["allow_origins"] = ["https://SYNTHETIC.invalid"]
    elif fault == "credentials":
        cors["allow_credentials"] = True
    elif fault == "max-age":
        cors["max_age"] = 301
    elif fault == "endpoint":
        current["disable_execute_api_endpoint"] = False
    elif fault == "duplicate":
        cors["allow_headers"].append("authorization")
    else:
        current["optional"] = None
    with pytest.raises(ValueError):
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


def test_cors_representation_drift_and_final_state_use_identical_narrow_comparison(cors_recovery):
    h = cors_recovery
    h.plan["resource_drift"].append(
        {
            "address": h.api_address,
            "change": {"actions": ["update"], "before": h.api_original, "after": h.api_refreshed},
        }
    )
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    final = copy.deepcopy(h.snapshot)
    final["state"]["resources"][-1]["instances"][0]["attributes"] = copy.deepcopy(h.api_refreshed)
    assert h.m.same_resource_states(h.snapshot, final)
    final["state"]["resources"][-1]["instances"][0]["attributes"]["id"] = "another-api"
    assert not h.m.same_resource_states(h.snapshot, final)


@pytest.mark.parametrize(
    "fault", ["other-address", "header", "unknown", "replace", "before", "after"]
)
def test_api_representation_drift_does_not_allow_other_drift(cors_recovery, fault):
    h = cors_recovery
    row = {
        "address": h.api_address,
        "change": {
            "actions": ["update"],
            "before": copy.deepcopy(h.api_original),
            "after": copy.deepcopy(h.api_refreshed),
        },
    }
    if fault == "other-address":
        row["address"] = "module.service.aws_apigatewayv2_api.other"
    elif fault == "header":
        row["change"]["after"]["cors_configuration"][0]["allow_headers"].append("unapproved")
    elif fault == "unknown":
        row["change"]["after_unknown"] = {"id": True}
    elif fault == "replace":
        row["change"]["replace_paths"] = [["id"]]
    elif fault == "before":
        row["change"]["before"]["id"] = "another-api"
    else:
        row["change"]["after"]["id"] = "another-api"
    h.plan["resource_drift"].append(row)
    with pytest.raises(ValueError):
        h.m.audit_plan(h.plan, h.descriptor, h.snapshot)


def test_header_case_equivalence_is_confined_to_fixed_api(cors_recovery):
    h = cors_recovery
    assert h.m.resource_state_equal(h.api_address, h.api_original, h.api_refreshed)
    assert not h.m.resource_state_equal(
        "module.service.aws_apigatewayv2_api.other", h.api_original, h.api_refreshed
    )
    assert not h.m.resource_state_equal(h.m.ADDRESS, h.api_original, h.api_refreshed)


@pytest.fixture
def recovery():
    import stage_recovery as m

    after_format = json.dumps(m.AFTER, sort_keys=True, separators=(",", ":"))
    before_format = json.dumps(m.BEFORE, sort_keys=True, separators=(",", ":"))
    artifact = {
        "artifact_bucket": "ai-interview-artifacts-123456789012-ap-northeast-1",
        "artifact_key": "lambda/original/100/1/app.zip",
        "artifact_version": "fixed-version",
        "artifact_sha256_base64": base64.b64encode(
            hashlib.sha256(b"fixed-runtime").digest()
        ).decode(),
    }
    stage = {
        "id": "api1/dev",
        "api_id": "api1",
        "name": "dev",
        "auto_deploy": True,
        "access_log_settings": [{"destination_arn": "arn:synthetic:logs", "format": after_format}],
        "tags": {"Project": "ai-interview"},
    }
    identity = {
        "lineage": "fixed-lineage",
        "serial": 13,
        "version_id": "state-version",
        "sha256": "1" * 64,
    }
    snapshot = {
        "identity": identity,
        "manifest": {
            "api_id": "api1",
            "mappings": {"worker": "worker-map", "streams": "streams-map"},
            "artifact": {
                "bucket": artifact["artifact_bucket"],
                "key": artifact["artifact_key"],
                "version": artifact["artifact_version"],
                "sha256_base64": artifact["artifact_sha256_base64"],
            },
            "configuration": dict.fromkeys(
                ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled"), False
            ),
        },
        "state": {
            "resources": [
                {
                    "module": "module.service",
                    "type": "aws_apigatewayv2_stage",
                    "name": "dev",
                    "instances": [{"attributes": stage}],
                },
                {
                    "module": "module.service",
                    "type": "aws_lambda_function",
                    "name": "main",
                    "instances": [
                        {
                            "index_key": "api",
                            "attributes": {"s3_key": artifact["artifact_key"], "version": "7"},
                        }
                    ],
                },
            ]
        },
    }
    descriptor = {
        "schema_version": 1,
        "kind": "gate-b-stage-access-log",
        "state_identity": identity,
        "state_snapshot_sha256": m.canonical_hash(snapshot),
        "artifact": artifact,
        "stage": {
            "address": m.ADDRESS,
            "api_id": "api1",
            "stage_name": "dev",
            "format_before": before_format,
            "format_after": after_format,
        },
    }
    before = copy.deepcopy(stage)
    before["access_log_settings"][0]["format"] = before_format
    unchanged = snapshot["state"]["resources"][1]["instances"][0]["attributes"]
    plan = {
        "terraform_version": "1.14.9",
        "complete": True,
        "resource_changes": [
            {
                "address": m.ADDRESS,
                "type": "aws_apigatewayv2_stage",
                "mode": "managed",
                "change": {
                    "actions": ["update"],
                    "before": before,
                    "after": stage,
                    "after_unknown": {"access_log_settings": [{}]},
                },
            },
            {
                "address": 'module.service.aws_lambda_function.main["api"]',
                "type": "aws_lambda_function",
                "mode": "managed",
                "change": {"actions": ["no-op"], "before": unchanged, "after": unchanged},
            },
        ],
        "resource_drift": [
            {
                "address": m.ADDRESS,
                "change": {"actions": ["update"], "before": stage, "after": before},
            }
        ],
        "planned_values": {
            "root_module": {
                "resources": [
                    {"address": m.ADDRESS, "mode": "managed", "values": stage},
                    {
                        "address": 'module.service.aws_lambda_function.main["api"]',
                        "mode": "managed",
                        "values": unchanged,
                    },
                ]
            }
        },
        "output_changes": {
            "manifest": {
                "actions": ["no-op"],
                "before": snapshot["manifest"],
                "after": snapshot["manifest"],
            }
        },
    }
    return SimpleNamespace(m=m, descriptor=descriptor, snapshot=snapshot, plan=plan)


def test_recovery_validates_fixed_state_and_only_stage_change_without_mutating_inputs(recovery):
    h = recovery
    original = copy.deepcopy((h.descriptor, h.snapshot, h.plan))
    assert h.m.validate(h.descriptor, "123456789012", "ap-northeast-1") == h.descriptor
    h.m.check_state(h.snapshot, h.descriptor)
    assert h.m.audit_plan(h.plan, h.descriptor, h.snapshot)["change"] == 1
    assert (h.descriptor, h.snapshot, h.plan) == original


@pytest.mark.parametrize(
    "fault",
    ["serial", "version", "snapshot", "artifact", "format", "scope", "duplicate-json", "standard"],
)
def test_invalid_approval_or_state_is_rejected(recovery, fault):
    h = recovery
    d = copy.deepcopy(h.descriptor)
    if fault == "serial":
        d["state_identity"]["serial"] = 14
    elif fault == "version":
        d["state_identity"]["version_id"] = "null"
    elif fault == "snapshot":
        d["state_snapshot_sha256"] = "2" * 64
    elif fault == "artifact":
        d["artifact"]["artifact_version"] = "different"
    elif fault == "format":
        d["stage"]["format_before"] = d["stage"]["format_after"]
    elif fault == "scope":
        d["stage"]["stage_name"] = "prod"
    elif fault == "duplicate-json":
        raw = d["stage"]["format_before"]
        d["stage"]["format_before"] = raw[:-1] + ',"requestId":"$context.requestId"}'
    with pytest.raises(ValueError):
        env = {"P4_STANDARD_ACTIVE": "false" if fault == "standard" else "true"}
        h.m.from_approval(
            {"stage_recovery": d, "account_id": "123456789012", "region": "ap-northeast-1"}, env
        )
        h.m.check_state(h.snapshot, d)


@pytest.mark.parametrize(
    "fault",
    [
        "new-lambda",
        "missing-noop",
        "missing-planned",
        "unknown",
        "replace",
        "import",
        "move",
        "deposed",
        "tag",
        "destination",
        "output",
        "extra-drift",
        "duplicate",
        "provider-version",
    ],
)
def test_plan_rejects_every_unapproved_change_or_coverage_gap(recovery, fault):
    h = recovery
    p = copy.deepcopy(h.plan)
    row = p["resource_changes"][0]
    if fault == "new-lambda":
        p["resource_changes"][1]["change"]["actions"] = ["update"]
    elif fault == "missing-noop":
        p["resource_changes"].pop()
    elif fault == "missing-planned":
        p["planned_values"]["root_module"]["resources"].pop()
    elif fault == "unknown":
        row["change"]["after_unknown"] = {"id": True}
    elif fault == "replace":
        row["change"]["actions"] = ["delete", "create"]
    elif fault == "import":
        row["change"]["importing"] = {"id": "x"}
    elif fault in ("move", "deposed"):
        row["previous_address" if fault == "move" else "deposed"] = "unexpected"
    elif fault == "tag":
        row["change"]["after"]["tags"] = {"Project": "changed"}
    elif fault == "destination":
        row["change"]["after"]["access_log_settings"][0]["destination_arn"] = "unexpected"
    elif fault == "output":
        p["output_changes"]["manifest"]["actions"] = ["update"]
    elif fault == "extra-drift":
        p["resource_drift"].append(copy.deepcopy(p["resource_changes"][1]))
    elif fault == "duplicate":
        p["resource_changes"].append(copy.deepcopy(row))
    else:
        p["terraform_version"] = "1.16.7"
    with pytest.raises(ValueError, match="PlanRejected"):
        h.m.audit_plan(p, h.descriptor, h.snapshot)


def test_null_shape_mismatch_is_still_rejected_with_value_free_diagnostic(recovery):
    from standard_diagnostics import Diagnostic

    h = recovery
    p = copy.deepcopy(h.plan)
    address = 'module.service.aws_lambda_function.main["api"]'
    # JSON planned values may omit optional nulls; diagnostics must not accept this implicitly.
    h.snapshot["state"]["resources"][1]["instances"][0]["attributes"]["optional"] = None
    with pytest.raises(ValueError, match="PlanRejected") as failure:
        h.m.audit_plan(p, h.descriptor, h.snapshot)
    projected = Diagnostic().projection(failure.value)
    assert projected["reason_code"] == "StageRecoveryPlanRejected"
    assert projected["stage_audit"] == {
        "rule": "other-resource-state-match",
        "resource_index": 2,
        "differing_attribute_count": 1,
        "optional_nulls_only": True,
    }
    assert address not in json.dumps(projected)


def test_actual_state_value_mismatch_is_distinct_from_null_shape(recovery):
    from standard_diagnostics import Diagnostic

    h = recovery
    p = copy.deepcopy(h.plan)
    h.snapshot["state"]["resources"][1]["instances"][0]["attributes"]["version"] = "private-value"
    with pytest.raises(ValueError, match="PlanRejected") as failure:
        h.m.audit_plan(p, h.descriptor, h.snapshot)
    projected = Diagnostic().projection(failure.value)
    assert projected["stage_audit"]["optional_nulls_only"] is False
    assert projected["stage_audit"]["differing_attribute_count"] == 1
    assert "private-value" not in json.dumps(projected)


def test_recovery_guard_rejects_lambda_upload_and_envelope_before_four_plan_objects(
    recovery, monkeypatch, tmp_path
):
    import plan_authorization as m
    from test_plan_authorization import bind, environment, run_record

    h = recovery
    env, desc = environment(artifact_digest=h.m.artifact_digest(h.descriptor))
    env["P4_STANDARD_ACTIVE"] = "true"
    env["GITHUB_ACTOR_ID"] = "76547980"
    desc.update(stage_recovery=h.descriptor, s3_put_limit=5)
    bind(env, desc)
    history = run_record(
        env,
        path=".github/workflows/p4-standard-plan.yml",
        actor={"id": 76547980},
        triggering_actor={"id": 76547980},
    )
    guard = m.Guard(
        env,
        tmp_path / "journal",
        github_get=lambda *a: {"total_count": 1, "workflow_runs": [history]},
        recipient_check=lambda *a: None,
    )
    bucket = h.descriptor["artifact"]["artifact_bucket"]
    with pytest.raises(ValueError, match="S3ScopeOrCount"):
        guard.put(bucket, "lambda/anything/app.zip", lambda: pytest.fail("upload forbidden"))

    guard = m.Guard(
        env,
        tmp_path / "journal2",
        github_get=lambda *a: {"total_count": 1, "workflow_runs": [history]},
        recipient_check=lambda *a: None,
    )
    with pytest.raises(ValueError, match="S3ScopeOrCount"):
        guard.put(bucket, "plans/123/1/envelope.json", lambda: pytest.fail("early envelope"))
    guard = m.Guard(
        env,
        tmp_path / "journal3",
        github_get=lambda *a: {"total_count": 1, "workflow_runs": [history]},
        recipient_check=lambda *a: None,
    )
    calls = []
    for name in ("dev.tfplan", "plan.json", "summary.json", "review.private.json", "envelope.json"):
        guard.put(bucket, "plans/123/1/" + name, lambda name=name: calls.append(name))
    assert len(calls) == 5


@pytest.mark.parametrize(
    "fault", [None, "binding-mode", "package", "plan", "source", "state", "nonstandard"]
)
@pytest.mark.parametrize("scenario", ["recovery", "state15_recovery"])
def test_apply_requires_immutable_envelope_binding_and_new_exact_plan_consent(
    request, scenario, fault
):
    h = request.getfixturevalue(scenario)
    d = h.descriptor
    e = {
        "stage_recovery": d,
        "package": d["artifact"],
        "code_sha": "a" * 40,
        "plan_sha256": "b" * 64,
        "run_id": "123",
        "run_attempt": "1",
    }
    b = {
        "stage_recovery": d,
        "state_identity": d["state_identity"],
        "code_sha": "a" * 40,
        "plan_sha256": "b" * 64,
    }
    env = {
        "P4_STANDARD_ACTIVE": "true",
        "P4_OPERATION": "apply",
        "AWS_DEV_ACCOUNT_ID": "123456789012",
        "AWS_REGION": "ap-northeast-1",
        "P4_APPROVED_SOURCE_SHA": "a" * 40,
        "P4_PLAN_HASH": "b" * 64,
        "P4_PLAN_RUN_ID": "123",
    }
    if fault == "binding-mode":
        b.pop("stage_recovery")
    elif fault == "package":
        e["package"] = {}
    elif fault == "plan":
        env["P4_PLAN_HASH"] = "c" * 64
    elif fault == "source":
        env["P4_APPROVED_SOURCE_SHA"] = "c" * 40
    elif fault == "state":
        b["state_identity"] = {}
    elif fault == "nonstandard":
        env["P4_STANDARD_ACTIVE"] = "false"
    if fault:
        with pytest.raises(ValueError):
            h.m.envelope_recovery(e, b, env)
    else:
        assert h.m.envelope_recovery(e, b, env) == d


@pytest.mark.parametrize("target", ["envelope", "binding", "both"])
def test_null_recovery_cannot_bypass_normal_artifact_binding(recovery, target):
    envelope, binding = {}, {}
    if target in ("envelope", "both"):
        envelope["stage_recovery"] = None
    if target in ("binding", "both"):
        binding["stage_recovery"] = None
    with pytest.raises(ValueError):
        recovery.m.envelope_recovery(envelope, binding, {})
    assert recovery.m.envelope_recovery({}, {}, {}) is None


@pytest.mark.parametrize("fault", [None, "api", "worker", "scheduler", "stage", "readiness"])
def test_fresh_live_checks_fail_closed_without_credentials(recovery, monkeypatch, fault):
    import github_control

    h = recovery
    calls = []

    def client(name, **kwargs):
        assert kwargs["config"].retries == {"total_max_attempts": 1}

        def api(**kwargs):
            calls.append("api")
            return {"DisableExecuteApiEndpoint": fault != "api"}

        def mapping(**kwargs):
            calls.append(kwargs["UUID"])
            return {"State": "Enabled" if fault == "worker" else "Disabled"}

        return SimpleNamespace(
            get_api=api,
            get_event_source_mapping=mapping,
            get_schedule=lambda **k: {"State": "ENABLED" if fault == "scheduler" else "DISABLED"},
            get_stage=lambda **k: {
                "AccessLogSettings": {
                    "DestinationArn": "arn:synthetic:logs",
                    "Format": "bad" if fault == "stage" else h.descriptor["stage"]["format_before"],
                }
            },
        )

    def github(path, env):
        flag = "true" if "/dev-plan/" in path else "false"
        if fault == "readiness":
            flag = "false"
        return {
            "total_count": 2,
            "variables": [
                {"name": k, "value": flag} for k in ("P4_STANDARD_READY", "P4_AWS_EXECUTION_READY")
            ],
        }

    monkeypatch.setattr(github_control, "github_json", github)
    args = (SimpleNamespace(client=client), h.snapshot, h.descriptor, {"P4_OPERATION": "plan"})
    if fault:
        with pytest.raises(ValueError):
            h.m.check_live(*args)
    else:
        h.m.check_live(*args)
        assert calls == ["api", "worker-map", "streams-map"]


@pytest.mark.parametrize("returncode", [0, 1])
def test_apply_process_records_real_return_code_before_receipt(
    recovery, monkeypatch, tmp_path, returncode
):
    import ci_identity

    h = recovery
    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: None)
    child = SimpleNamespace(
        returncode=returncode,
        communicate=lambda **k: (b"private stdout", b"private stderr"),
        poll=lambda: returncode,
    )
    monkeypatch.setattr(h.m.subprocess, "Popen", lambda *a, **k: child)
    if returncode:
        with pytest.raises(ValueError):
            h.m.apply_process(["terraform", "apply"], tmp_path, cwd=tmp_path, env={})
    else:
        assert (
            h.m.apply_process(["terraform", "apply"], tmp_path, cwd=tmp_path, env={})
            == b"private stdout"
        )
    recorded = (tmp_path / "recovery-process-exit.private.json").read_text()
    assert json.loads(recorded)["returncode"] == returncode
    assert "private stdout" not in recorded and "private stderr" not in recorded


@pytest.mark.parametrize("returncode", [0, 1])
def test_recovery_apply_child_drops_app_token_and_preserves_parent(
    recovery, monkeypatch, tmp_path, returncode
):
    import ci_identity

    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: None)
    environment = {
        "P4_ENV_READ_TOKEN": "synthetic-app-token",
        "GH_TOKEN": "synthetic-github-token",
        "AWS_SESSION_TOKEN": "synthetic-session-token",
        "PATH": "synthetic-path",
    }
    before = environment.copy()
    calls = []

    def launch(command, **kwargs):
        calls.append(command)
        assert "P4_ENV_READ_TOKEN" not in kwargs["env"]
        assert "GH_TOKEN" not in kwargs["env"]
        assert kwargs["env"] == {
            k: v for k, v in before.items() if k not in {"P4_ENV_READ_TOKEN", "GH_TOKEN"}
        }
        assert kwargs["env"] is not environment
        return SimpleNamespace(
            returncode=returncode,
            communicate=lambda **k: (b"", b""),
            poll=lambda: returncode,
        )

    monkeypatch.setattr(recovery.m.subprocess, "Popen", launch)
    if returncode:
        with pytest.raises(ValueError):
            recovery.m.apply_process(
                ["terraform", "apply"], tmp_path, cwd=tmp_path, env=environment
            )
    else:
        recovery.m.apply_process(["terraform", "apply"], tmp_path, cwd=tmp_path, env=environment)
    assert environment == before
    assert calls == [["terraform", "apply"]]


@pytest.mark.parametrize("unknown", [False, True])
def test_apply_deadline_interrupts_once_and_never_relaunches(
    recovery, monkeypatch, tmp_path, unknown
):
    import ci_identity

    h = recovery
    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: None)
    ticks = iter([0, 1201])
    monkeypatch.setattr(h.m.time, "monotonic", lambda: next(ticks))
    launches, signals = [], []

    def communicate(**kwargs):
        if unknown:
            raise h.m.subprocess.TimeoutExpired("terraform", kwargs["timeout"])
        return b"", b""

    child = SimpleNamespace(
        returncode=1, poll=lambda: None, send_signal=signals.append, communicate=communicate
    )

    def launch(*args, **kwargs):
        launches.append(True)
        return child

    monkeypatch.setattr(h.m.subprocess, "Popen", launch)
    with pytest.raises(ValueError):
        h.m.apply_process(["terraform", "apply"], tmp_path, cwd=tmp_path, env={})
    assert launches == [True] and signals == [h.m.signal.SIGINT]
    name = (
        "recovery-process-unknown.private.json"
        if unknown
        else "recovery-process-interrupted.private.json"
    )
    assert (tmp_path / name).is_file()
    assert not (tmp_path / "recovery-process-exit.private.json").exists()


@pytest.mark.parametrize("bad_state", [False, True])
def test_ci_recovery_skips_build_and_lambda_upload_and_binds_new_envelope(
    recovery, monkeypatch, tmp_path, bad_state
):
    import ci_deploy as m
    import github_control
    import stage_request_budget

    h = recovery
    for key, value in {
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "P4_STANDARD_ACTIVE": "true",
        "GITHUB_SHA": "a" * 40,
        "P4_PACKAGE_BASE_SHA": "b" * 40,
    }.items():
        monkeypatch.setenv(key, value)
    descriptor = {
        "account_id": "123456789012",
        "region": "ap-northeast-1",
        "stage_recovery": h.descriptor,
    }
    guard = SimpleNamespace(
        package=descriptor, record=lambda *a, **k: None, check=lambda *a: None, fail=lambda *a: None
    )
    closed = []
    monkeypatch.setattr(m, "PROJECT", tmp_path)
    monkeypatch.setattr(m, "preflight", lambda env: ("123456789012", "ap-northeast-1", "plan", {}))
    monkeypatch.setattr(m, "initialize", lambda *a: guard)
    monkeypatch.setattr(m, "checked_git", lambda *a: "a" * 40)
    monkeypatch.setattr(github_control, "verify_environment_access", lambda *a: None)
    monkeypatch.setattr(
        stage_request_budget,
        "install",
        lambda *a: SimpleNamespace(close=lambda: closed.append(True)),
    )
    observed = copy.deepcopy(h.snapshot)
    if bad_state:
        observed["identity"]["serial"] = 14
    monkeypatch.setattr(m, "plan_state_preflight", lambda *a: observed)
    monkeypatch.setattr(m, "build_package", lambda *a: pytest.fail("recovery must reuse artifact"))
    objects = {}
    monkeypatch.setattr(m, "role_session", lambda *a: None)
    monkeypatch.setattr(m, "s3_client", lambda *a: None)

    def put(s3, bucket, key, body):
        assert key.startswith("plans/123/1/")
        objects[key] = body
        return "new-object-version"

    monkeypatch.setattr(m, "put", put)

    def execute(operation, path, directory):
        assert operation == "plan" and json.loads(path.read_bytes()) == h.descriptor["artifact"]
        directory.mkdir()
        for name in ("dev.tfplan", "plan.json", "summary.json", "review.private.json"):
            (directory / name).write_bytes(b"synthetic-private")
        return {"plan_sha256": "c" * 64}

    monkeypatch.setattr(m, "execute", execute)
    assert m.main() == int(bad_state)
    assert closed == [True]
    if bad_state:
        assert objects == {}
    else:
        assert len(objects) == 5
        envelope = json.loads(objects["plans/123/1/envelope.json"])
        assert envelope["stage_recovery"] == h.descriptor
        assert envelope["package"] == h.descriptor["artifact"]


@pytest.mark.parametrize(
    "operation,post_apply_failure",
    [
        ("plan", None),
        ("apply", None),
        ("verify", None),
        ("apply", "manifest"),
        ("apply", "live-stage"),
        ("apply", "final-state"),
    ],
)
@pytest.mark.parametrize(
    "scenario", ["recovery", "policy_cache_recovery", "state14_recovery", "state15_recovery"]
)
def test_terraform_recovery_checks_full_plan_and_live_closure_before_and_after(
    request, monkeypatch, tmp_path, operation, scenario, post_apply_failure
):
    import deployment_guards
    import manifest
    import terraform_dev as m

    h = request.getfixturevalue(scenario)
    source = tmp_path / "source"
    root = source / "terraform/environments/dev"
    root.mkdir(parents=True)
    (root / ".terraform.lock.hcl").write_text("fixed lock")
    directory = source / ".p4-artifacts/run"
    directory.parent.mkdir()
    inputs = tmp_path / "inputs.json"
    inputs.write_text("{}")
    values = dict.fromkeys(
        ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled"), False
    )
    account, region, code_sha = "123456789012", "ap-northeast-1", "a" * 40
    guard = SimpleNamespace(
        package={"stage_recovery": h.descriptor, "account_id": account, "region": region},
        check=lambda *a: None,
    )
    monkeypatch.setenv("P4_STANDARD_ACTIVE", "true")
    monkeypatch.setattr(m, "PROJECT", source)
    monkeypatch.setattr(m, "require_aws_execution", lambda: None)
    monkeypatch.setattr(m, "required_guard", lambda: guard)
    monkeypatch.setattr(m, "account_settings", lambda *a: (account, region))
    monkeypatch.setattr(m, "terraform_environment", lambda *a: {})
    monkeypatch.setattr(m, "inputs", lambda *a: values)
    monkeypatch.setattr(m, "validate_inputs", lambda *a, **k: None)
    monkeypatch.setattr(m, "checked_git", lambda *a: code_sha)
    monkeypatch.setattr(m, "checked_session", lambda *a, **k: object())
    monkeypatch.setattr(m, "credential_environment", lambda session, env: env)
    import ci_identity

    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: None)
    observed_live, audits, commands = [], [], []

    def check_live(*a, **k):
        observed_live.append(k.get("applied", False))
        if k.get("applied") and post_apply_failure == "live-stage":
            m.checkpoint("post-apply-verification")
            raise ValueError("StageRecoveryScopeMismatch")

    monkeypatch.setattr(h.m, "check_live", check_live)
    audit = h.m.audit_plan

    def checked_audit(*args):
        audits.append(True)
        return audit(*args)

    monkeypatch.setattr(h.m, "audit_plan", checked_audit)
    monkeypatch.setattr(deployment_guards, "audit_retention", lambda *a, **k: None)
    final = copy.deepcopy(h.snapshot)
    if scenario == "policy_cache_recovery":
        h.m.state_resources(final)[h.m.API_ROLE]["inline_policy"] = copy.deepcopy(
            h.refreshed_role["inline_policy"]
        )
    final["identity"] = final["identity"] | {
        "serial": h.snapshot["identity"]["serial"] + 1,
        "version_id": "new-version",
    }
    if post_apply_failure == "final-state":
        h.m.state_resources(final)[h.m.ADDRESS]["tags"]["Project"] = "unauthorized"
    snapshots = iter([h.snapshot, h.snapshot] + ([final] if operation == "apply" else []))
    historical_reads = []

    def read_snapshot(*args, **kwargs):
        if operation == "verify":
            if "historical_version_id" in kwargs:
                historical_reads.append(kwargs["historical_version_id"])
                return h.snapshot
            return final
        return next(snapshots)

    monkeypatch.setattr(deployment_guards, "read_state_snapshot", read_snapshot)
    monkeypatch.setattr(
        manifest, "read_manifest", lambda *a: h.snapshot["manifest"] | {"versions": {}}
    )

    def wait_for_manifest(*a, **k):
        if post_apply_failure == "manifest":
            raise ValueError("private verification failure")

    monkeypatch.setattr(manifest, "wait_for_manifest", wait_for_manifest)

    def run(command, **kwargs):
        commands.append(command)
        if command[1] == "version":
            return b'{"terraform_version":"1.14.9"}'
        if command[1] == "plan":
            (directory / "dev.tfplan").write_bytes(b"saved plan")
        if command[1] == "show":
            return json.dumps(h.plan).encode()
        if command[1] == "output":
            return b"{}"
        return b""

    monkeypatch.setattr(m, "run", run)

    def apply_process(command, *a, **k):
        from standard_diagnostics import process_event

        commands.append(command)
        process_event("apply", "admission")
        process_event("apply", "launched")
        process_event("apply", "exit-observed", returncode=0)

    monkeypatch.setattr(h.m, "apply_process", apply_process)
    approved = hashlib.sha256(b"saved plan").hexdigest()
    if operation in {"apply", "verify"}:
        directory.mkdir()
        (directory / "dev.tfplan").write_bytes(b"saved plan")
        if operation == "verify":
            (directory / "apply-completed.json").write_text(json.dumps({"plan_sha256": approved}))
        binding = m.bind_plan(root, account, region, code_sha, inputs)
        binding.update(
            state_identity=h.snapshot["identity"],
            log_retention_approval_sha256=None,
            stage_recovery=h.descriptor,
            plan_sha256=approved,
        )
        (directory / "plan.json").write_text(json.dumps(binding))
    if post_apply_failure:
        import standard_diagnostics as diagnostics

        diagnostic = diagnostics.Diagnostic()
        token = diagnostics.CURRENT.set(diagnostic)
        try:
            with pytest.raises(ValueError) as raised:
                m.execute(operation, inputs, directory, approved)
            value = diagnostic.projection(raised.value)
        finally:
            diagnostics.CURRENT.reset(token)
        assert value["failure_stage"] == "post-apply-verification"
        assert value["process_started"] is value["process_exit_observed"] is True
        assert value["process_returncode"] == 0
        assert value["terraform_command_kind"] == "apply"
        assert (directory / "apply-completed.json").is_file()
        assert sum(c[1] == "apply" for c in commands) == 1
        assert "private verification failure" not in json.dumps(value)
        return
    result = m.execute(operation, inputs, directory, approved if operation != "plan" else None)
    assert result["status"] == ("planned" if operation == "plan" else "applied_readback_verified")
    assert audits == ([] if operation == "verify" else [True])
    assert observed_live == (
        [True, True] if operation == "verify" else [False, operation == "apply"]
    )
    assert historical_reads == (
        [h.descriptor["state_identity"]["version_id"]] if operation == "verify" else []
    )
    if operation != "verify":
        actual = next(c for c in commands if c[1] == operation)
        assert "-lock-timeout=0s" in actual
        assert not any(c in actual for c in ("-refresh=false", "-refresh-only", "-target"))
    else:
        assert not any(c[1] in {"apply", "plan"} for c in commands)
        # A completed recovery must still reject unauthorized post-Apply State changes.
        h.m.state_resources(final)[h.m.ADDRESS]["tags"]["Project"] = "unauthorized"
        with pytest.raises(ValueError, match="StageRecoveryFinalStateMismatch"):
            m.execute("verify", inputs, directory, approved)


def test_terraform_run_does_not_inherit_github_tokens(monkeypatch, tmp_path):
    import terraform_dev as m

    monkeypatch.delenv("P4_STANDARD_ACTIVE", raising=False)
    monkeypatch.setattr(m, "active_guard", lambda: None)
    parent = {
        "GH_TOKEN": "synthetic-github-token",
        "P4_ENV_READ_TOKEN": "synthetic-environment-token",
        "AWS_SESSION_TOKEN": "synthetic-aws-session-token",
        "PATH": "synthetic-path",
    }
    before = dict(parent)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs["env"]))
        return SimpleNamespace(returncode=0, stdout=b"ok")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m.run(["terraform", "version"], cwd=tmp_path, env=parent) == b"ok"
    assert len(calls) == 1
    assert calls[0][0] == ["terraform", "version"]
    assert calls[0][1] == {
        "AWS_SESSION_TOKEN": before["AWS_SESSION_TOKEN"],
        "PATH": "synthetic-path",
    }
    assert parent == before
