"""Pydantic mirror of frontend/src/lib/api/schemas; preserve JS string semantics."""

import math
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, field_validator

ANSWER_MAX_LENGTH = 500

# z.uuid(): RFC variant/version, plus the nil and max UUIDs; retain original spelling.
UUID_PATTERN = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    r"|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)$",
    re.IGNORECASE,
)
JS_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    + "".join(chr(code) for code in range(0x2000, 0x200B))
    + "\u2028\u2029\u202f\u205f\u3000\ufeff"
)


class InvalidIdentifier(ValueError):
    """A request identifier is not a Zod-compatible UUID."""


def validate_id(value: str) -> str:
    """Validate an API identifier without Python UUID's permissive coercion."""
    if not isinstance(value, str) or not UUID_PATTERN.fullmatch(value):
        raise InvalidIdentifier("Invalid UUID")
    return value


Identifier = Annotated[str, AfterValidator(validate_id)]
Category = Literal[
    "job_change", "motivation", "strengths", "experience", "difficulty", "career", "questions"
]
CATEGORIES = (
    "job_change",
    "motivation",
    "strengths",
    "experience",
    "difficulty",
    "career",
    "questions",
)
Status = Literal["processing", "completed", "failed"]
PositiveInt = Annotated[int, Field(gt=0)]


class Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    def wire(self) -> dict:
        # Unset optional properties are omitted; required activeAttempt remains null.
        return self.model_dump(mode="json", exclude_unset=True)


class AnswerFields(Model):
    answer: str

    @field_validator("answer")
    @classmethod
    def answer_length(cls, value: str) -> str:
        length = len(value.encode("utf-16-le", errors="surrogatepass")) // 2
        if not 1 <= length <= ANSWER_MAX_LENGTH or not value.strip(JS_WHITESPACE):
            raise ValueError("Invalid answer")
        return value


class CreateRequest(Model):
    category: Category
    difficulty: Literal["standard"]


class Created(Model):
    sessionId: Identifier


class Question(CreateRequest):
    id: Identifier
    question: Annotated[str, Field(min_length=1)]


class ErrorBody(Model):
    code: str
    message: str


class ActiveAttempt(Model):
    attemptId: Identifier
    evaluationId: Identifier
    status: Status


class SessionResponse(Model):
    sessionId: Identifier
    question: Question
    questionNumber: PositiveInt
    activeAttempt: ActiveAttempt | None


class SubmitRequest(AnswerFields):
    questionId: Identifier


class NextRequest(Model):
    fromAttemptId: Identifier


class Processing(Model):
    evaluationId: Identifier
    attemptId: Identifier
    status: Literal["processing"]


class Completed(Model):
    evaluationId: Identifier
    attemptId: Identifier
    status: Literal["completed"]


class Failed(Model):
    evaluationId: Identifier
    attemptId: Identifier
    status: Literal["failed"]
    error: ErrorBody


EvaluationResponse = Annotated[Processing | Completed | Failed, Field(discriminator="status")]
evaluation_adapter = TypeAdapter(EvaluationResponse)


class EvaluationResult(Model):
    score: Annotated[int, Field(ge=0, le=100)]

    @field_validator("score", mode="before")
    @classmethod
    def integer_score(cls, value: object) -> object:
        """Match JSON/Zod integer values without coercing strings or booleans."""
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return int(value)
        return value

    summary: str
    strengths: list[str]
    improvements: list[str]
    # None is not accepted when explicitly supplied (Zod optional != nullable).
    exampleAnswer: str = Field(default=None, validate_default=False)  # type: ignore[assignment]


class Feedback(EvaluationResult, AnswerFields):
    attemptId: Identifier
    sessionId: Identifier
    question: Question
    questionNumber: PositiveInt
    createdAt: str

    @field_validator("createdAt")
    @classmethod
    def utc_datetime(cls, value: str) -> str:
        from datetime import datetime

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
            raise ValueError("Expected UTC ISO date")
        datetime.fromisoformat(value)
        return value
