# Part 4: Forms and Views

---

## Where Does Validation Live?

The original plan used Django REST Framework serializers for input validation. With a
server-rendered frontend, **Django forms** do that job natively — and they bring CSRF
handling, error rendering, and field-level validation for free.

| Concern | DRF serializer (original) | Django form (this plan) |
|---------|--------------------------|-------------------------|
| Validate input | `serializer.is_valid(raise_exception=True)` | `form.is_valid()` |
| Render errors | Hand-write JSON error responses | `{{ form.errors }}` in a template |
| CSRF protection | Manual — read cookie, set header | `{% csrf_token %}` |
| File uploads | `request.FILES` | `forms.FileField` |
| Output format | JSON | Rendered HTML |

Forms also work identically if you later add the JSON API in Part 10, which is one
reason they are the right choice for a project that might grow a second frontend.

---

## The Forms

`trivia/forms.py`:

```python
from django import forms

# Google Takeout watch-history exports are large but finite. 25 MB comfortably
# holds a decade of heavy watching and is small enough to parse in one go.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class WatchHistoryUploadForm(forms.Form):
    """Validates a Google Takeout watch-history.json upload.

    A plain Form, not a ModelForm: we are not creating a single model
    instance here, we are validating a file and then bulk-creating hundreds
    of rows from it.
    """

    file = forms.FileField(
        label="watch-history.json",
        help_text=(
            "Export your data from Google Takeout, then unzip it and upload "
            "the watch-history.json file from the YouTube folder."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]

        if uploaded.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f"That file is {uploaded.size / 1024 / 1024:.1f} MB. "
                f"The limit is {MAX_UPLOAD_BYTES / 1024 / 1024:.0f} MB."
            )

        name = (uploaded.name or "").lower()
        if not name.endswith(".json"):
            raise forms.ValidationError(
                "That does not look like a .json file. Takeout archives are "
                "zipped — unzip it first, then upload the .json inside."
            )

        return uploaded


class AnswerForm(forms.Form):
    """Validates one submitted answer against a specific question's options.

    Not a ModelForm either: the choice set is dynamic, because it comes from
    the question's JSONField rather than from a fixed list in the model.
    """

    def __init__(self, *args, question, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        self.fields["selected_answer"] = forms.ChoiceField(
            choices=[(opt, opt) for opt in question.options],
            widget=forms.RadioSelect,
            label="Your answer",
        )

    def clean_selected_answer(self):
        return self.cleaned_data["selected_answer"]
```

### Why `forms.Form` and Not `forms.ModelForm`

`ModelForm` is for creating or updating **one** model instance from form fields, and it
infers its fields and validation from the model. Neither form here does that:

- The upload form validates a *file* and then triggers a `bulk_create` of many
  `WatchHistoryEntry` rows. There is no single model to map onto.
- The answer form's choices are **dynamic** — they come from `question.options`, a
  `JSONField`, which `ModelForm` cannot introspect.

Reaching for `ModelForm` out of habit and then fighting it is a common source of
unnecessary code.

### Why Validate the Extension AND the Size

Both checks exist because of specific real failures:

- **Size.** `json.load()` reads the entire file into memory, then builds a list of dicts
  in memory, then `bulk_create` builds a list of model instances. A multi-gigabyte
  upload can exhaust the server's RAM. Django's own
  `DATA_UPLOAD_MAX_MEMORY_SIZE` (2.5 MB default) does not apply to file uploads, so
  nothing upstream stops this.
- **Extension.** Users upload `Takeout-123456789.zip` directly, or
  `subscriptions.json`, or `my-account.json`. Catching it here produces "unzip it
  first" instead of a confusing parse error from deep inside the parser.

> [!NOTE]
> The extension check is a **usability** check, not a security control. It is trivially
> bypassed by renaming a file, and that is fine — `parse_takeout_json` validates the
> actual content. Never rely on a filename to decide whether input is safe.

---

## The Views

`trivia/views.py`:

```python
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
from .services.llm_service import LLMError, generate_questions
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
            try:
                entries = parse_takeout_json(form.cleaned_data["file"])
            except TakeoutParseError as exc:
                # Not a form-level problem (the file exists and is .json), so we
                # attach it to the field rather than using form.add_error on
                # "file" -- same result, clearer intent.
                form.add_error("file", str(exc))
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

    return render(request, "trivia/upload.html", {"form": form})


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

    attempt = QuizAttempt.objects.create(user=request.user)
    questions, failures = _build_questions(attempt, topics)

    if not questions:
        # Every topic failed. Leaving an empty attempt in the database would
        # show the user a quiz with no questions and no explanation.
        attempt.delete()
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
    """Call the LLM once per topic. Returns (questions, failure_messages).

    One failing topic must not kill the whole quiz, but a silent failure is
    worse than a visible one -- so every failure is recorded and surfaced to
    the user rather than swallowed by a bare `except Exception: continue`.
    """
    questions = []
    failures = []

    for topic in topics:
        try:
            generated = generate_questions(
                topic.label,
                num_questions=QUESTIONS_PER_TOPIC,
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
```

---

## Every Security Fix, Explained

The original plan's views had four defects. Each is visible in the code above, marked
where it occurs.

### 1. Cross-User Question Access — the Serious One

```python
# ORIGINAL — no ownership check on the question at all
question = Question.objects.get(id=serializer.validated_data["question_id"])
```

Any authenticated user could POST any `question_id` and receive
`{"is_correct": ..., "correct_answer": "..."}` — **the full answer key for every
question in the database**, by incrementing an integer. The original plan had a whole
section warning that viewsets must scope queries to `request.user`, then shipped this.

The fix is two constraints, not one:

```python
question = get_object_or_404(
    Question,
    pk=question_id,
    attempt=attempt,      # belongs to THIS attempt
    user=request.user,    # and belongs to THIS user
)
```

`attempt=attempt` matters as much as `user=request.user`. Without it, a user could pair
their own attempt with a question id from an old attempt, or from a topic they have since
deleted interest in, and the quiz would score it.

> [!IMPORTANT]
> The feedback fragment reveals `correct_answer` **after** the user has answered. That is
> correct and intended — you always find out the answer once you have committed. The
> original plan's design was sound here; the bug was that "after answering" was not
> actually enforced.

### 2. `.get()` Raising `DoesNotExist` — 500 Instead of 404

```python
# ORIGINAL
attempt = QuizAttempt.objects.get(id=attempt_id, user=request.user)
# → DoesNotExist exception → unhandled → HTTP 500 with a stack trace
```

```python
# THIS PLAN
attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)
# → HTTP 404 "Not Found"
```

`get_object_or_404` is `get()` plus an exception handler. It is the single most-used
function in idiomatic Django, and its absence is one of the clearest signals that code
was written without thinking about the failure path.

### 3. Unlimited Score Inflation

```python
# ORIGINAL — no guard
answer = Answer.objects.create(...)
if answer.is_correct:
    attempt.score += 1
    attempt.save()
```

Nothing stopped repeated POSTs of the same `question_id` to the same `attempt_id`, each
incrementing the score. On a six-question quiz a user could reach any score they liked.

The fix is threefold:

| Layer | Mechanism |
|-------|-----------|
| Database | `UniqueConstraint` on `Answer(attempt, question)` from Part 2 |
| View | `Answer.objects.filter(...).first()` early-return showing the prior answer |
| Model | `save()` override recomputes `is_correct`, so the value cannot be forged |

The view's early-return also improves UX: instead of a 500 from the constraint, the user
sees the answer they already gave.

### 4. `except Exception: continue` Swallowing Every Failure

```python
# ORIGINAL
for topic in topics:
    try:
        raw_questions = generate_questions(topic.label, num_questions=2)
    except Exception:
        continue          # ← a missing API key, a rate limit, and a bug are
                         #    all indistinguishable from each other here
```

If `ANTHROPIC_API_KEY` was unset, the user got `201 Created` with an empty question list
and no error message. The page rendered "Your quiz" with nothing on it. The most likely
cause of a completely broken app produced zero diagnostics.

This version:

- Catches `LLMError` specifically and **records the message** for display.
- Catches bare `Exception` separately and **logs the traceback** with
  `logger.exception(...)`, so genuine bugs are debuggable, while still not killing the
  request.
- Distinguishes **partial** failure (some questions generated → show them, warn the user)
  from **total** failure (delete the empty attempt, show the reason).
- Never leaves an empty `QuizAttempt` in the database.

> [!TIP]
> The rule this encodes: **an empty result is a failure.** If your code produces nothing,
> something went wrong, and the user should be told what. A silent `continue` converts a
> diagnosable bug into an unexplainable UI.

### Two Further Improvements

**Score is re-aggregated, not incremented.**

```python
attempt.score = attempt.answers.filter(is_correct=True).count()
```

The original did `attempt.score += 1`. Incrementing assumes every prior write succeeded.
Re-counting is idempotent: running it twice, or recovering from a partially failed
request, gives the same answer. It is one extra cheap query on a table with a handful of
rows.

**Uploads delete previous history.**

```python
WatchHistoryEntry.objects.filter(user=user).delete()
```

The original appended. Upload a second, corrected Takeout file and you would compute
interests over the union of both, permanently. Since `InterestTopic` is replaced on every
upload, keeping stale `WatchHistoryEntry` rows means the interests shown no longer
correspond to the data that produced them. Deleting first makes the operation idempotent:
uploading the same file twice gives the same result.

> [!NOTE]
> If you want to support *merging* multiple Takeout exports instead, delete this line —
> but then dedupe on `(user, video_title, watched_at)`, or the same video watched on three
> devices will be counted three times and inflate its channel's weight.

---

## Transactions — Why `transaction.atomic()`

```python
with transaction.atomic():
    WatchHistoryEntry.objects.filter(user=user).delete()
    WatchHistoryEntry.objects.bulk_create(...)
    InterestTopic.objects.filter(user=user).delete()
    topics = InterestTopic.objects.bulk_create(...)
```

Without it, an exception halfway through — a database full, a lock timeout, a network
blip — leaves the user with new watch rows but stale interests, or worse, with their
interests deleted and nothing to replace them. Neither state is recoverable by the user,
and neither is visible: the page would just show stale or empty data.

`atomic()` means all of it happens or none of it does.

**Caveat:** the LLM call in `generate_quiz` happens *outside* any transaction, on
purpose. Holding a database transaction open across a 30-second network call locks rows
for 30 seconds and will exhaust your connection pool under any real traffic. The pattern
is: do slow external work first, then take a short transaction for the database writes.

The correct production fix is a background task queue. That is a genuine enhancement for
a real deployment, and it is explicitly **not** in this plan — see the honest scope note
in Part 9.

---

## `bulk_create` and `batch_size`

```python
WatchHistoryEntry.objects.bulk_create(
    [WatchHistoryEntry(user=user, **entry) for entry in entries],
    batch_size=500,
)
```

Instead of one `INSERT` per entry — 50,000 queries for a large Takeout export —
`bulk_create` batches them. `batch_size=500` bounds each statement's parameter count,
which matters because SQLite has a limit on bound parameters per statement (999 by
default on older builds) and very long single statements can exceed
`max_query_length` on PostgreSQL.

> [!WARNING]
> `bulk_create` does **not** call `save()` on each object. Our `Answer.save()` override
> that computes `is_correct` would be silently skipped. This is why `Answer` is created
> one at a time in `submit_answer` (a handful of rows, and the override is required),
> while `WatchHistoryEntry` — which has no `save()` override — uses `bulk_create`.
>
> In Django 4.1+ you can pass `objs` to `bulk_create` to have it call `save()` on each
> object, but that defeats the performance benefit.

---

## View Types Used

| Decorator / helper | Purpose |
|--------------------|---------|
| `@login_required` | Redirect anonymous users to the login page |
| `get_object_or_404` | Fetch one object, or return HTTP 404 |
| `render(request, template, context)` | Render an HTML template |
| `redirect("namespace:name", arg=...)` | HTTP 302 to a named URL |
| `messages.success/error/warning` | Queue a one-request flash message |
| `@require_POST` | Return 405 for anything but POST |

### `@login_required` Versus DRF's `IsAuthenticated`

Both send anonymous users away. The difference is where they go and what they get:

| | `@login_required` | `IsAuthenticated` |
|---|---|---|
| Anonymous → | Redirect (302) to `LOGIN_URL` | 403 or 401 JSON |
| Browser sees | The login page | A JSON error body |
| Designed for | Server-rendered HTML | API clients |

For HTMX, a 302 to the login page works: HTMX follows redirects and swaps the returned
login HTML in. If you want a nicer experience, return `401` from an `htmx:trigger` event
in Part 8.

> [!TIP]
> Add `@require_POST` above `@login_required` on any view that only handles POST. The
> decorator order matters: `@require_POST` must be **above** `@login_required`, so an
> anonymous GET is rejected for the right reason.

---

## HTTP Status Codes

| Code | Constant | Meaning | Used When |
|------|----------|---------|-----------|
| 200 | `HTTP_200_OK` | Success | Default for GET, and for our HTMX fragments |
| 302 | `HTTP_302_FOUND` | Redirect | After upload, after redirect-to-quiz |
| 400 | `HTTP_400_BAD_REQUEST` | Client error | Invalid input, failed form validation |
| 403 | `HTTP_403_FORBIDDEN` | Not allowed | Authenticated but no permission |
| 404 | `HTTP_404_NOT_FOUND` | Not found | Wrong id, **or someone else's id** |
| 405 | `HTTP_405_METHOD_NOT_ALLOWED` | Wrong method | GET on a POST-only view |
| 500 | `HTTP_500_INTERNAL_SERVER_ERROR` | Server error | Unhandled exception — a bug |

> [!NOTE]
> `get_object_or_404` returning 404 for *someone else's* object rather than 403 is
> deliberate. A 403 would confirm the object exists, which leaks information. 404 is
> indistinguishable from "no such object", which is what you want.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`forms.Form`** | Validates non-model input; renders errors for templates |
| **`forms.FileField`** | File upload with size/type validation |
| **`clean_<field>()`** | Per-field validation, runs after the built-in checks |
| **`@login_required`** | Redirect anonymous users to the login page |
| **`get_object_or_404`** | Fetch one row or return 404 — never 500 |
| **`transaction.atomic()`** | All the writes happen, or none do |
| **`bulk_create`** | Batched insert; skips `save()` overrides |
| **`messages`** | Flash messages that survive one redirect |
| **Ownership scoping** | Every query filtered by `user=request.user` |
| **Idempotency** | Re-running an operation gives the same result |

---

**→ Continue to [Part 5: URL Configuration](./05_urls.md)**
