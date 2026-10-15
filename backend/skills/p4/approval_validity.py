"""New Stage2 approvals only: immutable 72-hour issue window, not a lease."""

import re
from datetime import datetime, timedelta

REVISION = 1
VALIDITY_SECONDS = 72 * 60 * 60
UTC_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def utc_stamp(value):
    if not isinstance(value, str) or UTC_STAMP.fullmatch(value) is None:
        raise ValueError("AbsoluteUtcApprovalTimestampRequired")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("InvalidApprovalTimestamp") from None


def validate_window(descriptor):
    """Reject legacy lifetime in this new release; never rewrite old bytes."""
    window = descriptor["operator_execution"]
    if (
        type(window.get("approval_expiry_policy_revision")) is not int
        or window["approval_expiry_policy_revision"] != REVISION
    ):
        raise ValueError("ApprovalExpiryPolicyRevisionMismatch")
    if (
        type(window.get("approval_validity_seconds")) is not int
        or window["approval_validity_seconds"] != VALIDITY_SECONDS
    ):
        raise ValueError("ApprovalValidityChanged")
    issued = utc_stamp(window.get("issued_at_utc"))
    expiry = utc_stamp(descriptor.get("expires_at_utc"))
    if expiry - issued != timedelta(seconds=VALIDITY_SECONDS):
        raise ValueError("ApprovalLifetimeMismatch")
    return issued, expiry


def admission(descriptor, now, required_seconds):
    issued, expiry = validate_window(descriptor)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("ApprovalClockUnknown")
    if type(required_seconds) is not int or required_seconds < 0:
        raise ValueError("ApprovalBudgetInvalid")
    if now < issued:
        raise ValueError("ApprovalNotYetIssued")
    if now + timedelta(seconds=required_seconds) >= expiry:
        raise ValueError("ApprovalExpiredOrInsufficientTime")
    return expiry


def fresh_window(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("ApprovalClockUnknown")
    issued = now.replace(microsecond=0)
    expiry = issued + timedelta(seconds=VALIDITY_SECONDS)
    return {
        "approval_expiry_policy_revision": REVISION,
        "approval_validity_seconds": VALIDITY_SECONDS,
        "issued_at_utc": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at_utc": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
