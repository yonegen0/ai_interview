"""Allowlisted EMF observations, with no user-controlled names or dimensions."""

import json
import math
from time import time

from interview_backend.models.internal import IntegrityError, StorageError, StorageFormatError

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
        if component not in {"api", "worker", "dispatcher"} or environment not in {"dev", "test"}:
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
            try:
                result = target(*args, **kwargs)
            except IntegrityError, StorageFormatError:
                self.metrics.emit("IntegrityError")
                raise
            except StorageError:
                self.metrics.emit("DBError")
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
                if evaluation.failure_reason == "OUTCOME_UNKNOWN":
                    self.metrics.emit("OutcomeUnknown")
            if status == "lost_lease":
                self.metrics.emit("LostLease")
            if name == "claim" and status in {"busy", "terminal", "stale"}:
                self.metrics.emit("DuplicateSuppressed")
            if name == "fail_delivery" and status == "applied":
                self.metrics.emit("DeliveryFailure")
            return result

        return invoke
