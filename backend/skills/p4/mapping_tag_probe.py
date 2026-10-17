"""Approval-bound, finite OIDC ListTags probe. No Terraform or AWS mutations."""

import base64
import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ACCOUNT = "835384817629"
REGION = "ap-northeast-1"
REPOSITORY = "yonegen0/ai_interview"
WORKFLOW = ".github/workflows/p4-mapping-tag-probe.yml"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ai-interview-ci-plan"
ARN_PATTERN = re.compile(
    r"arn:aws:lambda:ap-northeast-1:835384817629:event-source-mapping:[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
)


def require(value):
    if not value:
        raise ValueError("ProbeBindingRejected")


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(raw, expected, env, root, now):
    require(re.fullmatch("[0-9a-f]{64}", expected) and digest(raw) == expected)
    p = json.loads(raw, object_pairs_hook=unique)
    require(
        set(p)
        == {
            "schema",
            "kind",
            "issued_at_utc",
            "expires_at_utc",
            "source_sha",
            "oidc_subject",
            "mapping_arns",
            "files",
            "repair_after_sha256",
            "consent_sha256",
            "dispatch_max",
            "run_attempt",
        }
    )
    require(p["schema"] == 1 and p["kind"] == "PR17_EXACT_MAPPING_LISTTAGS_ONLY")
    require(p["dispatch_max"] == 1 and p["run_attempt"] == 1)
    require(re.fullmatch("[0-9a-f]{64}", p["consent_sha256"]))
    require(
        p["repair_after_sha256"]
        == "68652441b97806d050c5cc48158d24ea9873f71524d0150775018168fa4dca17"
    )
    issued, expiry = [
        datetime.fromisoformat(p[k].replace("Z", "+00:00"))
        for k in ("issued_at_utc", "expires_at_utc")
    ]
    require(issued.utcoffset() == timedelta(0) and expiry.utcoffset() == timedelta(0))
    require(
        expiry - issued == timedelta(hours=72) and issued <= now < expiry - timedelta(minutes=10)
    )
    require(
        env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    )
    require(
        env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_REF") == "refs/heads/main"
    )
    require(
        env.get("GITHUB_RUN_ATTEMPT") == "1"
        and re.fullmatch("[0-9]+", env.get("GITHUB_RUN_ID", ""))
    )
    require(env.get("P4_AWS_EXECUTION_READY") == "false")
    require(
        re.fullmatch("[0-9a-f]{40}", p["source_sha"]) and env.get("GITHUB_SHA") == p["source_sha"]
    )
    require(env.get("GITHUB_WORKFLOW_REF") == f"{REPOSITORY}/{WORKFLOW}@refs/heads/main")
    require(
        re.fullmatch(
            r"repo:yonegen0(@[0-9]+)?/ai_interview(@[0-9]+)?:environment:dev", p["oidc_subject"]
        )
    )
    arns = p["mapping_arns"]
    require(type(arns) is list and len(arns) == 2 and len(set(arns)) == 2)
    require(all(type(a) is str and ARN_PATTERN.fullmatch(a) for a in arns))
    require(
        digest(json.dumps(sorted(arns), separators=(",", ":")).encode())
        == "49dde7df52f03bef7c8affa1e4a8c5c0a3d233dd554618ac6a9fbba7d614db91"
    )
    required_files = {
        WORKFLOW,
        "backend/skills/p4/mapping_tag_probe.py",
        "backend/pyproject.toml",
        "backend/uv.lock",
        ".github/actions/finite-artifact/action.yml",
        ".github/actions/finite-artifact/publish.cjs",
    }
    require(set(p["files"]) == required_files)
    for path, sha in p["files"].items():
        require(re.fullmatch("[0-9a-f]{64}", sha) and digest((root / path).read_bytes()) == sha)
    return p, expiry


def claims(token, p, env, now):
    payload = token.split(".")[1]
    c = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)), object_pairs_hook=unique
    )
    require(
        c["iss"] == "https://token.actions.githubusercontent.com"
        and c["aud"] == "sts.amazonaws.com"
    )
    for key, value in {
        "sub": p["oidc_subject"],
        "repository": REPOSITORY,
        "environment": "dev",
        "ref": "refs/heads/main",
        "sha": p["source_sha"],
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": "1",
        "workflow_ref": env["GITHUB_WORKFLOW_REF"],
    }.items():
        require(str(c[key]) == value)
    require(c["exp"] > now.timestamp() + 30 and c["nbf"] <= now.timestamp())
    # This decode is preflight. AWS STS verifies the JWT signature.


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def oidc(env):
    u = urlsplit(env["ACTIONS_ID_TOKEN_REQUEST_URL"])
    require(
        u.scheme == "https" and u.hostname and u.hostname.endswith(".actions.githubusercontent.com")
    )
    require(not u.username and not u.password and u.port in (None, 443) and not u.fragment)
    q = dict(parse_qsl(u.query)) | {"audience": "sts.amazonaws.com"}
    request = Request(
        urlunsplit(u._replace(query=urlencode(q))),
        headers={"Authorization": "Bearer " + env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
    )
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        raw = response.read(65537)
        require(len(raw) <= 65536)
        return json.loads(raw, object_pairs_hook=unique)["value"]


def policy(p, expiry):
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["lambda:ListTags"],
                "Resource": sorted(p["mapping_arns"]),
                "Condition": {"DateLessThan": {"aws:CurrentTime": expiry.isoformat()}},
            }
        ],
    }


def probe(session, config, p, expiry, env, clock):
    require(clock() < expiry - timedelta(seconds=30))
    sts = session.client("sts", endpoint_url=f"https://sts.{REGION}.amazonaws.com", config=config)
    identity = sts.get_caller_identity()
    expected_arn = (
        f"arn:aws:sts::{ACCOUNT}:assumed-role/ai-interview-ci-plan/p4-{env['GITHUB_RUN_ID']}-tags"
    )
    require(identity["Account"] == ACCOUNT and identity["Arn"] == expected_arn)
    client = session.client(
        "lambda", endpoint_url=f"https://lambda.{REGION}.amazonaws.com", config=config
    )
    rows = []
    for arn in sorted(p["mapping_arns"]):
        require(clock() < expiry - timedelta(seconds=30))
        response = client.list_tags(Resource=arn)
        require(response["ResponseMetadata"]["HTTPStatusCode"] == 200)
        rows.append(
            {
                "resource_sha256": digest(arn.encode()),
                "http_status": 200,
                "request_id": response["ResponseMetadata"]["RequestId"],
            }
        )
        del response  # Tag contents are deliberately excluded from all evidence.
    return rows


class WireCounter:
    """Count before-send callbacks, reject a second send for any SDK operation."""

    def __init__(self):
        self.counts = {}

    def before_send(self, request, event_name, **kwargs):
        label = event_name.removeprefix("before-send.")
        require(
            label in {"sts.AssumeRoleWithWebIdentity", "sts.GetCallerIdentity", "lambda.ListTags"}
        )
        limit = 2 if label == "lambda.ListTags" else 1
        count = self.counts.get(label, 0)
        require(count < limit)
        header = str(request.headers.get("amz-sdk-request", ""))
        require(not re.search(r"attempt=(?:[2-9]|[0-9]{2,})", header))
        self.counts[label] = count + 1


def run(env, root, clock):
    p, expiry = validate(
        env["P4_TAG_PROBE_PACKAGE"].encode(), env["P4_TAG_PROBE_SHA256"], env, root, clock()
    )
    from boto3 import Session
    from botocore import UNSIGNED
    from botocore.config import Config

    config = Config(
        retries={"total_max_attempts": 1},
        connect_timeout=5,
        read_timeout=15,
        ignore_configured_endpoint_urls=True,
    )
    meter = WireCounter()
    token = oidc(env)
    claims(token, p, env, clock())
    require(clock() < expiry - timedelta(minutes=5))
    # Explicit dummy credentials prevent ambient profile/metadata credential resolution.
    unsigned_session = Session(
        aws_access_key_id="unused", aws_secret_access_key="unused", region_name=REGION
    )
    unsigned_session.events.register("before-send.*.*", meter.before_send)
    sts = unsigned_session.client(
        "sts",
        endpoint_url=f"https://sts.{REGION}.amazonaws.com",
        config=config.merge(Config(signature_version=UNSIGNED)),
    )
    response = sts.assume_role_with_web_identity(
        RoleArn=ROLE,
        RoleSessionName=f"p4-{env['GITHUB_RUN_ID']}-tags",
        WebIdentityToken=token,
        DurationSeconds=900,
        Policy=json.dumps(policy(p, expiry), separators=(",", ":")),
    )
    require(
        response["AssumedRoleUser"]["Arn"]
        == (
            f"arn:aws:sts::{ACCOUNT}:assumed-role/ai-interview-ci-plan/"
            f"p4-{env['GITHUB_RUN_ID']}-tags"
        )
    )
    c = response["Credentials"]
    require(c["Expiration"] > clock() + timedelta(minutes=2))
    session_expiry = c["Expiration"]
    session = Session(
        aws_access_key_id=c["AccessKeyId"],
        aws_secret_access_key=c["SecretAccessKey"],
        aws_session_token=c["SessionToken"],
        region_name=REGION,
    )
    session.events.register("before-send.*.*", meter.before_send)
    del token, c, response, sts, unsigned_session
    rows = probe(session, config, p, min(expiry, session_expiry), env, clock)
    require(
        meter.counts
        == {"sts.AssumeRoleWithWebIdentity": 1, "sts.GetCallerIdentity": 1, "lambda.ListTags": 2}
    )
    return {
        "passed": True,
        "approval_sha256": env["P4_TAG_PROBE_SHA256"],
        "source_sha": p["source_sha"],
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": 1,
        "plan_role_identity_verified": True,
        "listtags": rows,
        "aws_requests": sum(meter.counts.values()),
        "sdk_before_send_counts": meter.counts,
        "oidc_gets": 1,
        "retry": 0,
        "terraform_calls": 0,
        "aws_mutations": 0,
        "READY": False,
        "formal_resume_ready": False,
    }


def main():
    out = Path(os.environ["RUNNER_TEMP"]) / "p4-tag-probe"
    out.mkdir(mode=0o700, exist_ok=False)
    result = {
        "passed": False,
        "reason": "ProbeFailedNoRetry",
        "READY": False,
        "formal_resume_ready": False,
    }
    try:
        result = run(os.environ, Path(__file__).resolve().parents[3], lambda: datetime.now(UTC))
    except Exception:
        pass  # Never print exception text, responses, tags, tokens or credentials.
    result["finished_at_utc"] = datetime.now(UTC).isoformat()
    with (out / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write("\n")
    print("ListTags probe: " + ("PASS" if result["passed"] else "FAIL (no retry)"))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
