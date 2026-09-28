"""Reusing generated questions so the same topic is not paid for twice.

Generation is the only thing in this app that costs money, and the topic set is
small and repetitive: a user with ten interests will quiz the same three over
and over. Caching turns the tenth quiz on "F1 Official" into a database read.

The cache stores plain dicts, not `Question` rows. A new attempt still gets its
own copy of every question, so an answer key is never shared between users and
grading one user can never affect another.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from trivia.models import QuestionCache
from trivia.services.llm_service import LLMError, generate_questions

logger = logging.getLogger("trivia.cache")


def _validate_shape(batch, num_questions):
    """A cache hit is only useful if it is the right shape.

    Cached data outlives the code that made it: if a model change alters the
    prompt or the validator, an old batch is not merely stale, it may be
    unusable. Checking here means a bad cache row costs one paid generation,
    not a broken quiz.
    """
    if not isinstance(batch, list) or len(batch) < num_questions:
        return False
    for item in batch:
        if not isinstance(item, dict):
            return False
        if not str(item.get("prompt_text", "")).strip():
            return False
        options = item.get("options")
        if not isinstance(options, list) or len(options) < 2:
            return False
        if str(item.get("correct_answer", "")).strip() not in options:
            return False
    return True


def take_cached_questions(topic_label, num_questions):
    """Reusable question dicts for a topic, or `[]` on a miss."""
    if settings.QUESTION_CACHE_TTL_DAYS <= 0:
        return []

    fingerprint = QuestionCache.fingerprint_for(topic_label, num_questions)
    try:
        entry = QuestionCache.objects.get(
            topic_label=topic_label.strip()[:100], fingerprint=fingerprint
        )
    except QuestionCache.DoesNotExist:
        return []

    batch = entry.fresh_questions(num_questions)
    if batch and _validate_shape(batch, num_questions):
        logger.info(
            "cache hit",
            extra={"topic": topic_label, "questions": len(batch),
                   "used": entry.times_used},
        )
        return batch

    if entry.times_used:
        # The row exists but is expired or malformed. Delete it so the next
        # request starts clean rather than re-checking a bad batch forever.
        entry.delete()
    return []


def store_questions(topic_label, batch):
    """Save a freshly generated batch for reuse. Never raises.

    A cache write failing must not fail the request that generated perfectly
    good questions, so every database error here is logged and swallowed.
    """
    if not batch or settings.QUESTION_CACHE_TTL_DAYS <= 0:
        return None

    label = topic_label.strip()[:100]
    fingerprint = QuestionCache.fingerprint_for(label, len(batch))
    payload = batch[: QuestionCache.MAX_BATCH]

    try:
        with transaction.atomic():
            entry, created = QuestionCache.objects.get_or_create(
                topic_label=label,
                fingerprint=fingerprint,
                defaults={"questions": payload},
            )
            if not created:
                # Keep whichever batch is longer, and restart the cycle.
                if len(entry.questions or []) < len(payload):
                    entry.questions = payload
                entry.times_used = 0
                entry.last_used_at = None
                entry.save(update_fields=["questions", "times_used", "last_used_at"])
        logger.info("cache stored", extra={"topic": label, "questions": len(payload)})
        return entry
    except IntegrityError:
        # Two requests raced to fill the same row. The other one won, which is
        # exactly the outcome we wanted.
        return None
    except Exception:  # pragma: no cover - defensive
        logger.warning("cache store failed", extra={"topic": label}, exc_info=True)
        return None


def questions_for_topic(topic_label, num_questions, use_cache=True):
    """Cached questions when possible, generated ones otherwise.

    Returns `(questions, source)` where source is "cache" or "llm", so callers
    can log and tests can assert which path ran.
    """
    if use_cache:
        cached = take_cached_questions(topic_label, num_questions)
        if cached:
            return cached, "cache"

    generated = generate_questions(topic_label, num_questions=num_questions)
    store_questions(topic_label, generated)
    return generated, "llm"


__all__ = ["questions_for_topic", "take_cached_questions", "store_questions", "LLMError"]
