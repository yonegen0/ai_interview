"""Observe runtime transaction records through run-owned exact GetItem keys only."""

from interview_backend.repositories.codec import PARTITIONS, from_wire, key


def read_exact(client, table, native_key):
    from interview_backend.repositories.codec import to_wire

    response = client.get_item(TableName=table, Key=to_wire(native_key), ConsistentRead=True)
    item = from_wire(response["Item"]) if "Item" in response else None
    if item is not None and any(item.get(k) != v for k, v in native_key.items()):
        raise ValueError("RuntimeReceiptExactKeyMismatch")
    return item


def cursor_revisions(client, table):
    result = {}
    for partition in PARTITIONS:
        item = read_exact(client, table, key("RecoveryCursor", "", partition.removeprefix("WORK#")))
        result[partition] = item["rev"] if item else -1
    return result


def collect(client, manifest, approval, run, before_cursors):
    import json

    table, owner = manifest["table_name"], approval["subjects"]["USER_A"]
    evaluations = {r["evaluation_id"] for r in run.rows if "evaluation_id" in r}
    worker, dispatch = False, False
    for eid in sorted(evaluations):
        item = read_exact(client, table, key("Evaluation", owner, eid))
        message = read_exact(client, table, key("Dispatch", owner, eid))
        if (
            item
            and item.get("kind") == "Evaluation"
            and json.loads(item["data"]).get("status") in {"completed", "failed"}
        ):
            worker = True
        if message and message.get("kind") == "Dispatch":
            data = json.loads(message["data"])
            if (
                data.get("status") in {"QUEUED", "CLAIMED", "DONE"}
                and data.get("delivery_attempts", 0) > 0
            ):
                dispatch = True
    run.record("Worker-transaction-record-observed", "passed" if worker else "not_run")
    run.record("Dispatcher-transaction-record-observed", "passed" if dispatch else "not_run")
    after = cursor_revisions(client, table)
    recovered = before_cursors is not None and all(after[p] > before_cursors[p] for p in PARTITIONS)
    run.record("Recovery-checkpoint-transaction-observed", "passed" if recovered else "not_run")
    # A successful ADMIN transaction contains the narrow USER-key ConditionCheck.
    admin = approval["subjects"]["ADMIN"]
    admin_keys = {
        r["request_key"] for r in run.rows if r["check"].startswith("admin-") and "request_key" in r
    }
    conditioncheck = False
    for request_key in sorted(admin_keys):
        item = read_exact(client, table, key("IdempotencyRecord", admin, request_key))
        if item and item.get("kind") == "IdempotencyRecord":
            conditioncheck = True
    run.record(
        "ADMIN-ConditionCheck-business-record-observed", "passed" if conditioncheck else "not_run"
    )
    # Reclaim, ACK-loss, lease/deadline and the independent IAM simulator case stay separate.
    run.record("Recovery-reclaim-lease-boundary", "not_run")
    run.record("IAM-ConditionCheck1-independent-case", "not_run")
