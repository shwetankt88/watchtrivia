# Building Watchtrivia: a complete tutorial

Throughout this tutorial, we'll walk you through building **Watchtrivia** — an
app that takes your YouTube watch history, figures out your interests, and
generates a quiz on them using an LLM.

By the end you'll have:

- A public-facing feature set: upload watch history, view interests, take a quiz
- An admin site where you (as the app owner) can inspect any user's data
- A REST API connecting a Django backend to a React frontend
- A test suite covering the business logic

We'll assume you have Python 3.10+, Node.js, and pip installed already.

This tutorial mirrors the structure of Django's own "Writing your first
Django app" tutorial — small, verified steps, in order, each building on the
last.

---

## Part 1: Project setup

### Projects vs. apps

A **project** is the overall Django site — settings, top-level URL routing.
An **app** is one self-contained piece of functionality your project uses —
here, everything Watchtrivia does lives in one app called `trivia`.

### Create the project

```bash
mkdir watchtrivia && cd watchtrivia
mkdir backend && cd backend
python3 -m venv venv
source venv/bin/activate      # venv\Scripts\activate on Windows
pip install django djangorestframework django-cors-headers pymongo python-dotenv anthropic scikit-learn
django-admin startproject watchtrivia .
```

The trailing `.` matters — it puts `manage.py` in your current directory
instead of nesting everything one level deeper.

### Create the app

```bash
python manage.py startapp trivia
```

> **Note:** don't name your app `quiz` if you're on a fresh Python — it
> collides with a standard-library module and Django will refuse. `trivia`
> is what we use throughout.

Verify it worked:

```bash
python manage.py runserver
```

Visit `http://localhost:8000/` — you should see Django's "The install
worked successfully!" page.

When you're comfortable with the basic project structure, continue to Part 2
to start defining your data.

---

## Part 2: Models and the admin site

### Designing the data

Watchtrivia needs to track:

- **WatchHistoryEntry** — one row per video from a user's Takeout export
- **InterestTopic** — a computed interest, with a weight, per user
- **Question** — an LLM-generated quiz question, tied to a topic
- **QuizAttempt** — one quiz session, with a running score
- **Answer** — one submitted answer, tied to an attempt and a question

Open `trivia/models.py` and define them:

```python
from django.conf import settings
from django.db import models


class WatchHistoryEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watch_history")
    video_title = models.CharField(max_length=500)
    channel_name = models.CharField(max_length=255, blank=True)
    watched_at = models.DateTimeField(null=True, blank=True)
    raw_category = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.video_title[:50]} ({self.channel_name})"


class InterestTopic(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interests")
    label = models.CharField(max_length=100)
    weight = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-weight"]

    def __str__(self):
        return f"{self.label} ({self.weight:.2f}) - {self.user}"


class Question(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="questions")
    topic = models.ForeignKey(InterestTopic, on_delete=models.CASCADE, related_name="questions")
    prompt_text = models.TextField()
    options = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.prompt_text[:60]


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(default=0)

    def __str__(self):
        return f"Attempt by {self.user} on {self.started_at:%Y-%m-%d}"


class Answer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answer = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.is_correct = self.selected_answer.strip().lower() == self.question.correct_answer.strip().lower()
        super().save(*args, **kwargs)
```

**What's happening here:**
- Each class is a database table; each field is a column.
- `ForeignKey` expresses "many of these belong to one of those" — many
  `WatchHistoryEntry` rows belong to one `User`.
- `on_delete=models.CASCADE` means: delete the parent, delete its children
  too, so you never end up with orphaned rows.
- `JSONField` lets `options` hold a flexible list without needing a
  separate table — a small taste of the schema flexibility MongoDB is
  built around (more on that in Part 9).
- Overriding `save()` on `Answer` means correctness is computed
  automatically every time an answer is saved — the caller never has to
  remember to check it themselves.

### Register the app

Django won't pick up `trivia` until you tell it to, in
`watchtrivia/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'trivia',
]
```

### Create and run migrations

```bash
python manage.py makemigrations trivia
python manage.py migrate
```

`makemigrations` looks at your models and writes a migration file
describing the schema change. `migrate` applies it to the database. This
is version control for your schema — every change is a reviewable,
committable file.

### Register with the admin site

In `trivia/admin.py`:

```python
from django.contrib import admin
from .models import WatchHistoryEntry, InterestTopic, Question, QuizAttempt, Answer


@admin.register(WatchHistoryEntry)
class WatchHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("video_title", "channel_name", "user", "watched_at")
    list_filter = ("user",)
    search_fields = ("video_title", "channel_name")


@admin.register(InterestTopic)
class InterestTopicAdmin(admin.ModelAdmin):
    list_display = ("label", "weight", "user")
    list_filter = ("user",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("prompt_text", "topic", "user", "created_at")
    list_filter = ("topic",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "started_at", "completed_at", "score")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_answer", "is_correct")
```

Create an admin user and check it out:

```bash
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://localhost:8000/admin/` and log in — you now have a full CRUD
UI for every model, entirely for free. This is one of Django's biggest
advantages over a microframework like Flask.

When you're comfortable managing data through the admin, continue to Part 3
to write the logic that actually populates it.

---

## Part 3: Services — parsing, ranking, and the LLM

Django convention encourages keeping business logic *out* of views, in
plain modules. This makes it independently testable and keeps views thin.

Create `trivia/services/` with an `__init__.py` and three files.

### Parsing the Takeout export

`trivia/services/takeout_parser.py`:

```python
import json
from datetime import datetime


def parse_takeout_json(file_obj):
    raw_data = json.load(file_obj)
    entries = []

    for item in raw_data:
        if "titleUrl" not in item or "watch?v=" not in item.get("titleUrl", ""):
            continue

        title = item.get("title", "").replace("Watched ", "", 1)
        channel = ""
        if item.get("subtitles"):
            channel = item["subtitles"][0].get("name", "")

        watched_at = None
        if item.get("time"):
            try:
                watched_at = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            except ValueError:
                pass

        entries.append({
            "video_title": title,
            "channel_name": channel,
            "watched_at": watched_at,
        })

    return entries
```

Notice this file has **zero Django imports**. That's deliberate — you can
test it with plain `pytest`/`unittest` in milliseconds, no database, no
server.

### Ranking interests (v1: channel frequency)

`trivia/services/interest_ranker.py`:

```python
from collections import Counter


def rank_interests(watch_entries, top_n=5):
    channel_counts = Counter(
        entry["channel_name"] for entry in watch_entries if entry.get("channel_name")
    )

    if not channel_counts:
        return []

    total = sum(channel_counts.values())
    top_channels = channel_counts.most_common(top_n)

    return [
        {"label": channel, "weight": round(count / total, 3)}
        for channel, count in top_channels
    ]
```

This is intentionally the simplest version that works — count videos per
channel, normalize to a 0–1 weight. A natural v2 upgrade (once this works
end to end) is TF-IDF + K-Means clustering on video *titles* instead of
just channel names, for finer-grained topics than "whichever channel you
watched most."

### Generating questions with the LLM

`trivia/services/llm_service.py`:

```python
import json
import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You generate multiple-choice trivia questions.
Return ONLY valid JSON, no other text, no markdown code fences.
Format: a JSON list of objects, each with keys:
"prompt_text" (string), "options" (list of 4 strings), "correct_answer" (string, must exactly match one option).
"""


def generate_questions(topic_label, num_questions=3):
    user_prompt = f"Generate {num_questions} trivia questions about: {topic_label}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()

    try:
        questions = json.loads(raw_text)
    except json.JSONDecodeError:
        retry_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_text},
                {"role": "user", "content": "That wasn't valid JSON. Return ONLY the JSON list, nothing else."},
            ],
        )
        raw_text = retry_response.content[0].text.strip()
        questions = json.loads(raw_text)

    return questions
```

The key design decision: **prompt for JSON only**, and retry once with a
sharper reminder if the model wraps its answer in prose or code fences.

You'll need an API key. Create `backend/.env`:

```
ANTHROPIC_API_KEY=your-key-here
```

When you're comfortable with the three services, continue to Part 4 to
expose them over an API.

---

## Part 4: Serializers and views (the API layer)

### Serializers: translating models to and from JSON

`trivia/serializers.py`:

```python
from rest_framework import serializers
from .models import WatchHistoryEntry, InterestTopic, Question, QuizAttempt, Answer


class WatchHistoryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchHistoryEntry
        fields = ["id", "video_title", "channel_name", "watched_at"]


class InterestTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterestTopic
        fields = ["id", "label", "weight"]


class QuestionSerializer(serializers.ModelSerializer):
    topic_label = serializers.CharField(source="topic.label", read_only=True)

    class Meta:
        model = Question
        # correct_answer is deliberately excluded - never send the answer to the frontend!
        fields = ["id", "prompt_text", "options", "topic_label"]


class AnswerSubmitSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_answer = serializers.CharField()


class QuizAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = ["id", "started_at", "completed_at", "score"]
```

Note `AnswerSubmitSerializer` is a plain `Serializer`, not a
`ModelSerializer` — it validates incoming data that doesn't map 1:1 to a
model on input.

### Views: the actual endpoints

`trivia/views.py`:

```python
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .models import WatchHistoryEntry, InterestTopic, Question, QuizAttempt, Answer
from .serializers import (
    WatchHistoryEntrySerializer, InterestTopicSerializer, QuestionSerializer,
    AnswerSubmitSerializer, QuizAttemptSerializer,
)
from .services.takeout_parser import parse_takeout_json
from .services.interest_ranker import rank_interests
from .services.llm_service import generate_questions


class InterestTopicViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InterestTopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # IMPORTANT: only return the logged-in user's own data
        return InterestTopic.objects.filter(user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_watch_history(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

    parsed_entries = parse_takeout_json(uploaded_file)

    WatchHistoryEntry.objects.bulk_create([
        WatchHistoryEntry(user=request.user, **entry) for entry in parsed_entries
    ])

    ranked = rank_interests(parsed_entries, top_n=5)

    InterestTopic.objects.filter(user=request.user).delete()
    topics = InterestTopic.objects.bulk_create([
        InterestTopic(user=request.user, label=item["label"], weight=item["weight"])
        for item in ranked
    ])

    return Response(InterestTopicSerializer(topics, many=True).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_quiz(request):
    topics = InterestTopic.objects.filter(user=request.user)[:3]
    if not topics:
        return Response({"error": "No interests found - upload watch history first"}, status=400)

    attempt = QuizAttempt.objects.create(user=request.user)
    created_questions = []

    for topic in topics:
        try:
            raw_questions = generate_questions(topic.label, num_questions=2)
        except Exception:
            continue  # don't let one bad LLM response kill the whole quiz

        for q in raw_questions:
            question = Question.objects.create(
                user=request.user, topic=topic,
                prompt_text=q["prompt_text"], options=q["options"],
                correct_answer=q["correct_answer"],
            )
            created_questions.append(question)

    return Response({
        "attempt_id": attempt.id,
        "questions": QuestionSerializer(created_questions, many=True).data,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_answer(request, attempt_id):
    serializer = AnswerSubmitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    attempt = QuizAttempt.objects.get(id=attempt_id, user=request.user)
    question = Question.objects.get(id=serializer.validated_data["question_id"])

    answer = Answer.objects.create(
        attempt=attempt, question=question,
        selected_answer=serializer.validated_data["selected_answer"],
    )

    if answer.is_correct:
        attempt.score += 1
        attempt.save()

    return Response({"is_correct": answer.is_correct, "correct_answer": question.correct_answer})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_attempt(request, attempt_id):
    attempt = QuizAttempt.objects.get(id=attempt_id, user=request.user)
    attempt.completed_at = timezone.now()
    attempt.save()
    return Response(QuizAttemptSerializer(attempt).data)
```

**Two view styles used here, on purpose:**
- `ViewSet` auto-generates list/detail endpoints from one class — DRF's
  equivalent of Django's generic views.
- `@api_view` + a plain function is simpler for one-off actions that
  aren't standard CRUD, like "generate a quiz."

`get_queryset` filtering by `request.user` is not optional — skip it and
any logged-in user could read anyone else's data.

When you're comfortable with the views, continue to Part 5 to wire up
URLs.

---

## Part 5: URLconf

### App-level URLs

`trivia/urls.py`:

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("interests", views.InterestTopicViewSet, basename="interest")

urlpatterns = [
    path("", include(router.urls)),
    path("upload-history/", views.upload_watch_history, name="upload-history"),
    path("generate-quiz/", views.generate_quiz, name="generate-quiz"),
    path("attempts/<int:attempt_id>/submit-answer/", views.submit_answer, name="submit-answer"),
    path("attempts/<int:attempt_id>/complete/", views.complete_attempt, name="complete-attempt"),
]
```

### Project-level URLs

`watchtrivia/urls.py`:

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('trivia.urls')),
]
```

Anything under `/api/` is handed off to the `trivia` app's own URLconf —
this is how Django keeps multi-app projects from becoming one giant flat
file.

When you're comfortable with routing, continue to Part 6 to finish the
settings that make cross-origin requests and the API work correctly.

---

## Part 6: Settings — CORS and DRF config

In `watchtrivia/settings.py`, add to `MIDDLEWARE` and configure DRF:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',   # add this, near the top
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# React's Vite dev server runs on 5173 by default
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

**Why CORS matters:** browsers block a page on `localhost:5173` from
calling an API on `localhost:8000` by default — the Same-Origin Policy, a
core browser security feature. `django-cors-headers` explicitly whitelists
your frontend's origin so the browser allows the request through.

When you're comfortable with the settings, continue to Part 7 to write
tests.

---

## Part 7: Testing

Django's test runner builds a temporary database, runs your tests against
it, then destroys it — your real dev database is never touched.

Structure tests as a package so you can split by concern:

```bash
rm trivia/tests.py
mkdir trivia/tests
touch trivia/tests/__init__.py
```

### Testing services directly (no database needed)

`trivia/tests/test_interest_ranker.py`:

```python
from django.test import SimpleTestCase
from trivia.services.interest_ranker import rank_interests


class RankInterestsTests(SimpleTestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(rank_interests([]), [])

    def test_ranks_by_frequency_descending(self):
        entries = [
            {"channel_name": "F1 Channel"},
            {"channel_name": "F1 Channel"},
            {"channel_name": "F1 Channel"},
            {"channel_name": "Finance Channel"},
        ]
        result = rank_interests(entries, top_n=2)
        self.assertEqual(result[0]["label"], "F1 Channel")
        self.assertAlmostEqual(result[0]["weight"], 0.75)
```

Use `SimpleTestCase` (not `TestCase`) when a test touches no database —
it's faster since Django skips the transaction wrapping.

### Testing models and the API (database-backed)

`trivia/tests/test_models_and_api.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from trivia.models import InterestTopic, Question, QuizAttempt, Answer


class AnswerAutoScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="shwetank", password="testpass123")
        self.topic = InterestTopic.objects.create(user=self.user, label="F1", weight=0.8)
        self.question = Question.objects.create(
            user=self.user, topic=self.topic,
            prompt_text="Who won the 2021 F1 championship?",
            options=["Hamilton", "Verstappen", "Bottas", "Perez"],
            correct_answer="Verstappen",
        )
        self.attempt = QuizAttempt.objects.create(user=self.user)

    def test_correct_answer_is_marked_correct(self):
        answer = Answer.objects.create(attempt=self.attempt, question=self.question, selected_answer="Verstappen")
        self.assertTrue(answer.is_correct)


class InterestTopicAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="shwetank", password="testpass123")
        self.other_user = User.objects.create_user(username="other", password="testpass123")
        InterestTopic.objects.create(user=self.user, label="F1", weight=0.8)
        InterestTopic.objects.create(user=self.other_user, label="Finance", weight=0.5)

    def test_user_only_sees_their_own_interests(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/interests/")
        labels = [item["label"] for item in response.data]
        self.assertIn("F1", labels)
        self.assertNotIn("Finance", labels)
```

`TestCase` wraps each test in a transaction and rolls it back afterward —
tests never leak data into each other, and you don't clean up manually.

Run everything:

```bash
python manage.py makemigrations trivia
python manage.py test trivia -v 2
```

When you're comfortable with the test suite, continue to Part 8 to build
the frontend.

---

## Part 8: The React frontend

### Scaffold

```bash
cd ../frontend
npm create vite@latest . -- --template react
npm install axios
```

### API client

`src/api.js`:

```javascript
import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api",
  withCredentials: true,   // sends/receives the Django session cookie
});

export default api;
```

### The main component

`src/App.jsx`:

```jsx
import { useState } from "react";
import api from "./api";
import "./App.css";

function App() {
  const [interests, setInterests] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [attemptId, setAttemptId] = useState(null);
  const [status, setStatus] = useState("idle");

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setStatus("uploading");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await api.post("/upload-history/", formData);
      setInterests(response.data);
      setStatus("ready");
    } catch (err) {
      console.error(err);
      setStatus("idle");
    }
  };

  const handleGenerateQuiz = async () => {
    setStatus("generating");
    try {
      const response = await api.post("/generate-quiz/");
      setAttemptId(response.data.attempt_id);
      setQuestions(response.data.questions);
      setStatus("quiz");
    } catch (err) {
      console.error(err);
      setStatus("ready");
    }
  };

  const handleAnswer = async (questionId, selectedAnswer) => {
    const response = await api.post(`/attempts/${attemptId}/submit-answer/`, {
      question_id: questionId,
      selected_answer: selectedAnswer,
    });
    alert(response.data.is_correct ? "Correct!" : `Wrong - it was ${response.data.correct_answer}`);
  };

  return (
    <div className="app">
      <h1>Watchtrivia</h1>

      {status === "idle" && (
        <div>
          <p>Upload your Google Takeout watch-history.json to get started.</p>
          <input type="file" accept=".json" onChange={handleFileUpload} />
        </div>
      )}

      {status === "uploading" && <p>Processing your watch history...</p>}

      {(status === "ready" || status === "generating") && (
        <div>
          <h2>Your top interests</h2>
          <ul>
            {interests.map((topic) => (
              <li key={topic.id}>{topic.label} - {(topic.weight * 100).toFixed(0)}%</li>
            ))}
          </ul>
          <button onClick={handleGenerateQuiz} disabled={status === "generating"}>
            {status === "generating" ? "Generating quiz..." : "Generate my quiz"}
          </button>
        </div>
      )}

      {status === "quiz" && (
        <div>
          <h2>Your quiz</h2>
          {questions.map((q) => (
            <div key={q.id} className="question-card">
              <p><strong>{q.topic_label}:</strong> {q.prompt_text}</p>
              {q.options.map((option) => (
                <button key={option} onClick={() => handleAnswer(q.id, option)}>{option}</button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default App;
```

**How this works, conceptually:**
- `useState` holds data that changes over time; calling its setter tells
  React "re-render with this new value." You never manually touch the DOM.
- `{status === "ready" && (...)}` is React's conditional rendering — just
  JavaScript, no special template syntax.
- `key={q.id}` isn't optional — React uses `key` to track which list item
  is which across re-renders. Skip it and list updates get buggy.

When you're comfortable with the component, continue to Part 9 to run
everything together and see what's left to build.

---

## Part 9: Running it all, and what's next

### Run both servers

```bash
# terminal 1
cd backend && source venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# terminal 2
cd frontend
npm run dev
```

### Try it end to end

1. Log into `http://localhost:8000/admin/` with your superuser account —
   this sets a session cookie in your browser.
2. Open `http://localhost:5173` in the **same browser** — since both point
   at the same Django backend, the session cookie carries over.
3. Get your watch history from `https://takeout.google.com` (deselect
   everything except YouTube, choose JSON format), upload it, and generate
   your quiz.

### A note on the database

Everything above runs on Django's default SQLite. MongoDB was part of the
original plan — the intended pattern is **polyglot persistence**: keep
`User` accounts and `QuizAttempt` scores in a relational database (what
Django's ORM and admin expect), and move `WatchHistoryEntry` and generated
`Question` data into MongoDB via `pymongo` directly, since that data is
naturally variable-shaped and doesn't need Django's ORM or admin. This
isn't wired up yet — worth tackling once the relational version is solid.

### What's left to build

- Proper signup/login API endpoints for the React app (it currently
  depends on logging into `/admin/` to get a session — fine for
  development, not for a real app)
- Move `generate_quiz` to a Celery background task — right now it runs
  synchronously, which will feel slow once a quiz has several questions
- MongoDB for `WatchHistoryEntry` and `Question`, as above
- Upgrade `rank_interests` from channel-frequency counting to TF-IDF +
  K-Means on video titles, for finer-grained topics
- A results screen showing an interest breakdown after a completed
  `QuizAttempt`

Each of these is a natural "next tutorial" — ask when you're ready to
tackle one.