"""Interactive EMAIL_OTP and live HTTP checks. Never persist tokens or follow redirects."""

import argparse
import getpass
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from manifest import read_manifest, verify_live_manifest

from interview_backend.deployment import account_settings, checked_session, require_aws_execution


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Api:
    def __init__(self, endpoint, token):
        self.endpoint, self.token = endpoint, token
        self.opener = build_opener(NoRedirect())

    def call(self, method, path, payload=None, key=None, headers=None):
        values = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        if key:
            values["Idempotency-Key"] = key
        values.update(headers or {})
        request = Request(
            self.endpoint + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=values,
            method=method,
        )
        try:
            response = self.opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("OversizeResponse")
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
            return response.code, body, dict(response.headers)


def login(client, client_id, email):
    response = client.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_AUTH",
        AuthParameters={"USERNAME": email, "PREFERRED_CHALLENGE": "EMAIL_OTP"},
    )
    if response.get("ChallengeName") == "SELECT_CHALLENGE":
        response = client.respond_to_auth_challenge(
            ClientId=client_id,
            ChallengeName="SELECT_CHALLENGE",
            Session=response["Session"],
            ChallengeResponses={"USERNAME": email, "ANSWER": "EMAIL_OTP"},
        )
    if response.get("ChallengeName") != "EMAIL_OTP":
        raise ValueError("EmailOtpRequired")
    code = getpass.getpass("Email OTP: ")
    response = client.respond_to_auth_challenge(
        ClientId=client_id,
        ChallengeName="EMAIL_OTP",
        Session=response["Session"],
        ChallengeResponses={"USERNAME": email, "EMAIL_OTP_CODE": code},
    )
    return response["AuthenticationResult"]


def check(condition):
    if not condition:
        raise AssertionError("LiveApiAssertionFailed")


def flow(api):
    create_key = str(uuid4())
    payload = {"category": "career", "difficulty": "standard"}
    status, created, _ = api.call("POST", "/sessions", payload, create_key)
    check(status == 201)
    check(api.call("POST", "/sessions", payload, create_key)[:2] == (201, created))
    sid = created["sessionId"]
    status, question, _ = api.call("GET", f"/sessions/{sid}/question")
    check(status == 200)
    answer_key = str(uuid4())
    answer = {"questionId": question["question"]["id"], "answer": "synthetic P4 answer"}
    path = f"/sessions/{sid}/answers"
    status, accepted, _ = api.call("POST", path, answer, answer_key)
    check(status == 202)
    check(api.call("POST", path, answer, answer_key)[:2] == (202, accepted))
    deadline = time.monotonic() + 180
    while True:
        status, evaluation, _ = api.call("GET", f"/evaluations/{accepted['evaluationId']}")
        check(status == 200)
        if evaluation["status"] != "processing":
            check(evaluation["status"] == "completed")
            break
        check(time.monotonic() < deadline)
        time.sleep(2)
    status, feedback, _ = api.call("GET", f"/attempts/{accepted['attemptId']}/feedback")
    check(status == 200 and feedback["answer"] == answer["answer"])
    next_key = str(uuid4())
    next_path = f"/sessions/{sid}/questions/next"
    next_payload = {"fromAttemptId": accepted["attemptId"]}
    status, next_question, _ = api.call("POST", next_path, next_payload, next_key)
    check(status == 200 and next_question["questionNumber"] == 2)
    check(api.call("POST", next_path, next_payload, next_key)[:2] == (200, next_question))
    check(api.call("POST", path, answer, answer_key)[:2] == (202, accepted))
    check(api.call("GET", "/unknown")[0] == 404)
    status, _, headers = api.call("DELETE", f"/sessions/{sid}/question")
    check(status == 405 and {k.lower(): v for k, v in headers.items()}.get("allow") == "GET")
    return sid, accepted


def main():
    parser = argparse.ArgumentParser()
    for name in ("manifest",):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    tokens = []
    client = None
    try:
        require_aws_execution()
        account, region = account_settings(Path(__file__).resolve().parents[3])
        manifest = read_manifest(args.manifest, account, region)
        session = checked_session(account, region)
        verify_live_manifest(session, manifest)
        print(json.dumps({"account": account, "region": region, "versions": manifest["versions"]}))
        client = boto3.client(
            "cognito-idp",
            region_name=region,
            config=Config(
                signature_version=UNSIGNED,
                retries={"total_max_attempts": 1},
                connect_timeout=5,
                read_timeout=15,
            ),
        )
        for label in ("USER", "ADMIN"):
            email = getpass.getpass(f"Synthetic test user {label} email (hidden): ")
            tokens.append(login(client, manifest["client_id"], email))
        first, second = [Api(manifest["api_endpoint"], value["AccessToken"]) for value in tokens]
        sid, accepted = flow(first)
        for path in (
            f"/sessions/{sid}/question",
            f"/evaluations/{accepted['evaluationId']}",
            f"/attempts/{accepted['attemptId']}/feedback",
        ):
            check(second.call("GET", path)[0] == 404)
        id_api = Api(manifest["api_endpoint"], tokens[0]["IdToken"])
        check(id_api.call("GET", f"/sessions/{sid}/question")[0] == 401)
        client.global_sign_out(AccessToken=tokens[0]["AccessToken"])
        try:
            client.initiate_auth(
                ClientId=manifest["client_id"],
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": tokens[0]["RefreshToken"]},
            )
        except client.exceptions.NotAuthorizedException:
            pass
        else:
            raise AssertionError("RefreshMustFailAfterLogout")
        # Actual token expiry, not an injected clock. Do not assert immediate revocation.
        print("Waiting for five-minute access token expiry; tokens remain only in memory.")
        for _ in range(31):
            time.sleep(10)
            if first.call("GET", f"/sessions/{sid}/question")[0] == 401:
                break
        else:
            raise AssertionError("ExpiredTokenAccepted")
        print(
            json.dumps(
                {
                    "result": "passed",
                    "verified": ["AU-01", "AU-02", "AU-03", "AU-08", "AU-09", "AU-12-logout"],
                    "partial": ["AU-06"],
                    "versions": manifest["versions"],
                }
            )
        )
        return 0
    except Exception:
        print("AuthE2EFailed", file=sys.stderr)
        return 1
    finally:
        if client:
            for token in tokens:
                try:
                    client.global_sign_out(AccessToken=token["AccessToken"])
                except Exception:
                    pass
                token.clear()
        tokens.clear()


if __name__ == "__main__":
    raise SystemExit(main())
