"""Read-only GitHub control-plane checks before requesting AWS credentials."""

import json
from urllib.request import Request, build_opener

from ci_identity import NoRedirect

from interview_backend.deployment import DeploymentError

REPOSITORY = "yonegen0/ai_interview"


def github_json(suffix, environment):
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/{suffix}",
        headers={
            "Authorization": "Bearer " + environment["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1048577)
            if len(raw) > 1048576:
                raise ValueError
            return json.loads(raw)
    except Exception:
        raise DeploymentError("GitHubControlPlaneUnavailable") from None


def validate_branch_rules(environment_details, policies):
    required = {"protected_branches": False, "custom_branch_policies": True}
    policy = environment_details.get("deployment_branch_policy")
    branches = policies.get("branch_policies", [])
    if (
        policy != required
        or policies.get("total_count") != 1
        or len(branches) != 1
        or branches[0].get("name") != "main"
        or branches[0].get("type") != "branch"
    ):
        raise DeploymentError("MainOnlyDevEnvironmentRequired")


def verify_dev_environment(environment):
    name = "dev"
    if environment.get("P4_STANDARD_ACTIVE") == "true":
        from ci_identity import standard_context

        name = standard_context(environment)
    details = github_json(f"environments/{name}", environment)
    policies = github_json(
        f"environments/{name}/deployment-branch-policies?per_page=100", environment
    )
    validate_branch_rules(details, policies)
    if name != "dev":
        branch = github_json("branches/main", environment)
        if branch.get("protected") is not True:
            raise DeploymentError("StandardProtectedMainRequired")
        if details.get("can_admins_bypass") is not False:
            raise DeploymentError("StandardEnvironmentBypassForbidden")
        if environment.get("P4_STANDARD_REVIEW_MODE") == "reviewers" and not any(
            rule.get("type") == "required_reviewers"
            and any(
                reviewer.get("type") == "User"
                and reviewer.get("reviewer", {}).get("id") == 76547980
                for reviewer in rule.get("reviewers", [])
            )
            for rule in details.get("protection_rules", [])
        ):
            raise DeploymentError("StandardRequiredReviewerMissing")
