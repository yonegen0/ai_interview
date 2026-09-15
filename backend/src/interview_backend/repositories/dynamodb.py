"""DynamoDB single-table adapter with bounded CAS transactions and strong reads."""

from copy import deepcopy
from random import uniform
from time import monotonic, sleep
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from interview_backend.models.internal import (
    Candidate,
    CandidatePage,
    CorruptCandidate,
    IntegrityError,
    RetryExhausted,
    StorageFormatError,
    StorageUnavailable,
)
from interview_backend.repositories.budget import CommitWindowExpired, remaining_budget
from interview_backend.repositories.codec import (
    PARTITIONS,
    canonical,
    decode,
    encode,
    from_wire,
    key,
    to_wire,
    validate_cursor_key,
    validate_key,
)
from interview_backend.repositories.domain import DomainRepository, utc_ms


class ConditionalConflict(Exception):
    pass


def client_for(region):
    if not region:
        raise ValueError("AWS region required")
    return boto3.client(
        "dynamodb",
        region_name=region,
        config=Config(
            retries={"total_max_attempts": 1, "mode": "standard"},
            connect_timeout=0.2,
            read_timeout=0.2,
        ),
    )


def table_definition(name):
    """Used only by explicitly selected integration fixtures, never bootstrap."""
    return {
        "TableName": name,
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [
            {"AttributeName": k, "AttributeType": "S"} for k in ("PK", "SK", "work_pk", "work_sk")
        ],
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "WorkIndex",
                "KeySchema": [
                    {"AttributeName": "work_pk", "KeyType": "HASH"},
                    {"AttributeName": "work_sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            }
        ],
        "StreamSpecification": {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
    }


class DynamoUnit:
    def __init__(self, repository, deadline):
        self.repo, self.deadline = repository, deadline
        self.reads, self.writes = {}, {}
        self.ignored = set()
        self.frozen = False
        self.window = None

    def _remember(self, reference, item):
        if not item:
            self.reads[reference] = (None, None)
        else:
            native = from_wire(item)
            if any(native[k] != v for k, v in key(*reference).items()):
                raise IntegrityError("requested_key")
            self.reads[reference] = decode(native)
        return deepcopy(self.reads[reference][0])

    def get(self, reference):
        if reference not in self.reads:
            response = self.repo._call(
                "get_item",
                self.deadline,
                TableName=self.repo.table,
                Key=to_wire(key(*reference)),
                ConsistentRead=True,
            )
            return self._remember(reference, response.get("Item"))
        return deepcopy(self.reads[reference][0])

    def many(self, references):
        if self.frozen:
            return [self.get(r) for r in references]
        response = self.repo._call(
            "transact_get_items",
            self.deadline,
            TransactItems=[
                {"Get": {"TableName": self.repo.table, "Key": to_wire(key(*r))}} for r in references
            ],
        )
        if len(response.get("Responses", [])) != len(references):
            raise StorageFormatError("transaction_read_count")
        return [
            self._remember(r, value.get("Item"))
            for r, value in zip(references, response["Responses"], strict=True)
        ]

    def revision(self, reference):
        return self.reads[reference][1]

    def refresh(self, reference):
        self.reads.pop(reference, None)
        return self.get(reference)

    def ignore_dependency(self, reference):
        self.ignored.add(reference)

    def put(self, reference, record):
        if reference not in self.reads:
            self.get(reference)
        self.writes[reference] = record

    def new(self, reference, record):
        # No read is necessary: absence is proved by the atomic Put condition.
        if reference in self.reads and self.reads[reference][0] is not None:
            raise IntegrityError("id_collision")
        self.reads[reference] = (None, None)
        self.writes[reference] = record

    def actions(self):
        actions = []
        for reference, (_record, revision) in self.reads.items():
            if reference not in self.writes and (
                reference[0] == "Attempt" or reference in self.ignored
            ):
                continue  # Immutable and never deleted in P3.
            values = {":r": revision, ":k": reference[0], ":v": 1}
            condition = (
                "attribute_not_exists(PK)"
                if revision is None
                else ("attribute_exists(PK) AND rev = :r AND kind = :k AND schema_version = :v")
            )
            action = {"TableName": self.repo.table, "ConditionExpression": condition}
            if revision is not None:
                action["ExpressionAttributeValues"] = to_wire(values)
            if reference in self.writes:
                item = encode(
                    reference[0], self.writes[reference], 0 if revision is None else revision + 1
                )
                action["Item"] = to_wire(item)
                actions.append({"Put": action})
            else:
                action["Key"] = to_wire(key(*reference))
                actions.append({"ConditionCheck": action})
        return actions


class DynamoDBRepository(DomainRepository):
    def __init__(
        self,
        client,
        table,
        clock=utc_ms,
        monotonic_clock=monotonic,
        sleeper=sleep,
        jitter=uniform,
        token_factory=lambda: str(uuid4()),
    ):
        if not table or client is None:
            raise ValueError("Explicit DynamoDB client and table required")
        super().__init__(clock)
        self.client, self.table = client, table
        self.monotonic, self.sleep, self.jitter, self.token = (
            monotonic_clock,
            sleeper,
            jitter,
            token_factory,
        )

    def _call(self, method, deadline, *, window=None, **kwargs):
        remaining = remaining_budget.get()
        if deadline - self.monotonic() < 0.4 or (remaining is not None and remaining() < 400):
            raise RetryExhausted("storage_budget")
        if window is not None and not window.valid(self.clock()):
            raise CommitWindowExpired
        try:
            return getattr(self.client, method)(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            reasons = {r.get("Code") for r in exc.response.get("CancellationReasons", [])}
            if code == "ConditionalCheckFailedException" or (
                code == "TransactionCanceledException"
                and reasons <= {"None", "ConditionalCheckFailed", "TransactionConflict"}
                and reasons & {"ConditionalCheckFailed", "TransactionConflict"}
            ):
                raise ConditionalConflict from None
            if code in {"ValidationException", "IdempotentParameterMismatchException"} or (
                code == "TransactionCanceledException" and "ValidationError" in reasons
            ):
                raise StorageFormatError("storage_validation") from None
            raise StorageUnavailable("storage_request") from None
        except BotoCoreError:
            raise StorageUnavailable("storage_transport") from None

    def _atomic(self, operation, *, temporal=False, conflict_once=False):
        remaining = remaining_budget.get()
        deadline = self.monotonic() + min(5, remaining() / 1000 if remaining else 5)
        previous, token, last_error = None, None, None
        sends = 0
        # Four observations allow a final confirmation after the third write.
        for observation in range(4):
            unit = DynamoUnit(self, deadline)
            try:
                result = operation(unit)
                if not unit.writes:
                    return deepcopy(result)
                if temporal:
                    # Re-evaluate time immediately before sending, using this coherent snapshot.
                    unit.frozen = True
                    unit.writes.clear()
                    unit.ignored.clear()
                    unit.window = None
                    result = operation(unit)
                    if not unit.writes:
                        return deepcopy(result)
                actions = unit.actions()
                if sends >= 3 or observation == 3:
                    break
                signature = canonical(actions)
                if signature != previous:
                    previous, token = signature, self.token()
                try:
                    self._call(
                        "transact_write_items",
                        deadline,
                        window=unit.window,
                        TransactItems=actions,
                        ClientRequestToken=token,
                    )
                except CommitWindowExpired:
                    continue
                sends += 1
                return deepcopy(result)
            except ConditionalConflict:
                sends += 1 if unit.writes else 0
                if conflict_once:
                    return False
                last_error = RetryExhausted("conditional_retry")
            except StorageUnavailable:
                sends += 1 if unit.writes else 0
                last_error = StorageUnavailable("storage_request")
            if observation < 2:
                delay = self.jitter(0, (0.1, 0.2)[observation])
                if deadline - self.monotonic() < delay + 0.4:
                    break
                self.sleep(delay)
        if isinstance(last_error, StorageUnavailable):
            raise last_error
        raise RetryExhausted("storage_retry")

    def due_candidates(self, partition, cutoff, cursor=None, limit=100):
        if partition not in PARTITIONS or limit != 100:
            raise ValueError("query_parameters")
        request = {
            "TableName": self.table,
            "IndexName": "WorkIndex",
            "KeyConditionExpression": "work_pk = :p AND work_sk <= :cutoff",
            "ExpressionAttributeValues": to_wire({":p": partition, ":cutoff": f"{cutoff:013d}#~"}),
            "Limit": 100,
            "ScanIndexForward": True,
        }
        if cursor is not None:
            validate_cursor_key(cursor, partition)
            request["ExclusiveStartKey"] = to_wire(cursor)
        response = self._call("query", self.monotonic() + 5, **request)
        candidates = []
        for raw in response.get("Items", []):
            try:
                item = from_wire(raw)
                validate_cursor_key(item, partition)
            except StorageFormatError, ValueError, TypeError, KeyError:
                candidates.append(CorruptCandidate(None))
                continue
            try:
                validate_key(item, partition)
            except StorageFormatError:
                candidates.append(CorruptCandidate(item))
                continue
            eid = item["SK"].split("#", 1)[1]
            candidates.append(Candidate(item["PK"][5:], eid, item))
        try:
            continuation = (
                from_wire(response["LastEvaluatedKey"])
                if response.get("LastEvaluatedKey")
                else None
            )
            if continuation is not None:
                validate_cursor_key(continuation, partition)
        except StorageFormatError, ValueError, TypeError, KeyError:
            return CandidatePage(tuple(candidates), None, False)
        return CandidatePage(tuple(candidates), continuation)
