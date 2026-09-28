import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AnswerForm, WatchHistoryUploadForm
from .models import (
    Answer,
    InterestTopic,
    Question,
    QuizAttempt,
    WatchHistoryEntry,
)
from .services.interest_ranker import rank_interests
from .services.llm_service import LLMError
from .services.question_cache import questions_for_topic
from .services.quota import QuotaExceeded, consume, release, status_for
from .services.takeout_parser import TakeoutParseError, parse_takeout_json

logger = logging.getLogger(__name__)

# How many interest topics to draw questions from.
TOPICS_PER_QUIZ = 3
# How many questions to request per topic.
QUESTIONS_PER_TOPIC = 2


# ---------------------------------------------------------------------------
# Upload & interests
# ---------------------------------------------------------------------------

@login_required
def upload_history(request):
    """Accept a Takeout watch-history.json upload and recompute interests."""
    if request.method == "POST":
        form = WatchHistoryUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Charged after validation but before parsing, so a rejected file
            # costs nothing and a re-upload of the same data cannot be used to
            # churn the database.
            try:
                consume(request.user, "upload")
            except QuotaExceeded as exc:
                form.add_error("file", str(exc))
            else:
                try:
                    entries = parse_takeout_json(form.cleaned_data["file"])
                except TakeoutParseError as exc:
                    # Not a form-level problem (the file exists and is .json), so we
                    # attach it to the field rather than using form.add_error on
                    # "file" -- same result, clearer intent.
                    form.add_error("file", str(exc))
                    release(request.user, "upload")
                else:
                    topics = _process_upload(request.user, entries)
                    messages.success(
                        request,
                        f"Imported {len(entries):,} videos and "
                        f"found {len(topics)} interests.",
                    )
                    return redirect("trivia:interests")
    else:
        form = WatchHistoryUploadForm()

    return render(
        request,
        "trivia/upload.html",
        {"form": form, "upload_quota": status_for(request.user, "upload")},
    )


def _process_upload(user, entries):
    """Persist parsed entries, replace the user's interests, return the new topics.

    This is a pure data function: it takes no `request` and touches no session
    or message framework, so the API layer in Part 10 can call it too.

    Wrapped in a transaction: a half-applied upload — new watch rows but stale
    interests — is worse than no upload at all, because the user has no way to
    tell it happened.
    """
    with transaction.atomic():
        # A re-upload replaces history rather than accumulating duplicates,
        # otherwise interests get computed over stale entries forever.
        WatchHistoryEntry.objects.filter(user=user).delete()

        WatchHistoryEntry.objects.bulk_create(
            [
                WatchHistoryEntry(user=user, **entry)
                for entry in entries
            ],
            batch_size=500,
        )

        ranked = rank_interests(entries, top_n=5)

        InterestTopic.objects.filter(user=user).delete()
        topics = InterestTopic.objects.bulk_create(
            [
                InterestTopic(user=user, label=item["label"], weight=item["weight"])
                for item in ranked
            ]
        )

    return topics


@login_required
def interests(request):
    """Show the user's computed interest topics."""
    topics = InterestTopic.objects.filter(user=request.user)
    return render(
        request,
        "trivia/interests.html",
        {"topics": topics},
    )


# ---------------------------------------------------------------------------
# Quiz lifecycle
# ---------------------------------------------------------------------------

@login_required
@require_POST
def generate_quiz(request):
    """Create a QuizAttempt with LLM-generated questions from top interests."""
    topics = list(InterestTopic.objects.filter(user=request.user)[:TOPICS_PER_QUIZ])
    if not topics:
        messages.error(
            request,
            "You have no interests yet. Upload your watch history first.",
        )
        return redirect("trivia:upload")

    # Charged before the LLM is called, never after: a limit checked once the
    # questions already exist is a limit that costs money before it works. The
    # allowance is refunded below if nothing usable came back.
    try:
        consume(request.user, "quiz")
    except QuotaExceeded as exc:
        messages.error(request, str(exc))
        return redirect("trivia:interests")

    attempt = QuizAttempt.objects.create(user=request.user)
    questions, failures = _build_questions(attempt, topics)

    if not questions:
        # Every topic failed. Leaving an empty attempt in the database would
        # show the user a quiz with no questions and no explanation.
        attempt.delete()
        release(request.user, "quiz")
        messages.error(
            request,
            "Could not generate any questions. "
            + (
                failures[0]
                if failures
                else "Please try again in a moment."
            ),
        )
        return redirect("trivia:interests")

    if failures:
        # Partial success is still a usable quiz, but say so rather than
        # pretending everything worked.
        messages.warning(
            request,
            f"Generated {len(questions)} questions, but {len(failures)} topic(s) "
            "could not be reached. Try again for a full quiz.",
        )

    return redirect("trivia:quiz", attempt_id=attempt.id)


def _build_questions(attempt, topics):
    """Get questions for every topic. Returns (questions, failure_messages).

    Questions come from `question_cache.questions_for_topic`, which serves a
    stored batch when the same topic has been quizzed before and only calls
    Claude on a miss. On a public site that is the difference between one paid
    generation per topic per month and one per user per click.

    One failing topic must not kill the whole quiz, but a silent failure is
    worse than a visible one -- so every failure is recorded and surfaced to
    the user rather than swallowed by a bare `except Exception: continue`.
    """
    questions = []
    failures = []

    for topic in topics:
        try:
            generated, source = questions_for_topic(
                topic.label, num_questions=QUESTIONS_PER_TOPIC
            )
        except LLMError as exc:
            logger.warning("LLM generation failed for topic %r: %s", topic.label, exc)
            failures.append(str(exc))
            continue
        except Exception:
            # Genuinely unexpected -- log the traceback so it is debuggable,
            # but do not let one topic take down the request.
            logger.exception("Unexpected error generating questions for %r", topic.label)
            failures.append(
                f"An unexpected error occurred while generating questions "
                f"for '{topic.label}'."
            )
            continue

        logger.info(
            "questions ready",
            extra={"topic": topic.label, "count": len(generated), "source": source},
        )

        for item in generated:
            questions.append(
                Question(
                    user=attempt.user,
                    attempt=attempt,
                    topic=topic,
                    prompt_text=item["prompt_text"],
                    options=item["options"],
                    correct_answer=item["correct_answer"],
                )
            )

    if questions:
        Question.objects.bulk_create(questions)
        attempt.question_count = len(questions)
        attempt.save(update_fields=["question_count"])

    return questions, failures


@login_required
def quiz(request, attempt_id):
    """Render the questions for one attempt, with whatever is already answered."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("user"),
        pk=attempt_id,
        user=request.user,          # <-- ownership check
    )
    questions = list(attempt.questions.select_related("topic"))
    answers = {a.question_id: a for a in attempt.answers.all()}

    # Build the pairing the template needs here rather than making the
    # template do dict lookups. See the note in Part 8.
    rows = [{"question": q, "answer": answers.get(q.id)} for q in questions]

    return render(
        request,
        "trivia/quiz.html",
        {"attempt": attempt, "rows": rows, "answered_count": len(answers)},
    )


@login_required
@require_POST
def submit_answer(request, attempt_id, question_id):
    """Record one answer and return the rendered feedback fragment.

    Responds to HTMX with an HTML partial; falls back to a redirect for
    non-JS requests, so the whole quiz works with JavaScript disabled.
    """
    # Both lookups are ownership-scoped. The question must belong to THIS
    # attempt, not merely to this user -- otherwise a user can pair their own
    # attempt with a question id from a different attempt and score it.
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)
    question = get_object_or_404(
        Question,
        pk=question_id,
        attempt=attempt,
        user=request.user,
    )

    existing = Answer.objects.filter(attempt=attempt, question=question).first()
    if existing:
        # The unique constraint would reject this anyway; catching it here
        # lets the user see what they already chose instead of a 500.
        return _render_answer_feedback(
            request, attempt, question, existing, already_answered=True
        )

    form = AnswerForm(request.POST, question=question)
    if not form.is_valid():
        return _render_answer_feedback(
            request, attempt, question, None, form=form
        )

    with transaction.atomic():
        answer = Answer.objects.create(
            attempt=attempt,
            question=question,
            selected_answer=form.cleaned_data["selected_answer"],
        )
        if answer.is_correct:
            # Re-aggregate from the answers rather than incrementing a
            # counter, so the score is always correct even if a previous
            # write was lost or an answer was edited in the admin.
            attempt.score = attempt.answers.filter(is_correct=True).count()
            attempt.save(update_fields=["score"])

    return _render_answer_feedback(request, attempt, question, answer)


def _render_answer_feedback(request, attempt, question, answer, form=None,
                            already_answered=False):
    """Render the small fragment HTMX swaps in after an answer.

    The non-HTMX branch is what makes "works without JavaScript" true. Without
    it, a JS-disabled browser navigates to this view and is shown a bare HTML
    fragment with no <html>, no navbar, and no way back -- technically a
    response, practically a dead end.
    """
    if not request.headers.get("HX-Request"):
        if form is not None and not form.is_valid():
            # Nothing was recorded, so send them back to fix the input rather
            # than silently dropping a bad submission.
            messages.error(request, "Please choose one of the options.")
        elif already_answered:
            messages.info(request, "You already answered that question.")
        return redirect("trivia:quiz", attempt_id=attempt.id)

    context = {
        "attempt": attempt,
        "question": question,
        "answer": answer,
        "correct_answer": question.correct_answer,
        "form": form,
        "already_answered": already_answered,
        "total_questions": attempt.questions.count(),
        "answered_count": attempt.answers.count(),
    }
    return render(request, "trivia/partials/answer_feedback.html", context)


@login_required
@require_POST
def complete_attempt(request, attempt_id):
    """Mark an attempt finished and show the score."""
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)

    if attempt.completed_at is None:
        attempt.completed_at = timezone.now()
        attempt.score = attempt.answers.filter(is_correct=True).count()
        attempt.save(update_fields=["completed_at", "score"])

    return redirect("trivia:results", attempt_id=attempt.id)


@login_required
def results(request, attempt_id):
    """Show a finished attempt's score and the questions the user missed."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("user"),
        pk=attempt_id,
        user=request.user,
    )
    answers = (
        attempt.answers.select_related("question", "question__topic")
        .order_by("question_id")
    )
    correct = answers.filter(is_correct=True).count()
    return render(
        request,
        "trivia/results.html",
        {
            "attempt": attempt,
            "answers": answers,
            # The score is out of every question in the attempt, not just the
            # ones answered. Using answers.count() here would report 2/3 for a
            # user who got 2 of 6 right and abandoned the rest.
            "total": attempt.questions.count(),
            "correct": correct,
            # Kept separately so the template can say "you left 3 unanswered"
            # instead of silently treating them as wrong.
            "answered": answers.count(),
            "unanswered": attempt.questions.count() - answers.count(),
        },
    )
