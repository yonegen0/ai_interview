"""DynamoDB single-table adapter with bounded CAS transactions and strong reads."""

from copy import deepcopy
from random import uniform
from time import monotonic, sleep
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from interview_backend.models.internal import (
    BusinessError,
    Candidate,
    CandidatePage,
    CorruptCandidate,
    IntegrityError,
    Reply,
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
from interview_backend.repositories.domain import (
    PREVIOUS_ANSWER_MAX_ATTEMPTS,
    DomainRepository,
    utc_ms,
)

PREVIOUS_ANSWER_PAGE_SIZE = 100


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

    def exists(self, reference):
        """Read keys only; an absent record remains a transactional dependency."""
        if reference in self.reads:
            return self.reads[reference][0] is not None
        expected = key(*reference)
        response = self.repo._call(
            "get_item",
            self.deadline,
            TableName=self.repo.table,
            Key=to_wire(expected),
            ConsistentRead=True,
            ProjectionExpression="#pk, #sk",
            ExpressionAttributeNames={"#pk": "PK", "#sk": "SK"},
        )
        item = response.get("Item")
        if item:
            native = from_wire(item)
            if any(native.get(k) != v for k, v in expected.items()):
                raise IntegrityError("requested_key")
            return True
        self.reads[reference] = (None, None)
        return False

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

    def previous_answer(self, owner: str, question_id: str) -> Reply:
        """Read only this owner's attempts, and never treat truncated history as absence."""
        deadline = self.monotonic() + 4.5
        request = {
            "TableName": self.table,
            "KeyConditionExpression": "PK = :owner AND begins_with(SK, :attempt)",
            "ExpressionAttributeValues": to_wire(
                {":owner": f"USER#{owner}", ":attempt": "ATTEMPT#"}
            ),
            "ConsistentRead": True,
            "Limit": PREVIOUS_ANSWER_PAGE_SIZE,
        }
        latest = None
        evaluated = 0
        previous_sort_key = ""
        while evaluated < PREVIOUS_ANSWER_MAX_ATTEMPTS:
            page = self._call("query", deadline, **request)
            items = page.get("Items", [])
            if not isinstance(items, list) or len(items) > PREVIOUS_ANSWER_PAGE_SIZE:
                raise StorageFormatError("previous_answer_page")
            evaluated += len(items)
            if evaluated > PREVIOUS_ANSWER_MAX_ATTEMPTS:
                raise BusinessError(503, "PREVIOUS_ANSWER_UNAVAILABLE")
            for raw in items:
                item = from_wire(raw)
                record, _ = decode(item)
                if item.get("kind") != "Attempt" or record.owner != owner:
                    raise StorageFormatError("previous_answer_owner")
                if record.question.id == question_id and (
                    latest is None
                    or (record.created_at, record.id) > (latest.created_at, latest.id)
                ):
                    latest = record
            cursor = page.get("LastEvaluatedKey")
            if not cursor:
                return Reply(
                    200, {"questionId": question_id, "answer": latest.answer if latest else None}
                )
            native_cursor = from_wire(cursor)
            sort_key = native_cursor.get("SK")
            if (
                native_cursor.get("PK") != f"USER#{owner}"
                or not isinstance(sort_key, str)
                or not sort_key.startswith("ATTEMPT#")
                or sort_key <= previous_sort_key
            ):
                raise StorageFormatError("previous_answer_cursor")
            previous_sort_key = sort_key
            request["ExclusiveStartKey"] = cursor
        raise BusinessError(503, "PREVIOUS_ANSWER_UNAVAILABLE")

    def practice_progress(self, owner: str, defaults) -> Reply:
        from interview_backend.repositories.practice_progress import (
            PROGRESS_MAX_RECORDS,
            PROGRESS_PAGE_SIZE,
            count_completed_questions,
        )

        bank = self.get_question_bank(defaults)
        active_ids = {q["id"] for q in bank["questions"]}
        if not active_ids:
            return Reply(200, {
                "bankVersion": bank["version"], "totalQuestions": 0,
                "completedQuestions": 0,
            })

        deadline = self.monotonic() + 4.5

        def load(prefix, kind):
            records = []
            request = {
                "TableName": self.table,
                "KeyConditionExpression": "PK = :owner AND begins_with(SK, :prefix)",
                "ExpressionAttributeValues": to_wire({
                    ":owner": f"USER#{owner}", ":prefix": prefix,
                }),
                "ConsistentRead": True,
                "Limit": PROGRESS_PAGE_SIZE,
            }
            previous = ""
            while True:
                page = self._call("query", deadline, **request)
                items = page.get("Items", [])
                if not isinstance(items, list) or len(items) > PROGRESS_PAGE_SIZE:
                    raise StorageFormatError("progress_page")
                if len(records) + len(items) > PROGRESS_MAX_RECORDS:
                    raise BusinessError(503, "PRACTICE_PROGRESS_UNAVAILABLE")
                for raw in items:
                    item = from_wire(raw)
                    record, _ = decode(item)
                    if item.get("kind") != kind or record.owner != owner:
                        raise StorageFormatError("progress_owner")
                    records.append(record)
                cursor = page.get("LastEvaluatedKey")
                if not cursor:
                    return records
                if len(records) >= PROGRESS_MAX_RECORDS:
                    raise BusinessError(503, "PRACTICE_PROGRESS_UNAVAILABLE")
                native = from_wire(cursor)
                position = native.get("SK")
                if (
                    native.get("PK") != f"USER#{owner}"
                    or not isinstance(position, str)
                    or not position.startswith(prefix)
                    or position <= previous
                ):
                    raise StorageFormatError("progress_cursor")
                previous = position
                request["ExclusiveStartKey"] = cursor

        attempts = load("ATTEMPT#", "Attempt")
        evaluations = load("EVALUATION#", "Evaluation")
        completed = count_completed_questions(owner, active_ids, attempts, evaluations)
        return Reply(200, {
            "bankVersion": bank["version"], "totalQuestions": len(active_ids),
            "completedQuestions": completed,
        })

    def history(self, owner: str, params: dict) -> Reply:
        """Read complete bounded key-prefix ranges; a truncated range is never 'latest'."""
        from interview_backend.repositories.history import (
            HISTORY_MAX_RECORDS,
            HISTORY_PAGE_SIZE,
            build_history,
            parse_history_query,
        )

        now = self.clock()
        mode, _, _, _, _ = parse_history_query(owner, params, now)
        prefixes = (
            ("ATTEMPT#", "Attempt"),
            ("EVALUATION#", "Evaluation"),
            ("COACHING#", "AttemptCoaching"),
            ("ASSIST_HISTORY#", "AssistHistory"),
            ("STAR_GENERATION#", "StarGeneration"),
        )
        if mode in {"normal", "coaching"}:
            prefixes = prefixes[:3]
        elif mode not in {"all"}:
            prefixes = prefixes[3:]
        deadline = self.monotonic() + 4.5
        selected = {kind: [] for _, kind in prefixes}
        for prefix, kind in prefixes:
            request = {
                "TableName": self.table,
                "KeyConditionExpression": "PK = :owner AND begins_with(SK, :prefix)",
                "ExpressionAttributeValues": to_wire(
                    {
                        ":owner": f"USER#{owner}",
                        ":prefix": prefix,
                    }
                ),
                "ConsistentRead": True,
                "Limit": HISTORY_PAGE_SIZE,
            }
            previous = ""
            while True:
                page = self._call("query", deadline, **request)
                items = page.get("Items", [])
                if not isinstance(items, list) or len(items) > HISTORY_PAGE_SIZE:
                    raise StorageFormatError("history_page")
                for raw in items:
                    item = from_wire(raw)
                    record, _ = decode(item)
                    if item.get("kind") != kind or record.owner != owner:
                        raise StorageFormatError("history_owner")
                    selected[kind].append(record)
                cursor = page.get("LastEvaluatedKey")
                if cursor and len(selected[kind]) >= HISTORY_MAX_RECORDS:
                    raise BusinessError(503, "HISTORY_SEARCH_LIMIT")
                if not cursor:
                    break
                native = from_wire(cursor)
                position = native.get("SK")
                if (
                    native.get("PK") != f"USER#{owner}"
                    or not isinstance(position, str)
                    or not position.startswith(prefix)
                    or position <= previous
                ):
                    raise StorageFormatError("history_cursor")
                previous = position
                request["ExclusiveStartKey"] = cursor
        return build_history(
            owner,
            params,
            now,
            *(
                selected.get(kind, [])
                for kind in (
                    "Attempt",
                    "Evaluation",
                    "AttemptCoaching",
                    "AssistHistory",
                    "StarGeneration",
                )
            ),
        )

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
