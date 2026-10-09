"""Allowlisted EMF observations, with no user-controlled names or dimensions."""

import json
import math
from time import time

from interview_backend.models.internal import IntegrityError, StorageError, StorageFormatError
from interview_backend.operational_logs import log_event

UNITS = {
    **dict.fromkeys(
        (
            "ApiRequest",
            "ApiFailure",
            "Unauthorized",
            "InvalidConfiguration",
            "InvalidEvent",
            "InternalInvocationFailed",
            "WorkerBatchFailure",
            "StreamBatchFailure",
            "DBError",
            "IntegrityError",
            "MissingEvaluation",
            "RecoveryHeartbeat",
            "RecoveryBudgetStop",
            "RecoveryCursorConflict",
            "RecoveryPartitionBlocked",
            "ExpiredLease",
            "DeadlineOverdue",
            "OutcomeUnknown",
            "EvaluationCompleted",
            "EvaluationFailed",
            "DuplicateSuppressed",
            "LostLease",
            "DeliveryFailure",
        ),
        "Count",
    ),
    "ApiDuration": "Milliseconds",
    "EvaluationLatency": "Milliseconds",
    "PendingAge": "Seconds",
    "QueuedAge": "Seconds",
    "RecoverySweepLag": "Seconds",
}


class Metrics:
    def __init__(self, component, *, environment="dev", sink=print, clock=time):
        if component not in {"api", "worker", "dispatcher", "admin"} or environment not in {
            "dev",
            "test",
        }:
            raise ValueError("InvalidMetricDimension")
        self.component, self.environment, self.sink, self.clock = (
            component,
            environment,
            sink,
            clock,
        )

    def emit(self, name, value=1):
        if (
            name not in UNITS
            or type(value) not in {int, float}
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("InvalidMetric")
        item = {
            "_aws": {
                "Timestamp": int(self.clock() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": "AIInterview",
                        "Dimensions": [["Project", "Environment", "Component"]],
                        "Metrics": [{"Name": name, "Unit": UNITS[name]}],
                    }
                ],
            },
            "Project": "ai-interview",
            "Environment": self.environment,
            "Component": self.component,
            name: value,
        }
        try:
            self.sink(json.dumps(item, allow_nan=False, separators=(",", ":")))
        except Exception:
            # Telemetry delivery must never cause a business retry or expose sink exceptions.
            pass

    def classification(self, name):
        # The existing callback reports SweepLag as a classification, not a duration.
        if name == "RecoverySweepLag":
            return
        self.emit(name)


class ObservedRepository:
    """Observe committed operation results; never read/write again for terminal counters."""

    def __init__(self, repository, metrics):
        self.repository, self.metrics = repository, metrics

    def __getattr__(self, name):
        target = getattr(self.repository, name)
        if not callable(target) or name.startswith("_"):
            return target

        def invoke(*args, **kwargs):
            evaluation_id = kwargs.get("evaluation_id")
            if args and name in {
                "finish",
                "mark_call_started",
                "confirm_delivery",
                "fail_delivery",
            }:
                evaluation_id = getattr(args[0], "evaluation_id", None)
            elif len(args) > 1 and name in {
                "recover",
                "claim",
                "acquire_delivery",
                "evaluation_contract_version",
            }:
                evaluation_id = args[1]
            try:
                result = target(*args, **kwargs)
            except IntegrityError, StorageFormatError:
                self.metrics.emit("IntegrityError")
                log_event("storage_failure", evaluationId=evaluation_id)
                raise
            except StorageError:
                self.metrics.emit("DBError")
                log_event("storage_failure", evaluationId=evaluation_id)
                raise
            status = getattr(result, "status", None)
            evaluation = getattr(result, "evaluation", None)
            if (
                name in {"finish", "recover"}
                and status in {"applied", "failed"}
                and evaluation is not None
            ):
                self.metrics.emit(
                    "EvaluationCompleted"
                    if evaluation.status == "completed"
                    else "EvaluationFailed"
                )
                self.metrics.emit(
                    "EvaluationLatency", max(0, evaluation.finished_at - evaluation.created_at)
                )
                provider_id = getattr(evaluation.execution_config, "provider_id", None)
                log_event(
                    "evaluation_terminal",
                    evaluationId=evaluation.id,
                    attemptId=evaluation.attempt_id,
                    status=evaluation.status,
                    failureReason=evaluation.failure_reason,
                    elapsedMs=max(0, evaluation.finished_at - evaluation.created_at),
                    provider="openai"
                    if provider_id and provider_id.startswith("openai")
                    else ("fake" if provider_id == "fake" else "unknown"),
                )
                if evaluation.failure_reason == "OUTCOME_UNKNOWN":
                    self.metrics.emit("OutcomeUnknown")
            if name == "claim" and status == "acquired":
                lease = getattr(result, "lease", None)
                log_event(
                    "worker_claimed",
                    evaluationId=evaluation_id,
                    generation=getattr(lease, "generation", None),
                )
            if status == "lost_lease":
                self.metrics.emit("LostLease")
            if name == "claim" and status in {"busy", "terminal", "stale"}:
                self.metrics.emit("DuplicateSuppressed")
            if name == "fail_delivery" and status == "applied":
                self.metrics.emit("DeliveryFailure")
            body = getattr(result, "body", None)
            if name.startswith("accept") or name.startswith("retry_coaching"):
                if isinstance(body, dict) and getattr(result, "status", None) == 202:
                    log_event(
                        "evaluation_accepted",
                        evaluationId=body.get("evaluationId"),
                        attemptId=body.get("attemptId"),
                    )
            if name in {"confirm_delivery", "fail_delivery"} and status == "applied":
                log_event(
                    "dispatch_confirmed" if name == "confirm_delivery" else "dispatch_deferred",
                    evaluationId=evaluation_id,
                )
            if name == "recover" and status == "requeued":
                log_event("work_requeued", evaluationId=evaluation_id)
            return result

        return invoke
