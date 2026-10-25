"""Offline migration evidence checks. Passing never authorizes State access or Apply."""

import argparse
import hashlib
import json
import re
from pathlib import Path

AWS = "registry.terraform.io/hashicorp/aws"
ADDITIONS = {
    "aws_sns_topic": ("attributes", "maximum_message_size"),
    "aws_cloudwatch_metric_alarm": ("block_types", "evaluation_window"),
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(unknown(item) for item in value)
    return value is not False


def resource_types(configuration):
    """Inventory the copied HCL, including all local modules; never inspect State."""
    kinds = set()
    for name, raw in configuration.items():
        if name.endswith(".tf.json"):
            raise ValueError("MigrationHclJsonReviewRequired")
        if not name.endswith(".tf"):
            continue
        text = raw.decode("utf-8")
        if re.search(r'(?m)^\s*data\s+"', text):
            raise ValueError("MigrationDataSourceReviewRequired")
        kinds.update(re.findall(r'(?m)^\s*resource\s+"([a-z0-9_]+)"\s+"', text))
    if not kinds or any(not kind.startswith("aws_") for kind in kinds):
        raise ValueError("MigrationResourceInventoryRequired")
    return kinds


def compare_schemas(before, after, kinds):
    """Allow only the two reviewed additions; schema equality is not default proof."""
    if not kinds:
        raise ValueError("MigrationResourceInventoryRequired")
    selected = []
    for document in (before, after):
        if document.get("format_version") != "1.0":
            raise ValueError("MigrationSchemaFormatReviewRequired")
        providers = document.get("provider_schemas", {})
        if set(providers) != {AWS}:
            raise ValueError("MigrationSchemaProviderMismatch")
        resources = providers[AWS].get("resource_schemas", {})
        if not kinds <= resources.keys():
            raise ValueError("MigrationResourceSchemaMissing")
        selected.append({kind: resources[kind] for kind in sorted(kinds)})
    changes = {}
    for kind in sorted(kinds):
        old, new = selected[0][kind], selected[1][kind]
        if (
            type(old.get("version")) is not int
            or type(new.get("version")) is not int
            or old["version"] != new["version"]
        ):
            raise ValueError("MigrationStateUpgraderReviewRequired")
        expected = json.loads(encoded(old))
        if kind in ADDITIONS:
            collection, field = ADDITIONS[kind]
            added = new["block"].get(collection, {}).get(field)
            if field not in old["block"].get(collection, {}) and added is not None:
                if kind == "aws_sns_topic" and (
                    added.get("type") != "number"
                    or added.get("optional") is not True
                    or added.get("computed") is not True
                    or added.get("required")
                ):
                    raise ValueError("MigrationResourceSchemaReviewRequired")
                if kind == "aws_cloudwatch_metric_alarm" and (
                    added.get("nesting_mode") != "list"
                    or added.get("min_items", 0) != 0
                    or added.get("max_items") != 1
                ):
                    raise ValueError("MigrationResourceSchemaReviewRequired")
                expected["block"].setdefault(collection, {})[field] = added
                changes[kind] = f"{collection}.{field}"
        if encoded(expected) != encoded(new):
            raise ValueError("MigrationResourceSchemaReviewRequired")
    return {
        "resource_types": sorted(kinds),
        "schema_versions": {kind: selected[1][kind]["version"] for kind in sorted(kinds)},
        "additions": changes,
        "baseline_schema_sha256": hashlib.sha256(encoded(selected[0])).hexdigest(),
        "candidate_schema_sha256": hashlib.sha256(encoded(selected[1])).hexdigest(),
        "defaults_and_state_upgraders_proven": False,
    }


def plan_resources(module):
    result = {}
    for row in module.get("resources", []):
        address = row["address"]
        if row.get("mode") != "managed" or address in result:
            raise ValueError("MigrationPlanResourceInventory")
        result[address] = row
    for child in module.get("child_modules", []):
        nested = plan_resources(child)
        if result.keys() & nested.keys():
            raise ValueError("MigrationPlanResourceInventory")
        result.update(nested)
    return result


def assert_noop_plan_pair(before, after, candidate):
    """Compare supplied JSON only. Never execute Terraform or accept a saved binary.

    This deliberately rejects new computed defaults, even for a claimed no-op.
    It is a review aid for synthetic evidence, not a production Plan authorization.
    """
    if candidate not in {"1.16.7", "1.17.0"}:
        raise ValueError("UnreviewedMigrationCandidate")
    inventories = []
    for document, version in ((before, "1.14.9"), (after, candidate)):
        if (
            not re.fullmatch(r"1\.[0-9]+", document.get("format_version", ""))
            or document.get("terraform_version") != version
            or document.get("complete") is not True
            or document.get("errored") is not False
            or type(document.get("applyable")) is not bool
            or document.get("resource_drift")
            or document.get("deferred_changes")
            or document.get("action_invocations")
            or any(check.get("status") != "pass" for check in document.get("checks", []))
        ):
            raise ValueError("MigrationIncompleteOrUnsupportedPlan")
        prior = document["prior_state"]["values"]
        planned = document["planned_values"]
        old = plan_resources(prior["root_module"])
        new = plan_resources(planned["root_module"])
        if not old or encoded(old) != encoded(new):
            raise ValueError("MigrationDefaultOrStateValuesChanged")
        if encoded(prior.get("outputs", {})) != encoded(planned.get("outputs", {})):
            raise ValueError("MigrationOutputsChanged")
        rows = document["resource_changes"]
        if len(rows) != len(old) or {row["address"] for row in rows} != old.keys():
            raise ValueError("MigrationPlanResourceInventory")
        for row in rows:
            change = row["change"]
            if (
                row.get("mode") != "managed"
                or row.get("previous_address")
                or change.get("actions") != ["no-op"]
                or change.get("importing")
                or change.get("replace_paths")
                or unknown(change.get("after_unknown", True))
                or encoded(change["before"]) != encoded(old[row["address"]]["values"])
                or encoded(change["after"]) != encoded(new[row["address"]]["values"])
            ):
                raise ValueError("MigrationResourceChangeOrUnknown")
        outputs = planned.get("outputs", {})
        changes = document.get("output_changes", {})
        if changes.keys() != outputs.keys():
            raise ValueError("MigrationOutputsChanged")
        for name, change in changes.items():
            if (
                change.get("actions") != ["no-op"]
                or unknown(change.get("after_unknown", True))
                or encoded(change.get("before")) != encoded(change.get("after"))
                or encoded(change.get("after")) != encoded(outputs[name]["value"])
            ):
                raise ValueError("MigrationOutputsChanged")
        inventories.append(new)
    if (
        encoded(inventories[0]) != encoded(inventories[1])
        or encoded(before.get("variables", {})) != encoded(after.get("variables", {}))
        or encoded(before["planned_values"].get("outputs", {}))
        != encoded(after["planned_values"].get("outputs", {}))
    ):
        raise ValueError("MigrationDefaultOrStateValuesChanged")
    return {"status": "SYNTHETIC_NOOP_COMPATIBLE_NOT_APPLY_APPROVAL", "resources": len(new)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-json", required=True)
    parser.add_argument("--candidate-json", required=True)
    parser.add_argument("--candidate", required=True, choices=("1.16.7", "1.17.0"))
    args = parser.parse_args()
    # Print only a count/status, never values from the supplied plan documents.
    print(
        json.dumps(
            assert_noop_plan_pair(
                json.loads(Path(args.baseline_json).read_text(encoding="utf-8")),
                json.loads(Path(args.candidate_json).read_text(encoding="utf-8")),
                args.candidate,
            )
        )
    )


if __name__ == "__main__":
    main()
