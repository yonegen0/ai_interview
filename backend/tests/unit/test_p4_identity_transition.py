"""Synthetic adoption and mocked recovery only; no Terraform or AWS execution."""

import copy
import io
import json
from types import SimpleNamespace

import pytest
from test_p4_recovery_migration import handoff  # noqa: F401


@pytest.fixture
def adoption(request):
    f = request.getfixturevalue("handoff")
    f.state["check_results"] = [
        {"object_kind": "resource", "config_addr": "a", "status": "pass", "objects": []},
        {"object_kind": "resource", "config_addr": "b", "status": "pass", "objects": []},
        {"object_kind": "resource", "config_addr": "a", "status": "pass", "objects": []},
    ]
    # The fixture handoff is unchanged: this helper's pure comparison tests use
    # an independent synthetic snapshot; integration tests use the bound backup.
    f.original = json.dumps(f.state).encode()
    f.destination = {"lineage": "synthetic-destination", "serial": 1}
    f.remote = json.dumps(f.state | f.destination).encode()
    f.record = {
        "schema_version": 1,
        "kind": "recovery-identity-adoption",
        "status": "REMOTE_STATE_OPERATIONAL_ADOPTED_READ_ONLY_VERIFIED",
        "terraform_version": "1.14.9",
        "workspace": "default",
        "recovery_handoff_sha256": f.m.hashed(f.path),
        "source_state_sha256": f.binding["state_sha256"],
        "source_identity": {"lineage": f.binding["lineage"], "serial": 34},
        "destination": f.binding["destination"],
        "destination_identity": f.destination,
    }
    f.adoption_path = f.write(f.run / "identity-adoption.private.json", f.record)
    return f


def test_explicit_adopted_transition_passes(adoption):
    f = adoption
    identity = f.m.load_adopted_identity(
        f.run, f.binding, f.m.hashed(f.path), f.m.hashed(f.adoption_path)
    )
    assert (
        f.m.bootstrap.compare_state_snapshot(f.original, f.remote, adopted_identity=identity)
        == "IDENTICAL"
    )


@pytest.mark.parametrize("serial,allowed", [(1, True), (2, True), (0, False)])
def test_serial_order_within_adopted_lineage(adoption, serial, allowed):
    f = adoption
    observed = json.dumps(json.loads(f.remote) | {"serial": serial}).encode()
    if allowed:
        assert (
            f.m.bootstrap.check_state_identity(observed, f.destination, allow_serial_advance=True)[
                "serial"
            ]
            == serial
        )
    else:
        with pytest.raises(f.m.DeploymentError):
            f.m.bootstrap.check_state_identity(observed, f.destination, allow_serial_advance=True)


def test_normal_operation_advances_canonical_serial_then_blocks_stale_state(adoption):
    f = adoption
    later = json.dumps(json.loads(f.remote) | {"serial": 2}).encode()
    canonical = f.m.bootstrap.check_state_identity(later, f.destination, allow_serial_advance=True)
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.check_state_identity(f.remote, canonical, allow_serial_advance=True)


def test_no_context_blocks_changed_identity(adoption):
    with pytest.raises(adoption.m.DeploymentError):
        adoption.m.bootstrap.compare_state_snapshot(adoption.original, adoption.remote)


def test_adopted_identity_blocks_source_rollback(adoption):
    f = adoption
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.compare_state_snapshot(f.original, f.original, adopted_identity=f.destination)
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.check_state_identity(f.original, f.destination, allow_serial_advance=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "attributes",
        "dependencies",
        "deposed",
        "outputs",
        "sensitive",
        "unknown",
        "version",
        "check_status",
        "check_duplicate",
        "nested_order",
        "bool_attribute",
    ],
)
def test_semantic_difference_blocks_even_approved_transition(adoption, mutation):
    f = adoption
    remote = json.loads(f.remote)
    inst = remote["resources"][0]["instances"][0]
    if mutation == "attributes":
        inst["attributes"]["id"] = "changed"
    elif mutation in {"dependencies", "deposed"}:
        inst[mutation] = ["changed"]
    elif mutation == "outputs":
        remote["outputs"]["state_bucket"]["value"] = "changed"
    elif mutation == "sensitive":
        remote["outputs"]["state_bucket"]["sensitive"] = True
    elif mutation == "unknown":
        remote["unknown_field"] = None
    elif mutation == "version":
        remote["version"] = 3
    elif mutation == "check_status":
        remote["check_results"][0]["status"] = "fail"
    elif mutation == "check_duplicate":
        remote["check_results"].pop()
    elif mutation == "nested_order":
        remote["check_results"][0]["objects"] = ["b", "a"]
    else:
        inst["attributes"]["id"] = True
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.compare_state_snapshot(
            f.original, json.dumps(remote).encode(), adopted_identity=f.destination
        )


def test_only_aggregate_order_is_benign_and_duplicates_preserved(adoption):
    f = adoption
    state = json.loads(f.remote)
    state["check_results"] = state["check_results"][1:] + state["check_results"][:1]
    assert (
        f.m.bootstrap.compare_state_snapshot(
            f.original, json.dumps(state).encode(), adopted_identity=f.destination
        )
        == "BENIGN_SERIALIZATION_DIFFERENCE"
    )
    # Equal length and equal set are insufficient: duplicate multiplicity matters.
    state["check_results"][1] = copy.deepcopy(state["check_results"][0])
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.compare_state_snapshot(
            f.original, json.dumps(state).encode(), adopted_identity=f.destination
        )


def test_nested_arrays_and_json_scalar_types_are_not_normalized(adoption):
    f = adoption
    source = json.loads(f.original)
    source["check_results"][0]["objects"] = ["a", "b"]
    remote = copy.deepcopy(source) | f.destination
    remote["check_results"][0]["objects"].reverse()
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.compare_state_snapshot(
            json.dumps(source).encode(), json.dumps(remote).encode(), adopted_identity=f.destination
        )
    source["outputs"]["test"] = {"value": 1}
    remote = copy.deepcopy(source) | f.destination
    remote["outputs"]["test"]["value"] = True
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.compare_state_snapshot(
            json.dumps(source).encode(), json.dumps(remote).encode(), adopted_identity=f.destination
        )


def test_verification_does_not_allow_even_forward_serial_change(adoption):
    f = adoption
    later = json.dumps(json.loads(f.remote) | {"serial": 2}).encode()
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.compare_state_snapshot(f.remote, later)


@pytest.mark.parametrize(
    "field,value",
    [
        ("recovery_handoff_sha256", "wrong"),
        ("source_state_sha256", "wrong"),
        ("status", "pending"),
        ("terraform_version", "1.14.8"),
        ("workspace", "dev"),
        ("destination", {}),
        ("source_identity", {"lineage": "other", "serial": 34}),
        ("destination_identity", {"lineage": "synthetic-B", "serial": 1}),
        ("destination_identity", {"lineage": "new", "serial": True}),
        ("destination_identity", {"lineage": "new", "serial": 2}),
    ],
)
def test_rehashed_but_wrong_adoption_binding_blocked(adoption, field, value):
    f = adoption
    f.record[field] = value
    f.write(f.adoption_path, f.record)
    with pytest.raises(f.m.DeploymentError):
        f.m.load_adopted_identity(f.run, f.binding, f.m.hashed(f.path), f.m.hashed(f.adoption_path))


@pytest.mark.parametrize("approval", [None, "0" * 64])
def test_marker_requires_explicit_correct_approval(adoption, approval):
    f = adoption
    with pytest.raises(f.m.DeploymentError, match="ApprovedIdentityAdoptionRequired"):
        f.m.load_adopted_identity(f.run, f.binding, f.m.hashed(f.path), approval)


def test_adopted_migration_rejected_before_external_calls(adoption, monkeypatch):
    f = adoption
    monkeypatch.setattr(f.m.bootstrap, "migration_target", lambda *a, **k: pytest.fail("AWS"))
    with pytest.raises(f.m.DeploymentError, match="AdoptedStateMigrationForbidden"):
        f.m.bootstrap.migrate_state(f.run, {}, f.run / "terraform.tfstate", "bucket", "a", "r")
    with pytest.raises(f.m.DeploymentError, match="AdoptedStateVerifyOnly"):
        f.m.execute("migrate", f.path, f.m.hashed(f.path), adoption_hash="approved")
    for operation in ("inspect", "migrate", "verify", "apply", "replan"):
        with pytest.raises(f.m.DeploymentError, match="RecoveryIdentityAdoptionRequired"):
            f.m.bootstrap.operation_allowed(str(f.run), operation)


@pytest.mark.parametrize(
    "failure", [None, "rollback", "unknown_identity", "content", "version", "serial", "pull"]
)
def test_recovery_uses_destination_before_and_after_plan(adoption, monkeypatch, failure):
    f = adoption
    original = f.files["backup"].read_bytes()
    remote = json.dumps(json.loads(original) | f.destination).encode()
    (f.run / "pre-migration.tfstate").write_bytes(original)
    f.write(f.run / "migration-attempt.json", {"recovery_handoff_sha256": f.m.hashed(f.path)})
    monkeypatch.setattr(f.m, "inspect", lambda *a, **k: (f.binding, f.state, f.run, {}, None))
    monkeypatch.setattr(f.m, "validate_handoff", lambda *a, **k: None)
    monkeypatch.setattr(f.m.bootstrap, "prerequisites", lambda *a: None)
    monkeypatch.setattr(f.m.bootstrap, "checked_source", lambda *a: "synthetic")
    calls = []

    def readback(session, bucket, account, baseline, **options):
        calls.append(baseline)
        if len(calls) == 1:
            assert options == {"adopted_identity": f.destination}
            assert baseline == original
            return "synthetic-version", remote
        assert baseline == remote and options == {}
        if failure == "rollback":
            return "synthetic-version", original
        changed = json.loads(remote)
        if failure == "unknown_identity":
            changed["lineage"] = "unapproved"
        elif failure == "content":
            changed["outputs"] = {}
        elif failure == "serial":
            changed["serial"] = 2
        return (
            "changed-version" if failure == "version" else "synthetic-version",
            json.dumps(changed).encode(),
        )

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        assert "apply" not in command and "init" not in command
        if command[0] == "git":
            return b"synthetic"
        if command[1:3] == ["state", "pull"]:
            return original if failure == "pull" else remote
        if command[1] == "plan":
            (f.run / "migration-normal.tfplan").write_bytes(b"synthetic-plan")
            return b""
        assert command[1] == "show"
        return b'{"resource_changes": [], "output_changes": {}}'

    monkeypatch.setattr(f.m.bootstrap, "verify_state_version", readback)
    monkeypatch.setattr(f.m.bootstrap, "run", fake_run)
    immutable = {p: p.read_bytes() for p in (f.path, f.adoption_path, f.files["backup"])}
    if failure:
        with pytest.raises(f.m.DeploymentError):
            f.m.execute(
                "verify", f.path, f.m.hashed(f.path), adoption_hash=f.m.hashed(f.adoption_path)
            )
        assert not (f.run / "migration-receipt.json").exists()
        if failure == "pull":
            assert not any(c[1] == "plan" for c in commands)
    else:
        f.m.execute("verify", f.path, f.m.hashed(f.path), adoption_hash=f.m.hashed(f.adoption_path))
        receipt = f.m.read(f.run / "migration-receipt.json")
        assert receipt["destination_identity"] == f.destination
        assert receipt["source_identity"]["serial"] == 34
    assert all(p.read_bytes() == raw for p, raw in immutable.items())


def test_version_pinned_s3_readback_uses_approved_identity(adoption):
    f = adoption
    calls = []

    def get(**kwargs):
        calls.append(kwargs)
        return {
            "VersionId": "current",
            "ServerSideEncryption": "AES256",
            "Body": io.BytesIO(f.remote),
        }

    client = SimpleNamespace(head_object=lambda **k: {"VersionId": "current"}, get_object=get)
    session = SimpleNamespace(client=lambda *a: client)
    assert f.m.bootstrap.verify_state_version(
        session, "synthetic-bucket", f.account, f.original, adopted_identity=f.destination
    ) == ("current", f.remote)
    assert calls[0]["VersionId"] == "current"
    with pytest.raises(f.m.DeploymentError):
        f.m.bootstrap.verify_state_version(session, "synthetic-bucket", f.account, f.original)
