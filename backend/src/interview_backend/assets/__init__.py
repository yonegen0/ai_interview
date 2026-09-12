"""Load a validated question bank from packaged JSON."""

import json
from importlib.resources import files

from interview_backend.models.public import CATEGORIES, Question


def load_questions() -> tuple[Question, ...]:
    raw = files(__package__).joinpath("questions.json").read_text(encoding="utf-8")
    return validate_bank(json.loads(raw))


def validate_bank(values: list[dict]) -> tuple[Question, ...]:
    questions = tuple(Question.model_validate(value) for value in values)
    if len({q.id.lower() for q in questions}) != len(questions):
        raise ValueError("Duplicate question IDs")
    if {q.category for q in questions} != set(CATEGORIES):
        raise ValueError("Missing categories")
    return questions
