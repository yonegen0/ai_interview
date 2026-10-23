"""A closed Japanese edit grammar, with whole-field provenance.

This is deliberately narrower than semantic equivalence. No model-authored claim
is accepted merely because it cites a source. Qualifiers, subjects and sentence
order within each source field survive; only the reviewed surface edits below
are permitted. Unsupported compression requires clarification, never a retry.
"""

import re
from typing import Literal

from interview_backend.star_assist.models import Candidate, StarResult, Strict

STYLES = (("A", "conclusion"), ("B", "action"), ("C", "conversational"))
# These are discourse labels, not assertions of success, motivation or causality.
OPENINGS = {"A": "結果については、", "B": "取り組みについては、", "C": "このときは、"}
QUESTIONS = {
    "action": "この経験で、あなた自身が行ったことを具体的に教えてください。",
    "length": "条件や否定を残して、回答に使う経験を短く整理してください。",
    "conflict": "食い違う記述があります。同じ経験の事実関係を確認してください。",
    "grounding": "入力根拠を保った表現を確認できませんでした。行動と結果を具体的にしてください。",
}

# Only complete sentence endings are edited, never inner clauses or quoted speech.
# Negative, modal and conditional clauses are retained, not converted to success.
COMPACT_ENDINGS = (
    ("することができませんでした", "できませんでした"),
    ("することができなかった", "できなかった"),
    ("することができました", "できました"),
    ("することができた", "できた"),
    ("という状況にありました", "という状況でした"),
    ("ということが分かりました", "と分かりました"),
)
VERBAL_NOUNS = (
    "確認",
    "共有",
    "整理",
    "調整",
    "記録",
    "分析",
    "提案",
    "説明",
    "検証",
    "相談",
    "対応",
    "報告",
    "改善",
    "比較",
    "集計",
    "練習",
    "連絡",
)
POLITE_ENDINGS = (
    ("しなかった", "しませんでした"),
    ("できなかった", "できませんでした"),
    ("できた", "できました"),
    ("だった", "でした"),
    ("である", "です"),
    ("していた", "していました"),
)


class Passage(Strict):
    source: Literal["S", "T", "A", "R"]
    text: str


class ProseCandidate(Strict):
    id: Literal["A", "B", "C"]
    style: Literal["conclusion", "action", "conversational"]
    passages: list[Passage]


class ProsePlan(Strict):
    status: Literal["ready", "needs_information"]
    candidates: list[ProseCandidate]
    missingInformation: list[str]


def clarify(reason):
    return StarResult(
        status="needs_information", candidates=[], missingInformation=[QUESTIONS[reason]]
    )


def _ending(text, pairs):
    for before, after in pairs:
        if text.endswith(before):
            return text[: -len(before)] + after
    return text


def rewrite_field(source, identifier):
    """Produce a verifiable natural realization; no extraction across clauses.

    Quotes, newlines, numbers, names, conditions and unresolved prose stay intact.
    Conversation uses a softer explanatory ending only for an unquoted past
    sentence; it never invents an emotion, a reason or an inferred first-person actor.
    """
    if any(c in source for c in '「」『』"“”‘’?!！？') or any(
        marker in source for marker in ("社名", "氏名", "名前", "名称", "という名", "と呼ぶ")
    ):
        stripped = source.strip()
        return stripped if stripped.endswith(("。", "！", "？", "!", "?")) else stripped + "。"
    result = []
    for part in re.split(r"(。|\n)", source.strip()):
        if not part or part in {"。", "\n"}:
            result.append(part)
            continue
        compact = _ending(part, COMPACT_ENDINGS)
        compact = _ending(
            compact, tuple((n + "を行いました", n + "しました") for n in VERBAL_NOUNS)
        )
        polite = _ending(compact, POLITE_ENDINGS)
        if (
            polite == compact
            and compact.endswith("した")
            and not compact.endswith(("ました", "でした"))
        ):
            polite = compact[:-2] + "しました"
        if identifier == "B":
            # Only reviewed サ変 nouns take いたしました. Applying this to
            # godan 話しました/貸しました would corrupt the verb stem.
            polite = _ending(
                polite, tuple((n + "しました", n + "いたしました") for n in VERBAL_NOUNS)
            )
        if identifier == "C" and (
            not polite.endswith("ませんでした")
            or polite.endswith(("しませんでした", "できませんでした"))
        ):
            # Preserve negation: e.g. しませんでした -> しなかったんです.
            polite = _ending(
                polite,
                (
                    ("しませんでした", "しなかったんです"),
                    ("できませんでした", "できなかったんです"),
                    ("しました", "したんです"),
                    ("できました", "できたんです"),
                    ("でした", "だったんです"),
                ),
            )
        result.append(polite)
    rendered = "".join(result)
    return rendered if rendered.endswith(("。", "！", "？", "!", "?")) else rendered + "。"


def source_realizations(notes):
    """Finite, server-owned alternatives with source IDs; treated as data by LLM."""
    return {
        field: {identifier: rewrite_field(text, identifier) for identifier, _ in STYLES}
        for field, text in notes.items()
        if text.strip()
    }


def prompt_realizations(realizations):
    """Share identical surfaces to preserve the complete serialized input budget."""
    grouped = {}
    for field, variants in realizations.items():
        texts = {}
        for identifier, text in variants.items():
            texts[text] = texts.get(text, "") + identifier
        grouped[field] = {identifiers: text for text, identifiers in texts.items()}
    return grouped


def contradictory(notes):
    # Detect a finite set of exact opposite assertions. This is not an arbitrary
    # Japanese contradiction detector. Ambiguous cross-sentence relations remain
    # the model/human evaluation's responsibility and are never silently resolved.
    sentences = {
        s.strip() for text in notes.values() for s in re.split(r"[。\n]", text) if s.strip()
    }
    for sentence in sentences:
        for negative, positive in (
            ("しなかった", "した"),
            ("しませんでした", "しました"),
            ("できなかった", "できた"),
            ("できませんでした", "できました"),
        ):
            if sentence.endswith(negative) and sentence[: -len(negative)] + positive in sentences:
                return True
    return False


def validate_prose(plan, value):
    if plan.status == "needs_information":
        if plan.candidates or any(not q.strip() for q in plan.missingInformation):
            raise ValueError("StarPlan")
        # Model questions can themselves invent a premise or echo injected text.
        # Return a neutral server-owned clarification, not unverified free text.
        if not 1 <= len(plan.missingInformation) <= 4 or any(
            len(q) > 200 for q in plan.missingInformation
        ):
            raise ValueError("StarPlan")
        return clarify("grounding")
    if [(c.id, c.style) for c in plan.candidates] != list(STYLES) or plan.missingInformation:
        raise ValueError("StarPlan")
    facts = value.notes.model_dump()
    if not facts["A"].strip():
        return clarify("action")
    if contradictory(facts):
        return clarify("conflict")
    realizations = source_realizations(facts)
    candidates = []
    firsts = ("R" if "R" in realizations else "A", "A", "S" if "S" in realizations else "A")
    for c, first in zip(plan.candidates, firsts, strict=True):
        fields = [p.source for p in c.passages]
        if (
            not fields
            or fields[0] != first
            or len(fields) != len(set(fields))
            or set(fields) != set(realizations)
        ):
            return clarify("grounding")
        if any(p.text != realizations[p.source][c.id] for p in c.passages):
            return clarify("grounding")
        text = OPENINGS[c.id] + "".join(p.text for p in c.passages)
        if len(text) > 400:
            return clarify("length")
        candidates.append(Candidate(id=c.id, style=c.style, text=text))
    return StarResult(status="ready", candidates=candidates, missingInformation=[])
