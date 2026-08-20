# Part 4: Serializers and Views — The API Layer

---

## What is Django REST Framework (DRF)?

Django by itself serves **HTML pages**. But Watchtrivia's frontend is a separate React app that communicates via **JSON**. Django REST Framework adds everything you need to build a JSON API:

| DRF Component | Purpose | Django Equivalent |
|--------------|---------|-------------------|
| **Serializer** | Converts models ↔ JSON | Django Forms |
| **APIView / ViewSet** | Handles API requests | Django Views |
| **Router** | Auto-generates URL patterns | `urlpatterns` |
| **Permissions** | Controls who can access what | `@login_required` |
| **Authentication** | Identifies who's making the request | Django's auth middleware |

### The Request/Response Cycle with DRF

```
1. React sends:  POST /api/upload-history/  { file: ... }
                        ↓
2. Django's URL router matches "/api/upload-history/" to a view
                        ↓
3. DRF's permission classes check: is the user authenticated?
                        ↓
4. The view function receives a DRF Request object (enhanced HttpRequest)
                        ↓
5. A Serializer validates and transforms the input data
                        ↓
6. The view calls services and/or models to do the work
                        ↓
7. A Serializer transforms the output (model → dict → JSON)
                        ↓
8. DRF returns a Response object with JSON content
                        ↓
9. React receives:  201 Created  [{"id": 1, "label": "F1", "weight": 0.75}, ...]
```

---

## Serializers — Translating Between Python and JSON

### What is Serialization?

**Serialization** = converting a complex Python object (like a Django model instance) into a simple format (like a JSON-compatible dict).

**Deserialization** = the reverse — taking incoming JSON data and converting it into a validated Python object.

```
Serialization (output):
    Model Instance  →  Python Dict  →  JSON String
    InterestTopic(label="F1", weight=0.8)  →  {"label": "F1", "weight": 0.8}  →  '{"label":"F1","weight":0.8}'

Deserialization (input):
    JSON String  →  Python Dict  →  Validated Data  →  Model Instance
    '{"label":"F1"}'  →  {"label": "F1"}  →  validated  →  InterestTopic(label="F1")
```

### Writing the Serializers

Create `trivia/serializers.py`:

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
        # correct_answer is deliberately EXCLUDED
        fields = ["id", "prompt_text", "options", "topic_label"]


class AnswerSubmitSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_answer = serializers.CharField()


class QuizAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = ["id", "started_at", "completed_at", "score"]
```

### Deep Dive: `ModelSerializer` vs `Serializer`

#### `ModelSerializer` — Automatic from a Model

```python
class InterestTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterestTopic          # Which model to serialize
        fields = ["id", "label", "weight"]  # Which fields to include
```

`ModelSerializer` automatically:
- Creates serializer fields matching the model fields
- Implements `create()` and `update()` methods
- Adds validation based on model field constraints

It's equivalent to writing this manually:

```python
# This is what ModelSerializer generates for you:
class InterestTopicSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(max_length=100)
    weight = serializers.FloatField()
    
    def create(self, validated_data):
        return InterestTopic.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        instance.label = validated_data.get('label', instance.label)
        instance.weight = validated_data.get('weight', instance.weight)
        instance.save()
        return instance
```

#### `Serializer` (plain) — Manual, for Non-Model Data

```python
class AnswerSubmitSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_answer = serializers.CharField()
```

Use a plain `Serializer` when the incoming data doesn't map directly to a single model. Here, the frontend sends `{question_id: 5, selected_answer: "Verstappen"}` — that's not a direct `Answer` model creation (we also need the `attempt` FK).

### Security: Excluding `correct_answer`

```python
class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ["id", "prompt_text", "options", "topic_label"]
        # NOTE: correct_answer is NOT in this list!
```

> [!CAUTION]
> **Never send the correct answer to the frontend before the user answers!**
> If `correct_answer` were in the serializer, anyone could open browser DevTools,
> inspect the network response, and see all the answers. Excluding it from `fields`
> means it never leaves the server.

### Computed Fields: `source` Attribute

```python
class QuestionSerializer(serializers.ModelSerializer):
    topic_label = serializers.CharField(source="topic.label", read_only=True)
```

This creates a field called `topic_label` whose value comes from traversing the relationship: `question.topic.label`. Without this, the API would return `topic: 3` (just the FK ID) — not useful for the frontend.

| Parameter | Meaning |
|-----------|---------|
| `source="topic.label"` | Dot-notation path through relationships |
| `read_only=True` | This field appears in output but is ignored in input |

### Common Serializer Field Options

| Option | Purpose | Example |
|--------|---------|---------|
| `read_only=True` | Output only (not writable) | `id`, computed fields |
| `write_only=True` | Input only (not in output) | `password` |
| `required=False` | Not required in input | Optional fields |
| `allow_blank=True` | Empty strings are valid | Text fields |
| `source="..."` | Map to a different model attribute | Nested lookups |
| `default=...` | Default value if not provided | Fallback values |

---

## Views — The Actual API Endpoints

Views are where HTTP requests meet your business logic. DRF provides two styles:

### Style 1: `@api_view` — Function-Based Views

For **one-off actions** that don't fit the standard CRUD pattern.

### Style 2: `ViewSet` — Class-Based Views

For **standard CRUD operations** (list, retrieve, create, update, delete) on a model.

### The Complete Views File

`trivia/views.py`:

```python
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .models import WatchHistoryEntry, InterestTopic, Question, QuizAttempt, Answer
from .serializers import (
    WatchHistoryEntrySerializer,
    InterestTopicSerializer,
    QuestionSerializer,
    AnswerSubmitSerializer,
    QuizAttemptSerializer,
)
from .services.takeout_parser import parse_takeout_json
from .services.interest_ranker import rank_interests
from .services.llm_service import generate_questions


class InterestTopicViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing interest topics.
    
    list:    GET  /api/interests/     → all interests for the logged-in user
    retrieve: GET  /api/interests/1/   → a single interest by ID
    """
    serializer_class = InterestTopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InterestTopic.objects.filter(user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_watch_history(request):
    """
    Upload a Google Takeout watch-history.json file.
    
    Endpoint: POST /api/upload-history/
    Body: multipart/form-data with a 'file' field
    Returns: 201 with the computed interest topics
    """
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return Response(
            {"error": "No file uploaded"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 1. Parse the Takeout JSON
    parsed_entries = parse_takeout_json(uploaded_file)

    # 2. Save all entries to the database
    WatchHistoryEntry.objects.bulk_create([
        WatchHistoryEntry(user=request.user, **entry)
        for entry in parsed_entries
    ])

    # 3. Rank interests from the parsed data
    ranked = rank_interests(parsed_entries, top_n=5)

    # 4. Replace old interests with new ones
    InterestTopic.objects.filter(user=request.user).delete()
    topics = InterestTopic.objects.bulk_create([
        InterestTopic(
            user=request.user,
            label=item["label"],
            weight=item["weight"]
        )
        for item in ranked
    ])

    return Response(
        InterestTopicSerializer(topics, many=True).data,
        status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_quiz(request):
    """
    Generate a quiz from the user's top interests.
    
    Endpoint: POST /api/generate-quiz/
    Returns: 201 with attempt_id and list of questions
    """
    topics = InterestTopic.objects.filter(user=request.user)[:3]
    if not topics:
        return Response(
            {"error": "No interests found - upload watch history first"},
            status=400
        )

    attempt = QuizAttempt.objects.create(user=request.user)
    created_questions = []

    for topic in topics:
        try:
            raw_questions = generate_questions(topic.label, num_questions=2)
        except Exception:
            continue  # don't let one bad LLM response kill the whole quiz

        for q in raw_questions:
            question = Question.objects.create(
                user=request.user,
                topic=topic,
                prompt_text=q["prompt_text"],
                options=q["options"],
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
    """
    Submit an answer to a question.
    
    Endpoint: POST /api/attempts/<attempt_id>/submit-answer/
    Body: {"question_id": 1, "selected_answer": "Verstappen"}
    Returns: {"is_correct": true, "correct_answer": "Verstappen"}
    """
    serializer = AnswerSubmitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    attempt = QuizAttempt.objects.get(id=attempt_id, user=request.user)
    question = Question.objects.get(
        id=serializer.validated_data["question_id"]
    )

    answer = Answer.objects.create(
        attempt=attempt,
        question=question,
        selected_answer=serializer.validated_data["selected_answer"],
    )

    if answer.is_correct:
        attempt.score += 1
        attempt.save()

    return Response({
        "is_correct": answer.is_correct,
        "correct_answer": question.correct_answer
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_attempt(request, attempt_id):
    """
    Mark a quiz attempt as completed.
    
    Endpoint: POST /api/attempts/<attempt_id>/complete/
    Returns: The completed attempt with final score
    """
    attempt = QuizAttempt.objects.get(id=attempt_id, user=request.user)
    attempt.completed_at = timezone.now()
    attempt.save()
    return Response(QuizAttemptSerializer(attempt).data)
```

---

### Deep Dive: ViewSet vs @api_view

#### `ReadOnlyModelViewSet`

```python
class InterestTopicViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InterestTopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InterestTopic.objects.filter(user=self.request.user)
```

`ReadOnlyModelViewSet` automatically provides two endpoints:

| Action | HTTP Method | URL | What it does |
|--------|------------|-----|-------------|
| `list` | `GET` | `/api/interests/` | Returns all interests for the user |
| `retrieve` | `GET` | `/api/interests/1/` | Returns interest with id=1 |

Other ViewSet types:

| ViewSet Type | Provides |
|-------------|----------|
| `ReadOnlyModelViewSet` | `list` + `retrieve` |
| `ModelViewSet` | `list` + `retrieve` + `create` + `update` + `destroy` |
| `GenericViewSet` | Base class, you add mixins manually |

#### Why `get_queryset()` Filtering is Not Optional

```python
def get_queryset(self):
    return InterestTopic.objects.filter(user=self.request.user)
```

> [!CAUTION]
> **Without this filter, any logged-in user could see any other user's data.**
> If you wrote `return InterestTopic.objects.all()`, user A could see user B's interests.
> **Always scope queries to `request.user`** for user-owned data.

#### `@api_view` — Function-Based Views

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_watch_history(request):
    ...
```

- `@api_view(["POST"])` — only accept POST requests; return 405 for GET, PUT, etc.
- `@permission_classes([IsAuthenticated])` — return 403 if no user is logged in
- `request` is a DRF `Request` (enhanced Django `HttpRequest` with `.data`, `.FILES`, etc.)

Use `@api_view` for actions that don't fit CRUD: uploading a file, generating a quiz, submitting an answer.

### Understanding `request.FILES`

```python
uploaded_file = request.FILES.get("file")
```

When a form is submitted with `enctype="multipart/form-data"`, file data goes into `request.FILES` (not `request.data`). Each file is an `UploadedFile` object with:

| Attribute | Description |
|-----------|-------------|
| `.name` | Original filename |
| `.size` | Size in bytes |
| `.content_type` | MIME type |
| `.read()` | Read file contents |

### Understanding `bulk_create`

```python
WatchHistoryEntry.objects.bulk_create([
    WatchHistoryEntry(user=request.user, **entry)
    for entry in parsed_entries
])
```

Instead of:
```python
# SLOW: 1000 entries = 1000 separate INSERT queries
for entry in parsed_entries:
    WatchHistoryEntry.objects.create(user=request.user, **entry)
```

`bulk_create` sends a single SQL `INSERT` with all rows — dramatically faster for large datasets. A watch history might have thousands of entries.

### Understanding the `**` Unpacking Operator

```python
WatchHistoryEntry(user=request.user, **entry)
# entry = {"video_title": "F1 Race", "channel_name": "F1", "watched_at": ...}
# Equivalent to:
WatchHistoryEntry(
    user=request.user,
    video_title="F1 Race",
    channel_name="F1",
    watched_at=...
)
```

### HTTP Status Codes Used

| Code | Constant | Meaning | Used When |
|------|----------|---------|-----------|
| 200 | `HTTP_200_OK` | Success | Default for GET, PUT, PATCH |
| 201 | `HTTP_201_CREATED` | Resource created | After POST that creates data |
| 400 | `HTTP_400_BAD_REQUEST` | Client error | Invalid input, missing fields |
| 401 | `HTTP_401_UNAUTHORIZED` | Not logged in | No authentication provided |
| 403 | `HTTP_403_FORBIDDEN` | Not allowed | Authenticated but no permission |
| 404 | `HTTP_404_NOT_FOUND` | Not found | Resource doesn't exist |
| 405 | `HTTP_405_METHOD_NOT_ALLOWED` | Wrong method | GET on a POST-only endpoint |
| 500 | `HTTP_500_INTERNAL_SERVER_ERROR` | Server error | Unhandled exception |

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Serializer** | Translates between Python objects and JSON |
| **`ModelSerializer`** | Auto-generates fields from a Django model |
| **`Serializer`** | Manual field definitions for non-model data |
| **`ViewSet`** | Class that auto-generates CRUD endpoints |
| **`@api_view`** | Decorator for simple function-based API views |
| **`get_queryset()`** | Scopes data to the current user — critical for security |
| **`bulk_create()`** | Efficient mass-insertion into the database |
| **`request.FILES`** | Access uploaded files from multipart form data |
| **`request.data`** | Access parsed JSON/form body data |

---

**→ Continue to [Part 5: URL Configuration](./05_urls.md)**
