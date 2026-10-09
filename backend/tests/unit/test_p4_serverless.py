"""Independent serverless monitoring, cost-input and package-change contracts."""

import copy
import subprocess
from pathlib import Path

import pytest
from test_p4_artifact_inputs import valid_inputs
from test_p4_tools import manifest, tool

FLAGS = ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
ACTIVE_NAMES = {
    "api-Errors",
    "api-Throttles",
    "worker-Errors",
    "worker-Throttles",
    "dispatcher-Errors",
    "dispatcher-Throttles",
    "api-IntegrityError",
    "worker-IntegrityError",
    "dispatcher-IntegrityError",
    "OutcomeUnknown",
    "RecoveryHeartbeat",
    "RecoverySweepLag",
    "dlq-worker",
    "dlq-stream",
}


@pytest.fixture(autouse=True)
def tools_import_path(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))


@pytest.mark.parametrize("enabled", [None, *FLAGS, "all"])
def test_dev_alarm_contract(enabled):
    m = manifest()
    m["environment"] = "dev"
    m["alarm_topic_arn"] = "synthetic-topic"
    m["configuration"].update({key: enabled in (key, "all") for key in FLAGS})
    alarms = tool("manifest_alarms").expected_alarms(m, "dev")
    assert set(alarms) == ({"dev-" + n for n in ACTIVE_NAMES} if enabled else set())
    for name, alarm in alarms.items():
        assert alarm["AlarmActions"] == ["synthetic-topic"]
        assert alarm["EvaluationPeriods"] == (3 if name.endswith("Heartbeat") else 1)
        assert alarm["Threshold"] == (180 if name.endswith("SweepLag") else 1)
        assert alarm["Period"] == (
            300
            if name.removeprefix("dev-").split("-")[0] in {"api", "worker", "dispatcher"}
            else 60
        )
        if name.endswith(("Heartbeat", "SweepLag")):
            assert alarm["ActionsEnabled"] == m["configuration"]["scheduler_enabled"]


def test_test_environment_retains_full_monitoring():
    m = manifest()
    m["environment"] = "test"
    m["alarm_topic_arn"] = "synthetic-topic"
    m["configuration"].update({key: False for key in FLAGS})
    alarms = tool("manifest_alarms").expected_alarms(m, "test")
    assert len(alarms) == 32
    assert alarms["test-PendingAge"]["Threshold"] == 120
    assert alarms["test-iterator-age"]["Threshold"] == 120000
    assert alarms["test-failure-rate"]["Threshold"] == 20
    assert alarms["test-RecoverySweepLag"]["ActionsEnabled"] is True


@pytest.mark.parametrize("amount", ["10", "10.0", "10.00"])
def test_usd_input_and_original_preserved(amount):
    values = valid_inputs()
    del values["jpy_per_usd"], values["budget_rate_date"]
    values["monthly_budget_usd"] = amount
    original = copy.deepcopy(values)
    result = tool("terraform_dev").validate_inputs(values, "123456789012", "ap-northeast-1")
    assert result["monthly_budget_usd"] == "10.00"
    assert values == original


@pytest.mark.parametrize(
    "amount", ["0", "-1", "NaN", "Infinity", "1e1", "1.001", True, 10, " 10", "10\n"]
)
def test_invalid_usd(amount):
    values = valid_inputs()
    del values["jpy_per_usd"], values["budget_rate_date"]
    values["monthly_budget_usd"] = amount
    with pytest.raises(ValueError, match="InvalidMonthlyBudget"):
        tool("terraform_dev").validate_inputs(values, "123456789012", "ap-northeast-1")


def test_mixed_and_missing_budget_rejected():
    values = valid_inputs()
    values["monthly_budget_usd"] = "10.00"
    for data in (
        values,
        {
            k: v
            for k, v in values.items()
            if k not in {"monthly_budget_usd", "jpy_per_usd", "budget_rate_date"}
        },
    ):
        with pytest.raises(ValueError, match="ExplicitDeploymentInputsRequired"):
            tool("terraform_dev").validate_inputs(data, "123456789012", "ap-northeast-1")


def test_package_change_detection_over_multiple_commits(tmp_path):
    module = tool("package_changes")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Synthetic")
    git("config", "user.email", "synthetic@example.invalid")
    (tmp_path / "initial").write_text("initial")
    git("add", ".")
    git("commit", "-m", "initial")
    base = git("rev-parse", "HEAD")
    runtime = tmp_path / "backend/src/application.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("# synthetic")
    git("add", ".")
    git("commit", "-m", "runtime")
    middle = git("rev-parse", "HEAD")
    (tmp_path / "docs.md").write_text("docs")
    git("add", ".")
    git("commit", "-m", "docs")
    head = git("rev-parse", "HEAD")
    assert module.decision(tmp_path, {"before": base}, "push", head)["build_package"]
    assert not module.decision(tmp_path, {"before": middle}, "push", head)["build_package"]
    assert module.decision(
        tmp_path, {"pull_request": {"base": {"sha": base}}}, "pull_request", head
    )["build_package"]
    assert not module.decision(tmp_path, {}, "workflow_dispatch", head, middle)["build_package"]
    with pytest.raises(ValueError, match="BaseRequired"):
        module.decision(tmp_path, {}, "workflow_dispatch", head)
    with pytest.raises(subprocess.CalledProcessError):
        module.decision(tmp_path, {"before": "a" * 40}, "push", head)
    git("mv", "backend/src/application.py", "renamed-doc.md")
    git("commit", "-m", "move runtime outside package")
    renamed_head = git("rev-parse", "HEAD")
    assert module.decision(tmp_path, {"before": head}, "push", renamed_head)["build_package"]


@pytest.mark.parametrize("invalid", [None, "created", "deleted", "after", "missing_head"])
def test_new_branch_runs_full_package_without_guessing_base(tmp_path, invalid):
    module = tool("package_changes")
    for args in (
        ("init",),
        ("config", "user.name", "Synthetic"),
        ("config", "user.email", "synthetic@example.invalid"),
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "docs.md").write_text("docs-only new branch must still verify package")
    subprocess.run(["git", "add", "docs.md"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "synthetic"], cwd=tmp_path, check=True, capture_output=True
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    event = {"before": "0" * 40, "created": True, "deleted": False, "after": head}
    if invalid == "created":
        event["created"] = False
    elif invalid == "deleted":
        event["deleted"] = True
    elif invalid == "after":
        event["after"] = "a" * 40
    elif invalid == "missing_head":
        head = event["after"] = "a" * 40
    if invalid:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            module.decision(tmp_path, event, "push", head)
    else:
        assert module.decision(tmp_path, event, "push", head) == {
            "base": None,
            "head": head,
            "build_package": True,
            "reason": "new_branch_full_package_verification",
        }
