"""Unmerged PR B consistency; passing never releases the adoption HOLD."""

from pathlib import Path

import pytest
from test_p4_tools import tool


def test_six_candidate_scopes_and_official_generated_locks_agree():
    root = Path(__file__).resolve().parents[3]
    migration = tool("toolchain_migration")
    expected = tool("cloud_toolchain").NEW_EXECUTION_TERRAFORM_VERSION
    locks = []
    for scope, (filename, _) in migration.SCOPES.items():
        directory = root / "terraform" / scope
        text = (directory / filename).read_text()
        assert f'required_version = "= {expected}"' in text
        assert 'aws = { source = "hashicorp/aws", version = "= 6.70.0" }' in text
        selected = tool("offline_terraform").parse_lock(
            (directory / ".terraform.lock.hcl").read_text()
        )
        assert set(selected) == {migration.AWS}
        assert selected[migration.AWS]["version"] == "6.70.0"
        assert selected[migration.AWS]["constraints"] == "6.70.0"
        assert sum(value.startswith("h1:") for value in selected[migration.AWS]["hashes"]) >= 2
        locks.append(selected)
    assert all(value == locks[0] for value in locks)


def test_candidate_workflow_qualifies_explicit_legacy_source_without_aws_permission():
    root = Path(__file__).resolve().parents[3]
    text = (root / ".github/workflows/p4-toolchain-qualification.yml").read_text()
    assert "ref: 7ec3595aa02c5315f6d7600282b428d294d3d771" in text
    assert "--repository migration-baseline" in text
    assert "--candidate-repository ." in text
    expected = tool("cloud_toolchain").NEW_EXECUTION_TERRAFORM_VERSION
    assert f"--checkout-candidate {expected}" in text
    assert "--compare-provider-schemas" in text
    assert "id-token:" not in text and "environment:" not in text
    assert "workflow_dispatch:" not in text


@pytest.mark.parametrize(
    "change", ["old-cli", "other-cli", "windows", "arm64", "missing-platform", "format"]
)
def test_new_execution_contract_rejects_other_toolchains_before_authentication(change):
    m = tool("cloud_toolchain")
    value = {"terraform_version": "1.16.7", "platform": "linux_amd64"}
    m.assert_execution_version(value)
    if change == "old-cli":
        value["terraform_version"] = "1.14.9"
    elif change == "other-cli":
        value["terraform_version"] = "1.17.0"
    elif change == "windows":
        value["platform"] = "windows_amd64"
    elif change == "arm64":
        value["platform"] = "linux_arm64"
    elif change == "missing-platform":
        del value["platform"]
    else:
        value["format_version"] = "2.0"
    with pytest.raises(ValueError, match="CloudTerraformVersionMismatch"):
        m.assert_execution_version(value)


def test_fresh_plan_binding_requires_new_runtime_platform_and_rejects_legacy_binding(tmp_path):
    m = tool("terraform_dev")
    (tmp_path / ".terraform.lock.hcl").write_bytes(b"synthetic-lock-not-for-execution")
    inputs = tmp_path / "inputs.json"
    inputs.write_bytes(b"{}")
    expected = m.bind_plan(tmp_path, "123456789012", "ap-northeast-1", "a" * 40, inputs)
    assert expected["terraform_version"] == "1.16.7"
    assert expected["terraform_platform"] == "linux_amd64"
    plan = tmp_path / "synthetic-plan"
    plan.write_bytes(b"synthetic-plan-not-for-execution")
    actual = expected | {"plan_sha256": m.digest(plan)}
    m.assert_binding(actual, expected, plan, m.digest(plan))
    for changed in (
        {key: value for key, value in actual.items() if key != "terraform_platform"},
        actual | {"terraform_platform": "windows_amd64"},
        actual | {"terraform_version": "1.14.9"},
    ):
        with pytest.raises(ValueError, match="SavedPlanMismatch"):
            m.assert_binding(changed, expected, plan, m.digest(plan))


@pytest.mark.parametrize("failure", [None, "iam", "inventory", "changed-during-check"])
def test_actual_candidate_checkout_comparison_fails_closed_without_mutation(
    tmp_path, monkeypatch, failure
):
    from test_toolchain_migration import configurations

    m, before, after = configurations()
    roots = [tmp_path / "baseline", tmp_path / "candidate"]
    snapshots = [dict.fromkeys(config, "synthetic") for config in (before, after)]
    for root, config in zip(roots, (before, after), strict=True):
        for name, raw in config.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if failure == "iam":
        (roots[1] / "terraform/bootstrap/iam.tf").write_bytes(b"unapproved change")
    elif failure == "inventory":
        snapshots[1]["terraform/bootstrap/terraform.tfstate"] = "never-read"
    reads = []

    def snapshot(root):
        reads.append(root)
        if failure == "changed-during-check" and len(reads) > 2:
            return {}
        return snapshots[roots.index(root)]

    monkeypatch.setattr(m, "tracked_snapshot", snapshot)
    if failure:
        with pytest.raises(ValueError):
            m.verify_candidate_checkout(*roots, "1.16.7")
    else:
        m.verify_candidate_checkout(*roots, "1.16.7")
        assert len(reads) == 4
    assert all((roots[0] / name).read_bytes() == raw for name, raw in before.items())
