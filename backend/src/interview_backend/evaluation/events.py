"""Strict internal event schemas and source-specific Lambda adapters."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from interview_backend.models.internal import StorageError
from interview_backend.models.public import Identifier
from interview_backend.repositories.budget import storage_budget
from interview_backend.repositories.codec import decode, from_wire


class EvaluationRequested(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    eventVersion: int = Field(ge=1, le=1)
    type: Literal["EvaluationRequested"]
    ownerSub: str = Field(min_length=1)
    evaluationId: Identifier
    dispatchVersion: int = Field(ge=1)


class RecoveryTick(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    eventVersion: int = Field(ge=1, le=1)
    type: Literal["RecoveryTick"]


class InternalHandlers:
    def __init__(
        self,
        worker,
        dispatcher,
        recovery,
        *,
        queue_arn,
        stream_arn,
        scheduler_arn,
        metric=lambda classification: None,
        sources=None,
    ):
        self.sources = set(sources) if sources is not None else {"sqs", "streams", "scheduler"}
        arns = {"sqs": queue_arn, "streams": stream_arn, "scheduler": scheduler_arn}
        if (
            not self.sources
            or not self.sources <= arns.keys()
            or not all(arns[s] for s in self.sources)
        ):
            raise ValueError("Source ARNs required")
        self.worker, self.dispatcher, self.recovery = worker, dispatcher, recovery
        self.queue_arn, self.stream_arn, self.scheduler_arn = queue_arn, stream_arn, scheduler_arn
        self.metric = metric

    def sqs(self, event, context):
        if (
            "sqs" not in self.sources
            or not isinstance(event, dict)
            or not isinstance(event.get("Records"), list)
            or not event["Records"]
        ):
            raise ValueError("InvalidEvent")
        failures = []
        for record in event["Records"]:
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("messageId"), str)
                or not record["messageId"]
            ):
                raise ValueError("InvalidEvent")
            try:
                if (
                    record.get("eventSource") != "aws:sqs"
                    or record.get("eventSourceARN") != self.queue_arn
                ):
                    raise ValueError("source")
                message = EvaluationRequested.model_validate(json.loads(record["body"]))
                self.worker.run(
                    message.ownerSub,
                    message.evaluationId,
                    message.dispatchVersion,
                    context.get_remaining_time_in_millis,
                )
            except ValueError, KeyError, TypeError:
                self.metric("InvalidEvent")
                failures.append({"itemIdentifier": record["messageId"]})
            except StorageError:
                self.metric("WorkerBatchFailure")
                failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": failures}

    def streams(self, event, context):
        if (
            "streams" not in self.sources
            or not isinstance(event, dict)
            or not isinstance(event.get("Records"), list)
            or not event["Records"]
        ):
            raise ValueError("InvalidEvent")
        failures = []
        for record in event["Records"]:
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("dynamodb"), dict)
                or not isinstance(record["dynamodb"].get("SequenceNumber"), str)
                or not record["dynamodb"]["SequenceNumber"]
            ):
                raise ValueError("InvalidEvent")
            try:
                if (
                    record.get("eventSource") != "aws:dynamodb"
                    or record.get("eventSourceARN") != self.stream_arn
                ):
                    raise ValueError("source")
                if record.get("eventName") == "REMOVE":
                    continue
                if record.get("eventName") not in {"INSERT", "MODIFY"}:
                    raise ValueError("stream_event")
                image = from_wire(record["dynamodb"]["NewImage"])
                if image.get("kind") != "Dispatch":
                    continue
                decode(image)
                new = json.loads(image["data"])
                old_image = from_wire(record["dynamodb"].get("OldImage", {}))
                old = json.loads(old_image["data"]) if old_image else {}
                if new["status"] != "PENDING" or not (
                    record["eventName"] == "INSERT"
                    or old.get("status") != "PENDING"
                    or old.get("generation") != new["generation"]
                ):
                    continue
                message = EvaluationRequested(
                    eventVersion=1,
                    type="EvaluationRequested",
                    ownerSub=new["owner"],
                    evaluationId=new["id"],
                    dispatchVersion=new["generation"],
                )
                with storage_budget(context.get_remaining_time_in_millis):
                    self.dispatcher.dispatch(
                        message.ownerSub, message.evaluationId, message.dispatchVersion
                    )
            except ValueError, KeyError, TypeError:
                self.metric("InvalidEvent")
                failures.append({"itemIdentifier": record["dynamodb"]["SequenceNumber"]})
            except StorageError:
                self.metric("StreamBatchFailure")
                failures.append({"itemIdentifier": record["dynamodb"]["SequenceNumber"]})
        return {"batchItemFailures": failures}

    def scheduler(self, event, context, *, source_arn):
        # Source identity is trusted adapter configuration, never a payload field.
        if "scheduler" not in self.sources or source_arn != self.scheduler_arn:
            raise ValueError("source")
        RecoveryTick.model_validate(event)
        self.recovery.tick(context.get_remaining_time_in_millis)
