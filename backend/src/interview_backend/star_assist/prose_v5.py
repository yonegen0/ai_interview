"""Limited fact checks and per-candidate recovery for prose-v5.

This does not prove semantic accuracy. Claude writes natural prose; the server
keeps strictly valid candidates and fills only unsafe/missing slots from prose-v4.
"""

import re
import unicodedata
from collections import Counter
from typing import Literal

from pydantic import ValidationError

from interview_backend.star_assist.grounding import (
    STYLES,
    clarify,
    contradictory,
    safe_v4_candidates,
    source_realizations,
)
from interview_backend.star_assist.models import Candidate, StarResult, Strict


class ProseV5Reply(Strict):
    status: Literal["ready", "needs_information"]
    candidates: list[Candidate]
    missingInformation: list[str]


_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_CHANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:品|件|人|社|個|円|点|%|％)?\s*"
    r"(?:から|→|⇒)\s*(\d+(?:\.\d+)?)"
)
_OPPOSITES = (
    ("しなかった", "しました"),
    ("しませんでした", "しました"),
    ("していない", "しています"),
    ("していません", "しています"),
    ("できなかった", "できました"),
    ("できませんでした", "できました"),
)


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def _numbers(value: str) -> set[str]:
    return {m.group().replace(",", "") for m in _NUMBER.finditer(_normalized(value))}


def _unsafe_claim(text: str, notes: dict[str, str]) -> bool:
    """Reject new numbers, explicit reversed changes and clear negation flips."""
    original = _normalized("\n".join(notes.values()))
    normalized = _normalized(text)
    if _numbers(normalized) - _numbers(original):
        return True
    original_pairs = {(a, b) for a, b in _CHANGE.findall(original) if a != b}
    if any((b, a) in original_pairs for a, b in _CHANGE.findall(normalized)):
        return True
    for sentence in re.split(r"[。\n]", original):
        trimmed = sentence.strip().lstrip("・-* ").strip()
        for negative, positive in _OPPOSITES:
            if trimmed.endswith(negative):
                prefix = trimmed[: -len(negative)]
                if prefix and prefix + positive in normalized:
                    return True
    return False


def validate_prose_v5(raw: object, value) -> tuple[StarResult, str | None, bool]:
    """Salvage only independently validated candidates; never replay AI output."""
    notes = value.notes.model_dump()
    if not notes["A"].strip() or any(
        marker in notes["A"] for marker in ("一切行っていない", "何もしていない")
    ):
        return clarify("action"), "INPUT_ACTION_MISSING", False
    if contradictory(notes):
        return clarify("conflict"), "INPUT_CONFLICT", False

    fallback, _ = safe_v4_candidates(source_realizations(notes))
    if not isinstance(raw, dict):
        raw = {}
    try:
        ProseV5Reply.model_validate(raw)
        schema_valid = True
    except (ValidationError, ValueError, TypeError):
        schema_valid = False

    if raw.get("status") == "needs_information":
        if fallback is None:
            return clarify("length"), "INPUT_LENGTH_EXCEEDED", False
        return (
            StarResult(status="ready", candidates=fallback, missingInformation=[]),
            "MODEL_REQUESTED_INFORMATION" if schema_valid else "INVALID_SCHEMA",
            True,
        )

    entries = raw.get("candidates")
    entries = entries if isinstance(entries, list) else []
    counts = Counter(
        entry.get("id")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    )
    safe: dict[str, Candidate] = {}
    repaired = False
    if raw.get("status") == "ready" and raw.get("missingInformation") == []:
        for entry in entries[:12]:
            if not isinstance(entry, dict):
                continue
            identifier = entry.get("id")
            if identifier not in {"A", "B", "C"} or counts[identifier] != 1:
                continue
            expected = dict(STYLES)[identifier]
            candidate = entry
            if entry.get("style") != expected and entry.get("style") in dict(STYLES).values():
                candidate = {**entry, "style": expected}
                repaired = True
            try:
                parsed = Candidate.model_validate(candidate)
            except (ValidationError, ValueError, TypeError):
                continue
            if parsed.text.strip() and not _unsafe_claim(parsed.text, notes):
                safe[identifier] = parsed

    if fallback is None and len(safe) != 3:
        return clarify("length"), "INPUT_LENGTH_EXCEEDED", False

    restored = []
    fallback_used = False
    for index, (identifier, _) in enumerate(STYLES):
        if identifier in safe:
            restored.append(safe[identifier])
        else:
            restored.append(fallback[index])
            fallback_used = True
    result = StarResult(status="ready", candidates=restored, missingInformation=[])
    order_changed = list(safe) != [identifier for identifier, _ in STYLES if identifier in safe]
    reason = None
    if not schema_valid:
        reason = "INVALID_SCHEMA"
    elif fallback_used or repaired or order_changed:
        reason = "MODEL_STRUCTURE_MISMATCH"
    return result, reason, fallback_used
