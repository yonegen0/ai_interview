"""A fenced fake-only STAR worker. Storage uncertainty never retries generation."""

from time import monotonic
from uuid import uuid4

from interview_backend.models.internal import StorageError
from interview_backend.star_assist.models import StarResult
from interview_backend.star_assist.provider import FakeStarProvider, validate_fake_facts


class StarWorker:
    def __init__(
        self, repository, provider=None, monotonic_clock=monotonic, metric=lambda name: None
    ):
        self.repository = repository
        self.provider = provider or FakeStarProvider()
        if self.provider.provider_id != "fake":
            raise ValueError("StarFakeOnly")
        self.monotonic = monotonic_clock
        self.metric = metric

    def run(self, owner, identifier, generation=1, remaining_ms=None):
        lease = self.repository.star_claim(owner, identifier, generation, str(uuid4()))
        if lease is None:
            return False
        if (remaining_ms is not None and remaining_ms() < 50000) or (
            lease.deadline_at - self.repository.clock() < 50000
        ):
            return self.repository.star_finish(lease, "FAILED_BEFORE_START")
        # Retry only the storage observation for the same lease, never the Provider.
        started = False
        for _ in range(2):
            try:
                started = self.repository.star_start(lease)
                break
            except StorageError:
                continue
        if not started:
            return False
        began = self.monotonic()
        try:
            result = StarResult.model_validate(self.provider.generate(lease.question, lease.input))
            validate_fake_facts(lease.input, result)
            if self.monotonic() - began >= 40:
                raise TimeoutError
            status = "SUCCEEDED" if result.status == "ready" else "NEEDS_INFORMATION"
        except TimeoutError:
            result, status = None, "OUTCOME_UNKNOWN"
        except Exception:
            result, status = None, "FAILED_AFTER_START"
        for _ in range(2):
            try:
                finished = self.repository.star_finish(lease, status, result)
                if finished and status == "OUTCOME_UNKNOWN":
                    self.metric("OutcomeUnknown")
                return finished
            except StorageError:
                continue
        return False
