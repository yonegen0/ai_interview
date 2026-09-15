"""Invocation budget shared by nested storage operations; isolated per execution context."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from time import monotonic

remaining_budget = ContextVar("storage_remaining_budget", default=None)


@dataclass(frozen=True)
class CommitWindow:
    """Ephemeral UTC bounds: lower inclusive, upper exclusive; never serialized."""

    lower: int = 0
    upper: int | None = None
    remaining_ms: int = 0

    def valid(self, now):
        remaining = remaining_budget.get()
        return (
            type(now) is int
            and now >= self.lower
            and (self.upper is None or now < self.upper)
            and (remaining is None or remaining() >= self.remaining_ms)
        )


class CommitWindowExpired(Exception):
    pass


@contextmanager
def storage_budget(remaining):
    outer = remaining_budget.get()
    effective = remaining if outer is None else lambda: min(outer(), remaining())
    token = remaining_budget.set(effective)
    try:
        yield
    finally:
        remaining_budget.reset(token)


def invocation_budget(default_ms):
    def decorate(method):
        parameters = signature(method)

        @wraps(method)
        def run(*args, **kwargs):
            bound = parameters.bind(*args, **kwargs)
            remaining = bound.arguments.get("remaining_ms")
            clock = getattr(args[0], "monotonic", monotonic) if args else monotonic
            began = clock()
            if remaining is None:

                def remaining():
                    return max(0, default_ms - (clock() - began) * 1000)

            with storage_budget(remaining):
                return method(*args, **kwargs)

        return run

    return decorate
