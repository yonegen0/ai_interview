"""P2 native items, strict decoding, size checks and sparse WorkIndex mapping."""

import json
import re
import types
from copy import deepcopy
from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Literal, Union, get_args, get_origin, get_type_hints

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from pydantic import BaseModel

from interview_backend.models.internal import (
    Attempt,
    Dispatch,
    Evaluation,
    ExecutionConfig,
    IdempotentReply,
    IntegrityError,
    ItemTooLarge,
    RecoveryCursor,
    Reply,
    Session,
    StorageFormatError,
)
from interview_backend.models.public import (
    ActiveAttempt,
    Created,
    Feedback,
    Question,
    SessionResponse,
    validate_id,
)

PARTITIONS = ("WORK#DISPATCH_PENDING", "WORK#DISPATCH_QUEUED", "WORK#EVALUATION_RUNNING")
KINDS = {c.__name__: c for c in (Session, Attempt, Evaluation, Dispatch, RecoveryCursor)}
KINDS["IdempotencyRecord"] = IdempotentReply
PREFIXES = dict(
    zip(
        KINDS,
        ("SESSION", "ATTEMPT", "EVALUATION", "DISPATCH", "CURSOR", "IDEMPOTENCY"),
        strict=True,
    )
)
MAX_TIME = 9999999999999
FAILURE = {"code": "EVALUATION_FAILED", "message": "Evaluation could not be completed."}
REASONS = {
    "PREPARATION_FAILED",
    "PROVIDER_FAILED",
    "PROVIDER_TIMEOUT",
    "INVALID_RESULT",
    "RESULT_TOO_LARGE",
    "OUTCOME_UNKNOWN",
    "DEADLINE_EXCEEDED",
}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    )


def primitive(value):
    if isinstance(value, BaseModel):
        # Python mode also preserves lone UTF-16 surrogates.
        return value.model_dump(exclude_unset=True)
    if is_dataclass(value):
        data = {
            f.name: primitive(getattr(value, f.name))
            for f in fields(value)
            if getattr(value, f.name) is not None
            or (isinstance(value, Session) and f.name == "active")
            or (isinstance(value, RecoveryCursor) and f.name == "after")
        }
        if isinstance(value, IdempotentReply):
            data["request_hash"] = data.pop("fingerprint")
        if isinstance(value, Evaluation):
            data.pop("prompt_version", None)  # ExecutionConfig is the durable source.
        return data
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    return value


def check_type(value, hint):
    origin, args = get_origin(hint), get_args(hint)
    if origin in (Union, types.UnionType):
        return any(check_type(value, option) for option in args)
    if origin is Literal:
        return any(type(value) is type(option) and value == option for option in args)
    if origin is tuple:
        return isinstance(value, tuple) and all(check_type(v, args[0]) for v in value)
    if hint in (str, int, dict, type(None)):
        return type(value) is hint
    return isinstance(value, hint)


def validate(record):
    hints = get_type_hints(type(record))
    for field in fields(record):
        value = getattr(record, field.name)
        if not check_type(value, hints[field.name]):
            raise StorageFormatError("invalid_type")
        if is_dataclass(value):
            validate(value)
        if isinstance(value, BaseModel):
            type(value).model_validate(value.model_dump(exclude_unset=True))
        if type(value) is int and (value < 0 or (field.name.endswith("_at") and value > MAX_TIME)):
            raise StorageFormatError("invalid_number")
    if hasattr(record, "owner") and not record.owner.strip():
        raise IntegrityError("invalid_owner")
    for name in ("id", "attempt_id", "evaluation_id", "session_id", "lock_owner", "send_owner"):
        if getattr(record, name, None) is not None:
            try:
                validate_id(getattr(record, name))
            except ValueError:
                raise StorageFormatError("invalid_id") from None
    if isinstance(record, Session):
        if not record.questions or record.number < 1 or record.updated_at < record.created_at:
            raise IntegrityError("session_state")
        for question in record.questions:
            Question.model_validate(question.model_dump())
    if isinstance(record, Attempt):
        from interview_backend.models.public import AnswerFields

        AnswerFields(answer=record.answer)
        if record.question_number < 1:
            raise IntegrityError("attempt_number")
    if isinstance(record, ExecutionConfig):
        if (
            not record.provider_id
            or not record.model_id
            or not record.prompt_version
            or record.result_schema_version != 1
            or record.provider_timeout_ms != 40000
        ):
            raise StorageFormatError("execution_config")
    if isinstance(record, Evaluation):
        terminal = record.worker_state == "terminal"
        if terminal != (record.status in {"completed", "failed"}):
            raise IntegrityError("evaluation_state")
        if (record.finished_at is not None) != terminal:
            raise IntegrityError("finished_at")
        if record.call_phase == "started" and record.call_started_at is None:
            raise IntegrityError("started_marker")
        if record.call_phase == "not_started" and record.call_started_at is not None:
            raise IntegrityError("started_marker")
        lease = (record.lock_owner, record.lock_expires_at, record.execution_config)
        if any(v is None for v in lease) and not all(v is None for v in lease):
            raise IntegrityError("partial_lease")
        if record.worker_state == "pending" and (
            any(v is not None for v in lease) or record.call_phase != "not_started"
        ):
            raise IntegrityError("pending_lease")
        if record.worker_state == "running" or record.call_phase == "started":
            if any(v is None for v in lease) or record.lease_version < 1:
                raise IntegrityError("running_lease")
        if record.status == "completed":
            if record.feedback is None or record.call_phase != "started":
                raise IntegrityError("completed_result")
        elif record.feedback is not None:
            raise IntegrityError("unexpected_feedback")
        if record.status == "failed":
            if record.error != FAILURE or record.failure_reason not in REASONS:
                raise IntegrityError("failure_result")
        elif record.error is not None or record.failure_reason is not None:
            raise IntegrityError("unexpected_error")
    if isinstance(record, (Evaluation, Dispatch)):
        if record.deadline_at != record.created_at + 900000:
            raise IntegrityError("deadline")
    if isinstance(record, Dispatch):
        if record.status not in {"PENDING", "QUEUED", "CLAIMED", "DONE"} or record.generation < 1:
            raise IntegrityError("dispatch_state")
        if (record.send_owner is None) != (record.send_expires_at is None):
            raise IntegrityError("send_lease")
        if record.send_owner is not None and record.status != "PENDING":
            raise IntegrityError("send_state")
        if (record.claim_due_at is not None) != (record.status == "QUEUED"):
            raise IntegrityError("claim_due")
        if record.status == "QUEUED" and (
            record.queued_at is None or record.claim_due_at != record.queued_at + 120000
        ):
            raise IntegrityError("queued_time")
        if record.generation_attempts > record.delivery_attempts:
            raise IntegrityError("delivery_count")
    if isinstance(record, IdempotentReply):
        validate_id(record.key)
        if (
            record.fingerprint_version != 1
            or not re.fullmatch("[0-9a-f]{64}", record.fingerprint)
            or record.reply.status not in {200, 201, 202}
        ):
            raise StorageFormatError("idempotency_format")
        response_model = {201: Created, 202: ActiveAttempt, 200: SessionResponse}[
            record.reply.status
        ]
        parsed = response_model.model_validate(record.reply.body)
        if parsed.model_dump(exclude_unset=True) != record.reply.body:
            raise StorageFormatError("idempotency_body")
    if isinstance(record, RecoveryCursor):
        if record.partition not in PARTITIONS:
            raise StorageFormatError("cursor_partition")
        if record.cutoff > MAX_TIME:
            raise StorageFormatError("cursor_cutoff")
        if record.after is not None:
            validate_cursor_key(record.after, record.partition)


def key(kind, owner, identifier):
    return {
        "PK": "SYSTEM#RECOVERY" if kind == "RecoveryCursor" else f"USER#{owner}",
        "SK": f"{PREFIXES[kind]}#{identifier}",
    }


def work(record):
    if isinstance(record, Dispatch) and record.status == "PENDING":
        return PARTITIONS[0], min(
            record.deadline_at, max(record.next_at, record.send_expires_at or 0)
        )
    if isinstance(record, Dispatch) and record.status == "QUEUED":
        return PARTITIONS[1], min(record.deadline_at, record.claim_due_at)
    if isinstance(record, Evaluation) and record.worker_state == "running":
        return PARTITIONS[2], min(record.deadline_at, record.lock_expires_at)
    return None


def encode(kind, record, rev):
    if kind not in KINDS or not isinstance(record, KINDS[kind]) or type(rev) is not int or rev < 0:
        raise StorageFormatError("record_kind_revision")
    validate(record)
    identifier = (
        record.partition.removeprefix("WORK#")
        if kind == "RecoveryCursor"
        else record.key
        if kind == "IdempotencyRecord"
        else record.id
    )
    item = {
        **key(kind, getattr(record, "owner", ""), identifier),
        "kind": kind,
        "schema_version": 1,
        "rev": rev,
        "data": canonical(primitive(record)),
    }
    index = work(record)
    if index:
        item.update(work_pk=index[0], work_sk=f"{index[1]:013d}#{record.id}")
    if len(canonical(item).encode("ascii")) > 350 * 1024:
        raise ItemTooLarge("item_size")
    return item


def hydrate(kind, data):
    source = deepcopy(data)
    data = dict(data)
    if kind == "Session":
        data["questions"] = tuple(Question(**q) for q in data["questions"])
        if data["active"] is not None:
            data["active"] = ActiveAttempt(**data["active"])
    if kind == "Attempt":
        data["question"] = Question(**data["question"])
    if kind == "Evaluation":
        if "feedback" in data:
            data["feedback"] = Feedback(**data["feedback"])
        if "execution_config" in data:
            data["execution_config"] = ExecutionConfig(**data["execution_config"])
    if kind == "IdempotencyRecord":
        data["fingerprint"] = data.pop("request_hash")
        data["reply"] = Reply(**data["reply"])
    record = KINDS[kind](**data)
    validate(record)
    # Reject missing required fields, explicit optional nulls and unknown fields.
    if primitive(record) != source:
        raise StorageFormatError("noncanonical_fields")
    return record


def decode(item):
    try:
        item = integers(item)
        if (
            type(item["rev"]) is not int
            or item["rev"] < 0
            or type(item["schema_version"]) is not int
        ):
            raise StorageFormatError("revision")
        if item["schema_version"] != 1 or item["kind"] not in KINDS:
            raise StorageFormatError("schema_version")
        record = hydrate(item["kind"], json.loads(item["data"]))
        expected = encode(item["kind"], record, item["rev"])
        if any(item.get(k) != expected.get(k) for k in ("PK", "SK", "work_pk", "work_sk")):
            raise IntegrityError("physical_mapping")
        if set(item) != set(expected):
            raise StorageFormatError("item_fields")
        return record, item["rev"]
    except KeyError, TypeError, ValueError, OverflowError:
        raise StorageFormatError("invalid_item") from None


def integers(value):
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise StorageFormatError("noninteger")
        return int(value)
    if isinstance(value, dict):
        return {k: integers(v) for k, v in value.items()}
    return value


def to_wire(item):
    return {k: TypeSerializer().serialize(v) for k, v in item.items()}


def from_wire(item):
    return integers({k: TypeDeserializer().deserialize(v) for k, v in item.items()})


def validate_cursor_key(value, partition):
    if (
        type(value) is not dict
        or set(value) != {"PK", "SK", "work_pk", "work_sk"}
        or any(type(v) is not str or not v for v in value.values())
        or value["work_pk"] != partition
    ):
        raise StorageFormatError("cursor_key")


def validate_key(value, partition):
    validate_cursor_key(value, partition)
    if (
        set(value) != {"PK", "SK", "work_pk", "work_sk"}
        or any(type(v) is not str for v in value.values())
        or value["work_pk"] != partition
        or not value["PK"].startswith("USER#")
        or not re.fullmatch(r"\d{13}#.+", value["work_sk"])
    ):
        raise StorageFormatError("cursor_key")
    prefix = "EVALUATION#" if partition == PARTITIONS[2] else "DISPATCH#"
    if not value["SK"].startswith(prefix) or len(value["PK"]) <= 5:
        raise StorageFormatError("cursor_entity")
    identifier = value["SK"][len(prefix) :]
    try:
        validate_id(identifier)
    except ValueError:
        raise StorageFormatError("cursor_identifier") from None
    if value["work_sk"][14:] != identifier:
        raise StorageFormatError("cursor_identifier")
