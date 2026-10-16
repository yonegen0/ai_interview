"""Finite v2 process diagnostic contract shared byte-for-byte by producer/reader.

Only integer metadata and source-defined enums cross the public boundary.
Diagnostic classes are hints, never authorization or root-cause proof.
"""

import hashlib
import json
import re

HINTS = frozenset(
    (
        "authorization-denied-marker",
        "state-lock-marker",
        "expired-credentials-marker",
        "invalid-provider-configuration-marker",
        "unclassified",
    )
)
COMMANDS = frozenset(("version", "init", "plan", "show", "build"))
FIELDS = frozenset(
    (
        "returncode",
        "phase",
        "command_kind",
        "diagnostic_hints",
        "classification_complete",
        "hints_are_root_cause_proof",
        "private_event_sequence",
        "diagnostic_id",
    )
)


def require(ok):
    if not ok:
        raise ValueError("FiniteProcessDiagnosticRejected")


def identity(binding, kind, sequence, returncode):
    require(
        type(binding) is dict
        and set(binding) == {"run_id", "run_attempt", "source_sha", "parent_sha256"}
    )
    require(
        type(binding["run_id"]) is str
        and re.fullmatch(r"[1-9][0-9]*", binding["run_id"]) is not None
    )
    require(binding["run_attempt"] == "1")
    for name, length in (("source_sha", 40), ("parent_sha256", 64)):
        require(
            type(binding[name]) is str
            and re.fullmatch(r"[a-f0-9]{" + str(length) + r"}", binding[name]) is not None
        )
    payload = {
        **binding,
        "command_kind": kind,
        "private_event_sequence": sequence,
        "returncode": returncode,
        "format": "p4-process-failure-v2",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_context(value, binding, kind):
    require(type(value) is dict and set(value) == FIELDS)
    require(
        type(value["returncode"]) is int
        and -(2**31) <= value["returncode"] < 2**31
        and value["returncode"] != 0
    )
    require(
        value["phase"] == "process-exit"
        and type(kind) is str
        and kind in COMMANDS
        and value["command_kind"] == kind
    )
    hints = value["diagnostic_hints"]
    require(type(hints) is list and 1 <= len(hints) <= len(HINTS))
    require(all(type(h) is str and h in HINTS for h in hints))
    require(
        hints == sorted(set(hints)) and ("unclassified" not in hints or hints == ["unclassified"])
    )
    require(
        type(value["classification_complete"]) is bool
        and value["hints_are_root_cause_proof"] is False
    )
    require(
        type(value["private_event_sequence"]) is int
        and 1 <= value["private_event_sequence"] <= 10000
    )
    require(
        value["diagnostic_id"]
        == identity(binding, kind, value["private_event_sequence"], value["returncode"])
    )
    return value


def build_context(diagnostic, environment, kind, sequence):
    require(type(diagnostic) is dict and type(environment) is dict)
    binding = {
        k: environment.get(env)
        for k, env in (
            ("run_id", "GITHUB_RUN_ID"),
            ("run_attempt", "GITHUB_RUN_ATTEMPT"),
            ("source_sha", "GITHUB_SHA"),
            ("parent_sha256", "P4_CLOUD_PARENT_SHA256"),
        )
    }
    hints = diagnostic.get("diagnostic_hints")
    require(type(hints) is list and all(type(h) is str and h in HINTS for h in hints))
    value = {
        "returncode": diagnostic.get("returncode"),
        "phase": "process-exit",
        "command_kind": kind,
        "diagnostic_hints": sorted(set(hints)),
        "classification_complete": diagnostic.get("classification_complete"),
        "hints_are_root_cause_proof": False,
        "private_event_sequence": sequence,
        "diagnostic_id": identity(binding, kind, sequence, diagnostic.get("returncode")),
    }
    return validate_context(value, binding, kind)
