"""Server-owned access expiry, independent of Scheduler delivery or propagation."""

from time import time


def expired(environment, *, clock=time):
    value = environment.get("INTERVIEW_RELEASE_EXPIRES_AT", "0")
    try:
        end = int(value)
        if str(end) != value or end < 0:
            return True
    except ValueError, TypeError:
        return True
    return end != 0 and clock() >= end
