"""Simple deterministic guards, separate from Provider semantic judgement."""

import re
import unicodedata

from interview_backend.models.public import JS_WHITESPACE, CoachingInput, CoachingResult


class InvalidCoachingResult(ValueError):
    """A deterministic output violation, distinct from a Provider exception."""


def question_signature(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value) if c not in JS_WHITESPACE)


def unavailable(value: str) -> bool:
    normalized = question_signature(value).rstrip("。.!！")
    return normalized in {
        "分からない",
        "わからない",
        "分かりません",
        "わかりません",
        "特にない",
        "特にありません",
        "思いつかない",
        "思いつきません",
        "覚えていない",
        "覚えていません",
        "ありません",
    }


def validate_coaching_result(result: CoachingResult, context: CoachingInput) -> None:
    if result.status != "coaching":
        return
    if not context.can_ask_follow_up:
        raise InvalidCoachingResult("CoachingLimit")
    signature = question_signature(result.follow_up_question)
    previous = {question_signature(h.question) for h in context.coaching_history}
    previous.update(question_signature(q) for q in context.unavailable_questions)
    if signature in previous:
        raise InvalidCoachingResult("RepeatedQuestion")
    # Newlines and option lists alone do not prove that there are multiple questions.
    questions = [
        line
        for line in result.follow_up_question.splitlines()
        if re.match(r"^\s*(?:\d+[.)．、]|[-*・])\s*.+[?？]\s*$", line)
    ]
    if len(questions) >= 2:
        raise InvalidCoachingResult("MultipleQuestions")
