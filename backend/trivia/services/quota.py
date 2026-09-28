"""Per-user daily quotas, counted in the database.

The platform pays for every question, so the limit has to hold across every
gunicorn worker, not per process. A counter row locked with `select_for_update`
is the smallest thing that is actually correct: read the count, compare, write
the increment, all inside one transaction.

Why not a cache? A cache entry can be evicted, and an eviction would silently
hand a user a free quiz. Why not `F()` expressions alone? They make the update
atomic but cannot express "refuse if the new value would exceed the limit".
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from trivia.models import Profile

logger = logging.getLogger("trivia.quota")


class QuotaExceeded(Exception):
    """Raised when a user has no allowance left for a capped action."""

    def __init__(self, action, limit):
        self.action = action
        self.limit = limit
        super().__init__(
            f"Daily {action} limit of {limit} reached. It resets at midnight UTC."
        )


@dataclass(frozen=True)
class QuotaStatus:
    action: str
    used: int
    limit: int

    @property
    def remaining(self):
        return max(0, self.limit - self.used)

    @property
    def exhausted(self):
        return self.used >= self.limit


def _limit_for(action):
    if action == "quiz":
        return settings.QUIZZES_PER_DAY
    if action == "upload":
        return settings.UPLOADS_PER_DAY
    raise ValueError(f"Unknown quota action: {action}")


def get_profile(user):
    """The user's profile, created on first use.

    `get_or_create` is a single round trip in the common case and does not
    depend on a signal having fired.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


def status_for(user, action):
    profile = get_profile(user)
    if profile.quota_date != timezone.localdate():
        # Do not write just to read a status.
        return QuotaStatus(action=action, used=0, limit=_limit_for(action))
    used = profile.quizzes_today if action == "quiz" else profile.uploads_today
    return QuotaStatus(action=action, used=used, limit=_limit_for(action))


def consume(user, action, count=1):
    """Charge `count` against the user's daily allowance, or raise.

    The row is locked for the duration, so two requests racing at the same
    limit cannot both succeed. Callers that have already done expensive work
    (generating questions) should call this first.
    """
    limit = _limit_for(action)

    with transaction.atomic():
        profile, _ = Profile.objects.select_for_update().get_or_create(user=user)
        profile.rollover_quota()

        used = profile.quizzes_today if action == "quiz" else profile.uploads_today
        if used + count > limit:
            logger.info(
                "quota refused",
                extra={
                    "user": user.get_username(),
                    "action": action,
                    "used": used,
                    "limit": limit,
                },
            )
            raise QuotaExceeded(action, limit)

        if action == "quiz":
            profile.quizzes_today = used + count
            profile.total_quizzes += count
            profile.save(
                update_fields=["quizzes_today", "total_quizzes", "quota_date"]
            )
        else:
            profile.uploads_today = used + count
            profile.save(update_fields=["uploads_today", "quota_date"])

    return QuotaStatus(action=action, used=used + count, limit=limit)


def release(user, action, count=1):
    """Give back an allowance after a failure, so users are not charged for
    our errors. Best effort: if the row is gone, there is nothing to refund."""
    limit = _limit_for(action)
    with transaction.atomic():
        try:
            profile = Profile.objects.select_for_update().get(user=user)
        except Profile.DoesNotExist:
            return None
        if profile.quota_date != timezone.localdate():
            return None
        if action == "quiz":
            profile.quizzes_today = max(0, profile.quizzes_today - count)
            profile.total_quizzes = max(0, profile.total_quizzes - count)
            profile.save(update_fields=["quizzes_today", "total_quizzes"])
        else:
            profile.uploads_today = max(0, profile.uploads_today - count)
            profile.save(update_fields=["uploads_today"])
    return profile
