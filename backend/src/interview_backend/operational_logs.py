"""Small allowlisted correlation events, independent of EMF and business writes."""

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from time import time

from interview_backend.models.public import UUID_PATTERN
from interview_backend.repositories.codec import REASONS

_context = ContextVar("operational_log_context", default=None)
EVENTS = {
    "api_completed",
    "evaluation_accepted",
    "evaluation_terminal",
    "worker_claimed",
    "dispatch_confirmed",
    "dispatch_deferred",
    "work_requeued",
    "storage_failure",
    "invalid_configuration",
    "internal_batch_failure",
    "provider_usage",
}


@contextmanager
def invocation_context(component, environment, event, context):
    request = event.get("requestContext") if isinstance(event, dict) else None
    gateway = request.get("requestId") if isinstance(request, dict) else None
    token = _context.set(
        {
            "component": component,
            "environment": environment,
            "lambdaRequestId": getattr(context, "aws_request_id", None),
            "gatewayRequestId": gateway,
        }
    )
    try:
        yield
    finally:
        _context.reset(token)


def log_event(event, *, sink=None, **fields):
    context = _context.get()
    if context is None or event not in EVENTS:
        return
    output = {"event": event, "timestamp": int(time() * 1000)}
    # Do not serialize arbitrary objects, event bodies, owners, or exception strings.
    for key, value in (context | fields).items():
        if key in {"evaluationId", "attemptId", "generationId"}:
            valid = isinstance(value, str) and UUID_PATTERN.fullmatch(value)
        elif key in {"lambdaRequestId", "gatewayRequestId"}:
            valid = isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_+=/-]{1,128}", value)
        elif key in {"statusCode", "elapsedMs", "generation"}:
            valid = type(value) in {int, float} and 0 <= value <= 10**12
        elif key == "component":
            valid = isinstance(value, str) and value in {"api", "admin", "worker", "dispatcher"}
        elif key == "environment":
            valid = isinstance(value, str) and value in {"dev", "test"}
        elif key == "status":
            valid = isinstance(value, str) and value in {
                "processing",
                "completed",
                "failed",
                "applied",
                "requeued",
                "deferred",
            }
        elif key == "failureReason":
            valid = isinstance(value, str) and value in REASONS
        elif key == "provider":
            valid = isinstance(value, str) and value in {"fake", "openai", "bedrock", "anthropic", "unknown"}
        elif key == "workload":
            valid = isinstance(value, str) and value in {"evaluation", "star"}
        elif key in {
            "inputTokens",
            "outputTokens",
            "totalTokens",
            "cacheReadInputTokens",
            "cacheWriteInputTokens",
            "reasoningTokens",
        }:
            valid = type(value) is int and 0 <= value <= 10**12
        else:
            valid = False
        if valid:
            output[key] = value
    try:
        (sink or print)(json.dumps(output, allow_nan=False, separators=(",", ":")))
    except Exception:
        # An observability failure must never introduce a business retry.
        pass


def log_provider_usage(provider, observation, *, generation_id=None):
    """Normalize numeric transport usage; no content, owner or arbitrary metadata."""
    if not isinstance(observation, dict):
        return
    names = (
        {
            "inputTokens": "inputTokens",
            "outputTokens": "outputTokens",
            "totalTokens": "totalTokens",
            "cacheReadInputTokens": "cacheReadInputTokens",
            "cacheWriteInputTokens": "cacheWriteInputTokens",
        }
        if provider == "bedrock"
        else {
            "input_tokens": "inputTokens",
            "output_tokens": "outputTokens",
            "cached_tokens": "cacheReadInputTokens",
            "reasoning_tokens": "reasoningTokens",
            "cache_read_input_tokens": "cacheReadInputTokens",
            "cache_creation_input_tokens": "cacheWriteInputTokens",
        }
    )
    fields = {
        target: observation[source] for source, target in names.items() if source in observation
    }
    log_event(
        "provider_usage",
        provider=provider,
        workload="star" if generation_id is not None else "evaluation",
        generationId=generation_id,
        **fields,
    )
