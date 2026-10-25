"""Repeated storage validation reuses schema metadata, never record validity."""

from dataclasses import dataclass, replace

import pytest
from conftest import uid

from interview_backend.assets import load_questions
from interview_backend.models.internal import IntegrityError, Session, StorageFormatError
from interview_backend.repositories import codec


def test_repeated_schema_resolution_keeps_per_record_validation(monkeypatch):
    @dataclass
    class MeasuredSession(Session):
        pass

    original = codec.get_type_hints
    resolutions = []

    def resolve(record_type):
        resolutions.append(record_type)
        return original(record_type)

    monkeypatch.setattr(codec, "get_type_hints", resolve)
    record = MeasuredSession("synthetic-owner", uid(1), load_questions()[:1])
    codec.validate(record)
    codec.validate(replace(record, id=uid(2)))
    with pytest.raises(StorageFormatError, match="invalid_type"):
        codec.validate(replace(record, number=True))
    with pytest.raises(IntegrityError, match="session_state"):
        codec.validate(replace(record, number=0))
    with pytest.raises(IntegrityError, match="invalid_owner"):
        codec.validate(replace(record, owner=" "))
    with pytest.raises(StorageFormatError, match="invalid_id"):
        codec.validate(replace(record, id="invalid"))
    assert resolutions == [MeasuredSession]
