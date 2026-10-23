"""Strict public contracts and independent single-table records."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from interview_backend.models.public import Identifier
from interview_backend.text_limits import code_point_length

DAY = 86400
CATEGORIES = {
    "corporate_sales": "法人営業",
    "consumer_sales": "個人営業",
    "office_reception": "事務・受付",
    "retail_service": "接客・販売・サービス",
    "it_engineering": "IT・エンジニア",
    "manufacturing_technical": "製造・技術",
    "construction_management": "建設・施工管理",
    "healthcare_welfare": "医療・介護・福祉",
    "planning_management": "企画・管理",
    "other": "その他",
}
TargetCategory = Literal[
    "corporate_sales",
    "consumer_sales",
    "office_reception",
    "retail_service",
    "it_engineering",
    "manufacturing_technical",
    "construction_management",
    "healthcare_welfare",
    "planning_management",
    "other",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def text(value, maximum):
    if code_point_length(value) > maximum:
        raise ValueError("text_limit")
    return value


class Notes(Strict):
    S: str
    T: str
    A: str
    R: str

    @field_validator("S", "T", "A", "R")
    @classmethod
    def bounded(cls, value):
        return text(value, 2000)


class Candidate(Strict):
    id: Literal["A", "B", "C"]
    style: Literal["conclusion", "action", "conversational"]
    text: str

    @field_validator("text")
    @classmethod
    def bounded(cls, value):
        return text(value, 400)


class StarResult(Strict):
    status: Literal["ready", "needs_information"]
    candidates: list[Candidate]
    missingInformation: list[str]

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "ready":
            if [(c.id, c.style) for c in self.candidates] != [
                ("A", "conclusion"),
                ("B", "action"),
                ("C", "conversational"),
            ] or any(not c.text.strip() for c in self.candidates):
                raise ValueError("candidates")
        elif self.candidates or not self.missingInformation:
            raise ValueError("missing_information")
        if len(self.missingInformation) > 4:
            raise ValueError("missing_information")
        for value in self.missingInformation:
            text(value, 200)
        return self


class StarInput(Strict):
    notes: Notes
    targetCategory: TargetCategory | None
    industry: str
    company: str
    candidates: list[Candidate]
    selectedCandidateId: Literal["A", "B", "C"] | None
    generationId: Identifier | None

    @field_validator("industry", "company")
    @classmethod
    def bounded(cls, value, info):
        return text(value, 100 if info.field_name == "industry" else 200)

    @model_validator(mode="after")
    def consistent(self):
        if self.candidates and [(c.id, c.style) for c in self.candidates] != [
            ("A", "conclusion"),
            ("B", "action"),
            ("C", "conversational"),
        ]:
            raise ValueError("candidates")
        if self.selectedCandidateId and self.selectedCandidateId not in [
            c.id for c in self.candidates
        ]:
            raise ValueError("selection")
        if bool(self.candidates) != bool(self.generationId):
            raise ValueError("generation")
        return self


class Versioned(Strict):
    expectedVersion: int = Field(ge=0)


class CategorySelection(Versioned):
    expectedGeneration: Identifier | None
    targetCategory: TargetCategory


class DetailsSelection(Versioned):
    expectedGeneration: Identifier | None
    industry: str
    company: str

    @field_validator("industry", "company")
    @classmethod
    def bounded(cls, value, info):
        return text(value, 100 if info.field_name == "industry" else 200)


class PreferencesRequest(Strict):
    category: CategorySelection | None = None
    details: DetailsSelection | None = None

    @model_validator(mode="after")
    def changed(self):
        if self.category is None and self.details is None:
            raise ValueError("empty_preferences")
        return self


class ContextRequest(Strict):
    operationKind: Literal["initial_answer", "coaching_answer", "retry_attempt"]
    questionId: Identifier
    fromAttemptId: Identifier | None = None
    fromEvaluationId: Identifier | None = None

    @model_validator(mode="after")
    def origin(self):
        if (self.operationKind != "initial_answer") != bool(
            self.fromAttemptId and self.fromEvaluationId
        ):
            raise ValueError("origin")
        if self.operationKind == "initial_answer" and (self.fromAttemptId or self.fromEvaluationId):
            raise ValueError("origin")
        return self


class AnswerValue(Strict):
    answer: str
    applicationId: Identifier | None = None

    @field_validator("answer")
    @classmethod
    def bounded(cls, value):
        return text(value, 16000)


class AnswerUpdate(AnswerValue, Versioned):
    pass


class StarUpdate(StarInput, Versioned):
    pass


class GenerateRequest(Versioned):
    starDraftId: Identifier


class ApplyRequest(Versioned):
    candidateId: Literal["A", "B", "C"]
    answerDraftId: Identifier
    expectedAnswerVersion: int = Field(ge=1)


@dataclass
class TargetCategoryPreference:
    owner: str
    id: str
    target_category: str
    version: int
    updated_at: int
    expires_at: int


@dataclass
class TargetDetailsPreference:
    owner: str
    id: str
    industry: str
    company: str
    version: int
    updated_at: int
    expires_at: int


@dataclass
class AnswerContext:
    owner: str
    id: str
    session_id: str
    question_number: int
    question_id: str
    question_hash: str
    question: str
    operation_kind: str
    from_attempt_id: str | None = None
    from_evaluation_id: str | None = None
    answer_draft_id: str | None = None
    star_draft_id: str | None = None
    active_generation_id: str | None = None
    status: str = "ACTIVE"


@dataclass
class AnswerDraft:
    owner: str
    id: str
    context_id: str
    answer: str
    version: int
    updated_at: int
    expires_at: int
    status: str = "ACTIVE"
    application_id: str | None = None


@dataclass
class StarDraft:
    owner: str
    id: str
    context_id: str
    value: StarInput
    version: int
    updated_at: int
    expires_at: int
    status: str = "ACTIVE"
    original_candidates: tuple[Candidate, ...] = ()
    generation_target_category: str | None = None


@dataclass
class StarGeneration:
    owner: str
    id: str
    context_id: str
    star_draft_id: str
    input: StarInput
    question: str
    month: str
    created_at: int
    deadline_at: int
    status: str = "QUEUED"
    worker_state: str = "pending"
    quota_state: str = "reserved"
    lock_owner: str | None = None
    lock_expires_at: int | None = None
    call_started: bool = False
    result: StarResult | None = None
    finished_at: int | None = None
    expires_at: int | None = None
    provider_id: str = "fake"
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: str | None = None


@dataclass
class StarRequest:
    owner: str
    id: str
    fingerprint: str
    method: str
    path: str
    status: int
    receipt: dict
    created_at: int


@dataclass
class StarApplication:
    owner: str
    id: str
    context_id: str
    answer_draft_id: str
    generation_id: str
    candidate_id: str
    applied_hash: str
    updated_at: int
    expires_at: int


@dataclass
class AnswerAssist:
    owner: str
    id: str
    context_id: str
    application_id: str
    generation_id: str
    candidate_id: str
    final_hash: str
    edited: bool


@dataclass
class StarQuota:
    owner: str
    id: str
    month: str
    reserved: int = 0
    consumed: int = 0


@dataclass
class GlobalStarQuota(StarQuota):
    pass


@dataclass
class RecoveryRotation:
    owner: str
    id: str
    position: int = 0


@dataclass(frozen=True)
class StarRecoveryResult:
    """Committed recovery observation; never stored or exposed as an API response."""

    status: str
    outcome_unknown: bool = False


RECORDS = {
    c.__name__: c
    for c in (
        TargetCategoryPreference,
        TargetDetailsPreference,
        AnswerContext,
        AnswerDraft,
        StarDraft,
        StarGeneration,
        StarRequest,
        StarApplication,
        AnswerAssist,
        StarQuota,
        GlobalStarQuota,
        RecoveryRotation,
    )
}
PREFIXES = {
    "TargetCategoryPreference": "TARGET_CATEGORY",
    "TargetDetailsPreference": "TARGET_DETAILS",
    "AnswerContext": "ANSWER_CONTEXT",
    "AnswerDraft": "ANSWER_DRAFT",
    "StarDraft": "STAR_DRAFT",
    "StarGeneration": "STAR_GENERATION",
    "StarRequest": "STAR_REQUEST",
    "StarApplication": "STAR_APPLICATION",
    "AnswerAssist": "ANSWER_ASSIST",
    "StarQuota": "STAR_QUOTA",
    "GlobalStarQuota": "STAR_QUOTA",
    "RecoveryRotation": "ROTATION",
}
