"""Everything the dashboard shows, computed in one pass over the user's rows.

The numbers here are small (a person generates tens of attempts, not
millions), so the service favours readable SQL over clever aggregation: one
query for the totals, one for the daily series, one for the per-topic
breakdown. Each returns plain dicts, which keeps the template free of
aggregation logic and makes every figure testable without rendering a page.
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from trivia.models import Answer, InterestTopic, QuizAttempt


def _percentage(part, whole):
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 1)


def headline_stats(user):
    """The four numbers at the top of the dashboard.

    `answered` counts answer rows, not attempts: a half-finished quiz still
    has answers, and counting them keeps the accuracy figure honest.
    """
    attempt_totals = QuizAttempt.objects.filter(user=user).aggregate(
        attempts=Count("id"),
        completed=Count("id", filter=Q(completed_at__isnull=False)),
        total_score=Sum("score"),
    )

    answer_totals = Answer.objects.filter(attempt__user=user).aggregate(
        answered=Count("id"),
        correct=Count("id", filter=Q(is_correct=True)),
    )

    answered = answer_totals["answered"] or 0
    correct = answer_totals["correct"] or 0

    best = (
        QuizAttempt.objects.filter(user=user, completed_at__isnull=False)
        .order_by("-score", "completed_at")
        .first()
    )

    return {
        "attempts": attempt_totals["attempts"] or 0,
        "completed": attempt_totals["completed"] or 0,
        "total_score": attempt_totals["total_score"] or 0,
        "answered": answered,
        "correct": correct,
        "accuracy": _percentage(correct, answered),
        "best_score": best.score if best else 0,
        "distinct_attempts_answered": (
            Answer.objects.filter(attempt__user=user)
            .values("attempt_id")
            .distinct()
            .count()
        ),
    }


def daily_series(user, days=30):
    """Completed-attempt score and accuracy for the last `days` days.

    Returns one entry per day including days with no activity, because a chart
    with gaps in it lies about the gaps. Values are filled with `None` rather
    than 0 so a day with no quiz is not drawn as a zero-score day.
    """
    days = max(1, min(int(days), 365))
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = (
        Answer.objects.filter(attempt__user=user, answered_at__date__gte=start)
        .annotate(day=TruncDate("answered_at"))
        .values("day")
        .annotate(
            answered=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
        .order_by("day")
    )
    by_day = {
        row["day"]: row for row in rows if row["day"] is not None
    }

    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = by_day.get(day)
        if row:
            series.append(
                {
                    "day": day,
                    "answered": row["answered"],
                    "correct": row["correct"],
                    "accuracy": _percentage(row["correct"], row["answered"]),
                }
            )
        else:
            series.append(
                {
                    "day": day,
                    "answered": 0,
                    "correct": 0,
                    "accuracy": None,
                }
            )
    return series


def topic_breakdown(user, limit=5):
    """Per-interest accuracy, best first.

    Joins questions to their topic so the label is the one the user saw on the
    interests page. Attempts with no questions yet are skipped rather than
    reported as 0% accuracy.
    """
    rows = (
        Answer.objects.filter(attempt__user=user, question__topic__isnull=False)
        .values("question__topic__label")
        .annotate(
            answered=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
        .order_by("-correct", "-answered")
    )

    breakdown = [
        {
            "label": row["question__topic__label"],
            "answered": row["answered"],
            "correct": row["correct"],
            "accuracy": _percentage(row["correct"], row["answered"]),
        }
        for row in rows
    ]
    return breakdown[:limit]


def current_streak(user):
    """Consecutive days ending today (or yesterday) with at least one answer.

    Yesterday still counts: a user who played at 11pm and has not opened the
    site today yet has not broken their streak, and breaking it at midnight
    would punish people for having a life.
    """
    days = set(
        Answer.objects.filter(attempt__user=user)
        .annotate(day=TruncDate("answered_at"))
        .values_list("day", flat=True)
        .distinct()
    )
    if not days:
        return 0

    today = timezone.localdate()
    if today not in days:
        if today - timedelta(days=1) not in days:
            return 0
        cursor = today - timedelta(days=1)
    else:
        cursor = today

    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def personal_bests(user):
    """Best single attempt and the most accurate topic, for the dashboard cards."""
    best_attempt = (
        QuizAttempt.objects.filter(user=user, completed_at__isnull=False)
        .order_by("-score", "completed_at")
        .first()
    )
    fastest = (
        Answer.objects.filter(attempt__user=user)
        .values("attempt_id")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    topics = topic_breakdown(user, limit=1)
    return {
        "best_attempt": best_attempt,
        "best_topic": topics[0] if topics else None,
        "most_answered_attempt_id": fastest["attempt_id"] if fastest else None,
    }


def recent_attempts(user, limit=5):
    return list(
        QuizAttempt.objects.filter(user=user).prefetch_related("answers")[:limit]
    )


def full_dashboard(user, days=30):
    """Everything the dashboard template needs, in one call."""
    headline = headline_stats(user)
    return {
        "headline": headline,
        "series": daily_series(user, days=days),
        "topics": topic_breakdown(user),
        "streak": current_streak(user),
        "bests": personal_bests(user),
        "recent": recent_attempts(user),
        "has_interests": InterestTopic.objects.filter(user=user).exists(),
        "watch_history_count": user.watch_history.count(),
    }


__all__ = [
    "current_streak",
    "daily_series",
    "full_dashboard",
    "headline_stats",
    "personal_bests",
    "recent_attempts",
    "topic_breakdown",
]
