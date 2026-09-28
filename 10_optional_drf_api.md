# Part 10: Optional JSON API with DRF

---

## Read This First

**You do not need this part to finish Watchtrivia.** Parts 1–9 are a complete,
working application. This part exists for two reasons:

1. **The original plan promised a JSON API and never finished it.** Its Part 3 said
   "we'll build this in Part 10" and its Part 6 said "we'll add this in Part 11".
   Neither file existed. This part gives those promises a real home.
2. **You may genuinely want one** — for a mobile app, a public API, or a third-party
   client.

If you are following this tutorial to ship Watchtrivia, skip to the
[Key Concepts](#key-concepts-recap) at the end and stop.

---

## Why the Core App Does Not Need This

The server-rendered app in Parts 1–9 has no JSON API because nothing consumes JSON. The
frontend is the same process, so the browser gets finished HTML.

Adding a JSON API means adding:

| Cost | Detail |
|------|--------|
| A dependency | `djangorestframework` |
| A second set of views | DRF viewsets that duplicate the Django views |
| A second validation layer | Serializers mirroring the forms |
| A second URL namespace | `/api/…` alongside `/…` |
| CORS, **if** a separate origin consumes it | The only place CORS reappears |
| Auth complexity | Tokens, storage, refresh, or cookie sessions across origins |
| Tests | Every endpoint needs a second test suite |

None of that buys the HTMX app anything. So this part is genuinely optional, and the
code below is written to **coexist** with the existing views rather than replace them.

---

## Installation

```bash
pip install djangorestframework
pip freeze > requirements.txt
```

Add to `INSTALLED_APPS` in `settings.py`:

```python
INSTALLED_APPS = [
    # ... existing entries ...
    "rest_framework",
    "trivia",
]
```

Add to the bottom of `settings.py`:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
```

> [!NOTE]
> **`BrowsableAPIRenderer` in production is a mistake.** It renders an interactive HTML
> form for any endpoint, and it has had authentication-bypass issues in the past. The
> block above is fine for development; in production, drop it:
>
> ```python
> "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
> ```

> [!IMPORTANT]
> **There is no CORS configuration here, and that is correct.** CORS is only needed when
> a *browser* on a different origin calls this API. A mobile app, a server-to-server
> client, and a browser app served from the same origin all bypass CORS entirely — they
> are not browsers enforcing a same-origin policy.
>
> If you later call this API from JavaScript running on a *different* domain, *then* you
> add `django-cors-headers` and a specific allowlist. Do not add it "just in case."

---

## Authentication

### Option A — Session Auth (Simplest, Same as the Core App)

The configuration above already does this. DRF reads Django's session cookie, so a
logged-in browser is authenticated with no extra work.

This is the right choice if the API is consumed by the same Django-hosted frontend or by
a client on the same site.

### Option B — Token Auth (For Mobile and Third-Party Clients)

```bash
pip install djangorestframework-simplejwt
```

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
```

Add to `watchtrivia/urls.py`:

```python
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("", include("trivia.urls")),
    path("", include("trivia.api_urls")),   # namespace="api"
]
```

The flow:

```
1. POST /api/auth/token/  {username, password}
2. → {access: "eyJ...", refresh: "eyJ..."}
3. Client sends:  Authorization: Bearer eyJ...
4. Server validates the signature — no database lookup
5. On expiry: POST /api/auth/token/refresh/ with the refresh token
```

> [!WARNING]
> **Store the access token in memory, not `localStorage`.** Anything in
> `localStorage` is readable by any JavaScript running on your page, so one XSS
> vulnerability exfiltrates a long-lived credential. `localStorage` also survives
> browser close, so a stolen token stays valid until it expires. Memory storage means a
> page refresh logs the user out — annoying, and the correct trade.
>
> A refresh token in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie is the more
> common production pattern.

### Option C — DRF's Built-In Token Auth

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    # ... the other settings from the Session configuration above ...
}
```

Tokens never expire and are not scoped. Simple, and a poor fit for anything public. Use
JWT or sessions instead.

---

## Serializers

`trivia/serializers.py`:

```python
from rest_framework import serializers

from .models import Answer, InterestTopic, Question, QuizAttempt, WatchHistoryEntry


class WatchHistoryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchHistoryEntry
        fields = ["id", "video_title", "channel_name", "watched_at"]
        read_only_fields = fields


class InterestTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterestTopic
        fields = ["id", "label", "weight"]
        read_only_fields = fields


class QuestionSerializer(serializers.ModelSerializer):
    topic_label = serializers.CharField(source="topic.label", read_only=True)

    class Meta:
        model = Question
        # correct_answer is deliberately EXCLUDED — see below.
        fields = ["id", "prompt_text", "options", "topic_label"]
        read_only_fields = fields


class AnswerResultSerializer(serializers.Serializer):
    """Response shape for a submitted answer."""

    is_correct = serializers.BooleanField()
    correct_answer = serializers.CharField()


class AnswerSubmitSerializer(serializers.Serializer):
    """Request shape for submitting an answer."""

    question_id = serializers.IntegerField()
    selected_answer = serializers.CharField()


class QuizAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = ["id", "started_at", "completed_at", "score"]
        read_only_fields = fields
```

### `correct_answer` Must Stay Hidden

```python
fields = ["id", "prompt_text", "options", "topic_label"]
#                        ^ no correct_answer
```

> [!CAUTION]
> Anyone can open browser DevTools and read every API response. If `correct_answer` is in
> `fields`, the entire answer key is in the first response. It is revealed only by
> `submit_answer`, **after** the user has committed — and only for a question they
> actually own (see the view below).

### `read_only_fields` on Everything

Every model here is user-owned, and the user should never set `id`, `user`, or `weight`
via the API. Interests are *computed* by the ranking service, not chosen by the client.
Marking the fields read-only makes that structural rather than a convention.

### `source` for Traversing Relations

```python
topic_label = serializers.CharField(source="topic.label", read_only=True)
```

Produces `topic_label` by walking `question.topic.label`. Without it the response
contains `topic: 3` — an integer the client would have to resolve.

---

## API Views

`trivia/api_views.py`:

```python
import logging

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .forms import MAX_UPLOAD_BYTES
from .models import Answer, InterestTopic, Question, QuizAttempt
from .serializers import (
    AnswerResultSerializer,
    AnswerSubmitSerializer,
    InterestTopicSerializer,
    QuestionSerializer,
    QuizAttemptSerializer,
)
from .services.takeout_parser import TakeoutParseError, parse_takeout_json
from .views import TOPICS_PER_QUIZ, _build_questions, _process_upload

logger = logging.getLogger(__name__)


class InterestTopicViewSet(viewsets.ReadOnlyModelViewSet):
    """
    list:     GET /api/interests/     → the caller's interests
    retrieve: GET /api/interests/1/   → one interest
    """

    serializer_class = InterestTopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InterestTopic.objects.filter(user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_watch_history(request):
    """
    POST /api/upload-history/
    Body: multipart/form-data with a 'file' field
    Returns: 201 with the computed interests
    """
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return Response(
            {"detail": "No file uploaded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        return Response(
            {"detail": f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_entries = parse_takeout_json(uploaded_file)
    except TakeoutParseError as exc:
        # A user-supplied file is bad input, not a server fault.
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # The entire persistence + ranking step, reused from the HTML view.
    topics = _process_upload(request.user, parsed_entries)

    return Response(
        InterestTopicSerializer(topics, many=True).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_quiz(request):
    """
    POST /api/generate-quiz/
    Returns: 201 {attempt_id, questions} | 400 no interests | 502 LLM failure
    """
    topics = list(
        InterestTopic.objects.filter(user=request.user)[:TOPICS_PER_QUIZ]
    )
    if not topics:
        return Response(
            {"detail": "No interests found — upload watch history first."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    attempt = QuizAttempt.objects.create(user=request.user)
    questions, failures = _build_questions(attempt, topics)

    if not questions:
        attempt.delete()
        return Response(
            {"detail": failures[0] if failures else "Could not generate questions."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "attempt_id": attempt.id,
            "questions": QuestionSerializer(questions, many=True).data,
            "warnings": failures,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def attempt_detail(request, attempt_id):
    """
    GET  /api/attempts/<id>/   → the attempt and its questions
    POST /api/attempts/<id>/   → body: {question_id, selected_answer}
    """
    attempt = get_object_or_404(
        QuizAttempt, pk=attempt_id, user=request.user
    )

    if request.method == "GET":
        return Response(
            {
                "attempt": QuizAttemptSerializer(attempt).data,
                "questions": QuestionSerializer(
                    attempt.questions.select_related("topic"), many=True
                ).data,
            }
        )

    serializer = AnswerSubmitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Scope the question to THIS attempt as well as this user. Without
    # `attempt=attempt`, any authenticated user can pair their own attempt
    # with any question id in the database and read back the answer key.
    question = get_object_or_404(
        Question,
        pk=serializer.validated_data["question_id"],
        attempt=attempt,
        user=request.user,
    )

    existing = Answer.objects.filter(attempt=attempt, question=question).first()
    if existing:
        return Response(
            AnswerResultSerializer(
                {"is_correct": existing.is_correct,
                 "correct_answer": question.correct_answer}
            ).data
        )

    if serializer.validated_data["selected_answer"] not in question.options:
        return Response(
            {"detail": "selected_answer is not one of the options."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    answer = Answer.objects.create(
        attempt=attempt,
        question=question,
        selected_answer=serializer.validated_data["selected_answer"],
    )
    if answer.is_correct:
        attempt.score = attempt.answers.filter(is_correct=True).count()
        attempt.save(update_fields=["score"])

    return Response(
        AnswerResultSerializer(
            {"is_correct": answer.is_correct,
             "correct_answer": question.correct_answer}
        ).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_attempt(request, attempt_id):
    """POST /api/attempts/<id>/complete/ → the finalised attempt."""
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)

    if attempt.completed_at is None:
        attempt.completed_at = timezone.now()
        attempt.score = attempt.answers.filter(is_correct=True).count()
        attempt.save(update_fields=["completed_at", "score"])

    return Response(QuizAttemptSerializer(attempt).data)
```

### Reusing the Service and View Logic

Note the imports:

```python
from .views import TOPICS_PER_QUIZ, _build_questions, _process_upload
```

The API layer reuses the constants, the upload pipeline, and the question-building
helper from the HTML views rather than duplicating them. `_build_questions` already
handles partial failure, logs tracebacks, and validates LLM output; `_process_upload`
already wraps its writes in a transaction. None of that needed rewriting.

> [!TIP]
> This is the payoff of the service layer from Part 3. Logic that lives in a service is
> reusable by any frontend; logic buried in a Django view is not. The original plan
> could not have added a JSON API without either duplicating the LLM loop or refactoring
> first.
>
> Note that `_process_upload(user, entries)` deliberately takes no `request` and sets no
> messages — the HTML view supplies those, and the API view does not need them. A helper
> that reaches for `request` cannot be reused from a DRF view, because a DRF request is
> not a Django `HttpRequest`.

### The Bugs That Are Fixed Here

| Original plan's API | This version |
|---------------------|--------------|
| `Question.objects.get(id=...)` — no owner check | `get_object_or_404(Question, pk=..., attempt=attempt, user=request.user)` |
| `.get()` → 500 on a bad id | `get_object_or_404` → 404 |
| No duplicate-answer guard | `Answer.objects.filter(...).first()` early return |
| `except Exception: continue` | `_build_questions` records and reports failures |
| `status=400` bare int | `status.HTTP_400_BAD_REQUEST` |
| Malformed JSON → 500 | `TakeoutParseError` → 400 |
| No file size cap | 400 above `MAX_UPLOAD_BYTES` |
| `selected_answer` unvalidated against options | Explicit membership check |
| Total LLM failure returned 201 + empty list | 502 with the reason |

---

## API URLs

`trivia/api_urls.py`:

```python
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views

app_name = "api"

router = DefaultRouter()
router.register("interests", api_views.InterestTopicViewSet, basename="interest")

urlpatterns = [
    path("", include(router.urls)),
    path("upload-history/", api_views.upload_watch_history, name="upload-history"),
    path("generate-quiz/", api_views.generate_quiz, name="generate-quiz"),
    path("attempts/<int:attempt_id>/", api_views.attempt_detail, name="attempt-detail"),
    path(
        "attempts/<int:attempt_id>/complete/",
        api_views.complete_attempt,
        name="complete-attempt",
    ),
]
```

`DefaultRouter` generates `interest-list` and `interest-detail` from the viewset, so
those two endpoints need no manual URL.

### The Complete API Map

| Method | URL | Purpose |
|--------|-----|---------|
| GET | `/api/interests/` | The caller's interests |
| GET | `/api/interests/<id>/` | One interest |
| POST | `/api/upload-history/` | Upload Takeout file → 201 with interests |
| POST | `/api/generate-quiz/` | Build an attempt → 201 with questions |
| GET | `/api/attempts/<id>/` | Attempt + its questions |
| POST | `/api/attempts/<id>/` | Submit an answer → `{is_correct, correct_answer}` |
| POST | `/api/attempts/<id>/complete/` | Finalise the attempt |

### `get_queryset()` Is Not Optional

```python
def get_queryset(self):
    return InterestTopic.objects.filter(user=self.request.user)
```

> [!CAUTION]
> Returning `InterestTopic.objects.all()` lets user A read user B's interests. The
> original plan warned about this in prose and then broke it in `submit_answer`. Every
> user-owned endpoint here scopes to `request.user` at the queryset level, so a missed
> filter is a 404 rather than a data breach.

---

## DRF vs Django Forms

If you built the core app, you now have two validation layers. They are not redundant —
they serve different clients.

| | Django form (Parts 4–9) | DRF serializer (this part) |
|---|---|---|
| Client | A browser posting HTML | An API client posting JSON |
| Errors | Rendered in a template | Returned as a JSON structure |
| CSRF | `{% csrf_token %}` | Token header, or exempt with JWT |
| Field types | `FileField`, `ChoiceField` | `IntegerField`, `CharField` |
| Reused by | Server-rendered templates | Any HTTP client |

> [!IMPORTANT]
> A common mistake is trying to make one serve both. Keep the form for the HTML flow and
> the serializer for the API. They are thin wrappers over the same services, so the
> business logic is still written once.

---

## Testing the API

The same rules from Part 7, with DRF's client and the isolation tests that matter:

```python
# trivia/tests/test_api.py
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from trivia.models import Answer, InterestTopic, Question, QuizAttempt


class ApiIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="alice", password="pw12345678")
        self.other = User.objects.create_user(username="mallory", password="pw12345678")

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(reverse("api:interest-list"))
        self.assertIn(response.status_code, (401, 403))

    def test_user_only_sees_their_own_interests(self):
        InterestTopic.objects.create(user=self.user, label="Mine")
        InterestTopic.objects.create(user=self.other, label="Theirs")
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("api:interest-list"))
        labels = [item["label"] for item in response.data]
        self.assertIn("Mine", labels)
        self.assertNotIn("Theirs", labels)

    def test_another_users_attempt_is_404(self):
        attempt = QuizAttempt.objects.create(user=self.other)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse("api:attempt-detail", args=[attempt.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_score_another_users_question(self):
        """The answer-key leak the original plan shipped."""
        topic = InterestTopic.objects.create(user=self.other, label="Theirs")
        their_attempt = QuizAttempt.objects.create(user=self.other)
        their_question = Question.objects.create(
            user=self.other,
            attempt=their_attempt,
            topic=topic,
            prompt_text="Q?",
            options=["A", "B", "C", "D"],
            correct_answer="SecretAnswer",
        )
        my_attempt = QuizAttempt.objects.create(user=self.user)

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            reverse("api:attempt-detail", args=[my_attempt.id]),
            {"question_id": their_question.id, "selected_answer": "A"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("SecretAnswer", str(response.data))

    def test_question_serializer_never_exposes_the_answer(self):
        topic = InterestTopic.objects.create(user=self.user, label="F1")
        Question.objects.create(
            user=self.user, topic=topic, prompt_text="Q?",
            options=["A", "B", "C", "D"], correct_answer="SecretAnswer",
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("api:interest-list"))
        self.assertNotIn("SecretAnswer", str(response.data))
```

```bash
python manage.py test trivia
```

### `force_authenticate`

```python
self.client.force_authenticate(user=self.user)
```

Bypasses the login flow and the CSRF check for the duration of the test. Essential for
API tests — testing the login endpoint on every test would be noise, and testing it at
all belongs in its own test.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **DRF** | Adds serializers, viewsets, and a browsable API to Django |
| **Serializer** | Validates and converts between models and JSON |
| **`ModelSerializer`** | Generates fields from a model automatically |
| **`read_only_fields`** | Fields the client cannot set |
| **ViewSet** | Auto-generates CRUD endpoints |
| **`DefaultRouter`** | Generates URLs from registered viewsets |
| **`get_queryset()`** | Scopes every row to the current user |
| **`get_object_or_404`** | DRF's equivalent — 404, never 500 |
| **Session vs JWT auth** | Cookie-backed, or a bearer token with no server state |
| **CORS** | Only needed when a *browser* on another origin calls the API |
| **`force_authenticate`** | Bypass login in tests |

---

## The Complete Tutorial

| Part | Topic |
|------|-------|
| [1](./01_introduction_and_setup.md) | Introduction and setup |
| [2](./02_models_and_admin.md) | Models and the admin site |
| [3](./03_services.md) | Services — parsing, ranking, the LLM |
| [4](./04_forms_and_views.md) | Forms and views |
| [5](./05_urls.md) | URL configuration |
| [6](./06_templates_and_auth.md) | Settings, templates, authentication |
| [7](./07_testing.md) | Testing |
| [8](./08_htmx_frontend.md) | The frontend — templates + HTMX |
| [9](./09_running_and_next_steps.md) | Running it all and what is next |
| [10](./10_optional_drf_api.md) | Optional JSON API with DRF |

Three Python packages. One process. One port. No build step. No CORS. Every request
scoped to the requesting user. 76 tests. And a documented list of what is deliberately
not built.
