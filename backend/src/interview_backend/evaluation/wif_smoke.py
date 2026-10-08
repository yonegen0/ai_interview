"""Operator-only Worker WIF Smoke; no DDB, SQS or paid Responses request."""

import base64
import re
from time import monotonic, time

from interview_backend.evaluation.openai_auth import AWSFederation
from interview_backend.evaluation.openai_provider import Deadline, strict_json


def verify_claims(token, issuer, account, *, now=None):
    if not isinstance(issuer, str) or not re.fullmatch(
        r"https://[A-Za-z0-9-]+\.tokens\.sts\.global\.api\.aws", issuer
    ):
        raise ValueError("ObservedAWSIssuerRequired")
    if not re.fullmatch(r"\d{12}", account) or not isinstance(token, str) or len(token) > 65536:
        raise ValueError("AWSSubjectJWTRequired")
    parts = token.split(".")
    if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in parts):
        raise ValueError("AWSSubjectJWTRequired")
    header, claims = [
        strict_json(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))) for p in parts[:2]
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


def smoke(settings, environment, event, *, authentication_factory=AWSFederation):
    if (
        settings.component != "worker"
        or settings.function_name != "ai-interview-dev-worker"
        or settings.region != "ap-northeast-1"
        or environment.get("INTERVIEW_VALIDATION_ONLY") != "true"
        or environment.get("INTERVIEW_WIF_SMOKE_ENABLED") != "true"
        or environment.get("INTERVIEW_AI_PROVIDER") != "fake"
        or environment.get("INTERVIEW_OPENAI_AUTH") != "wif"
        or environment.get("INTERVIEW_OPENAI_ENABLED") != "true"
        or not isinstance(event, dict)
        or set(event) != {"operation", "run_id"}
        or event.get("operation") != "wif_smoke"
        or not re.fullmatch(r"[a-z0-9-]{1,24}", environment.get("INTERVIEW_WIF_SMOKE_RUN_ID", ""))
        or event.get("run_id") != environment["INTERVIEW_WIF_SMOKE_RUN_ID"]
    ):
        raise ValueError("ExplicitWorkerWIFSmokeRequired")
    issuer = environment.get("INTERVIEW_OPENAI_AWS_ISSUER")
    if not isinstance(issuer, str) or not re.fullmatch(
        r"https://[A-Za-z0-9-]+\.tokens\.sts\.global\.api\.aws", issuer
    ):
        raise ValueError("ObservedAWSIssuerRequired")
    observed = []

    def inspect(subject):
        observed.append(verify_claims(subject, issuer, settings.account))

    authentication = authentication_factory(
        settings.region,
        environment.get("INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID", ""),
        environment.get("INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID", ""),
        subject_observer=inspect,
    )
    # Short-lived access token is discarded. Exchange verifies the signature/mapping.
    access = authentication.token(Deadline(monotonic() + 40))
    if not isinstance(access, str) or not access:
        raise ValueError("VerifiedOpenAIExchangeRequired")
    del access
    if len(observed) != 1:
        raise ValueError("VerifiedWorkerSubjectRequired")
    return {
        "status": "WORKER_WIF_SMOKE_VERIFIED",
        **observed[0],
        "openai_exchange_verified": True,
        "paid_responses_calls": 0,
    }
