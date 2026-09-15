"""Display only allowlisted GitHub claims. Never exchange the token with AWS."""

import base64
import json
import os
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener

from ci_identity import REPOSITORY, NoRedirect, validated_claims

from interview_backend.deployment import DeploymentError


def discover(environment, *, opener=None):
    if (
        environment.get("P4_OIDC_DISCOVERY_READY") != "true"
        or environment.get("GITHUB_ACTIONS") != "true"
        or environment.get("GITHUB_REF") != "refs/heads/main"
        or environment.get("GITHUB_REPOSITORY") != REPOSITORY
    ):
        raise DeploymentError("OidcDiscoveryPrerequisitesUnconfirmed")
    try:
        url = urlsplit(environment["ACTIONS_ID_TOKEN_REQUEST_URL"])
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith(".actions.githubusercontent.com")
            or url.username
            or url.password
            or url.port not in {None, 443}
        ):
            raise ValueError
        query = dict(parse_qsl(url.query)) | {"audience": "sts.amazonaws.com"}
        request = Request(
            urlunsplit(url._replace(query=urlencode(query))),
            headers={"Authorization": "Bearer " + environment["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
        )
        with (opener or build_opener(NoRedirect())).open(request, timeout=15) as response:
            token = json.loads(response.read(65537))["value"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (
            claims["iss"] != "https://token.actions.githubusercontent.com"
            or not re.fullmatch(
                r"repo:yonegen0(?:@[0-9]+)?/ai_interview(?:@[0-9]+)?:environment:dev", claims["sub"]
            )
            or not re.fullmatch(r"[0-9]+", claims["repository_id"])
        ):
            raise ValueError
        validated_claims(token, claims["sub"], environment)
        return {key: claims[key] for key in ("iss", "aud", "sub", "repository", "repository_id")}
    except Exception:
        raise DeploymentError("OidcDiscoveryFailed") from None


def main():
    try:
        result = discover(os.environ)
    except Exception:
        print("OidcDiscoveryFailed", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
