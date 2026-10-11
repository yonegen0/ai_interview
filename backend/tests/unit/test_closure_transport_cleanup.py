"""Concrete transport safety: saved bytes, read-only snapshots and conditional keys."""

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_provider_validation_tools import tool

from interview_backend.repositories.codec import from_wire, to_wire


@pytest.mark.parametrize(
    "relative,staged",
    [
        ("backend/src/runtime.py", False),
        ("backend/skills/p4/helper.py", True),
        ("terraform/modules/service/main.tf", False),
        ("terraform/environments/dev/override.tf", False),
        ("backend/skills/p4/new_helper.py", False),
    ],
)
def test_clean_source_detects_changes_from_dev_subdirectory(tmp_path, monkeypatch, relative, staged):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "skills/p4"))
    module = tool("closure_aws")

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)

    for name in (
        "backend/src/runtime.py",
        "backend/skills/p4/helper.py",
        "terraform/modules/service/main.tf",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n")
    dev = tmp_path / "terraform/environments/dev"
    dev.mkdir(parents=True)
    git("init")
    git("add", ".")
    git(
        "-c",
        "user.name=Offline test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "base",
    )
    module.require_clean_source(dev, {})
    (tmp_path / relative).write_text("changed\n")
    if staged:
        git("add", relative)
    with pytest.raises(ValueError, match="CleanApprovedExecutionSourceRequired"):
        module.require_clean_source(dev, {})


def test_concrete_saved_plan_transport_rechecks_bytes(tmp_path, monkeypatch):
    tool("coaching_binding")
    module = tool("closure_aws")
    driver = object.__new__(module.TerraformAWS)
    driver.root, driver.env = tmp_path, {}
    calls = []
    review = {"resource_changes": []}

    def run(command, **kwargs):
        calls.append(command)
        if command[1] == "plan":
            Path(command[-1].removeprefix("-out=")).write_bytes(b"saved")
            return b""
        if command[1] == "show":
            return json.dumps(review).encode()
        return b""

    monkeypatch.setattr(module, "run", run)
    plan, result = driver.plan({"worker_enabled": False}, tmp_path)
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    driver.apply(plan, digest)
    assert result == review
    assert calls[-1] == ["terraform", "apply", "-input=false", "-lock-timeout=0s", str(plan)]
    plan.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SavedClosurePlanMismatch"):
        driver.apply(plan, digest)
    assert len(calls) == 3


@pytest.mark.parametrize(
    "bad", [None, "foreign-key", "changed-item", "processing", "wrong-account", "not-closed"]
)
def test_cleanup_only_approved_snapshot_keys_with_cas(tmp_path, bad):
    tool("coaching_binding")
    module = tool("cleanup_exact")
    run_id = "cleanup-" + uuid4().hex[:12]
    rows = [{"run_id": run_id, "evaluation_id": "e"}]
    native = {
        "PK": "USER#a",
        "SK": "EVALUATION#e",
        "kind": "Evaluation",
        "rev": 1,
        "data": json.dumps({"status": "processing" if bad == "processing" else "completed"}),
    }
    native = from_wire(to_wire(native))
    closed = tmp_path / "closed"
    raw_closed = json.dumps(
        {
            "status": "wrong" if bad == "not-closed" else "CLOSED_READBACK_VERIFIED",
            "active_lock": False,
            "state_outside_dev_resources": 0,
        }
    ).encode()
    closed.write_bytes(raw_closed)
    approved = {
        "PK": native["PK"],
        "SK": native["SK"],
        "rev": 1,
        "item_sha256": hashlib.sha256(
            json.dumps(native, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest(),
    }
    if bad == "foreign-key":
        approved["PK"] = "USER#other"
    if bad == "changed-item":
        approved["item_sha256"] = "0" * 64
    approval = {
        "cleanup_authorized": True,
        "closed_readback_verified": True,
        "table_name": "ai-interview-dev-main",
        "subject": "a",
        "run_id": run_id,
        "account_id": "123456789012",
        "region": "ap-northeast-1",
        "records": [approved],
        "closed_readback_path": str(closed),
        "closed_readback_sha256": hashlib.sha256(raw_closed).hexdigest(),
    }
    raw = json.dumps(approval).encode()
    deletes = []
    db = SimpleNamespace(
        get_item=lambda **kw: {"Item": to_wire(native)}, delete_item=lambda **kw: deletes.append(kw)
    )
    sts = SimpleNamespace(
        get_caller_identity=lambda: {
            "Account": "wrong" if bad == "wrong-account" else "123456789012"
        }
    )
    session = SimpleNamespace(client=lambda name, **kw: sts if name == "sts" else db)
    journal = Path(__file__).parents[2] / ".p4-artifacts" / (run_id + ".jsonl")
    if bad:
        with pytest.raises(ValueError):
            module.delete_approved(
                session,
                "ai-interview-dev-main",
                rows,
                "a",
                raw,
                hashlib.sha256(raw).hexdigest(),
                journal,
            )
        assert deletes == []
    else:
        assert (
            module.delete_approved(
                session,
                "ai-interview-dev-main",
                rows,
                "a",
                raw,
                hashlib.sha256(raw).hexdigest(),
                journal,
            )["deleted"]
            == 1
        )
        assert deletes[0]["ConditionExpression"] == "#r = :r AND #d = :d"
        assert from_wire(deletes[0]["Key"]) == {"PK": "USER#a", "SK": "EVALUATION#e"}
        with pytest.raises(FileExistsError):
            module.delete_approved(
                session,
                "ai-interview-dev-main",
                rows,
                "a",
                raw,
                hashlib.sha256(raw).hexdigest(),
                journal,
            )
        assert len(deletes) == 1


def test_runtime_receipts_use_exact_keys_and_keep_reclaim_unverified():
    tool("coaching_binding")
    module, live = tool("runtime_receipts"), tool("coaching_live")
    seen = []

    def get(**kwargs):
        native = from_wire(kwargs["Key"])
        seen.append(native)
        sk = native["SK"]
        kind = (
            "Evaluation"
            if sk.startswith("EVALUATION#")
            else "Dispatch"
            if sk.startswith("DISPATCH#")
            else "RecoveryCursor"
            if sk.startswith("CURSOR#")
            else "IdempotencyRecord"
        )
        data = (
            {"status": "completed"}
            if kind == "Evaluation"
            else {"status": "DONE", "delivery_attempts": 1}
        )
        return {"Item": to_wire(native | {"kind": kind, "rev": 1, "data": json.dumps(data)})}

    run = live.Run("runtime-offline")
    run.record("evaluation-created", evaluation_id="e")
    run.record("admin-add")
    run.record("admin-add-record", request_key=str(uuid4()))
    module.collect(
        SimpleNamespace(get_item=get),
        {"table_name": "synthetic"},
        {"subjects": {"USER_A": "a", "ADMIN": "admin"}},
        run,
        dict.fromkeys(module.PARTITIONS, 0),
    )
    assert any(
        r["check"] == "Recovery-checkpoint-transaction-observed" and r["status"] == "passed"
        for r in run.rows
    )
    assert run.rows[-2]["status"] == "not_run" and run.rows[-1]["status"] == "not_run"
    assert all(k["PK"] in {"USER#a", "SYSTEM#QUESTION_BANK", "SYSTEM#RECOVERY"} for k in seen)
    assert all(not k["SK"].startswith("CURSOR#WORK#") for k in seen)
