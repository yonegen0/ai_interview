"""Private readback diagnostics and strict SQS representation normalization.

No SDK/client, credential, file or network operation is performed on import.
The pinned verifier continues to enforce its complete deployment contract.
"""

import copy
import json
import re
import traceback
from pathlib import Path

from cloud_controller_core import canonical

VERSION = "sqs-semantic-v1"
FIELDS = (
    "QueueArn",
    "MessageRetentionPeriod",
    "VisibilityTimeout",
    "SqsManagedSseEnabled",
    "FifoQueue",
    "KmsMasterKeyId",
    "RedrivePolicy",
    "RedriveAllowPolicy",
)
SAFE_CODES = frozenset(
    (
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "QueueDoesNotExist",
        "AWS.SimpleQueueService.NonExistentQueue",
        "NonExistentQueue",
        "InvalidAddress",
        "InvalidAttributeName",
        "InvalidSecurity",
        "RequestThrottled",
        "Throttling",
        "ThrottlingException",
        "ExpiredToken",
        "ExpiredTokenException",
        "InvalidClientTokenId",
        "SignatureDoesNotMatch",
        "InternalError",
        "ServiceUnavailable",
    )
)


class ReadbackMismatch(ValueError):
    def __init__(self, reason, field=None):
        self.reason, self.field = reason, field
        super().__init__(reason)


def integer(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        return int(value)
    raise ReadbackMismatch("SqsIntegerRepresentationInvalid")


def boolean(value):
    if type(value) is bool:
        return value
    if value in ("true", "false") and isinstance(value, str):
        return value == "true"
    raise ReadbackMismatch("SqsBooleanRepresentationInvalid")


def json_object(value):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ReadbackMismatch("SqsDuplicateJsonKey")
            result[k] = v
        return result

    if not isinstance(value, str):
        raise ReadbackMismatch("SqsJsonRepresentationInvalid")
    try:
        result = json.loads(
            value,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ReadbackMismatch("SqsNonFiniteJson")),
        )
    except ReadbackMismatch:
        raise
    except ValueError, TypeError:
        raise ReadbackMismatch("SqsJsonMalformed") from None
    if not isinstance(result, dict):
        raise ReadbackMismatch("SqsJsonObjectRequired")
    return result


def policy(value, field):
    result = json_object(value)
    if field == "RedrivePolicy" and "maxReceiveCount" in result:
        result["maxReceiveCount"] = integer(result["maxReceiveCount"])
    if field == "RedriveAllowPolicy" and "sourceQueueArns" in result:
        arns = result["sourceQueueArns"]
        if (
            not isinstance(arns, list)
            or not all(isinstance(v, str) for v in arns)
            or len(set(arns)) != len(arns)
        ):
            raise ReadbackMismatch("SqsArnSetInvalid", field)
        result["sourceQueueArns"] = sorted(arns)
    return result


def normalize(attrs):
    if not isinstance(attrs, dict):
        raise ReadbackMismatch("SqsAttributesMapMissing")
    result = copy.deepcopy(attrs)
    for field in ("MessageRetentionPeriod", "VisibilityTimeout"):
        if field in attrs:
            try:
                result[field] = str(integer(attrs[field]))
            except ReadbackMismatch as e:
                e.field = field
                raise
    for field in ("SqsManagedSseEnabled", "FifoQueue"):
        if field in attrs:
            try:
                result[field] = str(boolean(attrs[field])).lower()
            except ReadbackMismatch as e:
                e.field = field
                raise
    for field in ("RedrivePolicy", "RedriveAllowPolicy"):
        if field in attrs and attrs[field] != "":
            try:
                result[field] = json.dumps(
                    policy(attrs[field], field), sort_keys=True, separators=(",", ":")
                )
            except ReadbackMismatch as e:
                e.field = field
                raise
    # No fields are removed, no required fields are filled, unknown values survive
    # for the established verifier. Only standard-queue FifoQueue omission has
    # the pre-existing false default in the original verifier.
    return result


def contracts(manifest):
    a, r, p = (
        manifest["account_id"],
        manifest["region"],
        "ai-interview-dev" if not manifest["run_id"] else "ai-interview-test-" + manifest["run_id"],
    )
    result = {}
    for key, suffix, retention, visibility in (
        ("queue_url", "main", "345600", "360"),
        ("worker_dlq_url", "worker-dlq", "1209600", "30"),
        ("stream_failure_url", "stream-failure", "1209600", "30"),
    ):
        result[manifest[key]] = {
            "role": key,
            "QueueArn": f"arn:aws:sqs:{r}:{a}:{p}-{suffix}",
            "MessageRetentionPeriod": retention,
            "VisibilityTimeout": visibility,
            "SqsManagedSseEnabled": "true",
        }
    return result


def verify_state(manifest, state):
    targets = contracts(manifest)
    queues = {
        i["attributes"]["url"]: i["attributes"]
        for res in state["resources"]
        if res.get("mode") == "managed" and res["type"] == "aws_sqs_queue"
        for i in res["instances"]
    }
    for url, expected in targets.items():
        if url not in queues:
            raise ReadbackMismatch("SqsStateResourceMissing")
        q = queues[url]
        fields = {
            "QueueArn": "arn",
            "MessageRetentionPeriod": "message_retention_seconds",
            "VisibilityTimeout": "visibility_timeout_seconds",
            "SqsManagedSseEnabled": "sqs_managed_sse_enabled",
        }
        for api, tf in fields.items():
            if tf not in q:
                raise ReadbackMismatch("SqsStateAttributeMissing", api)
            observed = normalize({api: q[tf]})[api]
            if observed != expected[api]:
                raise ReadbackMismatch("SqsStateContractDrift", api)
    return True


def verify_attributes(attrs, expected, manifest, *, all_attributes):
    for field in (
        "QueueArn",
        "MessageRetentionPeriod",
        "VisibilityTimeout",
        "SqsManagedSseEnabled",
    ):
        if field not in attrs:
            raise ReadbackMismatch("SqsRequiredAttributeMissing", field)
        if attrs[field] != expected[field]:
            raise ReadbackMismatch("SqsAttributeMismatch", field)
    if not all_attributes:
        return
    if attrs.get("FifoQueue", "false") != "false":
        raise ReadbackMismatch("SqsQueueTypeMismatch", "FifoQueue")
    if attrs.get("KmsMasterKeyId"):
        raise ReadbackMismatch("SqsEncryptionMismatch", "KmsMasterKeyId")
    role = expected["role"]
    if role == "queue_url":
        if "RedrivePolicy" not in attrs:
            raise ReadbackMismatch("SqsRequiredAttributeMissing", "RedrivePolicy")
        required = {
            "deadLetterTargetArn": contracts(manifest)[manifest["worker_dlq_url"]]["QueueArn"],
            "maxReceiveCount": 5,
        }
        if policy(attrs["RedrivePolicy"], "RedrivePolicy") != required:
            raise ReadbackMismatch("SqsRedriveMismatch", "RedrivePolicy")
    elif attrs.get("RedrivePolicy"):
        raise ReadbackMismatch("SqsUnexpectedRedrive", "RedrivePolicy")
    if role == "worker_dlq_url":
        if "RedriveAllowPolicy" not in attrs:
            raise ReadbackMismatch("SqsRequiredAttributeMissing", "RedriveAllowPolicy")
        if policy(attrs["RedriveAllowPolicy"], "RedriveAllowPolicy") != {
            "redrivePermission": "byQueue",
            "sourceQueueArns": [manifest["queue_arn"]],
        }:
            raise ReadbackMismatch("SqsRedriveAllowMismatch", "RedriveAllowPolicy")


def exception_info(error, seen=None):
    # Never persist exception strings, response bodies or error messages.
    response = getattr(error, "response", None)
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    safe = code if code in SAFE_CODES else ("OTHER" if code else None)
    frames = [
        {"module": Path(f.filename).name, "function": f.name, "line": f.lineno}
        for f in traceback.extract_tb(error.__traceback__)
        if Path(f.filename).name
        in {
            "manifest.py",
            "manifest_checks.py",
            "manifest_alarms.py",
            "configuration_contract.py",
            "readback_diagnostics.py",
            "aws_readonly.py",
            "read_scope.py",
        }
    ]
    result = {
        "exception_type": type(error).__name__
        if type(error).__module__
        in {"builtins", "botocore.exceptions", __name__, "controller_core"}
        else "OTHER",
        "aws_error_code": safe,
        "aws_error_code_sha256": canonical(code) if isinstance(code, str) else None,
        "reason_code": error.reason
        if isinstance(error, ReadbackMismatch)
        else "LiveReadbackException",
        "attribute": error.field if isinstance(error, ReadbackMismatch) else None,
        "check_stack": frames,
    }
    seen = set() if seen is None else seen
    seen.add(id(error))
    context = error.__context__
    if context is not None and id(context) not in seen and len(seen) < 5:
        result["underlying_exception"] = exception_info(context, seen)
    return result


class DiagnosticSession:
    def __init__(self, session, manifest, record, state_identity, state=None):
        self.session, self.manifest, self.record, self.identity = (
            session,
            manifest,
            record,
            state_identity,
        )
        self.targets = contracts(manifest)
        self.last = None
        self.sequence = 0
        if state is not None:
            try:
                verify_state(manifest, state)
            except Exception as error:
                self.emit("readback-state-contract-failed", **exception_info(error))
                raise
            self.emit("readback-state-contract-passed")

    def emit(self, stage, **fields):
        self.record(stage, normalization=VERSION, state_identity=self.identity, **fields)

    def client(self, service, **kwargs):
        from cloud_aws_readonly import ALLOWED

        underlying = self.session.client(service, **kwargs)
        owner = self

        class Client:
            def __getattr__(self, operation):
                if operation not in ALLOWED.get(service, set()):
                    raise ReadbackMismatch("DiagnosticMutationForbidden")
                call = getattr(underlying, operation)

                def run(**params):
                    owner.sequence += 1
                    context = {
                        "service": service,
                        "operation": operation,
                        "sequence": owner.sequence,
                        "arguments_sha256": canonical(params),
                    }
                    owner.last = context
                    owner.emit("readback-api-started", **context)
                    try:
                        response = call(**params)
                    except Exception as error:
                        owner.emit("readback-api-failed", **context, **exception_info(error))
                        raise
                    meta = (
                        response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
                    )
                    owner.emit(
                        "readback-api-succeeded", **context, http_status=meta.get("HTTPStatusCode")
                    )
                    if service == "sqs" and operation == "get_queue_attributes":
                        expected = owner.targets.get(params.get("QueueUrl"))
                        if expected is None:
                            raise ReadbackMismatch("SqsTargetOutsideManifest")
                        attrs = response.get("Attributes") if isinstance(response, dict) else None
                        # Raw values stay in private evidence and only these contract
                        # fields are retained. Queue Policy and arbitrary attributes
                        # are never saved by the diagnostics.
                        owner.emit(
                            "sqs-private-projection",
                            **context,
                            queue_role=expected["role"],
                            fields={
                                k: attrs[k]
                                for k in FIELDS
                                if isinstance(attrs, dict) and k in attrs
                            },
                            present_fields=[
                                k for k in FIELDS if isinstance(attrs, dict) and k in attrs
                            ],
                        )
                        try:
                            normalized = normalize(attrs)
                            verify_attributes(
                                normalized,
                                expected,
                                owner.manifest,
                                all_attributes=params.get("AttributeNames") == ["All"],
                            )
                        except Exception as error:
                            owner.emit(
                                "sqs-comparison-failed",
                                **context,
                                queue_role=expected["role"],
                                **exception_info(error),
                            )
                            raise
                        owner.emit(
                            "sqs-comparison-passed",
                            **context,
                            queue_role=expected["role"],
                            normalized_fields={k: normalized[k] for k in FIELDS if k in normalized},
                            fifo_omitted_standard_default="FifoQueue" not in normalized,
                        )
                        response = copy.deepcopy(response)
                        response["Attributes"] = normalized
                    return response

                return run

        return Client()
