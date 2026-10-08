"""Explicit WIF or secret authentication. Tokens exist only in memory, with no fallback."""

import re
from dataclasses import dataclass, field
from time import time

from interview_backend.evaluation.openai_provider import (
    HTTPTransport,
    ProviderFailure,
    http_error,
    strict_json,
)


@dataclass(repr=False)
class AWSFederation:
    region: str
    identity_provider_id: str
    service_account_id: str
    client_factory: object = field(default=None, repr=False)
    transport: object = field(default=None, repr=False)
    wall_clock: object = field(default=time, repr=False)

    def token(self, deadline):
        if (
            not all(
                re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value or "")
                for value in (self.identity_provider_id, self.service_account_id)
            )
            or self.region != "ap-northeast-1"
        ):
            raise ProviderFailure("AUTHENTICATION")
        try:
            if self.client_factory is None:
                import boto3
                from botocore.config import Config

                timeout = min(5, deadline.seconds() / 2)
                client = boto3.client(
                    "sts",
                    region_name=self.region,
                    endpoint_url=f"https://sts.{self.region}.amazonaws.com",
                    config=Config(
                        retries={"total_max_attempts": 1},
                        connect_timeout=timeout,
                        read_timeout=timeout,
                    ),
                )
            else:
                client = self.client_factory(deadline)
            subject = client.get_web_identity_token(
                Audience=["https://api.openai.com/v1"],
                SigningAlgorithm="ES384",
                DurationSeconds=300,
            )["WebIdentityToken"]
            if not isinstance(subject, str) or not subject:
                raise ProviderFailure("AUTHENTICATION")
            deadline.seconds()
            status, raw = (self.transport or HTTPTransport()).post(
                "auth.openai.com",
                "/oauth/token",
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                    "subject_token": subject,
                    "identity_provider_id": self.identity_provider_id,
                    "service_account_id": self.service_account_id,
                },
                {},
                deadline,
            )
            if status != 200:
                raise http_error(status, raw)
            data = strict_json(raw)
            if (
                data.get("token_type", "").lower() != "bearer"
                or not isinstance(data.get("access_token"), str)
                or not data["access_token"]
                or type(data.get("expires_at")) not in (int, float)
                or data["expires_at"] <= self.wall_clock() + deadline.seconds()
            ):
                raise ProviderFailure("AUTHENTICATION")
            return data["access_token"]
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderFailure("AUTHENTICATION") from None


@dataclass(repr=False)
class SecretAuthentication:
    region: str
    secret_arn: str
    client_factory: object = field(default=None, repr=False)

    def token(self, deadline):
        if (
            not re.fullmatch(
                r"arn:aws:secretsmanager:ap-northeast-1:\d{12}:secret:[A-Za-z0-9/_+=.@-]+",
                self.secret_arn or "",
            )
            or self.region != "ap-northeast-1"
        ):
            raise ProviderFailure("AUTHENTICATION")
        try:
            if self.client_factory is None:
                import boto3
                from botocore.config import Config

                timeout = min(5, deadline.seconds() / 2)
                client = boto3.client(
                    "secretsmanager",
                    region_name=self.region,
                    endpoint_url=f"https://secretsmanager.{self.region}.amazonaws.com",
                    config=Config(
                        retries={"total_max_attempts": 1},
                        connect_timeout=timeout,
                        read_timeout=timeout,
                    ),
                )
            else:
                client = self.client_factory(deadline)
            result = strict_json(client.get_secret_value(SecretId=self.secret_arn)["SecretString"])
            deadline.seconds()
            key = result.get("api_key")
            if not isinstance(key, str) or not key or any(c.isspace() for c in key):
                raise ProviderFailure("AUTHENTICATION")
            return key
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderFailure("AUTHENTICATION") from None
