import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def normalize_answer(value):
    """Normalize an answer string for tolerant comparison.

    Collapses internal whitespace and lowercases, so that "  Red  Bull " and
    "red bull" compare equal. Users retype answers; the LLM may pad them.
    """
    return " ".join(str(value).split()).casefold()


class Profile(models.Model):
    """Per-user settings and counters that are not authentication.

    Created on demand rather than by a post_save signal: a signup that fails
    halfway must not leave a half-built user behind, and `get_or_create` at
    the point of use keeps that logic in one place.
    """

    class Theme(models.TextChoices):
        SYSTEM = "system", "Match system"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    theme = models.CharField(
        max_length=8,
        choices=Theme.choices,
        default=Theme.SYSTEM,
    )
    # Daily quota counters. Reset by comparing `quota_date` to today, so no
    # cron job is needed and a user cannot lose their allowance by a deploy.
    quota_date = models.DateField(default=timezone.localdate)
    quizzes_today = models.PositiveIntegerField(default=0)
    uploads_today = models.PositiveIntegerField(default=0)
    total_quizzes = models.PositiveIntegerField(default=0)
    total_questions_answered = models.PositiveIntegerField(default=0)
    # Rolling streak in days, recomputed on each completed attempt.
    streak_days = models.PositiveIntegerField(default=0)
    last_quiz_date = models.DateField(null=True, blank=True)
    marketing_ok = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile for {self.user}"

    def rollover_quota(self):
        """Zero today's counters if the stored date is in the past.

        Returns True when a reset happened, so callers can log it.
        """
        today = timezone.localdate()
        if self.quota_date != today:
            self.quota_date = today
            self.quizzes_today = 0
            self.uploads_today = 0
            self.save(update_fields=["quota_date", "quizzes_today", "uploads_today"])
            return True
        return False

    def quizzes_remaining(self):
        return max(0, settings.QUIZZES_PER_DAY - self.quizzes_today)

    def uploads_remaining(self):
        return max(0, settings.UPLOADS_PER_DAY - self.uploads_today)


class WatchHistoryEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watch_history",
    )
    video_title = models.CharField(max_length=500)
    channel_name = models.CharField(max_length=255, blank=True)
    watched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-watched_at", "-id"]
        indexes = [models.Index(fields=["user", "-watched_at"])]

    def __str__(self):
        return f"{self.video_title[:50]} ({self.channel_name})"


class InterestTopic(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interests",
    )
    label = models.CharField(max_length=100)
    weight = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-weight"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "label"],
                name="unique_interest_label_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.weight:.2f}) - {self.user}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(default=0)
    # Unguessable token for the opt-in public results page. Null means private,
    # which is the default and the only state a user starts in.
    public_slug = models.CharField(
        max_length=32, null=True, blank=True, unique=True, editable=False
    )
    # How many questions were served, so a half-finished attempt still shows an
    # honest denominator on the results page.
    question_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "-started_at"])]

    def __str__(self):
        return f"Attempt by {self.user} on {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def is_complete(self):
        return self.completed_at is not None

    @property
    def total_questions(self):
        """Questions served: the stored count, or a count if the row predates it."""
        return self.question_count or self.questions.count()

    def save(self, *args, **kwargs):
        # Generate the slug on first save only. Re-saving an unshared attempt
        # must not silently publish it, and re-sharing must not invalidate a
        # link somebody has already posted.
        if self.public_slug is None and self._state.adding:
            self.public_slug = secrets.token_urlsafe(24)[:32]
        super().save(*args, **kwargs)

    def enable_sharing(self):
        """Make the results page public. Idempotent."""
        if self.public_slug is None:
            self.public_slug = secrets.token_urlsafe(24)[:32]
            self.save(update_fields=["public_slug"])
        return self.public_slug

    def disable_sharing(self):
        """Make the results page private again. Existing links stop working."""
        if self.public_slug is not None:
            self.public_slug = None
            self.save(update_fields=["public_slug"])


class Question(models.Model):
    """A trivia question belonging to one specific quiz attempt."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True,
    )
    topic = models.ForeignKey(
        InterestTopic,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    prompt_text = models.TextField()
    options = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.prompt_text[:60]

    def grades_correctly(self, value):
        """Whether `value` would be accepted as the correct answer for this question."""
        return normalize_answer(value) == normalize_answer(self.correct_answer)


class QuestionCache(models.Model):
    """Previously generated questions for a topic, reusable by any user.

    The platform pays per generated question, and the interesting topics are a
    small fixed set: a user who takes three quizzes about Formula 1 should not
    cause three generations. A cache row holds a validated batch of question
    dicts; new attempts copy from it into real `Question` rows, so an answer
    key can never be shared or mutated across users.

    `fingerprint` includes the model and question count, so changing either
    produces a new key instead of serving questions in the old shape.
    """

    MAX_BATCH = 10
    MIN_FRESH_QUESTIONS = 1

    topic_label = models.CharField(max_length=100, db_index=True)
    fingerprint = models.CharField(max_length=64, db_index=True)
    questions = models.JSONField()
    times_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_used_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["topic_label", "fingerprint"],
                name="unique_cache_entry_per_topic_fingerprint",
            )
        ]

    def __str__(self):
        return f"Cached questions for {self.topic_label!r} (used {self.times_used}x)"

    @staticmethod
    def fingerprint_for(topic_label, num_questions):
        payload = f"{topic_label.strip().casefold()}|{num_questions}|{settings.ANTHROPIC_MODEL}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def is_usable(self):
        """Whether this batch can be handed out again.

        Expired after `QUESTION_CACHE_TTL_DAYS` (a month by default) so a topic
        that has moved on does not serve trivia that is quietly out of date.
        """
        if self.last_used_at is None:
            return False
        ttl_days = settings.QUESTION_CACHE_TTL_DAYS
        if ttl_days <= 0:
            return False
        age = timezone.now() - self.last_used_at
        return age < timezone.timedelta(days=ttl_days)

    def fresh_questions(self, num_questions):
        """Up to `num_questions` question dicts not yet handed out.

        Cycling: when every cached question has been used once, the batch
        starts again rather than falling through to a paid generation. A
        user who retakes a quiz then gets a fresh shuffle of the same pool.
        """
        if not self.is_usable():
            return []
        used = self.questions
        if len(used) < num_questions:
            # Not enough in the pool at all; the caller will generate.
            return []

        if self.times_used >= len(used):
            self.times_used = 0
        batch = used[self.times_used : self.times_used + num_questions]
        if len(batch) < num_questions:
            batch = batch + used[: num_questions - len(batch)]
        self.times_used += len(batch)
        self.last_used_at = timezone.now()
        self.save(update_fields=["times_used", "last_used_at"])
        return batch


class Answer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    selected_answer = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_answer_per_question_per_attempt",
            ),
        ]

    def __str__(self):
        mark = "correct" if self.is_correct else "wrong"
        return f"{self.question_id}: {self.selected_answer} ({mark})"

    def save(self, *args, **kwargs):
        self.is_correct = (
            normalize_answer(self.selected_answer)
            == normalize_answer(self.question.correct_answer)
        )
        super().save(*args, **kwargs)
