"""Fresh deterministic runtime per test, with no external services."""

from datetime import UTC, datetime
from itertools import count

import pytest

from interview_backend.bootstrap import build_runtime


def uid(number: int) -> str:
    return f"10000000-0000-4000-8000-{number:012d}"


@pytest.fixture
def runtime():
    ids = count(1)
    return build_runtime(
        new_id=lambda: uid(next(ids)), clock=lambda: datetime(2026, 9, 11, tzinfo=UTC)
    )
