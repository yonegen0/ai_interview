"""Versioned text limits; counting never changes the stored applicant text."""

QUESTION_MAX_LENGTH = 200
COACHING_ANSWER_MAX_LENGTH = 400


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def code_point_length(value: str) -> int:
    # Also count explicit Python surrogate pairs like Array.from does in JS.
    return len(
        value.encode("utf-16-le", errors="surrogatepass").decode(
            "utf-16-le", errors="surrogatepass"
        )
    )


def score_values(answer: str, conclusion: int, specificity: int, reasoning: int) -> dict:
    length = code_point_length(answer)
    penalty = 0 if length <= 300 else 1 if length <= 350 else 2 if length <= 400 else 3
    base = conclusion + specificity + reasoning
    total = max(0, base - penalty)
    return dict(
        answerLength=length,
        lengthPenalty=penalty,
        baseScore=base,
        totalScore=total,
        rank="S" if total >= 26 else "A" if total >= 21 else "B" if total >= 15 else "C",
    )
