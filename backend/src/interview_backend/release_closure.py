"""Close only the Terraform-bound invite generation, then independently read it back.

The event cannot select targets. Expiry gates at the API/edge enforce the access
deadline while asynchronous AWS configuration changes propagate.
"""

import json
import os
from time import monotonic, sleep, time

import boto3
from botocore.config import Config


def close(target, clients, *, clock=time, timer=monotonic, pause=sleep):
    if clock() < target["expires_at"]:
        raise ValueError("ClosureBeforeDeadline")
    api, lambdas, scheduler, cf = (
        clients[k] for k in ("apigatewayv2", "lambda", "scheduler", "cloudfront")
    )
    if not api.get_api(ApiId=target["api_id"])["DisableExecuteApiEndpoint"]:
        api.update_api(ApiId=target["api_id"], DisableExecuteApiEndpoint=True)
    for uuid in target["mappings"]:
        state = lambdas.get_event_source_mapping(UUID=uuid)["State"]
        if state == "Enabled":
            lambdas.update_event_source_mapping(UUID=uuid, Enabled=False)
        elif state not in {"Disabled", "Disabling"}:
            raise RuntimeError("UnexpectedMappingState")
    args = {"Name": "recovery", "GroupName": target["schedule_group"]}
    schedule = scheduler.get_schedule(**args)
    if schedule["State"] != "DISABLED":
        fields = {
            k: schedule[k]
            for k in (
                "Description",
                "EndDate",
                "FlexibleTimeWindow",
                "KmsKeyArn",
                "ScheduleExpression",
                "ScheduleExpressionTimezone",
                "StartDate",
                "Target",
                "ActionAfterCompletion",
            )
            if k in schedule
        }
        scheduler.update_schedule(**args, **fields, State="DISABLED")
    response = cf.get_distribution_config(Id=target["distribution_id"])
    config = response["DistributionConfig"]
    if config["Enabled"]:
        config["Enabled"] = False
        cf.update_distribution(
            Id=target["distribution_id"], IfMatch=response["ETag"], DistributionConfig=config
        )
    deadline = timer() + 720
    while True:
        distribution = cf.get_distribution(Id=target["distribution_id"])["Distribution"]
        frontend_closed = (
            not distribution["DistributionConfig"]["Enabled"]
            and distribution["Status"] == "Deployed"
        )
        if frontend_closed:
            break
        if timer() >= deadline:
            raise RuntimeError("ClosureReadbackDeadlineExceeded")
        pause(30)
    observed = {
        "api_closed": api.get_api(ApiId=target["api_id"])["DisableExecuteApiEndpoint"],
        "mappings_closed": all(
            lambdas.get_event_source_mapping(UUID=u)["State"] == "Disabled"
            for u in target["mappings"]
        ),
        "recovery_closed": scheduler.get_schedule(**args)["State"] == "DISABLED",
        "frontend_closed": frontend_closed,
    }
    if not all(observed.values()):
        raise RuntimeError("ClosureReadbackFailed")
    alarms = target["alarms"]
    clients["cloudwatch"].delete_alarms(AlarmNames=alarms)
    remaining = clients["cloudwatch"].describe_alarms(AlarmNames=alarms)
    if remaining.get("MetricAlarms") or remaining.get("CompositeAlarms"):
        raise RuntimeError("ClosureAlarmReadbackFailed")
    return {"status": "PASS_CLOSED", **observed, "alarm_count": 0}


def handler(event, context):
    target = json.loads(os.environ["INTERVIEW_CLOSURE_TARGET"])
    config = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=15)
    counter = [0]

    class BoundedClient:
        def __init__(self, client):
            self.client = client

        def __getattr__(self, name):
            def invoke(**args):
                if counter[0] >= 48 or (counter[0] >= 47 and name != "publish"):
                    raise RuntimeError("ClosureSDKCap")
                counter[0] += 1
                return getattr(self.client, name)(**args)

            return invoke

    clients = {
        name: BoundedClient(boto3.client(name, region_name="ap-northeast-1", config=config))
        for name in ("apigatewayv2", "lambda", "scheduler", "cloudfront", "cloudwatch", "sns")
    }
    try:
        result = close(target, clients)
    except Exception:
        clients["sns"].publish(
            TopicArn=target["topic"],
            Subject="ai_interview closure requires attention",
            Message=(
                "Automatic physical closure could not be verified. "
                "Access expiry gates remain active; inspect closure logs."
            ),
        )
        raise RuntimeError("AutomaticClosureUnverified") from None
    print(json.dumps(result))
    clients["sns"].publish(
        TopicArn=target["topic"], Subject="ai_interview closed", Message=json.dumps(result)
    )
    return result
