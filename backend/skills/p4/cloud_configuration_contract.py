"""Raw approval -> pinned Terraform validator -> explicit readback representation.

No SDK, credentials, fallback defaults, or mutation of the raw approved payload.
Terraform's number output uses canonical decimal text; validate_inputs retains a
two-decimal USD input string. This one explicit representation conversion keeps
the approved amount unchanged and is separately pinned from the raw input SHA.
"""

from decimal import Decimal
from pathlib import Path

import terraform_dev
from cloud_controller_core import ACCOUNT, REGION, Refusal, canonical, digest, require

PACKAGE_KEYS = frozenset(
    ("artifact_bucket", "artifact_key", "artifact_version", "artifact_sha256_base64")
)
GENERATED_KEYS = frozenset(("account_id", "region", "cors_origins"))
SAFE_CONTRACT_REASONS = frozenset(
    (
        "RawConfigurationContractRejected",
        "NormalizerSourceChanged",
        "NormalizedConfigurationContractMismatch",
        "StateManifestConfigurationContractMismatch",
        "StateManifestContractRejected",
        "ReadbackImplementationContractFailure",
        "LiveDeploymentReadbackFailed",
    )
)


def configuration_only(normalized):
    return {k: v for k, v in normalized.items() if k not in PACKAGE_KEYS | {"account_id", "region"}}


def normalize_configuration(raw, package, contract):
    fields = {
        "revision",
        "raw_configuration_sha256",
        "normalized_configuration_sha256",
        "readback_configuration_sha256",
        "manifest_configuration_sha256",
        "baseline_manifest_schema_version",
        "normalizer_source_sha256",
        "baseline_artifact_inputs",
    }
    require(
        isinstance(contract, dict)
        and set(contract) == fields
        and type(contract["revision"]) is int
        and type(contract["baseline_manifest_schema_version"]) is int,
        "RawConfigurationContractRejected",
    )
    require(
        isinstance(raw, dict) and terraform_dev.valid_input_keys(raw, without_artifact=True),
        "RawConfigurationContractRejected",
    )
    require(
        isinstance(package, dict) and set(package) == PACKAGE_KEYS,
        "RawConfigurationContractRejected",
    )
    require(
        contract["revision"] == 1 and canonical(raw) == contract["raw_configuration_sha256"],
        "RawConfigurationContractRejected",
    )
    require(
        digest(Path(terraform_dev.__file__).read_bytes()) == contract["normalizer_source_sha256"],
        "NormalizerSourceChanged",
    )
    # The approved USD schema is explicit; the validator is still authoritative.
    require(
        all(
            type(v) is bool if k.endswith("_enabled") else isinstance(v, str)
            for k, v in raw.items()
        ),
        "RawConfigurationContractRejected",
    )
    try:
        normalized = terraform_dev.validate_inputs(raw | package, ACCOUNT, REGION)
    except Exception:
        raise Refusal("RawConfigurationContractRejected") from None
    verify_normalized(normalized, contract)
    return normalized


def verify_normalized(normalized, contract):
    require(
        isinstance(normalized, dict)
        and set(normalized) == set(terraform_dev.USD_INPUT_KEYS) | GENERATED_KEYS,
        "NormalizedConfigurationContractMismatch",
    )
    require(
        normalized["account_id"] == ACCOUNT
        and normalized["region"] == REGION
        and canonical(configuration_only(normalized))
        == contract["normalized_configuration_sha256"],
        "NormalizedConfigurationContractMismatch",
    )


def readback_inputs(normalized, contract):
    verify_normalized(normalized, contract)
    result = dict(normalized)
    amount = Decimal(normalized["monthly_budget_usd"])
    result["monthly_budget_usd"] = format(amount.normalize(), "f")
    require(
        Decimal(result["monthly_budget_usd"]) == amount
        and canonical(configuration_only(result)) == contract["readback_configuration_sha256"],
        "NormalizedConfigurationContractMismatch",
    )
    return result


def validate_manifest(manifest, normalized, contract, path):
    """Exact pinned configuration plus the established full manifest parser."""
    require(
        isinstance(manifest, dict)
        and type(manifest.get("schema_version")) is int
        and manifest["schema_version"] == contract["baseline_manifest_schema_version"]
        and isinstance(manifest.get("configuration"), dict)
        and canonical(manifest["configuration"]) == contract["manifest_configuration_sha256"],
        "StateManifestConfigurationContractMismatch",
    )
    verify_normalized(normalized, contract)
    from manifest import read_manifest

    try:
        import json
        import os

        with Path(path).open("x", encoding="utf-8") as f:
            json.dump(manifest, f)
            f.flush()
            os.fsync(f.fileno())
        parsed = read_manifest(path, ACCOUNT, REGION)
    except Exception:
        raise Refusal("StateManifestContractRejected") from None
    require(parsed == manifest, "StateManifestContractRejected")
    expected = readback_inputs(normalized, contract)
    # Schema 2/3 have no schema-4 monitoring fields. This is a pinned baseline,
    # not a silent omission or a migration of observed State to a newer schema.
    require(
        set(manifest["configuration"]) <= set(expected)
        and canonical(manifest["configuration"])
        == canonical({k: expected[k] for k in manifest["configuration"]}),
        "StateManifestConfigurationContractMismatch",
    )
    return expected


def verify_live(
    session, manifest, approved_inputs, *, journal=None, state_identity=None, state=None
):
    from cloud_readback_diagnostics import DiagnosticSession, exception_info
    from manifest import verify_live_manifest

    record = journal.record if journal is not None else lambda *a, **k: None
    wrapped = None
    try:
        wrapped = DiagnosticSession(session, manifest, record, state_identity, state)
        result = verify_live_manifest(
            wrapped,
            manifest,
            require_api_enabled=False,
            approved_inputs=approved_inputs | {"worker_ai_environment": {}},
        )
        record("live-readback-passed", state_identity=state_identity)
        return result
    except Exception as error:
        record(
            "live-readback-failed",
            state_identity=state_identity,
            last_api=wrapped.last if wrapped else None,
            **exception_info(error),
        )
        context = error.__context__
        if isinstance(error, (KeyError, TypeError, AttributeError)) or isinstance(
            context, (KeyError, TypeError, AttributeError)
        ):
            raise Refusal("ReadbackImplementationContractFailure") from None
        raise Refusal("LiveDeploymentReadbackFailed") from None
