"""Read existing evaluation metadata without exposing answers or creating retention records."""

from interview_backend.models.internal import Evaluation
from interview_backend.models.public import validate_id


def summarize_evaluation(evaluation, *, owner, evaluation_id):
    validate_id(evaluation_id)
    if (
        not isinstance(evaluation, Evaluation)
        or not isinstance(owner, str)
        or not owner.strip()
        or evaluation.owner != owner
        or evaluation.id != evaluation_id
    ):
        raise ValueError("ExactOwnerEvaluationRequired")
    config = evaluation.execution_config
    return {
        "userId": owner,
        "evaluationId": evaluation.id,
        "attemptId": evaluation.attempt_id,
        "requestedAtEpochMs": evaluation.created_at,
        "finishedAtEpochMs": evaluation.finished_at,
        "status": evaluation.status,
        "errorClassification": evaluation.failure_reason,
        "elapsedMs": None
        if evaluation.finished_at is None
        else max(0, evaluation.finished_at - evaluation.created_at),
        "providerId": config.provider_id if config else "unknown",
        "modelId": config.model_id if config else "unknown",
    }


def read_summary(client, table_name, *, owner, evaluation_id):
    """Exact consistent owner lookup, including legacy and terminal failed records."""
    from interview_backend.repositories.codec import decode, from_wire, to_wire

    validate_id(evaluation_id)
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("ExactOwnerEvaluationRequired")
    response = client.get_item(
        TableName=table_name,
        Key=to_wire({"PK": f"USER#{owner}", "SK": f"EVALUATION#{evaluation_id}"}),
        ConsistentRead=True,
    )
    if "Item" not in response:
        raise ValueError("SupportEvaluationUnavailable")
    evaluation, _ = decode(from_wire(response["Item"]))
    return summarize_evaluation(evaluation, owner=owner, evaluation_id=evaluation_id)
