"""Read-only GitHub control-plane checks before requesting AWS credentials."""

import json
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from ci_identity import NoRedirect

from interview_backend.deployment import DeploymentError

REPOSITORY = "yonegen0/ai_interview"
VARIABLE_PAGE_SIZE = 30
VARIABLE_MAX_PAGES = 10
ENVIRONMENT_REASONS = frozenset(
    {
        "GitHubEnvironmentAuthenticationFailed",
        "GitHubEnvironmentVariablesReadDenied",
        "GitHubEnvironmentNotFound",
        "GitHubEnvironmentRateLimited",
        "GitHubEnvironmentServiceUnavailable",
        "GitHubEnvironmentRedirectRejected",
        "GitHubEnvironmentResponseInvalid",
        "GitHubEnvironmentTokenExpired",
        "GitHubEnvironmentScopeMismatch",
        "GitHubEnvironmentReadinessMismatch",
    }
)


def environment_failure(reason):
    raise DeploymentError("GitHubControlPlaneUnavailable", reason_code=reason) from None


def environment_token(environment):
    """Conservative 55-minute deadline measured BEFORE the official action mints.

    The action exposes no expires_at output. GitHub installation tokens last one
    hour; this earlier local deadline cannot extend the server's expiration.
    Every request rechecks it, with a 30-second HTTP reserve. No token fallback.
    """
    if (
        environment.get("GITHUB_REPOSITORY") != REPOSITORY
        or environment.get("GITHUB_REPOSITORY_ID") != "1361325921"
    ):
        environment_failure("GitHubEnvironmentScopeMismatch")
    token = environment.get("P4_ENV_READ_TOKEN", "")
    started = environment.get("P4_ENV_TOKEN_STARTED_AT", "")
    if (
        not isinstance(token, str)
        or not re.fullmatch(r"[A-Za-z0-9_]+", token)
        or not isinstance(started, str)
        or not re.fullmatch(r"[0-9]{1,12}", started)
    ):
        environment_failure("GitHubEnvironmentAuthenticationFailed")
    now = time.time()
    if not int(started) <= now < int(started) + 3300 - 30:
        environment_failure("GitHubEnvironmentTokenExpired")
    return token


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def github_json(suffix, environment):
    variables = "variables" in suffix
    if variables and not re.fullmatch(
        r"environments/dev-(?:plan|apply)/variables\?per_page=30&page=(?:[1-9]|10)", suffix
    ):
        environment_failure("GitHubEnvironmentScopeMismatch")
    token = environment_token(environment) if variables else environment["GH_TOKEN"]
    return request_json(f"https://api.github.com/repos/{REPOSITORY}/{suffix}", token, variables)


def request_json(url, token, variables=False):
    request = Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1048577)
            if len(raw) > 1048576:
                raise ValueError
            value = json.loads(raw, object_pairs_hook=unique_object)
            if not isinstance(value, dict):
                raise ValueError
            return value
    except HTTPError as error:
        reason = "GitHubControlPlaneUnavailable"
        if variables:
            reason = {
                401: "GitHubEnvironmentAuthenticationFailed",
                403: "GitHubEnvironmentVariablesReadDenied",
                404: "GitHubEnvironmentNotFound",
                429: "GitHubEnvironmentRateLimited",
            }.get(error.code, reason)
            if 300 <= error.code < 400:
                reason = "GitHubEnvironmentRedirectRejected"
            elif 500 <= error.code < 600:
                reason = "GitHubEnvironmentServiceUnavailable"
        raise DeploymentError("GitHubControlPlaneUnavailable", reason_code=reason) from None
    except Exception:
        if variables:
            environment_failure("GitHubEnvironmentResponseInvalid")
        raise DeploymentError("GitHubControlPlaneUnavailable") from None


def environment_variables(name, environment):
    if name not in {"dev-plan", "dev-apply"}:
        environment_failure("GitHubEnvironmentScopeMismatch")
    variables, total = {}, None
    for page in range(1, VARIABLE_MAX_PAGES + 1):
        response = github_json(
            f"environments/{name}/variables?per_page={VARIABLE_PAGE_SIZE}&page={page}", environment
        )
        if not isinstance(response, dict):
            environment_failure("GitHubEnvironmentResponseInvalid")
        count, rows = response.get("total_count"), response.get("variables")
        if (
            type(count) is not int
            or not 0 <= count <= VARIABLE_PAGE_SIZE * VARIABLE_MAX_PAGES
            or (total is not None and count != total)
            or not isinstance(rows, list)
            or len(rows) != min(VARIABLE_PAGE_SIZE, count - len(variables))
        ):
            environment_failure("GitHubEnvironmentResponseInvalid")
        total = count
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("name"), str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", row["name"])
                or not isinstance(row.get("value"), str)
                or row["name"].upper() in variables
            ):
                environment_failure("GitHubEnvironmentResponseInvalid")
            variables[row["name"].upper()] = row["value"]
        if len(variables) == total:
            return variables
    environment_failure("GitHubEnvironmentResponseInvalid")


def verify_readiness(environment):
    operation = environment.get("P4_OPERATION")
    if operation not in {"plan", "apply"}:
        environment_failure("GitHubEnvironmentScopeMismatch")
    for name in ("dev-plan", "dev-apply"):
        variables = environment_variables(name, environment)
        expected = "true" if name == "dev-" + operation else "false"
        if any(
            variables.get(key) != expected
            for key in ("P4_STANDARD_READY", "P4_AWS_EXECUTION_READY")
        ):
            environment_failure("GitHubEnvironmentReadinessMismatch")


def verify_environment_access(environment):
    """GitHub-only capability gate, before any AWS credential request."""
    token = environment_token(environment)
    result = request_json(
        "https://api.github.com/installation/repositories?per_page=30&page=1", token, True
    )
    rows = result.get("repositories")
    if (
        type(result.get("total_count")) is not int
        or result["total_count"] != 1
        or not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
        or type(rows[0].get("id")) is not int
        or rows[0]["id"] != 1361325921
        or rows[0].get("full_name") != REPOSITORY
    ):
        environment_failure("GitHubEnvironmentScopeMismatch")
    verify_readiness(environment)


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


if __name__ == "__main__":
    import os

    try:
        verify_environment_access(os.environ)
    except Exception:
        raise SystemExit("GitHubEnvironmentCapabilityRefused") from None
    print("GitHubEnvironmentCapabilityPassed")
