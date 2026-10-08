"""Server-selected, owner-allowlisted validation samples; never interpret answer magic strings."""

import hashlib
import re

from interview_backend.evaluation.provider import CoachingPrompt


class ValidationScenario:
    model_id = "fake"

    def __init__(self, name, owner_hashes):
        if (
            name not in {"coaching_three", "provider_failure"}
            or not owner_hashes
            or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in owner_hashes)
        ):
            raise ValueError("InvalidValidationScenario")
        self.name, self.owner_hashes = name, frozenset(owner_hashes)
        self.provider_id = "fake:validation:" + name

    def authorize_owner(self, owner):
        if hashlib.sha256(owner.encode()).hexdigest() not in self.owner_hashes:
            raise ValueError("ValidationOwnerNotAllowed")

    def evaluate(self, prompt):
        # Called only by evaluate_for_owner; a general Provider entry must fail closed.
        raise ValueError("ValidationOwnerRequired")

    def evaluate_for_owner(self, prompt, owner):
        self.authorize_owner(owner)
        if not isinstance(prompt, CoachingPrompt) or self.name == "provider_failure":
            raise ValueError("ValidationProviderFailure")
        questions = (
            "本人の役割は何でしたか？",
            "本人が実行した行動は何ですか？",
            "理由は何ですか？",
        )
        count = prompt.context.coaching_count
        return {
            "status": "coaching" if count < 3 else "completed",
            "conclusion_score": 8,
            "specificity_score": 6,
            "reasoning_score": 6,
            "good_point": "検証用の決定的な評価です。",
            "improvement": "本人情報を確認します。",
            "follow_up_question": questions[count] if count < 3 else None,
            "example": prompt.context.latest_answer if count == 3 else None,
        }
