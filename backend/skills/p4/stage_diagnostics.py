"""Offline, exhaustive Stage recovery diagnosis. Never authorizes Plan or Apply.

Inputs and the address-level report stay private. Attribute values and exception
messages are never included. The production fail-closed auditor is unchanged.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import stage_recovery as recovery

ERRORS = (KeyError, TypeError, ValueError, AttributeError, IndexError)


def attributes_changed(before, after):
    """Names only; deliberately do not expose nested map keys or values."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    missing = object()
    return sorted(
        k for k in before.keys() | after.keys() if before.get(k, missing) != after.get(k, missing)
    )


def diagnose(plan: dict, descriptor: dict, snapshot: dict) -> dict:
    """Inspect every available address, collecting independent failures per row.

    A/B describe only the existing narrowly proven equivalences. C includes the
    intended Stage update, marked allowed. D is missing/ambiguous evidence.
    Counts are exclusive per resource, with D > C > B > A > MATCH priority.
    """
    global_findings = []

    def attempt(code, function, fallback):
        try:
            return function()
        except ERRORS:
            global_findings.append(code)
            return fallback

    original = attempt("state-shape", lambda: recovery.state_resources(snapshot), {})
    expected = attempt(
        "cache-projection",
        lambda: recovery.expected_state_resources(snapshot, descriptor),
        original,
    )
    attempt("state-binding", lambda: recovery.check_state(snapshot, descriptor), None)

    def index_rows(rows):
        result = defaultdict(list)
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("address"), str):
                global_findings.append("row-shape")
                continue
            if row.get("mode", "managed") == "managed":
                result[row["address"]].append(row)
        return result

    def flatten(root):
        rows = list(root.get("resources", []))
        for child in root.get("child_modules", []):
            rows.extend(flatten(child))
        return rows

    changes = attempt("change-shape", lambda: index_rows(plan["resource_changes"]), {})
    drifts = attempt("drift-shape", lambda: index_rows(plan.get("resource_drift", [])), {})
    planned = attempt(
        "planned-shape", lambda: index_rows(flatten(plan["planned_values"]["root_module"])), {}
    )
    refreshed = attempt(
        "refresh-evidence-missing",
        lambda: index_rows(flatten(plan["prior_state"]["values"]["root_module"])),
        {},
    )
    addresses = sorted(
        original.keys() | changes.keys() | drifts.keys() | planned.keys() | refreshed.keys()
    )

    def inspect(address):
        findings = []

        def note(category, code, before=None, after=None, *, allowed=False):
            findings.append(
                dict(
                    category=category,
                    code=code,
                    attributes=attributes_changed(before, after),
                    allowed=allowed,
                )
            )

        def check(code, function, category="C", before=None, after=None):
            try:
                recovery.require(function())
                return True
            except ERRORS:
                note(category, code, before, after)
                return False

        if "state-binding" in global_findings or "state-shape" in global_findings:
            note("D", "unbound-state")
        for label, mapping in (("change", changes), ("planned", planned), ("refresh", refreshed)):
            if len(mapping.get(address, [])) != 1:
                note("D", label + "-coverage")
        if address not in original:
            note("C", "resource-added")
        if len(drifts.get(address, [])) > 1:
            note("D", "duplicate-drift")

        row = changes.get(address, [None])[0]
        if row is not None:
            try:
                change = row["change"]
                before, after = change["before"], change["after"]
                check(
                    "unknown-values",
                    lambda: not recovery.has_unknown(change.get("after_unknown", {})),
                    "D",
                )
                check(
                    "import-move-deposed-replace",
                    lambda: (
                        not (
                            row.get("previous_address")
                            or row.get("deposed")
                            or change.get("importing")
                            or change.get("replace_paths")
                        )
                    ),
                )
                if address in planned:
                    check(
                        "planned-value-match",
                        lambda: planned[address][0]["values"] == after,
                        before=after,
                        after=planned[address][0].get("values"),
                    )
                if address in refreshed:
                    check(
                        "refresh-before-match",
                        lambda: recovery.resource_state_equal(
                            address, refreshed[address][0]["values"], before
                        ),
                        before=refreshed[address][0].get("values"),
                        after=before,
                    )
                if address == recovery.ADDRESS:

                    def valid_stage():
                        recovery.require(row["type"] == "aws_apigatewayv2_stage")
                        recovery.require(change["actions"] == ["update"])
                        recovery.stage_change(before, after, descriptor)
                        return after == expected[address]

                    if check("stage-format-only", valid_stage, before=before, after=after):
                        note("C", "intended-stage-format-update", before, after, allowed=True)
                else:
                    check(
                        "other-resource-noop",
                        lambda: change["actions"] == ["no-op"] and before == after,
                        before=before,
                        after=after,
                    )
                    check(
                        "state-match",
                        lambda: recovery.resource_state_equal(address, after, expected[address]),
                        before=original.get(address),
                        after=after,
                    )
                    if address in original and original[address] != after:
                        if original[address] != expected[address]:
                            note("B", "pinned-policy-cache", original[address], after, allowed=True)
                        elif recovery.resource_state_equal(address, original[address], after):
                            note(
                                "A",
                                "provider-representation",
                                original[address],
                                after,
                                allowed=True,
                            )
            except ERRORS:
                note("D", "change-evidence-invalid")

        def inspect_drift(drift):
            try:
                change = drift["change"]
                before, after = change["before"], change["after"]
                check(
                    "drift-before-match",
                    lambda: before == original[address],
                    before=original.get(address),
                    after=before,
                )
                check(
                    "drift-refresh-match",
                    lambda: after == refreshed[address][0]["values"],
                    before=after,
                    after=refreshed.get(address, [{}])[0].get("values"),
                )
                check(
                    "drift-identity",
                    lambda: (
                        not (
                            drift.get("previous_address")
                            or drift.get("deposed")
                            or change.get("importing")
                            or change.get("replace_paths")
                        )
                        and change["actions"] == ["update"]
                    ),
                )
                check(
                    "drift-unknown",
                    lambda: not recovery.has_unknown(change.get("after_unknown", {})),
                    "D",
                )

                def allowed_drift():
                    if address == recovery.ADDRESS:
                        recovery.stage_change(before, after, descriptor, drift=True)
                        return True
                    if (
                        address == recovery.API_ROLE
                        and descriptor.get("api_role_policy_cache_refresh") is True
                    ):
                        return after == expected[address]
                    return (
                        address == recovery.API_ADDRESS or recovery.fixed_route(address)
                    ) and recovery.resource_state_equal(address, before, after)

                if check("unapproved-drift", allowed_drift, before=before, after=after):
                    if (
                        address == recovery.ADDRESS
                        and "observed_deployment_id" in descriptor["stage"]
                    ):
                        note("B", "pinned-stage-deployment-cache", before, after, allowed=True)
            except ERRORS:
                note("D", "drift-evidence-invalid")

        for drift in drifts.get(address, []):
            inspect_drift(drift)

        if address in original and address in refreshed and address not in drifts:
            check(
                "unreported-refresh-difference",
                lambda: original[address] == refreshed[address][0]["values"],
                "D",
                original[address],
                refreshed[address][0].get("values"),
            )
        category = next(
            (c for c in ("D", "C", "B", "A") if any(f["category"] == c for f in findings)), "MATCH"
        )
        return dict(
            address=address,
            category=category,
            requires_action=any(not f["allowed"] for f in findings),
            findings=findings,
        )

    results = [inspect(address) for address in addresses]
    outputs = []
    for name, change in plan.get("output_changes", {}).items():
        try:
            recovery.require(change["actions"] == ["no-op"] and change["before"] == change["after"])
            recovery.require(not recovery.has_unknown(change.get("after_unknown", {})))
            status = "UNCHANGED"
        except ERRORS:
            status = "REJECTED"
            global_findings.append("output-change-or-unknown")
        outputs.append(dict(name=name, status=status))

    # This remains the sole existing formal Plan acceptance algorithm. Diagnostic
    # findings neither grant consent nor bypass its fail-fast rejection.
    try:
        recovery.audit_plan(plan, descriptor, snapshot)
        formal_plan_audit = "ACCEPTED"
    except ERRORS:
        formal_plan_audit = "REJECTED"
        global_findings.append("formal-plan-audit-rejected")
    counts = Counter(row["category"] for row in results)
    return dict(
        diagnostic_only=True,
        status="FINDINGS"
        if global_findings or any(r["requires_action"] for r in results)
        else "DIAGNOSED",
        state_resource_count=len(original),
        inspected_address_count=len(results),
        counts={c: counts[c] for c in ("MATCH", "A", "B", "C", "D")},
        formal_plan_audit=formal_plan_audit,
        global_findings=sorted(set(global_findings)),
        resources=results,
        outputs=outputs,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "snapshot", "descriptor", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        report = diagnose(
            *[json.loads(p.read_bytes()) for p in (args.plan, args.descriptor, args.snapshot)]
        )
        # Exclusive creation preserves prior private evidence. No raw input goes
        # to stdout; the caller must select an existing private output directory.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
    except (*ERRORS, OSError):
        parser.exit(2, "OfflineDiagnosisInputOrOutputRejected\n")
    print(
        json.dumps(
            {k: report[k] for k in ("diagnostic_only", "status", "state_resource_count", "counts")}
        )
    )
    return 0 if report["status"] == "DIAGNOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
