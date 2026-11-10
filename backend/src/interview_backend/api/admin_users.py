"""Cognito user list and nickname mutations; no identity data is stored in DynamoDB."""

import re
import unicodedata

from botocore.exceptions import ClientError

from interview_backend.models.internal import BusinessError


# Cognito sub is GUID-shaped, but its variant/version bits are not RFC UUIDs.
COGNITO_SUB_PATTERN = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def validate_cognito_sub(value: object) -> str:
    """Validate the existing Cognito sub wire shape without RFC UUID constraints."""
    if not isinstance(value, str) or COGNITO_SUB_PATTERN.fullmatch(value) is None:
        raise BusinessError(400, "VALIDATION_ERROR")
    return value


def normalize_nickname(value: object) -> str:
    """NFC and code-point semantics shared with the browser form."""
    if not isinstance(value, str):
        raise BusinessError(400, "VALIDATION_ERROR")
    normalized = unicodedata.normalize("NFC", value).strip()
    if any(unicodedata.category(char) == "Cc" for char in normalized):
        raise BusinessError(400, "VALIDATION_ERROR")
    if len(normalized) > 24:
        raise BusinessError(400, "VALIDATION_ERROR")
    return normalized


class CognitoUsers:
    """A small, injectable identity-provider boundary for the ADMIN Lambda."""

    def __init__(self, region: str, user_pool_id: str, client=None):
        self.region, self.user_pool_id = region, user_pool_id
        self.client = client

    def _client(self):
        if self.client is None:
            import boto3
            from botocore.config import Config

            self.client = boto3.client(
                "cognito-idp",
                region_name=self.region,
                config=Config(retries={"max_attempts": 1}),
            )
        return self.client

    @staticmethod
    def _attributes(attributes):
        return {
            row["Name"]: row["Value"]
            for row in attributes
            if isinstance(row, dict)
            and isinstance(row.get("Name"), str)
            and isinstance(row.get("Value"), str)
        }

    def list_users(self, limit: int, cursor: str | None):
        kwargs = {"UserPoolId": self.user_pool_id, "Limit": limit}
        if cursor is not None:
            kwargs["PaginationToken"] = cursor
        result = self._client().list_users(**kwargs)
        users = []
        for record in result.get("Users", []):
            attributes = self._attributes(record.get("Attributes") or [])
            sub = attributes.get("sub")
            if not isinstance(sub, str) or COGNITO_SUB_PATTERN.fullmatch(sub) is None:
                raise ValueError("missing_cognito_sub")
            users.append(
                {
                    "userId": sub,
                    "nickname": attributes.get("nickname") or None,
                    "email": attributes.get("email") or None,
                    "enabled": record.get("Enabled") is True,
                }
            )
        return {"users": users, "nextCursor": result.get("PaginationToken") or None}

    def update_nickname(self, user_id: str, nickname: str):
        try:
            self._client().admin_update_user_attributes(
                UserPoolId=self.user_pool_id,
                Username=user_id,
                UserAttributes=[{"Name": "nickname", "Value": nickname}],
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
                raise BusinessError(404, "NOT_FOUND") from None
            raise
        return {"userId": user_id, "nickname": nickname or None}
