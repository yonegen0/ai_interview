"""Role-specific Lambda composition. Importing this module does not access credentials."""

import os
from functools import lru_cache
from time import monotonic
from uuid import uuid4

from interview_backend.api.handler import Handler, error
from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.aws_settings import AwsSettings
from interview_backend.evaluation.dispatch import Dispatcher, Recovery, SQSPublisher
from interview_backend.evaluation.events import InternalHandlers
from interview_backend.evaluation.provider import FakeProvider
from interview_backend.evaluation.worker import Worker
from interview_backend.observability import Metrics, ObservedRepository
from interview_backend.repositories.budget import storage_budget
from interview_backend.repositories.dynamodb import DynamoDBRepository, client_for


class ApiEntry:
    def __init__(self, settings, handler, metrics=None):
        self.settings, self.handler = settings, handler
        self.metrics = metrics or Metrics("api")

    def __call__(self, event, context):
        started = monotonic()
        try:
            self.settings.require_invocation(context, {"live"})
            request = event.get("requestContext") or {}
            claims = ((request.get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
            if not (
                event.get("version") == "2.0"
                and request.get("accountId") == self.settings.account
                and request.get("apiId") == self.settings.api_id
                and request.get("stage") == self.settings.stage
                and claims.get("token_use") == "access"
                and claims.get("client_id") == self.settings.client_id
                and claims.get("iss") == self.settings.issuer
                and type(claims.get("sub")) is str
                and claims["sub"].strip()
            ):
                self.metrics.emit("Unauthorized")
                return error(401, "UNAUTHORIZED")
            with storage_budget(context.get_remaining_time_in_millis):
                result = self.handler(event)
            self.metrics.emit("ApiRequest")
            if result["statusCode"] >= 500:
                self.metrics.emit("ApiFailure")
            return result
        except Exception:
            self.metrics.emit("ApiFailure")
            return error(500, "INTERNAL_SERVER_ERROR")
        finally:
            self.metrics.emit("ApiDuration", max(0, (monotonic() - started) * 1000))


class WorkerEntry:
    def __init__(self, settings, worker, metrics=None):
        self.settings = settings
        self.metrics = metrics or Metrics("worker")
        self.handlers = InternalHandlers(
            worker,
            None,
            None,
            queue_arn=settings.queue_arn,
            stream_arn=None,
            scheduler_arn=None,
            sources={"sqs"},
            metric=self.metrics.classification,
        )

    def __call__(self, event, context):
        try:
            self.settings.require_invocation(context, {"live"})
            return self.handlers.sqs(event, context)
        except Exception:
            self.metrics.emit("InternalInvocationFailed")
        raise RuntimeError("InternalInvocationFailed") from None


class DispatcherEntry:
    def __init__(self, settings, dispatcher, recovery, metrics=None):
        self.settings = settings
        self.metrics = metrics or Metrics("dispatcher")
        self.handlers = InternalHandlers(
            None,
            dispatcher,
            recovery,
            queue_arn=None,
            stream_arn=settings.stream_arn,
            scheduler_arn=settings.schedule_arn,
            sources={"streams", "scheduler"},
            metric=self.metrics.classification,
        )

    def __call__(self, event, context):
        try:
            alias = self.settings.require_invocation(context, {"streams", "recovery"})
            if alias == "streams":
                return self.handlers.streams(event, context)
            # Authorization is the scheduler execution role and qualified invocation ARN.
            # Never consume a payload-supplied source ARN as authentication.
            self.handlers.scheduler(event, context, source_arn=self.settings.schedule_arn)
            return None
        except Exception:
            self.metrics.emit("InternalInvocationFailed")
        raise RuntimeError("InternalInvocationFailed") from None


@lru_cache(maxsize=3)
def build_entry(component):
    settings = AwsSettings.load(os.environ, component)
    metrics = Metrics(
        component, environment="test" if "-test-" in settings.function_name else "dev"
    )
    repository = ObservedRepository(
        DynamoDBRepository(client_for(settings.region), settings.table), metrics
    )
    if component == "api":
        application = Application(repository, load_questions(), lambda: str(uuid4()))
        return ApiEntry(settings, Handler(application), metrics)
    if component == "worker":
        return WorkerEntry(
            settings, Worker(repository, FakeProvider(), metric=metrics.classification), metrics
        )
    publisher = SQSPublisher.for_aws(settings.region, settings.queue_url)
    dispatcher = Dispatcher(repository, publisher)
    recovery = Recovery(repository, dispatcher, metric=metrics.classification, observe=metrics.emit)
    return DispatcherEntry(settings, dispatcher, recovery, metrics)


def _invoke(component, event, context):
    try:
        entry = build_entry(component)
    except Exception:
        Metrics(component).emit("InvalidConfiguration")
        if component == "api":
            return error(500, "INTERNAL_SERVER_ERROR")
        raise RuntimeError("InvalidConfiguration") from None
    return entry(event, context)


def api_handler(event, context):
    return _invoke("api", event, context)


def worker_handler(event, context):
    return _invoke("worker", event, context)


def dispatcher_handler(event, context):
    return _invoke("dispatcher", event, context)
