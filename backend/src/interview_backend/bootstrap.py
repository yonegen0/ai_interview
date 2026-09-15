"""Explicit dependency wiring; each runtime owns its own in-memory state."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from interview_backend.api.handler import Handler
from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.evaluation.dispatch import Dispatcher, FakePublisher, Publisher, Recovery
from interview_backend.evaluation.provider import FakeProvider, Provider
from interview_backend.evaluation.worker import Worker
from interview_backend.repositories.base import Repository
from interview_backend.repositories.memory import MemoryRepository


@dataclass
class Runtime:
    repository: Repository
    application: Application
    handler: Handler
    worker: Worker
    provider: Provider
    publisher: Publisher
    dispatcher: Dispatcher
    recovery: Recovery


def build_runtime(
    provider: Provider | None = None,
    new_id: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
    repository: Repository | None = None,
    mode: str = "memory",
    region: str | None = None,
    table: str | None = None,
    publisher: Publisher | None = None,
) -> Runtime:
    datetime_clock = clock or (lambda: datetime.now(UTC))

    def milliseconds():
        value = datetime_clock()
        if value.tzinfo is None:
            raise ValueError("Clock must be timezone aware")
        return int(value.timestamp() * 1000)

    if mode not in {"memory", "aws"}:
        raise ValueError("Unknown repository mode")
    if repository is None:
        if mode == "aws":
            from interview_backend.repositories.dynamodb import DynamoDBRepository, client_for

            if not region or not table:
                raise ValueError("AWS region and table required")
            repository = DynamoDBRepository(client_for(region), table, milliseconds)
        else:
            repository = MemoryRepository(milliseconds)
    evaluator = provider if provider is not None else FakeProvider()
    application = Application(repository, load_questions(), new_id or (lambda: str(uuid4())))
    worker = Worker(repository, evaluator, milliseconds)
    publisher = publisher if publisher is not None else FakePublisher()
    dispatcher = Dispatcher(repository, publisher, milliseconds)
    recovery = Recovery(repository, dispatcher, milliseconds)
    return Runtime(
        repository,
        application,
        Handler(application),
        worker,
        evaluator,
        publisher,
        dispatcher,
        recovery,
    )
