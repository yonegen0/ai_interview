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
    r"(?<![\d,])(?P<start>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<start_unit>品|件|人|社|個|円|点|%)?\s*(?:から|→|⇒)\s*"
    r"(?P<end>\d[\d,]*(?:\.\d+)?)\s*(?P<end_unit>品|件|人|社|個|円|点|%)?"
)
_NO_ACTION = frozenset({"特になし", "何もしていない", "一切行っていない", "行動は不明"})
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


def missing_action(notes: dict[str, str]) -> bool:
    """Reject only an empty A field or an unambiguous whole-field non-action."""
    action = _normalized(notes.get("A", "")).strip().strip("・-*。.!?？ \t\r\n")
    return not action or action in _NO_ACTION


def _changes(value: str) -> list[tuple[str, str, str, str]]:
    return [
        (
            match["start"].replace(",", ""),
            match["start_unit"] or "",
            match["end"].replace(",", ""),
            match["end_unit"] or "",
        )
        for match in _CHANGE.finditer(value)
    ]


def _compatible(unit: str, original_unit: str) -> bool:
    return not unit or not original_unit or unit == original_unit


def _unsafe_claim(text: str, notes: dict[str, str]) -> bool:
    """Reject new numbers, unambiguous incorrect change pairs and negation flips."""
    original = _normalized("\n".join(notes.values()))
    normalized = _normalized(text)
    if _numbers(normalized) - _numbers(original):
        return True
    original_pairs = _changes(original)
    for start, start_unit, end, end_unit in _changes(normalized):
        if any(
            start == ref_start
            and end == ref_end
            and _compatible(start_unit, ref_start_unit)
            and _compatible(end_unit, ref_end_unit)
            for ref_start, ref_start_unit, ref_end, ref_end_unit in original_pairs
        ):
            continue
        # Do not infer relationships from number order or unspecified units.
        # A unique explicit source anchor is needed to identify a wrong pairing.
        from_matches = [
            pair
            for pair in original_pairs
            if (pair[1] or pair[3])
            and pair[0] == start
            and _compatible(start_unit, pair[1])
        ]
        to_matches = [
            pair
            for pair in original_pairs
            if (pair[1] or pair[3])
            and pair[2] == end
            and _compatible(end_unit, pair[3])
        ]
        if len(from_matches) == 1 or len(to_matches) == 1:
            return True
        # Retain the previous exact reversed-change protection.
        if any(start == b and end == a and a != b for a, _, b, _ in original_pairs):
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
    if missing_action(notes):
        return clarify("action"), "INPUT_ACTION_MISSING", False
    if contradictory(notes):
        return clarify("conflict"), "INPUT_CONFLICT", False

    fallback, _ = safe_v4_candidates(source_realizations(notes))
    if not isinstance(raw, dict):
        raw = {}
    try:
        ProseV5Reply.model_validate(raw)
        schema_valid = True
    except ValidationError, ValueError, TypeError:
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
    if raw.get("status") == "ready" and raw.get("missingInformation", []) == []:
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
            except ValidationError, ValueError, TypeError:
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
