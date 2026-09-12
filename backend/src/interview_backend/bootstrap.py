"""Explicit dependency wiring; each runtime owns its own in-memory state."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from interview_backend.api.handler import Handler
from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.evaluation.provider import FakeProvider, Provider
from interview_backend.evaluation.worker import Worker
from interview_backend.repositories.memory import MemoryRepository


@dataclass
class Runtime:
    repository: MemoryRepository
    application: Application
    handler: Handler
    worker: Worker
    provider: Provider


def build_runtime(
    provider: Provider | None = None,
    new_id: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Runtime:
    repository = MemoryRepository()
    evaluator = provider if provider is not None else FakeProvider()
    application = Application(repository, load_questions(), new_id or (lambda: str(uuid4())))
    worker = Worker(repository, evaluator, clock or (lambda: datetime.now(UTC)))
    return Runtime(repository, application, Handler(application), worker, evaluator)
