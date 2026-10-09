"""Read existing evaluation metadata without exposing answers or creating retention records."""

from interview_backend.models.internal import Evaluation
from interview_backend.models.public import validate_id


def summarize_evaluation(evaluation, *, owner, evaluation_id):
    validate_id(evaluation_id)
    if (
        not isinstance(evaluation, Evaluation)
        or not owner
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
