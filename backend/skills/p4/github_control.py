"""Read-only GitHub control-plane checks before requesting AWS credentials."""

import json
import re
import time
from urllib.error import HTTPError, URLError
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
        "GitHubEnvironmentHttpRejected",
        "GitHubEnvironmentTransportFailed",
        "GitHubRepositoryAuthenticationFailed",
        "GitHubRepositoryHttpRejected",
        "GitHubRepositoryNotFound",
        "GitHubRepositoryRateLimited",
        "GitHubRepositoryServiceUnavailable",
        "GitHubRepositoryRedirectRejected",
        "GitHubRepositoryResponseInvalid",
        "GitHubRepositoryTransportFailed",
    }
)
CAPABILITY_PHASES = frozenset(
    {
        "token-preflight",
        "repository-scope",
        "dev-plan-variables",
        "dev-apply-variables",
        "readiness",
    }
)


class CapabilityFailure(DeploymentError):
    """Safe diagnostic metadata only; admission still uses DeploymentError."""

    def __init__(self, reason: str, phase: str, http_status: int | None = None):
        super().__init__("GitHubControlPlaneUnavailable", reason_code=reason)
        self.failure_phase = phase
        self.http_status = http_status


def environment_failure(reason, phase="token-preflight", http_status=None):
    raise CapabilityFailure(reason, phase, http_status) from None


def capability_call(failure_phase, function, *args, **kwargs):
    """Retain the known API stage even for unexpected, non-stringified errors."""
    try:
        return function(*args, **kwargs)
    except CapabilityFailure:
        raise
    except Exception:
        environment_failure("UNKNOWN", failure_phase)


def environment_token(environment, phase="token-preflight"):
    """Conservative 55-minute deadline measured BEFORE the official action mints.

    The action exposes no expires_at output. GitHub installation tokens last one
    hour; this earlier local deadline cannot extend the server's expiration.
    Every request rechecks it, with a 30-second HTTP reserve. No token fallback.
    """
    if (
        environment.get("GITHUB_REPOSITORY") != REPOSITORY
        or environment.get("GITHUB_REPOSITORY_ID") != "1361325921"
    ):
        environment_failure("GitHubEnvironmentScopeMismatch", phase)
    token = environment.get("P4_ENV_READ_TOKEN", "")
    started = environment.get("P4_ENV_TOKEN_STARTED_AT", "")
    if (
        not isinstance(token, str)
        or not re.fullmatch(r"[A-Za-z0-9_]+", token)
        or not isinstance(started, str)
        or not re.fullmatch(r"[0-9]{1,12}", started)
    ):
        environment_failure("GitHubEnvironmentAuthenticationFailed", phase)
    now = time.time()
    if not int(started) <= now < int(started) + 3300 - 30:
        environment_failure("GitHubEnvironmentTokenExpired", phase)
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
    phase = "unknown"
    if variables and not re.fullmatch(
        r"environments/dev-(?:plan|apply)/variables\?per_page=30&page=(?:[1-9]|10)", suffix
    ):
        environment_failure("GitHubEnvironmentScopeMismatch")
    if variables:
        phase = suffix.split("/")[1] + "-variables"
    token = environment_token(environment, phase) if variables else environment["GH_TOKEN"]
    return request_json(
        f"https://api.github.com/repos/{REPOSITORY}/{suffix}", token, variables, phase=phase
    )


def rate_limit_evidence(error: HTTPError) -> bool:
    """Only bounded numeric header values; never inspect/log the response body."""
    try:
        remaining = error.headers.get("X-RateLimit-Remaining")
        retry_after = error.headers.get("Retry-After")
        return remaining == "0" or (
            type(retry_after) is str
            and re.fullmatch(r"[0-9]{1,10}", retry_after) is not None
            and int(retry_after) > 0
        )
    except Exception:
        return False


def request_json(url, token, variables=False, *, phase="unknown"):
    capability = variables or phase == "repository-scope"
    prefix = "GitHubEnvironment" if variables else "GitHubRepository"
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
        if capability:
            status = error.code if type(error.code) is int and 100 <= error.code <= 599 else None
            kind = {401: "AuthenticationFailed", 404: "NotFound", 429: "RateLimited"}.get(
                status, "HttpRejected"
            )
            if status is not None:
                if 300 <= status < 400:
                    kind = "RedirectRejected"
                elif 500 <= status < 600:
                    kind = "ServiceUnavailable"
                elif status == 403 and rate_limit_evidence(error):
                    kind = "RateLimited"
            environment_failure(prefix + kind, phase, status)
        raise DeploymentError("GitHubControlPlaneUnavailable") from None
    except URLError, OSError:
        if capability:
            environment_failure(prefix + "TransportFailed", phase)
        raise DeploymentError("GitHubControlPlaneUnavailable") from None
    except ValueError, UnicodeError:
        if capability:
            environment_failure(prefix + "ResponseInvalid", phase)
        raise DeploymentError("GitHubControlPlaneUnavailable") from None
    except Exception:
        if capability:
            environment_failure("UNKNOWN", phase)
        raise DeploymentError("GitHubControlPlaneUnavailable") from None


def environment_variables(name, environment):
    if name not in {"dev-plan", "dev-apply"}:
        environment_failure("GitHubEnvironmentScopeMismatch")
    phase = name + "-variables"
    variables, total = {}, None
    for page in range(1, VARIABLE_MAX_PAGES + 1):
        response = github_json(
            f"environments/{name}/variables?per_page={VARIABLE_PAGE_SIZE}&page={page}", environment
        )
        if not isinstance(response, dict):
            environment_failure("GitHubEnvironmentResponseInvalid", phase)
        count, rows = response.get("total_count"), response.get("variables")
        if (
            type(count) is not int
            or not 0 <= count <= VARIABLE_PAGE_SIZE * VARIABLE_MAX_PAGES
            or (total is not None and count != total)
            or not isinstance(rows, list)
            or len(rows) != min(VARIABLE_PAGE_SIZE, count - len(variables))
        ):
            environment_failure("GitHubEnvironmentResponseInvalid", phase)
        total = count
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("name"), str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", row["name"])
                or not isinstance(row.get("value"), str)
                or row["name"].upper() in variables
            ):
                environment_failure("GitHubEnvironmentResponseInvalid", phase)
            variables[row["name"].upper()] = row["value"]
        if len(variables) == total:
            return variables
    environment_failure("GitHubEnvironmentResponseInvalid", phase)


def verify_readiness(environment):
    operation = environment.get("P4_OPERATION")
    if operation not in {"plan", "apply"}:
        environment_failure("GitHubEnvironmentScopeMismatch", "readiness")
    for name in ("dev-plan", "dev-apply"):
        variables = capability_call(name + "-variables", environment_variables, name, environment)
        expected = "true" if name == "dev-" + operation else "false"
        if any(
            variables.get(key) != expected
            for key in ("P4_STANDARD_READY", "P4_AWS_EXECUTION_READY")
        ):
            environment_failure("GitHubEnvironmentReadinessMismatch", "readiness")


def verify_environment_access(environment):
    """GitHub-only capability gate, before any AWS credential request."""
    token = capability_call("token-preflight", environment_token, environment)
    result = capability_call(
        "repository-scope",
        request_json,
        "https://api.github.com/installation/repositories?per_page=30&page=1",
        token,
        phase="repository-scope",
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
        environment_failure("GitHubEnvironmentScopeMismatch", "repository-scope")
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


def capability_projection(error: Exception) -> dict:
    """No exception text, URLs, identifiers, bodies, tokens or header values."""
    phase, reason, status = "unknown", "UNKNOWN", None
    if type(error) is CapabilityFailure:
        try:
            if type(error.failure_phase) is str and error.failure_phase in CAPABILITY_PHASES:
                phase = error.failure_phase
            if type(error.reason_code) is str and error.reason_code in ENVIRONMENT_REASONS:
                reason = error.reason_code
            if type(error.http_status) is int and 100 <= error.http_status <= 599:
                status = error.http_status
        except Exception:
            phase, reason, status = "unknown", "UNKNOWN", None
    return {
        "schema_version": 1,
        "failure_phase": phase,
        "reason_code": reason,
        "http_status": status,
        "capability_result": "FAIL",
    }


def main(environment) -> int:
    try:
        verify_environment_access(environment)
        print("GitHubEnvironmentCapabilityPassed")
    except Exception as error:
        try:
            print(json.dumps(capability_projection(error), sort_keys=True))
        except Exception:
            pass  # Broken output sinks still fail closed without exception text.
        return 1
    return 0


if __name__ == "__main__":
    import os

    raise SystemExit(main(os.environ))
