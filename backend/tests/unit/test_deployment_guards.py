"""Private approval, immutable State, drain and retention boundaries without AWS."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_cost_controls import cost_deployment as cost_deployment
from test_p4_manifest_v3 import admin_deployment as admin_deployment
from test_p4_tools import tool

from interview_backend.models.internal import StorageFormatError


@pytest.fixture(autouse=True)
def import_tools(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "skills/p4"))


def private_write(path, value):
    path.write_text(json.dumps(value))
    return str(path), tool("deployment_guards").sha256(path.read_bytes())


@pytest.fixture
def bound(cost_deployment, tmp_path):
    m, _, _ = cost_deployment
    m.update(environment="test", run_id="synthetic")
    m["configuration"].update(log_usage="developer", log_retention_days=3)
    m["test_closure_evidence_sha256"] = ""
    identity = {"lineage": "lineage", "serial": 9, "version_id": "v9", "sha256": "a" * 64}
    snapshot = {"identity": identity, "manifest": m, "state": {"resources": []}}
    proof = {
        "account_id": m["account_id"],
        "region": m["region"],
        "run_id": m["run_id"],
        "manifest_sha256": tool("deployment_guards").canonical_hash(m),
        "state_identity": identity,
        "issued_at_epoch": 10000,
        "expires_at_epoch": 10900,
        "status": "APPROVED_TEST_DRAIN",
        "alarm_count": 39,
        "approved_by": "reviewer",
        "observed_by": "operator",
        "writers_stopped_at_epoch": 0,
    }
    proof["reviewed_evidence"] = {}
    for kind in ("external_writers", "queue_ledger", "incident_resolution"):
        document = proof | {"status": "RECONCILED", "remaining": 0, "observed_at_epoch": 10000}
        path, digest = private_write(tmp_path / f"{kind}.json", document)
        proof["reviewed_evidence"][kind] = {"path": path, "sha256": digest}
    alarms = tool("manifest_alarms").expected_alarms(m, "ai-interview-test-synthetic")
    for i, name in enumerate(alarms):
        snapshot["state"]["resources"].append(
            {
                "module": "module.service",
                "mode": "managed",
                "type": "aws_cloudwatch_metric_alarm",
                "name": "emf",
                "instances": [{"index_key": str(i), "attributes": {"alarm_name": name}}],
            }
        )
    snapshot["state"]["resources"].append(
        {
            "module": "module.service",
            "mode": "managed",
            "type": "aws_dynamodb_table",
            "name": "main",
            "instances": [{"attributes": {"name": "unchanged"}}],
        }
    )
    path, digest = private_write(tmp_path / "proof.json", proof)
    after = copy.deepcopy(m)
    after["configuration"].update(test_monitoring_enabled=False, test_closure_confirmed=True)
    after["test_closure_evidence_sha256"] = digest
    values = tool("closure_adapter").state_instances(snapshot["state"])
    review = {
        "resource_changes": [
            {
                "address": a,
                "change": {
                    "before": v,
                    "after": None if "metric_alarm" in a else v,
                    "after_unknown": {},
                    "actions": ["delete"] if "metric_alarm" in a else ["no-op"],
                },
            }
            for a, v in values.items()
        ],
        "output_changes": {"manifest": {"before": copy.deepcopy(m), "after": after}},
    }
    return SimpleNamespace(
        m=m,
        snapshot=snapshot,
        proof=proof,
        path=path,
        digest=digest,
        private=tmp_path,
        review=review,
        after=after,
    )


def fake_session(*, queue="0", items=None, reserved=-1, age=3600):
    return SimpleNamespace(
        client=lambda name, **kw: SimpleNamespace(
            get_function_configuration=lambda **kw: {"Timeout": 60},
            get_function_concurrency=lambda **kw: {"ReservedConcurrentExecutions": reserved},
            get_function_event_invoke_config=lambda **kw: {"MaximumEventAgeInSeconds": age},
            scan=lambda **kw: {"Items": [] if items is None else items},
            query=lambda **kw: {"Count": 0},
            get_queue_attributes=lambda **kw: {
                "Attributes": dict.fromkeys(kw["AttributeNames"], queue)
            },
        )
    )


def invoke_guard(bound, monkeypatch, **kwargs):
    monkeypatch.setattr(
        __import__("test_monitoring_closure"), "verify_live_manifest", lambda *a, **kw: None
    )
    module = tool("test_closure_guard")
    return module.guard(
        fake_session(**kwargs),
        bound.m,
        bound.snapshot,
        bound.review,
        bound.path,
        bound.digest,
        bound.private,
        now=10010,
        sleep=lambda _: None,
    )


def test_test_closure_approved_state_bound_success(bound, monkeypatch):
    inventory, expected, observation = invoke_guard(bound, monkeypatch)
    assert len(inventory) == 1 and expected == bound.after
    assert observation["closure_eligible"] is False  # Observations never manufacture approval.


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", "000000000000"),
        ("region", "us-east-1"),
        ("run_id", "other"),
        ("manifest_sha256", "b" * 64),
        ("expires_at_epoch", 10010),
        ("issued_at_epoch", 11000),
        ("alarm_count", 38),
        ("approved_by", "operator"),
        ("reviewed_evidence", {}),
    ],
)
def test_test_closure_rejects_wrong_stale_self_approved_evidence(bound, monkeypatch, field, value):
    bound.proof[field] = value
    bound.path, bound.digest = private_write(Path(bound.path), bound.proof)
    bound.review["output_changes"]["manifest"]["after"]["test_closure_evidence_sha256"] = (
        bound.digest
    )
    with pytest.raises(ValueError):
        invoke_guard(bound, monkeypatch)


@pytest.mark.parametrize(
    "field,value", [("lineage", "wrong"), ("serial", 8), ("version_id", "v8"), ("sha256", "b" * 64)]
)
def test_changed_authoritative_state_rejects_old_drain(bound, monkeypatch, field, value):
    bound.snapshot["identity"] = bound.snapshot["identity"] | {field: value}
    with pytest.raises(ValueError, match="StateBound"):
        invoke_guard(bound, monkeypatch)


@pytest.mark.parametrize("kwargs", [{"queue": "1"}, {"reserved": 2}, {"items": [{}]}])
def test_unknown_dlq_inflight_or_schema_is_fail_closed(bound, monkeypatch, kwargs):
    with pytest.raises((ValueError, KeyError, StorageFormatError)):
        invoke_guard(bound, monkeypatch, **kwargs)


@pytest.mark.parametrize("kind", ["evaluation", "future-dispatch", "unresolved-outcome"])
def test_strong_scan_finds_work_hidden_by_empty_gsi(bound, monkeypatch, runtime, kind):
    from dataclasses import replace

    from test_events import accepted

    from interview_backend.models.internal import Evaluation
    from interview_backend.repositories.codec import encode, to_wire

    message = accepted(runtime)
    snapshot = runtime.repository.snapshot()
    if kind == "future-dispatch":
        row = replace(next(iter(snapshot.dispatches.values())), next_at=9999999999999)
        native = encode("Dispatch", row, 0)
    elif kind == "evaluation":
        row = next(iter(snapshot.evaluations.values()))
        native = encode("Evaluation", row, 0)
    else:
        pending = next(iter(snapshot.evaluations.values()))
        row = Evaluation(
            owner=pending.owner,
            id=pending.id,
            attempt_id=pending.attempt_id,
            worker_state="terminal",
            status="failed",
            created_at=pending.created_at,
            deadline_at=pending.deadline_at,
            finished_at=pending.created_at + 10,
            failure_reason="OUTCOME_UNKNOWN",
            error={"code": "EVALUATION_FAILED", "message": "Evaluation could not be completed."},
        )
        native = encode("Evaluation", row, 0)
    assert message["evaluationId"] == row.id
    with pytest.raises(ValueError, match="ResidualIncludingFutureWork|UnresolvedOutcomeUnknown"):
        invoke_guard(bound, monkeypatch, items=[to_wire(native)])


def test_async_default_lifetime_and_fresh_boundary_evidence(bound, monkeypatch):
    with pytest.raises(ValueError, match="AsyncRetryWindow"):
        invoke_guard(bound, monkeypatch, age=21600)
    reference = bound.proof["reviewed_evidence"]["queue_ledger"]
    document = json.loads(Path(reference["path"]).read_text())
    document["observed_at_epoch"] = 9000
    reference["path"], reference["sha256"] = private_write(Path(reference["path"]), document)
    bound.path, bound.digest = private_write(Path(bound.path), bound.proof)
    with pytest.raises(ValueError, match="StaleDrainBoundary"):
        invoke_guard(bound, monkeypatch)


def test_strong_scan_pagination_never_treats_first_empty_page_as_drained(bound):
    module = tool("test_closure_guard")
    session = fake_session()
    client = session.client("dynamodb")
    cursor = {"PK": {"S": "synthetic"}, "SK": {"S": "page"}}
    pages = iter([{"Items": [], "LastEvaluatedKey": cursor}, {"Items": [{}]}])
    calls = []

    def scan(**kwargs):
        calls.append(kwargs)
        return next(pages)

    client.scan = scan
    original = session.client
    session.client = lambda name, **kw: client if name == "dynamodb" else original(name, **kw)
    with pytest.raises(StorageFormatError):
        module.verify_quiescent(session, bound.m, bound.proof, now=10010)
    assert len(calls) == 2 and all(c["ConsistentRead"] is True for c in calls)
    assert calls[1]["ExclusiveStartKey"] == cursor


@pytest.mark.parametrize("bad", ["extra", "missing", "replace", "unapproved", "baseline", "output"])
def test_test_closure_rejects_changes_outside_39_alarms(bound, bad):
    entries = bound.review["resource_changes"]
    if bad == "extra":
        entries.append({"address": "extra", "change": {}})
    elif bad == "missing":
        entries.pop()
    elif bad == "replace":
        entries[0]["change"]["actions"] = ["delete", "create"]
    elif bad == "unapproved":
        entries[-1]["change"].update(actions=["delete"], after=None)
    elif bad == "baseline":
        entries[-1]["change"]["after"] = {"name": "changed"}
    else:
        bound.review["output_changes"]["manifest"]["after"]["artifact"] = {}
    with pytest.raises(ValueError):
        tool("test_closure_guard").audit_plan(bound.review, bound.snapshot, bound.m)


@pytest.mark.parametrize("bad", [None, "failure", "readback", "state-change", "expired"])
def test_apply_rechecks_state_expiry_and_never_retries(bound, monkeypatch, bad):
    monkeypatch.setattr(
        __import__("test_monitoring_closure"), "verify_live_manifest", lambda *a, **kw: None
    )
    final = copy.deepcopy(bound.snapshot)
    final["identity"].update(serial=10, version_id="v10", sha256="b" * 64)
    final["manifest"] = bound.after
    final["state"]["resources"] = [final["state"]["resources"][-1]]
    sequence = [bound.snapshot, copy.deepcopy(bound.snapshot), final]
    if bad == "state-change":
        sequence[1]["identity"]["serial"] += 1
    if bad == "readback":
        final["manifest"] = bound.m
    calls = []

    def apply(review):
        calls.append(review)
        if bad == "failure":
            raise RuntimeError("SyntheticPartialFailure")

    driver = SimpleNamespace(
        session=fake_session(),
        sleep=lambda _: None,
        snapshot=lambda: sequence.pop(0),
        apply=apply,
        verify=lambda _: None,
    )
    module = tool("test_closure_guard")
    clock = iter([10010, 10900 if bad == "expired" else 10070])

    def execute():
        return module.apply_once(
            driver,
            bound.private,
            bound.m,
            bound.review,
            bound.path,
            bound.digest,
            bound.private,
            now=lambda: next(clock),
        )

    if bad:
        with pytest.raises((ValueError, RuntimeError)):
            execute()
        assert not (bound.private / "test-apply-completed.json").exists()
    else:
        execute()
        assert (bound.private / "test-apply-completed.json").exists()
    if calls:
        with pytest.raises(ValueError, match="AlreadyAttempted"):
            execute()
    assert len(calls) == (0 if bad in {"state-change", "expired"} else 1)


def test_reopen_requires_all39_before_enablement(bound):
    tool("test_closure_guard").require_reopen(bound.snapshot, enabling=True)
    bound.snapshot["state"]["resources"].pop(0)
    with pytest.raises(ValueError, match="RestoreAndReadback39"):
        tool("test_closure_guard").require_reopen(bound.snapshot, enabling=True)


@pytest.fixture
def retention(bound):
    module = tool("deployment_guards")
    entries = []
    for address in module.LOG_ADDRESSES:
        before = {"name": address, "retention_in_days": 14}
        entries.append(
            {
                "address": address,
                "type": "aws_cloudwatch_log_group",
                "change": {
                    "before": before,
                    "after": before | {"retention_in_days": 3},
                    "actions": ["update"],
                    "after_unknown": {},
                },
            }
        )
    bound.review = {"resource_changes": entries}
    proof = bound.proof | {
        "operation": "LOG_RETENTION_SHORTENING",
        "reviewed_by": "operator",
        "changes": module.retention_changes(bound.review),
        "impact_reviews": {},
    }
    for kind in ("incidents", "support", "audit"):
        path, digest = private_write(
            bound.private / (kind + ".json"),
            proof
            | {
                "domain": kind,
                "status": "PRESERVED_OR_NO_OPEN_ITEMS",
                "open_items": 0,
                "preserved_artifacts": [],
            },
        )
        proof["impact_reviews"][kind] = {"path": path, "sha256": digest}
    bound.proof = proof
    bound.path, bound.digest = private_write(bound.private / "retention.json", proof)
    return bound


@pytest.mark.parametrize(
    "bad",
    [None, "approval", "replace", "rename", "address", "missing", "review", "open", "artifact"],
)
def test_retention_shortening_requires_private_preservation_approval(retention, bad):
    module, f = tool("deployment_guards"), retention
    if bad == "approval":
        f.digest = "0" * 64
    elif bad in {"replace", "rename", "address", "missing"}:
        entry = f.review["resource_changes"][0]
        if bad == "replace":
            entry["change"]["actions"] = ["delete", "create"]
        elif bad == "rename":
            entry["change"]["after"]["name"] = "renamed"
        elif bad == "address":
            entry["address"] = "other"
        else:
            f.review["resource_changes"].pop()
    elif bad == "review":
        f.proof["impact_reviews"].pop("support")
        f.path, f.digest = private_write(Path(f.path), f.proof)
    elif bad in {"open", "artifact"}:
        reference = f.proof["impact_reviews"]["incidents"]
        doc = json.loads(Path(reference["path"]).read_text())
        doc["open_items"] = 1
        if bad == "artifact":
            file = f.private / "preserved.log"
            file.write_text("synthetic")
            doc["preserved_artifacts"] = [{"path": str(file), "sha256": "0" * 64}]
        reference["path"], reference["sha256"] = private_write(Path(reference["path"]), doc)
        f.path, f.digest = private_write(Path(f.path), f.proof)

    def action():
        return module.audit_retention(
            f.review, f.m, f.snapshot, f.path, f.digest, f.private, now=10010
        )

    if bad:
        with pytest.raises(ValueError):
            action()
    else:
        assert action() == f.digest


def test_retention_input_customer_to_developer_is_guarded():
    from test_p4_artifact_inputs import valid_inputs

    values = valid_inputs() | {"log_usage": "developer"}
    with pytest.raises(ValueError, match="ApprovedRetentionShortening"):
        tool("terraform_dev").validate_inputs(
            values,
            "123456789012",
            "ap-northeast-1",
            previous_configuration={"log_usage": "customer"},
        )
