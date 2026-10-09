"""No live SDK: lock, VersionId, encryption and remote namespace readback failures."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from test_p4_tools import tool


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "lock",
        "lock-access",
        "null-version",
        "version-change",
        "get-version",
        "encryption",
        "lineage",
        "serial",
        "account",
        "run",
    ],
)
def test_authoritative_state_reads_fail_closed(monkeypatch, bad):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "skills/p4"))
    manifest = {"account_id": "123456789012", "region": "ap-northeast-1", "run_id": ""}
    state = {
        "lineage": "bound",
        "serial": 9,
        "outputs": {"manifest": {"value": manifest}},
        "resources": [],
    }
    if bad == "lineage":
        state["lineage"] = ""
    if bad == "serial":
        state["serial"] = True
    if bad == "account":
        manifest["account_id"] = "000000000000"
    if bad == "run":
        manifest["run_id"] = "other"
    calls = []

    def head(**kwargs):
        calls.append(kwargs)
        assert kwargs["ExpectedBucketOwner"] == "123456789012"
        if kwargs["Key"].endswith(".tflock"):
            if bad == "lock":
                return {"VersionId": "lock"}
            raise ClientError(
                {"Error": {"Code": "AccessDenied" if bad == "lock-access" else "404"}}, "HeadObject"
            )
        return {
            "VersionId": "null"
            if bad == "null-version"
            else "v10"
            if bad == "version-change" and len(calls) == 3
            else "v9"
        }

    def get(**kwargs):
        assert kwargs["VersionId"] == "v9" and kwargs["ExpectedBucketOwner"] == "123456789012"
        return {
            "VersionId": "v8" if bad == "get-version" else "v9",
            "ServerSideEncryption": "aws:kms" if bad == "encryption" else "AES256",
            "Body": io.BytesIO(json.dumps(state).encode()),
        }

    session = SimpleNamespace(
        client=lambda *a, **kw: SimpleNamespace(head_object=head, get_object=get)
    )

    def invoke():
        return tool("deployment_guards").read_state_snapshot(
            session, "123456789012", "ap-northeast-1", "dev/terraform.tfstate"
        )

    if bad:
        with pytest.raises(ValueError):
            invoke()
    else:
        result = invoke()
        assert result["identity"]["version_id"] == "v9" and result["state"] == state
