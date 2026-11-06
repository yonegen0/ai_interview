"""Bounded, owner-scoped history projection with stable snapshot pagination."""

import base64
import json
from datetime import UTC, datetime, timedelta, timezone

from interview_backend.models.internal import BusinessError, IntegrityError, Reply

JST = timezone(timedelta(hours=9))
HISTORY_MAX_RECORDS = 2000
HISTORY_PAGE_SIZE = 100
ASSIST_MODES = {"star", "prep", "motivation", "career_change", "career_plan"}
MODES = {"all", "normal", "coaching", "assist"} | ASSIST_MODES
PERIODS = {"all", "today", "7d", "30d"}


def parse_history_query(owner, params, now):
    """A cursor is a position hint, not authorization; owner always comes from JWT."""
    if not isinstance(params, dict) or set(params) - {"mode", "period", "limit", "cursor"}:
        raise BusinessError(400, "VALIDATION_ERROR")
    mode = params.get("mode", "all")
    period = params.get("period", "all")
    limit = params.get("limit", "5")
    if (
        mode not in MODES
        or period not in PERIODS
        or not isinstance(limit, str)
        or not limit.isascii()
        or not limit.isdecimal()
        or len(limit) > 3
    ):
        raise BusinessError(400, "VALIDATION_ERROR")
    count = int(limit)
    if not 1 <= count <= 100:
        raise BusinessError(400, "VALIDATION_ERROR")
    anchor, after = now, None
    cursor = params.get("cursor")
    if cursor is not None:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 700:
            raise BusinessError(400, "VALIDATION_ERROR")
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            if not isinstance(value, dict) or set(value) != {
                "owner",
                "mode",
                "period",
                "anchor",
                "after",
            }:
                raise ValueError("cursor_shape")
            anchor, after = value["anchor"], value["after"]
            if value["owner"] != owner or value["mode"] != mode or value["period"] != period:
                raise ValueError("cursor_scope")
            if (
                type(anchor) is not int
                or not 0 < anchor <= now
                or not isinstance(after, list)
                or len(after) != 2
            ):
                raise ValueError("cursor_anchor")
            if (
                type(after[0]) is not int
                or not 0 <= after[0] <= anchor
                or not isinstance(after[1], str)
                or not 0 < len(after[1]) <= 100
            ):
                raise ValueError("cursor_position")
            after = tuple(after)
        except (
            ValueError,
            UnicodeError,
            TypeError,
            KeyError,
            OverflowError,
            base64.binascii.Error,
        ):
            raise BusinessError(400, "VALIDATION_ERROR") from None
    return mode, period, count, anchor, after


def _period_start(period, anchor):
    if period == "all":
        return 0
    day = (
        datetime.fromtimestamp(anchor / 1000, UTC)
        .astimezone(JST)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    days = {"today": 1, "7d": 7, "30d": 30}[period]
    return int((day - timedelta(days=days - 1)).timestamp() * 1000)


def _row_for_attempt(attempt, evaluations, coachings):
    coaching = attempt.coaching_contract_version == 2
    current = coachings.get(attempt.id) if coaching else None
    if coaching and current is None:
        raise IntegrityError("history_missing_coaching")
    evaluation_id = current.current_evaluation_id if current else attempt.evaluation_id
    evaluation = evaluations.get(evaluation_id)
    if (
        evaluation is None
        or evaluation.attempt_id != attempt.id
        or evaluation.owner != attempt.owner
    ):
        raise IntegrityError("history_evaluation_relation")
    if (evaluation.coaching_contract_version == 2) != coaching:
        raise IntegrityError("history_evaluation_version")
    status = evaluation.status
    score = None
    if status == "completed":
        if evaluation.feedback is None:
            raise IntegrityError("history_missing_feedback")
        score = evaluation.feedback.totalScore if coaching else evaluation.feedback.score
    return {
        "id": "attempt:" + attempt.id,
        "kind": "coaching" if coaching else "normal",
        "label": attempt.question.question,
        "category": attempt.question.category,
        "createdAt": attempt.created_at,
        "status": status,
        "score": score,
        "scoreMax": 30 if coaching else 100,
        "attemptId": attempt.id,
        "evaluationId": evaluation_id,
        "generationId": None,
        "assistType": None,
    }


def _row_for_assist(record, question_id=None):
    return {
        "id": "assist:" + record.id,
        "kind": "assist",
        "label": record.question,
        "category": None,
        "createdAt": record.created_at,
        "status": record.status,
        "score": None,
        "scoreMax": None,
        "attemptId": None,
        "evaluationId": None,
        "generationId": record.id,
        "assistType": getattr(record, "assist_type", None) or record.input.assistType,
    }


def build_history(owner, params, now, attempts, evaluations, coachings, summaries, generations):
    mode, period, limit, anchor, after = parse_history_query(owner, params, now)
    evaluation_by_id = {v.id: v for v in evaluations}
    coaching_by_id = {v.id: v for v in coachings}
    rows = []
    if mode in {"all", "normal", "coaching"}:
        rows.extend(_row_for_attempt(v, evaluation_by_id, coaching_by_id) for v in attempts)
    if mode in {"all", "assist"} | ASSIST_MODES:
        # Live generation details win for pending states; the durable summary wins after TTL.
        by_id = {
            v.id: _row_for_assist(v)
            for v in generations
            if v.expires_at is None or v.expires_at * 1000 > now
        }
        for v in summaries:
            if v.id in by_id and by_id[v.id]["status"] in {"QUEUED", "PREPARED", "STARTED"}:
                live_status = by_id[v.id]["status"]
            else:
                live_status = v.status
            row = _row_for_assist(v)
            row["status"] = live_status
            by_id[v.id] = row
        rows.extend(by_id.values())
    if mode != "all":
        rows = [
            r
            for r in rows
            if r["kind"] == mode
            or (r["kind"] == "assist" and (mode == "assist" or r["assistType"] == mode))
        ]
    lower = _period_start(period, anchor)
    rows = [r for r in rows if lower <= r["createdAt"] <= anchor]
    rows.sort(key=lambda r: (r["createdAt"], r["id"]), reverse=True)
    usage = None
    if mode == "all" and period == "all":
        normal = [r["score"] for r in rows if r["kind"] == "normal" and r["status"] == "completed"]
        coaching = [
            r["score"] for r in rows if r["kind"] == "coaching" and r["status"] == "completed"
        ]
        usage = {
            "practiceAttempts": sum(r["kind"] != "assist" for r in rows),
            "evaluatedAttempts": len(normal) + len(coaching),
            "assistGenerations": sum(r["kind"] == "assist" for r in rows),
            "normalAverage": round(sum(normal) / len(normal), 1) if normal else None,
            "coachingAverage": round(sum(coaching) / len(coaching), 1) if coaching else None,
        }
    if after is not None:
        rows = [r for r in rows if (r["createdAt"], r["id"]) < after]
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        position = [page[-1]["createdAt"], page[-1]["id"]]
        packed = {
            "owner": owner,
            "mode": mode,
            "period": period,
            "anchor": anchor,
            "after": position,
        }
        next_cursor = (
            base64.urlsafe_b64encode(json.dumps(packed, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
    return Reply(200, {"items": page, "nextCursor": next_cursor, "usage": usage})
