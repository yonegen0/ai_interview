"""Evidence cannot accept private fields, missing cases, or cleanup failures."""

import pytest
from test_p4_tools import tool


def record():
    return {
        "test_id": "DB-01",
        "run_id": "synthetic",
        "source_sha": "a" * 40,
        "manifest_version": 2,
        "started_at": "2026-09-13T00:00:00+00:00",
        "finished_at": "2026-09-13T00:00:01+00:00",
        "result": "passed",
        "failure": "none",
        "cleanup": "passed",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"token": "private"},
        {"failure": "private"},
        {"cleanup": "failed"},
        {"cleanup": "not_run"},
        {"manifest_version": True},
        {"test_id": "AS-19"},
        {"finished_at": "2026-09-12T00:00:00+00:00"},
    ],
)
def test_evidence_rejects_invalid_or_private_fields(change):
    with pytest.raises(ValueError, match="InvalidEvidenceRecord"):
        tool("evidence").validate(record() | change)


def test_evidence_requires_every_case_and_one_run():
    module = tool("evidence")
    assert module.outcome([record()], ["DB-01"]) == "passed"
    assert module.outcome([record()], ["DB-01", "DB-02"]) == "failed"
    assert module.outcome([record() | {"result": "not_run"}], ["DB-01"]) == "failed"
    with pytest.raises(ValueError, match="ConflictingEvidence"):
        module.outcome([record(), record()], ["DB-01"])
    with pytest.raises(ValueError, match="ConflictingEvidence"):
        module.outcome([record(), record() | {"test_id": "DB-02", "run_id": "other"}], [])
