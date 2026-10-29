"""API 2022-11-28 branch/tag boundaries; no network or policy relaxation."""

import copy

import pytest

from interview_backend.deployment import DeploymentError


def details():
    return {
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
        "can_admins_bypass": False,
        "protection_rules": [],
    }


def policies():
    # Both real Environment GETs on 2026-10-28 included type=branch.
    return {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]}


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_observed_policy_with_extra_api_metadata_is_accepted(monkeypatch, operation):
    import ci_identity
    import github_control

    name = "dev-" + operation
    monkeypatch.setattr(ci_identity, "standard_context", lambda env: name)
    rows = policies()
    rows["branch_policies"][0].update(id=123, node_id="SYNTHETIC")
    calls = []

    def get(suffix, env):
        calls.append(suffix)
        if suffix == "branches/main":
            return {"protected": True}
        if suffix == f"environments/{name}":
            return details()
        assert suffix == f"environments/{name}/deployment-branch-policies?per_page=100"
        return rows

    monkeypatch.setattr(github_control, "github_json", get)
    github_control.verify_dev_environment(
        {"P4_STANDARD_ACTIVE": "true", "P4_STANDARD_REVIEW_MODE": "manual"}
    )
    assert len(calls) == 3


@pytest.mark.parametrize("field", ["name", "type"])
def test_missing_name_or_type_is_rejected_instead_of_assuming_branch(field):
    from github_control import validate_branch_rules

    rows = policies()
    del rows["branch_policies"][0][field]
    with pytest.raises(DeploymentError, match="MainOnlyDevEnvironmentRequired"):
        validate_branch_rules(details(), rows)


@pytest.mark.parametrize("value", [None, False, 1, [], {}, "tag", "", "Branch"])
def test_wrong_branch_type_fails_closed(value):
    from github_control import validate_branch_rules

    rows = policies()
    rows["branch_policies"][0]["type"] = value
    with pytest.raises(DeploymentError, match="MainOnlyDevEnvironmentRequired"):
        validate_branch_rules(details(), rows)


@pytest.mark.parametrize(
    "rows",
    [
        {},
        {"total_count": 0, "branch_policies": []},
        {"total_count": 1, "branch_policies": []},
        {"total_count": "1", "branch_policies": [{"name": "main", "type": "branch"}]},
        {"total_count": 2, "branch_policies": [{"name": "main", "type": "branch"}]},
        {
            "total_count": 2,
            "branch_policies": [
                {"name": "main", "type": "branch"},
                {"name": "main", "type": "tag"},
            ],
        },
        {
            "total_count": 1,
            "branch_policies": [
                {"name": "main", "type": "branch"},
                {"name": "*", "type": "branch"},
            ],
        },
        {"total_count": 1, "branch_policies": [{"name": "*", "type": "branch"}]},
        {"total_count": 1, "branch_policies": [{"name": "refs/heads/main", "type": "branch"}]},
    ],
)
def test_incomplete_extra_or_wildcard_policies_are_rejected(rows):
    from github_control import validate_branch_rules

    with pytest.raises(DeploymentError, match="MainOnlyDevEnvironmentRequired"):
        validate_branch_rules(details(), rows)


@pytest.mark.parametrize("review_mode", ["manual", "reviewers"])
@pytest.mark.parametrize("fault", ["bypass", "unprotected", "missing-reviewer", "tag"])
def test_environment_protection_modes_fail_closed(monkeypatch, review_mode, fault):
    import ci_identity
    import github_control

    monkeypatch.setattr(ci_identity, "standard_context", lambda env: "dev-plan")
    environment = copy.deepcopy(details())
    environment["protection_rules"] = [
        {
            "type": "required_reviewers",
            "reviewers": [{"type": "User", "reviewer": {"id": 76547980}}],
        }
    ]
    rows = policies()
    branch = {"protected": True}
    if fault == "bypass":
        environment["can_admins_bypass"] = True
    elif fault == "unprotected":
        branch["protected"] = False
    elif fault == "tag":
        rows["branch_policies"][0]["type"] = "tag"
    else:
        environment["protection_rules"] = []

    def get(suffix, env):
        if suffix == "branches/main":
            return branch
        return rows if "deployment-branch-policies" in suffix else environment

    monkeypatch.setattr(github_control, "github_json", get)
    env = {"P4_STANDARD_ACTIVE": "true", "P4_STANDARD_REVIEW_MODE": review_mode}
    if fault == "missing-reviewer" and review_mode == "manual":
        github_control.verify_dev_environment(env)
    else:
        with pytest.raises(DeploymentError):
            github_control.verify_dev_environment(env)
