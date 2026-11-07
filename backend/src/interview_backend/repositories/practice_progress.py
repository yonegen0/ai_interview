"""Owner-scoped practice progress: count distinct questions with a successful initial evaluation.

This intentionally does not reuse the history screen's latest-evaluation projection.
"""

from interview_backend.models.internal import IntegrityError

PROGRESS_MAX_RECORDS = 2000
PROGRESS_PAGE_SIZE = 100


def count_completed_questions(owner, active_ids, attempts, evaluations):
    """Return the count of completed active question IDs, never a partial count."""
    by_attempt = {}
    for attempt in attempts:
        if attempt.owner != owner or attempt.id in by_attempt:
            raise IntegrityError("progress_attempt_relation")
        by_attempt[attempt.id] = attempt

    by_evaluation = {}
    for evaluation in evaluations:
        if evaluation.owner != owner or evaluation.id in by_evaluation:
            raise IntegrityError("progress_evaluation_owner")
        by_evaluation[evaluation.id] = evaluation

    completed = set()
    for evaluation in evaluations:
        if evaluation.status != "completed":
            continue
        if evaluation.feedback is None:
            raise IntegrityError("progress_missing_feedback")
        attempt = by_attempt.get(evaluation.attempt_id)
        if (
            attempt is None
            or attempt.coaching_contract_version != evaluation.coaching_contract_version
        ):
            raise IntegrityError("progress_missing_attempt")
        if evaluation.feedback.attemptId != attempt.id:
            raise IntegrityError("progress_feedback_relation")

        if evaluation.coaching_contract_version == 2:
            # Follow-up rounds (1-3) cannot complete an additional bank question.
            if evaluation.round_index != 0:
                continue
            if evaluation.feedback.evaluationId != evaluation.id:
                raise IntegrityError("progress_feedback_relation")
            if evaluation.id != attempt.evaluation_id:
                source = by_evaluation.get(evaluation.retry_of_evaluation_id)
                if (
                    source is None
                    or source.owner != owner
                    or source.attempt_id != attempt.id
                    or source.coaching_contract_version != 2
                    or source.round_index != 0
                    or source.status != "failed"
                ):
                    raise IntegrityError("progress_retry_relation")
        elif (
            evaluation.coaching_contract_version is not None
            or evaluation.id != attempt.evaluation_id
            or evaluation.round_index is not None
        ):
            raise IntegrityError("progress_initial_relation")

        if attempt.question.id in active_ids:
            completed.add(attempt.question.id)
    return len(completed)
