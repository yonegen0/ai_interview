"""Candidate-only synthetic State and Plan review (no credentials, State access or Apply).

The JSON format check supplements toolchain_compatibility; neither can prove
provider upgrader behavior or that caller-supplied bytes came from remote State.
"""

import hashlib
import json
import re

import candidate_bootstrap_preflight as preflight
import toolchain_compatibility as compatibility

STRUCTURAL_KEYS = {
    "address",
    "module_address",
    "mode",
    "type",
    "name",
    "index",
    "provider_name",
    "schema_version",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mask(value, *, allow_metadata=False):
    """Reject unresolved unknown leaves and malformed mask values."""
    if type(value) is dict:
        for key, item in value.items():
            require(type(key) is str, "CandidateUnknownMaskMalformed")
            if allow_metadata and key in STRUCTURAL_KEYS:
                require(type(item) in {str, int}, "CandidateUnknownMaskMalformed")
            else:
                mask(item, allow_metadata=key in {"root_module", "child_modules", "resources"})
    elif type(value) is list:
        for item in value:
            mask(item, allow_metadata=allow_metadata)
    else:
        require(value is False, "CandidateUnknownOrMalformedMask")


def sensitive_mask(value):
    """Sensitivity metadata can be True without implying resource drift."""
    if type(value) is dict:
        for item in value.values():
            sensitive_mask(item)
    elif type(value) is list:
        for item in value:
            sensitive_mask(item)
    else:
        require(type(value) is bool, "CandidateSensitivityMaskMalformed")


def resource_metadata(module):
    require(type(module) is dict, "CandidateStateModuleMalformed")
    resources = module.get("resources", [])
    children = module.get("child_modules", [])
    require(type(resources) is list and type(children) is list, "CandidateStateModuleMalformed")
    for row in resources:
        require(
            type(row) is dict
            and type(row.get("address")) is str
            and type(row.get("schema_version")) is int
            and row["schema_version"] >= 0
            and type(row.get("values")) is dict,
            "CandidateStateResourceSchemaUnproven",
        )
        sensitive_mask(row.get("sensitive_values", {}))
    for child in children:
        resource_metadata(child)


def inspect_plan(document):
    """Strict candidate supplement for unknown, sensitive and deferred evidence."""
    require(type(document) is dict, "CandidatePlanDocumentMalformed")
    # HashiCorp JSON output uses a major/minor format independent of raw State v4.
    version = document.get("format_version")
    require(
        type(version) is str and re.fullmatch(r"1\\.\\d+", version) is not None,
        "CandidatePlanFormatVersionUnsupported",
    )
    for name in ("resource_drift", "deferred_changes", "action_invocations"):
        require(
            name not in document or document[name] == [],
            "CandidateDeferredOrUnsupportedChanges",
        )
    if "proposed_unknown" in document:
        proposed = document["proposed_unknown"]
        require(type(proposed) is dict, "CandidateUnknownMaskMalformed")
        mask(proposed, allow_metadata=True)
    for stage in ("prior_state", "planned_values"):
        container = document.get(stage)
        require(type(container) is dict, "CandidatePlanStateStructureMissing")
        if stage == "prior_state":
            values = container.get("values")
            require(type(values) is dict, "CandidatePlanStateStructureMissing")
            module = values.get("root_module")
        else:
            module = container.get("root_module")
        require(type(module) is dict, "CandidatePlanStateStructureMissing")
        resource_metadata(module)
    require(type(document.get("resource_changes")) is list, "CandidatePlanChangesMissing")
    for row in document["resource_changes"]:
        require(
            type(row) is dict and type(row.get("change")) is dict,
            "CandidatePlanChangeMalformed",
        )
        change = row["change"]
        require(
            "deposed" not in row and "action_reason" not in row,
            "CandidatePlanExtraActionReview",
        )
        sensitive_mask(change.get("before_sensitive", {}))
        sensitive_mask(change.get("after_sensitive", {}))
        if "after_unknown" in change:
            mask(change["after_unknown"])
    return {"status": "CANDIDATE_JSON_STRUCTURE_REVIEW_ONLY", "authorized": False}


def compare_offline_plans(baseline, candidate):
    inspect_plan(baseline)
    inspect_plan(candidate)
    result = compatibility.assert_noop_plan_pair(baseline, candidate, preflight.CLI)
    return {
        "status": "CANDIDATE_SYNTHETIC_NOOP_NOT_APPLY_APPROVAL",
        "authorized": False,
        "resources": result["resources"],
        "real_state_compatibility_proven": False,
    }


def inspect_raw_state(raw, identity):
    """Check provided raw State bytes, not where those bytes came from."""
    preflight.state_identity(identity)
    require(
        type(raw) is bytes and hashlib.sha256(raw).hexdigest() == identity["sha256"],
        "CandidateRawStateDigestMismatch",
    )

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "CandidateRawStateMalformed")
            result[key] = value
        return result

    def no_nonfinite(_):
        raise ValueError("CandidateRawStateMalformed")

    try:
        state = json.loads(raw, object_pairs_hook=unique_fields, parse_constant=no_nonfinite)
    except (UnicodeError, ValueError) as error:
        raise ValueError("CandidateRawStateMalformed") from error
    require(
        type(state) is dict
        and type(state.get("version")) is int
        and state["version"] == 4
        and type(state.get("lineage")) is str
        and state["lineage"] == identity["lineage"]
        and type(state.get("serial")) is int
        and state["serial"] == identity["serial"]
        and type(state.get("resources")) is list
        and type(state.get("outputs")) is dict,
        "CandidateRawStateIdentityMismatch",
    )
    return {
        "status": "LOCAL_STATE_BYTES_MATCH_CLAIM_ONLY",
        "authorized": False,
        "remote_version_id_proven": False,
        "provider_upgrader_proven": False,
    }
