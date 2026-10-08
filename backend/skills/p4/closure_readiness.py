"""Offline execution certificate required before any supported Enablement apply."""

import hashlib
import json
from pathlib import Path


def fingerprints():
    root = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in (
            "closure_adapter.py",
            "closure_aws.py",
            "closure_readiness.py",
            "suite_binding.py",
            "coaching_binding.py",
            "terraform_dev.py",
        )
    }


def require_closure_ready(path, approved_sha256):
    if not path or not approved_sha256:
        raise ValueError("EnablementForbiddenUntilClosureValidated")
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    if (
        hashlib.sha256(raw).hexdigest() != approved_sha256
        or value.get("status") != "OFFLINE_CLOSURE_EXECUTION_VERIFIED"
        or value.get("source_sha256") != fingerprints()
        or value.get("tests_passed") is not True
    ):
        raise ValueError("EnablementForbiddenUntilClosureValidated")
    return value


def bound_callback_ready(callback, approval, audit=None, authenticate=None):
    from closure_adapter import BoundClosure
    from suite_binding import CognitoAuthenticate, SuiteAudit

    if not isinstance(callback, BoundClosure):
        raise ValueError("ConcreteClosureCallbackRequired")
    if (
        not isinstance(audit, SuiteAudit)
        or not isinstance(authenticate, CognitoAuthenticate)
        or audit.close is not callback
    ):
        raise ValueError("ConcreteAuthAuditCallbacksRequired")
    require_closure_ready(
        approval.get("closure_validation_path"), approval.get("closure_validation_sha256")
    )
    return True
