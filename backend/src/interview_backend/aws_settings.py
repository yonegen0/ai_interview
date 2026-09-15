"""Explicit, account-scoped Lambda configuration; reading settings never calls AWS."""

import re
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigurationError(ValueError):
    def __init__(self):
        super().__init__("InvalidConfiguration")


@dataclass(frozen=True)
class AwsSettings:
    component: str
    account: str
    region: str
    table: str
    function_name: str
    queue_arn: str = ""
    queue_url: str = ""
    stream_arn: str = ""
    schedule_arn: str = ""
    client_id: str = ""
    user_pool: str = ""
    api_id: str = ""
    stage: str = "dev"

    @property
    def issuer(self):
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool}"

    @property
    def function_arn(self):
        return f"arn:aws:lambda:{self.region}:{self.account}:function:{self.function_name}"

    @classmethod
    def load(cls, env: Mapping[str, str], component: str):
        def required(name, pattern):
            value = env.get(f"INTERVIEW_{name}", "")
            if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
                raise ConfigurationError()
            return value

        if (
            component not in {"api", "worker", "dispatcher"}
            or env.get("INTERVIEW_COMPONENT") != component
        ):
            raise ConfigurationError()
        account = required("ACCOUNT_ID", r"\d{12}")
        region = required("REGION", r"(?:ap|us|eu|ca|sa|me|af|il|mx)-[a-z]+-\d+")
        if env.get("AWS_REGION", region) != region:
            raise ConfigurationError()
        table = required("TABLE_NAME", r"ai-interview-(?:dev|test-[a-z0-9-]+)-[A-Za-z0-9_.-]+")
        function = required("FUNCTION_NAME", rf"ai-interview-(?:dev|test-[a-z0-9-]+)-{component}")
        prefix = function.removesuffix(f"-{component}")
        if table != f"{prefix}-main":
            raise ConfigurationError()
        if env.get("AWS_LAMBDA_FUNCTION_NAME", function) != function:
            raise ConfigurationError()
        config = dict(
            component=component, account=account, region=region, table=table, function_name=function
        )
        if component == "api":
            config.update(
                client_id=required("CLIENT_ID", r"[a-zA-Z0-9]{1,128}"),
                user_pool=required("USER_POOL_ID", re.escape(region) + r"_[a-zA-Z0-9]+"),
                api_id=required("API_ID", r"[a-z0-9]+"),
                stage=required("STAGE", r"dev"),
            )
        else:
            queue = required(
                "QUEUE_ARN",
                rf"arn:aws:sqs:{re.escape(region)}:{account}:{re.escape(prefix)}-main",
            )
            config["queue_arn"] = queue
            if component == "dispatcher":
                url = env.get("INTERVIEW_QUEUE_URL", "")
                if url != f"https://sqs.{region}.amazonaws.com/{account}/{queue.rsplit(':', 1)[1]}":
                    raise ConfigurationError()
                config.update(
                    queue_url=url,
                    stream_arn=required(
                        "STREAM_ARN",
                        rf"arn:aws:dynamodb:{re.escape(region)}:{account}:table/{re.escape(table)}/stream/[0-9T:.\-]+",
                    ),
                    schedule_arn=required(
                        "SCHEDULE_ARN",
                        rf"arn:aws:scheduler:{re.escape(region)}:{account}:schedule/{re.escape(prefix)}/recovery",
                    ),
                )
        return cls(**config)

    def require_invocation(self, context, aliases):
        arn = getattr(context, "invoked_function_arn", None)
        if arn not in {f"{self.function_arn}:{alias}" for alias in aliases}:
            raise ConfigurationError()
        remaining = context.get_remaining_time_in_millis()
        if type(remaining) is not int or remaining < 0:
            raise ConfigurationError()
        return arn.rsplit(":", 1)[1]
