"""Exact dev Worker federation grant; no credential or AWS client creation."""

import base64
import json
import re
from time import time


def worker_statement(account, *, boundary=False):
    if not re.fullmatch(r"\d{12}", account):
        raise ValueError("ExactAccountRequired")
    conditions = {
        "ForAllValues:StringEquals": {"sts:IdentityTokenAudience": ["https://api.openai.com/v1"]},
        "NumericLessThanEquals": {"sts:DurationSeconds": 300},
        "StringEquals": {"sts:SigningAlgorithm": "ES384"},
        "Null": {
            "sts:IdentityTokenAudience": "false",
            "sts:DurationSeconds": "false",
            "sts:SigningAlgorithm": "false",
        },
    }
    if boundary:
        conditions["ArnEquals"] = {
            "aws:PrincipalArn": f"arn:aws:iam::{account}:role/ai-interview-dev-worker-runtime"
        }
    return {
        "Sid": "WorkerOpenAIWIF",
        "Effect": "Allow",
        "Action": ["sts:GetWebIdentityToken"],
        "Resource": ["*"],
        "Condition": conditions,
    }


def verify_worker_claims(token, info, account, *, now=None):
    """Decode in memory only; OpenAI exchange must independently verify signature."""
    issuer = info.get("IssuerIdentifier")
    if (
        info.get("JwtVendingEnabled") is not True
        or not isinstance(issuer, str)
        or not re.fullmatch(r"https://[A-Za-z0-9-]+\.tokens\.sts\.global\.api\.aws", issuer)
    ):
        raise ValueError("ObservedEnabledAWSIssuerRequired")
    if not isinstance(token, str) or len(token) > 65536:
        raise ValueError("AWSSubjectJWTRequired")
    parts = token.split(".")
    if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
        raise ValueError("AWSSubjectJWTRequired")
    header, claims = [
        json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))) for p in parts[:2]
    ]
    now = time() if now is None else now
    subject = f"arn:aws:iam::{account}:role/ai-interview-dev-worker-runtime"
    audience = "https://api.openai.com/v1"
    if (
        header.get("alg") != "ES384"
        or claims.get("iss") != issuer
        or claims.get("sub") != subject
        or claims.get("aud") not in (audience, [audience])
    ):
        raise ValueError("WorkerIssuerAudienceSubjectMismatch")
    iat, exp = claims.get("iat"), claims.get("exp")
    if (
        type(iat) is not int
        or type(exp) is not int
        or not 0 < exp - iat <= 300
        or iat > now + 30
        or exp <= now + 40
    ):
        raise ValueError("ShortFreshSubjectTokenRequired")
    return {
        "issuer": issuer,
        "audience": audience,
        "subject": subject,
        "ttl_seconds": exp - iat,
        "signature_verified_locally": False,
    }


def verify_mapping(mapping, claims, expected):
    keys = (
        "issuer",
        "audience",
        "subject",
        "project_id",
        "service_account_id",
        "identity_provider_id",
    )
    if any(
        not isinstance(expected.get(k), str) or not expected[k] or mapping.get(k) != expected[k]
        for k in keys
    ):
        raise ValueError("ObservedOpenAIMappingMismatch")
    if (
        any(mapping[k] != claims[k] for k in ("issuer", "audience", "subject"))
        or mapping.get("permissions") != ["api.model.request"]
        or mapping.get("gpt6_luna_access_verified") is not True
    ):
        raise ValueError("ExactWorkerModelMappingRequired")
    return True
