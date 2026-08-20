# Part 7: Testing

---

## Why Test?

Testing answers one question: **"Does this code do what I think it does?"**

Without tests:
- You change model A → you don't know if view B broke
- You refactor a service → you manually test every endpoint in the browser
- You deploy to production → users find the bugs

With tests:
- You change model A → run `python manage.py test` → know immediately if anything broke
- You refactor a service → tests pass → confident the behavior is preserved
- You deploy → CI runs all tests → bugs caught before users see them

---

## Django's Test Framework

Django's test runner:
1. Creates a **temporary test database** (separate from your dev database)
2. Runs all migration files against it
3. Runs your tests
4. Destroys the database

Your real data is never touched.

### Types of Tests

| Type | What it tests | Speed | Database? | Django class |
|------|--------------|-------|-----------|-------------|
| **Unit test** | One function in isolation | Fast (ms) | No | `SimpleTestCase` |
| **Integration test** | Multiple components together | Medium | Yes | `TestCase` |
| **API test** | Full HTTP request → response | Medium | Yes | `TestCase` + `APIClient` |
| **End-to-end test** | Browser → frontend → API → DB | Slow | Yes | Selenium/Playwright |

### Setting Up the Test Package

Django generates a single `tests.py` file. For a real project, split into a package:

```powershell
# From the backend/ directory
del trivia\tests.py
mkdir trivia\tests
```

Create these files:
- `trivia/tests/__init__.py` (empty)
- `trivia/tests/test_interest_ranker.py`
- `trivia/tests/test_models_and_api.py`

---

## Unit Tests — Testing Services (No Database)

`trivia/tests/test_interest_ranker.py`:

```python
from django.test import SimpleTestCase
from trivia.services.interest_ranker import rank_interests


class RankInterestsTests(SimpleTestCase):
    """Tests for the interest ranking service.
    
    Uses SimpleTestCase because this service has no database
    dependencies — it's a pure function.
    """

    def test_empty_input_returns_empty_list(self):
        """Verify graceful handling of empty watch history."""
        result = rank_interests([])
        self.assertEqual(result, [])

    def test_entries_without_channel_names_are_ignored(self):
        """Entries with missing or empty channel names should be skipped."""
        entries = [
            {"channel_name": ""},
            {"channel_name": "F1 Channel"},
            {},  # no channel_name key at all
        ]
        result = rank_interests(entries, top_n=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label"], "F1 Channel")

    def test_ranks_by_frequency_descending(self):
        """Most-watched channel should be ranked first."""
        entries = [
            {"channel_name": "F1 Channel"},
            {"channel_name": "F1 Channel"},
            {"channel_name": "F1 Channel"},
            {"channel_name": "Finance Channel"},
        ]
        result = rank_interests(entries, top_n=2)
        self.assertEqual(result[0]["label"], "F1 Channel")
        self.assertEqual(result[1]["label"], "Finance Channel")

    def test_weights_are_normalized_proportions(self):
        """Weights should sum to approximately 1.0 (within rounding)."""
        entries = [
            {"channel_name": "F1 Channel"},
            {"channel_name": "F1 Channel"},
            {"channel_name": "F1 Channel"},
            {"channel_name": "Finance Channel"},
        ]
        result = rank_interests(entries, top_n=2)
        # F1: 3/4 = 0.75, Finance: 1/4 = 0.25
        self.assertAlmostEqual(result[0]["weight"], 0.75, places=2)
        self.assertAlmostEqual(result[1]["weight"], 0.25, places=2)

    def test_top_n_limits_results(self):
        """Only the top N interests should be returned."""
        entries = [
            {"channel_name": f"Channel {i}"}
            for i in range(20)
        ]
        result = rank_interests(entries, top_n=3)
        self.assertEqual(len(result), 3)
```

### Understanding Test Structure

Every test method follows the **Arrange-Act-Assert** pattern:

```python
def test_ranks_by_frequency_descending(self):
    # ARRANGE — set up the input data
    entries = [
        {"channel_name": "F1 Channel"},
        {"channel_name": "F1 Channel"},
        {"channel_name": "Finance Channel"},
    ]
    
    # ACT — call the function being tested
    result = rank_interests(entries, top_n=2)
    
    # ASSERT — verify the output is correct
    self.assertEqual(result[0]["label"], "F1 Channel")
```

### `SimpleTestCase` vs `TestCase`

| Class | Database? | Transaction wrapping? | Speed |
|-------|-----------|----------------------|-------|
| `SimpleTestCase` | No | No | Very fast (ms) |
| `TestCase` | Yes | Yes (auto-rollback) | Slower (creates/destroys DB) |
| `TransactionTestCase` | Yes | No (actually commits) | Slowest |

**Rule: Use `SimpleTestCase` whenever possible.** Only use `TestCase` when your test creates, reads, or modifies database records.

### Assert Methods

| Method | Checks |
|--------|--------|
| `assertEqual(a, b)` | `a == b` |
| `assertNotEqual(a, b)` | `a != b` |
| `assertTrue(x)` | `x is True` |
| `assertFalse(x)` | `x is False` |
| `assertIn(a, b)` | `a in b` |
| `assertNotIn(a, b)` | `a not in b` |
| `assertIsNone(x)` | `x is None` |
| `assertAlmostEqual(a, b)` | `a ≈ b` (floating-point) |
| `assertRaises(Exc)` | Code raises `Exc` |
| `assertContains(response, text)` | Response body contains text |

---

## Integration Tests — Testing Models and the API

`trivia/tests/test_models_and_api.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from trivia.models import InterestTopic, Question, QuizAttempt, Answer


class AnswerAutoScoringTests(TestCase):
    """Test that Answer.save() automatically computes is_correct."""

    def setUp(self):
        """Create test data used by every test in this class.
        
        setUp() runs BEFORE each test method, guaranteeing clean
        state. Thanks to TestCase's transaction rollback, data from
        one test never leaks into another.
        """
        self.user = User.objects.create_user(
            username="shwetank", password="testpass123"
        )
        self.topic = InterestTopic.objects.create(
            user=self.user, label="F1", weight=0.8
        )
        self.question = Question.objects.create(
            user=self.user,
            topic=self.topic,
            prompt_text="Who won the 2021 F1 championship?",
            options=["Hamilton", "Verstappen", "Bottas", "Perez"],
            correct_answer="Verstappen",
        )
        self.attempt = QuizAttempt.objects.create(user=self.user)

    def test_correct_answer_is_marked_correct(self):
        answer = Answer.objects.create(
            attempt=self.attempt,
            question=self.question,
            selected_answer="Verstappen",
        )
        self.assertTrue(answer.is_correct)

    def test_incorrect_answer_is_marked_incorrect(self):
        answer = Answer.objects.create(
            attempt=self.attempt,
            question=self.question,
            selected_answer="Hamilton",
        )
        self.assertFalse(answer.is_correct)

    def test_case_insensitive_matching(self):
        """Answer matching should be case-insensitive."""
        answer = Answer.objects.create(
            attempt=self.attempt,
            question=self.question,
            selected_answer="verstappen",  # lowercase
        )
        self.assertTrue(answer.is_correct)

    def test_whitespace_is_trimmed(self):
        """Leading/trailing whitespace should be ignored."""
        answer = Answer.objects.create(
            attempt=self.attempt,
            question=self.question,
            selected_answer="  Verstappen  ",
        )
        self.assertTrue(answer.is_correct)


class InterestTopicAPITests(TestCase):
    """Test the /api/interests/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="shwetank", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="other", password="testpass123"
        )
        InterestTopic.objects.create(
            user=self.user, label="F1", weight=0.8
        )
        InterestTopic.objects.create(
            user=self.other_user, label="Finance", weight=0.5
        )

    def test_unauthenticated_request_is_rejected(self):
        """Requests without auth should get 403."""
        response = self.client.get("/api/interests/")
        self.assertEqual(response.status_code, 403)

    def test_user_only_sees_their_own_interests(self):
        """Users should not see other users' interests."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/interests/")
        labels = [item["label"] for item in response.data]
        self.assertIn("F1", labels)
        self.assertNotIn("Finance", labels)

    def test_response_format(self):
        """Each interest should have id, label, and weight."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/interests/")
        self.assertEqual(response.status_code, 200)
        interest = response.data[0]
        self.assertIn("id", interest)
        self.assertIn("label", interest)
        self.assertIn("weight", interest)
```

### Understanding `setUp()`

`setUp()` runs before **each** test method. Combined with `TestCase`'s transaction rollback:

```
test_correct_answer_is_marked_correct:
    1. setUp() creates user, topic, question, attempt
    2. Test runs
    3. Transaction rolls back → all data deleted
    
test_incorrect_answer_is_marked_incorrect:
    1. setUp() creates user, topic, question, attempt (fresh!)
    2. Test runs
    3. Transaction rolls back → all data deleted
```

Tests never leak data into each other.

### Understanding `APIClient`

DRF's `APIClient` simulates HTTP requests without starting a server:

```python
self.client = APIClient()

# Authenticate as a user (skips password check)
self.client.force_authenticate(user=self.user)

# Make requests
response = self.client.get("/api/interests/")
response = self.client.post("/api/upload-history/", data, format="multipart")

# Check the response
response.status_code  # 200, 201, 403, etc.
response.data         # parsed JSON as a Python dict/list
```

---

## Running Tests

```powershell
# Run all tests
python manage.py test trivia -v 2

# Run a specific test file
python manage.py test trivia.tests.test_interest_ranker -v 2

# Run a specific test class
python manage.py test trivia.tests.test_models_and_api.AnswerAutoScoringTests -v 2

# Run a single test method
python manage.py test trivia.tests.test_models_and_api.AnswerAutoScoringTests.test_correct_answer_is_marked_correct -v 2
```

The `-v 2` flag shows verbose output — each test name and PASS/FAIL.

Expected output:

```
test_empty_input_returns_empty_list ... ok
test_entries_without_channel_names_are_ignored ... ok
test_ranks_by_frequency_descending ... ok
test_weights_are_normalized_proportions ... ok
test_top_n_limits_results ... ok
test_correct_answer_is_marked_correct ... ok
test_incorrect_answer_is_marked_incorrect ... ok
test_case_insensitive_matching ... ok
test_whitespace_is_trimmed ... ok
test_unauthenticated_request_is_rejected ... ok
test_user_only_sees_their_own_interests ... ok
test_response_format ... ok

Ran 12 tests in 0.234s
OK
```

---

## Test Naming Conventions

Good test names read like specifications:

```python
# BAD — vague, doesn't describe expected behavior
def test_rank(self):
def test_api(self):

# GOOD — describes the scenario and expected outcome
def test_empty_input_returns_empty_list(self):
def test_user_only_sees_their_own_interests(self):
def test_unauthenticated_request_is_rejected(self):
```

> [!TIP]
> A good test name should tell you **what broke** without reading the test body.
> If `test_case_insensitive_matching` fails, you know immediately that
> answer matching is no longer case-insensitive.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`SimpleTestCase`** | Tests without database access (fastest) |
| **`TestCase`** | Tests with database, auto-rollback between tests |
| **`setUp()`** | Create fresh test data before each test method |
| **`APIClient`** | DRF's test client for simulating API requests |
| **`force_authenticate()`** | Bypass login flow in tests |
| **Arrange-Act-Assert** | Standard test structure pattern |
| **`-v 2`** | Verbose output showing each test result |

---

**→ Continue to [Part 8: The React Frontend](./08_react_frontend.md)**
