"""Outbox delivery and round-robin recovery; no polling from public GET."""

from copy import deepcopy
from dataclasses import replace
from random import uniform
from time import monotonic
from typing import Protocol
from uuid import uuid4

import boto3
from botocore.config import Config

from interview_backend.models.internal import (
    CorruptCandidate,
    IntegrityError,
    RetryExhausted,
    StorageFormatError,
    StorageUnavailable,
)
from interview_backend.repositories.budget import invocation_budget
from interview_backend.repositories.codec import PARTITIONS, canonical
from interview_backend.repositories.domain import utc_ms


class Publisher(Protocol):
    def publish(self, event: dict) -> None: ...


class FakePublisher:
    def __init__(self, behavior=None):
        self.events = []
        self.behavior = behavior

    def publish(self, event):
        if self.behavior:
            self.behavior(event)
        self.events.append(deepcopy(event))


class SQSPublisher:
    def __init__(self, client, queue_url):
        if not queue_url:
            raise ValueError("queue_url")
        self.client, self.queue_url = client, queue_url

    def publish(self, event):
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=canonical(event))

    @classmethod
    def for_aws(cls, region, queue_url):
        if not region or not queue_url:
            raise ValueError("Explicit region and queue URL required")
        client = boto3.client(
            "sqs",
            region_name=region,
            config=Config(
                retries={"total_max_attempts": 1, "mode": "standard"},
                connect_timeout=1,
                read_timeout=1,
            ),
        )
        return cls(client, queue_url)


class Dispatcher:
    def __init__(
        self,
        repository,
        publisher,
        clock=utc_ms,
        jitter=uniform,
        new_sender_id=lambda: str(uuid4()),
    ):
        self.repository, self.publisher, self.clock = repository, publisher, clock
        self.jitter, self.new_sender_id = jitter, new_sender_id

    def dispatch(self, owner, evaluation_id, generation):
        claim = self.repository.acquire_delivery(
            owner, evaluation_id, generation, self.new_sender_id()
        )
        if claim.status == "deadline_due":
            self.repository.recover(owner, evaluation_id)
            return claim.status
        if claim.status != "acquired":
            return claim.status
        delivery = claim.delivery
        if self.clock() >= min(delivery.expires_at, delivery.deadline_at):
            return "obsolete"
        try:
            self.publisher.publish(delivery.event())
        except Exception:
            attempts = self.repository.delivery_attempts(owner, evaluation_id)
            maximum = min(300000, 10000 * 2 ** min(max(attempts - 1, 0), 5))
            next_at = self.clock() + int(self.jitter(maximum / 2, maximum))
            self.repository.fail_delivery(delivery, next_at)
            return "deferred"
        return self.repository.confirm_delivery(delivery).status


class Recovery:
    def __init__(
        self,
        repository,
        dispatcher,
        clock=utc_ms,
        monotonic_clock=monotonic,
        metric=lambda classification: None,
        observe=None,
    ):
        self.repository, self.dispatcher, self.clock = repository, dispatcher, clock
        self.monotonic, self.metric = monotonic_clock, metric
        self.observe = observe

    @invocation_budget(30000)
    def tick(self, remaining_ms=None):
        started = self.monotonic()
        remaining = remaining_ms or (
            lambda: max(0, 30000 - int((self.monotonic() - started) * 1000))
        )
        finished, blocked, checkpointed = set(), set(), set()
        while remaining() > 5000 and len(finished | blocked) < 3:
            for partition in PARTITIONS:
                if partition in finished | blocked or remaining() <= 5000:
                    continue
                try:
                    snapshot = self.repository.get_cursor(partition)
                    cursor = snapshot.cursor
                    if self.observe:
                        self.observe(
                            "RecoverySweepLag",
                            max(0, self.clock() - cursor.cycle_started_at) / 1000,
                        )
                    if self.clock() - cursor.cycle_started_at > 180000:
                        self.metric("RecoverySweepLag")
                    page = self.repository.due_candidates(partition, cursor.cutoff, cursor.after)
                    after, complete = cursor.after, True
                    for candidate in page.candidates:
                        if remaining() <= 5000:
                            complete = False
                            break
                        if isinstance(candidate, CorruptCandidate):
                            self.metric(candidate.classification)
                            if candidate.key is None:
                                blocked.add(partition)
                                complete = False
                                break
                            after = candidate.key
                            continue
                        try:
                            if self.observe:
                                for name, value in self.repository.work_observation(
                                    candidate.owner, candidate.evaluation_id
                                ):
                                    self.observe(name, value)
                            self.repository.recover(candidate.owner, candidate.evaluation_id)
                            event = self.repository.dispatch_event(
                                candidate.owner, candidate.evaluation_id
                            )
                            if event:
                                self.dispatcher.dispatch(
                                    event["ownerSub"],
                                    event["evaluationId"],
                                    event["dispatchVersion"],
                                )
                        except IntegrityError, StorageFormatError:
                            self.metric("IntegrityError")
                        except StorageUnavailable, RetryExhausted:
                            self.metric("DBError")
                            blocked.add(partition)
                            complete = False
                            break
                        after = candidate.key
                    now = self.clock()
                    if complete and not page.continuation_valid:
                        self.metric("IntegrityError")
                        blocked.add(partition)
                        complete = False
                    if complete:
                        after = page.continuation
                    next_cursor = replace(cursor, after=after, updated_at=now)
                    if complete and after is None:
                        next_cursor = replace(next_cursor, cutoff=now, cycle_started_at=now)
                        finished.add(partition)
                    if not self.repository.save_cursor(snapshot, next_cursor):
                        if self.observe:
                            self.observe("RecoveryCursorConflict", 1)
                        return  # Another recovery owns the checkpoint; do not overwrite it.
                    checkpointed.add(partition)
                except StorageUnavailable, RetryExhausted:
                    self.metric("DBError")
                    blocked.add(partition)
                except IntegrityError, StorageFormatError:
                    self.metric("IntegrityError")
                    blocked.add(partition)
        if self.observe:
            if blocked:
                self.observe("RecoveryPartitionBlocked", len(blocked))
            if remaining() <= 5000 and len(finished | blocked) < 3:
                self.observe("RecoveryBudgetStop", 1)
            if len(checkpointed) == 3 and not blocked:
                self.observe("RecoveryHeartbeat", 1)
