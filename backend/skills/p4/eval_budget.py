"""Pre-count immutable requests and reserve money before any Responses generation."""

import base64
import hashlib
import http.client
import json
import os
import re
import ssl
from datetime import date
from decimal import Decimal
from time import time

from interview_backend.evaluation.openai_provider import (
    Deadline,
    HTTPTransport,
    OpenAIProvider,
    strict_json,
)

NANO_USD = 1_000_000_000
# Fast x long-context x regional uplift, including worst cache-write rate.
# 2026-10-08 official pricing. Fail closed when the approved snapshot expires.
RATES = {
    "model": "gpt-6-luna",
    "observed_on": "2026-10-08",
    "valid_until": "2026-10-15",
    "input_nano_usd_per_token": 550,
    "output_nano_usd_per_token": 1650,
    "source": "https://developers.openai.com/api/docs/models/gpt-6-luna",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pricing_hash():
    return sha(RATES)


def bind_authentication(authentication, expected):
    from interview_backend.evaluation.openai_auth import AWSFederation, SecretAuthentication

    if (
        expected.get("status") != "AUTHENTICATION_READBACK_VERIFIED"
        or expected.get("gpt6_luna_access_verified") is not True
        or not isinstance(expected.get("project_id"), str)
        or not expected["project_id"]
        or expected.get("region") != "ap-northeast-1"
        or authentication.region != "ap-northeast-1"
    ):
        raise ValueError("VerifiedProjectModelAuthenticationRequired")
    if expected.get("mode") == "wif" and isinstance(authentication, AWSFederation):
        if expected.get("permissions") != ["api.model.request"]:
            raise ValueError("NarrowWIFModelScopeRequired")
        if authentication.identity_provider_id != expected.get(
            "identity_provider_id"
        ) or authentication.service_account_id != expected.get("service_account_id"):
            raise ValueError("ApprovedLocalWIFMappingRequired")
        issuer, subject = expected.get("issuer"), expected.get("subject")
        if (
            not isinstance(issuer, str)
            or not re.fullmatch(r"https://[A-Za-z0-9-]+\.tokens\.sts\.global\.api\.aws", issuer)
            or not isinstance(subject, str)
            or not re.fullmatch(r"arn:aws:iam::\d{12}:(?:role|user)/[A-Za-z0-9+=,.@_/-]+", subject)
        ):
            raise ValueError("ObservedLocalIssuerAndSubjectRequired")

        def observe(token):
            parts = token.split(".")
            if len(parts) != 3 or len(token) > 65536:
                raise ValueError("LocalSubjectJWTRequired")
            header, claims = [
                strict_json(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))) for p in parts[:2]
            ]
            if (
                header.get("alg") != "ES384"
                or claims.get("iss") != issuer
                or claims.get("sub") != subject
                or claims.get("aud")
                not in ("https://api.openai.com/v1", ["https://api.openai.com/v1"])
            ):
                raise ValueError("LocalWIFClaimsMismatch")
            iat, exp = claims.get("iat"), claims.get("exp")
            if (
                type(iat) is not int
                or type(exp) is not int
                or not 0 < exp - iat <= 300
                or iat > time() + 30
                or exp <= time() + 40
            ):
                raise ValueError("FreshLocalSubjectTokenRequired")

        authentication.subject_observer = observe
    elif expected.get("mode") == "secret" and isinstance(authentication, SecretAuthentication):
        if authentication.secret_arn != expected.get("secret_arn"):
            raise ValueError("ExplicitApprovedSecretRequired")
    else:
        raise ValueError("ApprovedAuthenticationModeRequired")


def money(value):
    if not isinstance(value, str):
        raise ValueError("ExplicitDollarLimitRequired")
    amount = Decimal(value) * NANO_USD
    if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
        raise ValueError("InvalidDollarLimit")
    return int(amount)


def checked_pricing(approved_hash, today=None):
    today = today or date.today()
    if approved_hash != pricing_hash() or not date.fromisoformat(
        RATES["observed_on"]
    ) <= today <= date.fromisoformat(RATES["valid_until"]):
        raise ValueError("CurrentApprovedPricingRequired")


def request_payload(provider, prompt):
    """Capture the existing provider's actual serialized request with no network/auth."""
    captured = []

    class CaptureComplete(Exception):
        pass

    class CaptureAuthentication:
        def token(self, deadline):
            return "offline-capture"

    class CaptureTransport:
        def post(self, host, path, payload, headers, deadline):
            if (host, path) != ("api.openai.com", "/v1/responses"):
                raise ValueError("UnexpectedProviderEndpoint")
            captured.append(payload)
            raise CaptureComplete

    capture = OpenAIProvider(
        CaptureAuthentication(), transport=CaptureTransport(), settings=provider.settings
    )
    try:
        capture.evaluate(prompt)
    except CaptureComplete:
        pass
    if len(captured) != 1:
        raise ValueError("SingleRequestPayloadRequired")
    return captured[0]


class CountHTTPTransport:
    """Separate operator-tool endpoint; deployed Provider transport stays unchanged."""

    def post(self, host, path, payload, headers, deadline):
        if (host, path) != ("api.openai.com", "/v1/responses/input_tokens"):
            raise ValueError("TokenCountEndpointRequired")
        connection = http.client.HTTPSConnection(
            host, timeout=deadline.seconds(), context=ssl.create_default_context()
        )
        try:
            connection.connect()
            sock = connection.sock
            sock.settimeout(deadline.seconds())
            connection.request(
                "POST",
                path,
                body=canonical(payload),
                headers={"Content-Type": "application/json", **headers},
            )
            sock.settimeout(deadline.seconds())
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("TokenCountFailedNoRetry")
            chunks, size = [], 0
            while True:
                sock.settimeout(deadline.seconds())
                part = response.read1(8192)
                if not part:
                    break
                chunks.append(part)
                size += len(part)
                if size > 65536:
                    raise ValueError("OversizedTokenCountResponse")
                if response.isclosed():
                    break
            deadline.seconds()
            return response.status, b"".join(chunks)
        finally:
            connection.close()


def count_request(payload, authentication, *, transport=None, deadline=None):
    """Explicitly authorized preflight API; no generation and no retry."""
    deadline = deadline or Deadline(__import__("time").monotonic() + 40)
    token = authentication.token(deadline)
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        raise ValueError("CountAuthenticationRequired")
    # Include the exact messages and structured-output schema; never count only answer text.
    count_payload = {k: payload[k] for k in ("model", "input", "text", "tools")}
    status, raw = (transport or CountHTTPTransport()).post(
        "api.openai.com",
        "/v1/responses/input_tokens",
        count_payload,
        {"Authorization": "Bearer " + token},
        deadline,
    )
    data = strict_json(raw)
    if (
        status != 200
        or not isinstance(data, dict)
        or data.get("object") != "response.input_tokens"
        or type(data.get("input_tokens")) is not int
        or data["input_tokens"] < 0
    ):
        raise ValueError("VerifiedInputTokenCountRequired")
    return {"request_sha256": sha(payload), "input_tokens": data["input_tokens"]}


def maximum(count, payload):
    output = payload.get("max_output_tokens")
    if (
        type(output) is not int
        or not 1 <= output <= 4096
        or payload.get("model") != RATES["model"]
        or payload.get("tools") != []
    ):
        raise ValueError("BoundedLunaRequestRequired")
    if (
        count.get("request_sha256") != sha(payload)
        or type(count.get("input_tokens")) is not int
        or count["input_tokens"] < 0
    ):
        raise ValueError("TokenCountBindingMismatch")
    return (
        count["input_tokens"] * RATES["input_nano_usd_per_token"]
        + output * RATES["output_nano_usd_per_token"]
    )


class Budget:
    def __init__(self, stream, payloads, counts, limit, *, max_calls=38):
        if (
            type(max_calls) is not int
            or not 1 <= max_calls <= 38
            or len(payloads) != len(counts)
            or not 1 <= len(payloads) <= max_calls
        ):
            raise ValueError("Maximum38CallsRequired")
        self.stream, self.limit = stream, money(limit)
        self.payloads, self.counts = payloads, counts
        self.reservations = [maximum(c, p) for c, p in zip(counts, payloads, strict=True)]
        self.reserved, self.used, self.calls, self.frozen = sum(self.reservations), 0, 0, False
        self.pending = None
        if self.reserved > self.limit:
            raise ValueError("BudgetWouldBeExceeded")
        self.record(
            "ALL_REQUESTS_RESERVED",
            pricing_sha256=pricing_hash(),
            max_calls=max_calls,
            counts=counts,
            reservations_nano_usd=self.reservations,
        )

    def record(self, status, **values):
        self.stream.write(
            json.dumps(
                {
                    "budget_status": status,
                    "used_nano_usd": self.used,
                    "reserved_nano_usd": self.reserved,
                    "calls_started": self.calls,
                    **values,
                }
            )
            + "\n"
        )
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def start(self, payload):
        if self.frozen or self.pending is not None or self.calls >= len(self.payloads):
            raise ValueError("NoFurtherPaidCallsAllowed")
        index = self.calls
        if sha(payload) != sha(self.payloads[index]) or self.used + self.reserved > self.limit:
            raise ValueError("RequestOrBudgetMismatch")
        self.pending = index
        self.calls += 1
        self.record("CALL_RESERVED_STARTED", request_sha256=sha(payload), index=index)

    def settle(self, usage):
        index = self.pending
        if index is None:
            raise ValueError("StartedCallRequired")
        if not isinstance(usage, dict) or any(
            type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")
        ):
            self.frozen = True
            self.record("USAGE_UNKNOWN_STOP", index=index)
            raise ValueError("UsageUnknownNoFurtherCalls")
        amount = (
            usage["input_tokens"] * RATES["input_nano_usd_per_token"]
            + usage["output_tokens"] * RATES["output_nano_usd_per_token"]
        )
        self.used += amount
        self.reserved -= self.reservations[index]
        self.pending = None
        if amount > self.reservations[index] or self.used + self.reserved > self.limit:
            self.frozen = True
            self.record("MEASURED_USAGE_EXCEEDED_RESERVATION_STOP", index=index)
            raise ValueError("ReservationExceededNoFurtherCalls")
        self.record("USAGE_ACCOUNTED", index=index)


class ReservedTransport:
    def __init__(self, budget, transport=None):
        self.budget, self.transport = budget, transport or HTTPTransport()

    def post(self, host, path, payload, headers, deadline):
        if (host, path) != ("api.openai.com", "/v1/responses"):
            raise ValueError("GenerationEndpointRequired")
        self.budget.start(payload)
        return self.transport.post(host, path, payload, headers, deadline)
