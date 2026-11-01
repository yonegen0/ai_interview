"""A fenced single-call STAR worker. Storage uncertainty never retries generation."""

from time import monotonic
from uuid import uuid4

from interview_backend.evaluation.openai_provider import Deadline, ProviderFailure
from interview_backend.models.internal import StorageError
from interview_backend.operational_logs import log_provider_usage
from interview_backend.star_assist.live_provider import PROVIDER_IDS
from interview_backend.star_assist.models import StarResult
from interview_backend.star_assist.provider import FakeStarProvider, validate_fake_facts


class StarWorker:
    def __init__(
        self,
        repository,
        provider=None,
        monotonic_clock=monotonic,
        metric=lambda name: None,
        authorize_owner=None,
    ):
        self.repository = repository
        self.provider = provider or FakeStarProvider()
        if self.provider.provider_id not in PROVIDER_IDS | {"fake"}:
            raise ValueError("StarProviderConfiguration")
        self.authorize_owner = authorize_owner
        self.monotonic = monotonic_clock
        self.metric = metric

    def run(self, owner, identifier, generation=1, remaining_ms=None):
        lease = self.repository.star_claim(
            owner, identifier, generation, str(uuid4()), self.provider.provider_id
        )
        if lease is None:
            return False
        if (remaining_ms is not None and remaining_ms() < 50000) or (
            lease.deadline_at - self.repository.clock() < 50000
        ):
            return self.repository.star_finish(lease, "FAILED_BEFORE_START")
        if self.authorize_owner:
            try:
                self.authorize_owner(owner)
            except Exception:
                return self.repository.star_finish(lease, "FAILED_BEFORE_START")
        # Retry only the storage observation for the same lease, never the Provider.
        started = False
        for _ in range(2):
            try:
                if self.provider.provider_id == "fake":
                    started = self.repository.star_start(lease)
                else:
                    settings = self.provider.transport.settings
                    started = self.repository.star_start(
                        lease,
                        monthly_user_limit=settings.monthly_user_limit,
                        monthly_global_limit=settings.monthly_global_limit,
                    )
                break
            except StorageError:
                continue
        if not started:
            return False
        began = self.monotonic()
        try:
            if self.provider.provider_id == "fake":
                raw = self.provider.generate(lease.question, lease.input)
                result = StarResult.model_validate(raw)
                validate_fake_facts(lease.input, result)
            else:
                seconds = min(
                    40,
                    (lease.lock_expires_at - self.repository.clock()) / 1000 - 10,
                    (lease.deadline_at - self.repository.clock()) / 1000 - 10,
                    remaining_ms() / 1000 - 10 if remaining_ms else 40,
                )
                deadline = Deadline(began + seconds, self.monotonic)
                result = StarResult.model_validate(
                    self.provider.generate_with_deadline(lease.question, lease.input, deadline)
                )
            if self.monotonic() - began >= 40:
                raise TimeoutError
            status = "SUCCEEDED" if result.status == "ready" else "NEEDS_INFORMATION"
        except TimeoutError:
            result, status = None, "OUTCOME_UNKNOWN"
        except ProviderFailure as exc:
            result = None
            status = (
                "OUTCOME_UNKNOWN"
                if exc.uncertain or exc.kind == "TIMEOUT"
                else "FAILED_AFTER_START"
            )
        except Exception:
            result, status = None, "FAILED_AFTER_START"
        if self.provider.provider_id.startswith("star:"):
            log_provider_usage(
                "bedrock"
                if self.provider.provider_id.startswith("star:bedrock:")
                else "anthropic"
                if self.provider.provider_id.startswith("star:anthropic:")
                else "openai",
                getattr(self.provider, "last_observation", None),
                generation_id=identifier,
            )
        for _ in range(2):
            try:
                finished = self.repository.star_finish(lease, status, result)
                if finished and status == "OUTCOME_UNKNOWN":
                    self.metric("OutcomeUnknown")
                return finished
            except StorageError:
                continue
        return False
