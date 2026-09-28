# Part 7: Testing

---

## Why Test?

Testing answers one question: **"Does this code do what I think it does?"**

Without tests you change model A and have no idea whether view B still works. With
tests, `python manage.py test` tells you in seconds.

> [!IMPORTANT]
> The original plan's test suite had 12 tests: 5 for `rank_interests` — a `Counter`
> and a division — and 3 for one API list endpoint. **Nothing tested the parser**, which
> is the fiddliest code in the project, with its "Watched " prefix stripping, `Z`
> timestamp handling, and several crash paths. Nothing tested upload, quiz generation,
> or answer submission. Nothing tested whether one user could see another's data, which
> turned out to be a real bug.
>
> This part tests the code most likely to break, and the code most likely to be a
> security problem.

---

## Django's Test Framework

1. Creates a **temporary test database**, separate from your dev database
2. Runs all migrations against it
3. Runs your tests
4. Destroys it

Your real data is never touched.

### Types of Tests

| Type | Tests | Speed | Database? | Class |
|------|-------|-------|-----------|-------|
| **Unit** | One pure function | Fastest (ms) | No | `SimpleTestCase` |
| **Integration** | Models and their logic | Medium | Yes | `TestCase` |
| **View** | A full request → response cycle | Medium | Yes | `TestCase` + `Client` |
| **End-to-end** | Browser → app → database | Slowest | Yes | Selenium / Playwright |

### The Test Package

Django generates a single `tests.py`. Split it into a package:

```bash
rm trivia/tests.py
mkdir trivia/tests
touch trivia/tests/__init__.py
```

Four files:

| File | Covers |
|------|--------|
| `test_takeout_parser.py` | The pure parser — no database, no Django |
| `test_interest_ranker.py` | The pure ranker — no database, no Django |
| `test_models.py` | `save()` overrides, constraints, properties |
| `test_views.py` | Every endpoint, including cross-user isolation |

---

## Unit Tests — The Parser

`trivia/tests/test_takeout_parser.py`:

```python
import io
import json
from datetime import datetime, timezone

from django.test import SimpleTestCase

from trivia.services.takeout_parser import (
    TakeoutParseError,
    parse_takeout_json,
    parse_takeout_monthly_json,
)


def make_entry(title, video_id="abc", channel="Test Channel", time=None):
    """Build one raw Takeout entry."""
    entry = {
        "header": "YouTube",
        "title": title,
        "titleUrl": f"https://www.youtube.com/watch?v={video_id}",
        "subtitles": [{"name": channel}],
    }
    if time is not None:
        entry["time"] = time
    return entry


def parse(raw):
    return parse_takeout_json(io.StringIO(json.dumps(raw)))


class ParseTitleTests(SimpleTestCase):
    def test_strips_watched_prefix(self):
        result = parse([make_entry("Watched F1 Highlights")])
        self.assertEqual(result[0]["video_title"], "F1 Highlights")

    def test_strips_only_the_first_watched_prefix(self):
        """A title legitimately containing 'Watched' must survive intact."""
        result = parse([make_entry("Watched I Watched Every Star Wars Movie")])
        self.assertEqual(
            result[0]["video_title"], "I Watched Every Star Wars Movie"
        )

    def test_strips_whitespace_after_prefix(self):
        """Google emits 'Watched  Foo' with two spaces on some accounts."""
        result = parse([make_entry("Watched  Double Space")])
        self.assertEqual(result[0]["video_title"], "Double Space")

    def test_leaves_untitled_entries_out(self):
        with self.assertRaises(TakeoutParseError):
            parse([make_entry("Watched   ")])


class ParseFilteringTests(SimpleTestCase):
    def test_keeps_real_videos(self):
        result = parse([make_entry("Watched A", video_id="a")])
        self.assertEqual(len(result), 1)

    def test_skips_entries_without_watch_url(self):
        """Homepage visits and 'Watched [Deleted video]' have no watch?v= URL."""
        raw = [
            {"title": "Visited the YouTube homepage",
             "titleUrl": "https://www.youtube.com/?gl=US"},
            {"title": "Watched [Deleted video]", "subtitles": [{"name": "Gone"}]},
        ]
        with self.assertRaises(TakeoutParseError):
            parse(raw)

    def test_skips_non_dict_items(self):
        """A bare string in the array must not crash the parser."""
        result = parse(["a string", 42, None, make_entry("Watched Real", "r")])
        self.assertEqual(len(result), 1)

    def test_raises_when_no_videos_found(self):
        """Uploading subscriptions.json must fail loudly, not silently."""
        with self.assertRaises(TakeoutParseError):
            parse([{"title": "Some Channel", "titleUrl": "https://youtube.com/c/abc"}])


class ParseChannelTests(SimpleTestCase):
    def test_extracts_channel_name(self):
        result = parse([make_entry("Watched A", channel="F1 Official")])
        self.assertEqual(result[0]["channel_name"], "F1 Official")

    def test_missing_subtitles_gives_empty_string(self):
        raw = [{
            "title": "Watched A",
            "titleUrl": "https://www.youtube.com/watch?v=a",
        }]
        result = parse(raw)
        self.assertEqual(result[0]["channel_name"], "")

    def test_malformed_subtitles_give_empty_string(self):
        raw = [{
            "title": "Watched A",
            "titleUrl": "https://www.youtube.com/watch?v=a",
            "subtitles": ["not a dict"],
        }]
        result = parse(raw)
        self.assertEqual(result[0]["channel_name"], "")


class ParseTimestampTests(SimpleTestCase):
    def test_parses_zulu_suffix(self):
        result = parse([make_entry("Watched A", time="2024-12-15T14:30:00.000Z")])
        self.assertEqual(
            result[0]["watched_at"],
            datetime(2024, 12, 15, 14, 30, tzinfo=timezone.utc),
        )

    def test_converts_offsets_to_utc(self):
        result = parse([make_entry("Watched A", time="2024-12-13T10:15:00.000+05:30")])
        self.assertEqual(
            result[0]["watched_at"],
            datetime(2024, 12, 13, 4, 45, tzinfo=timezone.utc),
        )

    def test_treats_naive_timestamps_as_utc(self):
        result = parse([make_entry("Watched A", time="2024-12-15T14:30:00")])
        self.assertEqual(
            result[0]["watched_at"],
            datetime(2024, 12, 15, 14, 30, tzinfo=timezone.utc),
        )

    def test_always_returns_aware_datetimes(self):
        """USE_TZ=True means a naive datetime triggers a warning and wrong maths."""
        result = parse([make_entry("Watched A", time="2024-12-15T14:30:00Z")])
        self.assertIsNotNone(result[0]["watched_at"].tzinfo)

    def test_unparseable_timestamp_becomes_none(self):
        result = parse([make_entry("Watched A", time="last tuesday")])
        self.assertIsNone(result[0]["watched_at"])

    def test_missing_timestamp_becomes_none(self):
        result = parse([make_entry("Watched A")])
        self.assertIsNone(result[0]["watched_at"])


class ParseErrorTests(SimpleTestCase):
    def test_malformed_json_raises(self):
        with self.assertRaises(TakeoutParseError) as ctx:
            parse_takeout_json(io.StringIO("{not valid json"))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_json_object_at_top_level_raises(self):
        with self.assertRaises(TakeoutParseError):
            parse_takeout_json(io.StringIO('{"entries": []}'))

    def test_empty_list_raises(self):
        with self.assertRaises(TakeoutParseError):
            parse_takeout_json(io.StringIO("[]"))

    def test_error_message_names_the_right_file(self):
        """The user needs to know which file to upload, not just that it failed."""
        with self.assertRaises(TakeoutParseError) as ctx:
            parse_takeout_json(io.StringIO("[]"))
        self.assertIn("watch-history.json", str(ctx.exception))


class MonthlyVariantTests(SimpleTestCase):
    def test_flattens_nested_arrays(self):
        raw = [
            [make_entry("Watched A", "a", "Channel One")],
            [make_entry("Watched B", "b", "Channel Two")],
        ]
        result = parse_takeout_monthly_json(io.StringIO(json.dumps(raw)))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["channel_name"], "Channel One")
```

### `SimpleTestCase` and Why It Is the Default Choice

| Class | Database | Transactions | Speed |
|-------|----------|--------------|-------|
| `SimpleTestCase` | No access | No | Fastest |
| `TestCase` | Yes | Auto-rollback | Slower |
| `TransactionTestCase` | Yes | Actually commits | Slowest |

**Rule: use `SimpleTestCase` unless the test touches the database.** The parser has no
Django dependency, so its 25 tests run in milliseconds with no database created at all.

> [!NOTE]
> `SimpleTestCase` **blocks** database queries. If a test accidentally starts hitting
> the database, Django raises an error rather than silently creating a slow test. That is
> a feature: it keeps the "pure function" boundary honest.

---

## Unit Tests — The Ranker

`trivia/tests/test_interest_ranker.py`:

```python
from django.test import SimpleTestCase

from trivia.services.interest_ranker import rank_interests, renormalize


def entries(*channels):
    """Build a watch-entry list from channel names."""
    return [{"channel_name": channel} for channel in channels]


class RankInterestsTests(SimpleTestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(rank_interests([]), [])

    def test_entries_without_channel_names_are_ignored(self):
        result = rank_interests(
            [{"channel_name": ""}, {"channel_name": "F1"}, {}], top_n=5
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label"], "F1")

    def test_ranks_by_frequency_descending(self):
        result = rank_interests(
            entries("F1", "F1", "F1", "Finance"), top_n=2
        )
        self.assertEqual(result[0]["label"], "F1")
        self.assertEqual(result[1]["label"], "Finance")

    def test_top_n_limits_results(self):
        result = rank_interests(entries(*[f"Channel {i}" for i in range(20)]), top_n=3)
        self.assertEqual(len(result), 3)

    def test_weight_is_share_of_total_history(self):
        result = rank_interests(entries("A", "A", "A", "B"), top_n=2)
        self.assertAlmostEqual(result[0]["weight"], 0.75, places=2)
        self.assertAlmostEqual(result[1]["weight"], 0.25, places=2)


class WeightSemanticsTests(SimpleTestCase):
    """Pin down exactly what weight means.

    The original plan asserted that weights sum to 1.0. That test passed
    only because it used 2 channels with top_n=2, so the top-N happened to
    cover the whole history. These tests use 6 channels and top_n=3, where
    the distinction is real.
    """

    def test_weights_do_not_sum_to_one_when_top_n_truncates(self):
        data = entries(*(["A"] * 30 + ["B"] * 20 + ["C"] * 10 + ["D"] * 5
                         + ["E"] * 3 + ["F"] * 2))
        result = rank_interests(data, top_n=3)
        self.assertEqual(len(result), 3)
        self.assertLess(sum(item["weight"] for item in result), 1.0)

    def test_weight_denominator_is_full_history_not_top_n(self):
        """30 of 70 videos is 0.429, not 30/60 (the top-3 total)."""
        data = entries(*(["A"] * 30 + ["B"] * 20 + ["C"] * 10 + ["D"] * 5
                         + ["E"] * 3 + ["F"] * 2))
        result = rank_interests(data, top_n=3)
        self.assertAlmostEqual(result[0]["weight"], 30 / 70, places=2)

    def test_weights_sum_to_one_when_top_n_covers_everything(self):
        result = rank_interests(entries("A", "A", "B"), top_n=5)
        self.assertAlmostEqual(sum(item["weight"] for item in result), 1.0, places=2)

    def test_renormalize_makes_returned_set_sum_to_one(self):
        data = entries(*(["A"] * 30 + ["B"] * 20 + ["C"] * 10 + ["D"] * 5
                         + ["E"] * 3 + ["F"] * 2))
        result = renormalize(rank_interests(data, top_n=3))
        self.assertAlmostEqual(sum(item["weight"] for item in result), 1.0, places=2)

    def test_renormalize_handles_empty_input(self):
        self.assertEqual(renormalize([]), [])

    def test_min_share_drops_weak_interests(self):
        data = entries(*(["A"] * 90 + ["B"] * 6 + ["C"] * 4))
        result = rank_interests(data, top_n=5, min_share=0.1)
        self.assertEqual([item["label"] for item in result], ["A"])
```

> [!TIP]
> `test_min_share_drops_weak_interests` documents a real product decision: without a
> threshold, a user who watched 200 F1 videos and one video each from 40 other channels
> gets five "interests" that are all noise. `min_share=0.02` is a reasonable default.

---

## Integration Tests — Models

`trivia/tests/test_models.py`:

```python
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from trivia.models import (
    Answer,
    InterestTopic,
    Question,
    QuizAttempt,
    WatchHistoryEntry,
    normalize_answer,
)


class NormalizeAnswerTests(TestCase):
    def test_collapses_internal_whitespace(self):
        self.assertEqual(normalize_answer("Red  Bull"), normalize_answer("Red Bull"))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(normalize_answer("  Red Bull  "), normalize_answer("Red Bull"))

    def test_is_case_insensitive(self):
        self.assertEqual(normalize_answer("RED BULL"), normalize_answer("red bull"))

    def test_handles_none(self):
        self.assertEqual(normalize_answer(None), normalize_answer("None"))


class AnswerScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345678")
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

    def _answer(self, selected):
        return Answer.objects.create(
            attempt=self.attempt,
            question=self.question,
            selected_answer=selected,
        )

    def test_correct_answer_marked_correct(self):
        self.assertTrue(self._answer("Verstappen").is_correct)

    def test_incorrect_answer_marked_incorrect(self):
        self.assertFalse(self._answer("Hamilton").is_correct)

    def test_matching_is_case_insensitive(self):
        self.assertTrue(self._answer("verstappen").is_correct)

    def test_matching_ignores_surrounding_whitespace(self):
        self.assertTrue(self._answer("  Verstappen  ").is_correct)

    def test_matching_ignores_internal_whitespace(self):
        self.question.options = ["Red  Bull", "Red Bull", "Oracle", "Ferrari"]
        self.question.correct_answer = "Red Bull"
        self.question.save()
        self.assertTrue(self._answer("Red  Bull").is_correct)

    def test_is_correct_recomputed_on_update(self):
        answer = self._answer("Hamilton")
        self.assertFalse(answer.is_correct)
        answer.selected_answer = "Verstappen"
        answer.save()
        self.assertTrue(answer.is_correct)

    def test_question_grades_correctly_helper(self):
        self.assertTrue(self.question.grades_correctly(" VERSTAPPEN "))
        self.assertFalse(self.question.grades_correctly("Hamilton"))


class AnswerConstraintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345678")
        self.topic = InterestTopic.objects.create(
            user=self.user, label="F1", weight=0.8
        )
        self.attempt = QuizAttempt.objects.create(user=self.user)
        self.question = Question.objects.create(
            user=self.user,
            attempt=self.attempt,
            topic=self.topic,
            prompt_text="Q?",
            options=["A", "B", "C", "D"],
            correct_answer="A",
        )

    def test_same_question_cannot_be_answered_twice_in_one_attempt(self):
        """The constraint that makes quiz scores meaningful."""
        Answer.objects.create(
            attempt=self.attempt, question=self.question, selected_answer="A"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Answer.objects.create(
                    attempt=self.attempt,
                    question=self.question,
                    selected_answer="A",
                )

    def test_retaking_creates_a_fresh_question_not_a_shared_one(self):
        """A retake must not be blocked by the unique constraint.

        It is not blocked because generate_quiz creates *new* Question rows for
        each attempt (Part 4). A retake is a new attempt with its own
        questions, so (attempt, question) is always a new pair.

        Note what this test deliberately does NOT do: reuse self.question in a
        second attempt. Question.attempt is the attempt that question was shown
        in, so pairing it with another attempt would be a data-integrity bug --
        the constraint is keyed on (attempt, question) and would happily allow
        it, which is exactly why the views scope question lookups by attempt.
        """
        retake = QuizAttempt.objects.create(user=self.user)
        retake_question = Question.objects.create(
            user=self.user,
            attempt=retake,
            topic=self.topic,
            prompt_text="Q?",
            options=["A", "B", "C", "D"],
            correct_answer="B",
        )

        Answer.objects.create(
            attempt=self.attempt, question=self.question, selected_answer="A"
        )
        Answer.objects.create(
            attempt=retake, question=retake_question, selected_answer="B"
        )

        self.assertEqual(Answer.objects.count(), 2)
        self.assertEqual(
            Answer.objects.filter(is_correct=True).count(), 1
        )


class QuizAttemptPropertyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345678")

    def test_is_complete_false_when_not_completed(self):
        self.assertFalse(QuizAttempt.objects.create(user=self.user).is_complete)

    def test_is_complete_true_after_completion(self):
        from django.utils import timezone

        attempt = QuizAttempt.objects.create(
            user=self.user, completed_at=timezone.now()
        )
        self.assertTrue(attempt.is_complete)


class WatchHistoryEntryTests(TestCase):
    def test_str_truncates_long_titles(self):
        user = User.objects.create_user(username="alice", password="pw12345678")
        entry = WatchHistoryEntry.objects.create(
            user=user,
            video_title="x" * 200,
            channel_name="Some Channel",
        )
        self.assertLessEqual(len(str(entry)), 60)
```

### `setUp()` and Transaction Rollback

`setUp()` runs before **each** test method:

```
test_correct_answer_marked_correct:
    1. setUp() creates user, topic, question, attempt
    2. Test runs
    3. Transaction rolls back — all data deleted

test_incorrect_answer_marked_incorrect:
    1. setUp() creates user, topic, question, attempt (fresh)
    2. Test runs
    3. Transaction rolls back
```

Tests never leak data into each other, and you never need manual teardown.

### Testing the UniqueConstraint

```python
with self.assertRaises(IntegrityError):
    with transaction.atomic():
        Answer.objects.create(...)
```

The inner `transaction.atomic()` is required. Without it, the `IntegrityError` leaves
the connection in a broken transaction state and every subsequent query in the test
raises `TransactionManagementError`. This is a common and confusing failure; the nested
atomic block is the fix.

---

## View Tests — The Important Ones

`trivia/tests/test_views.py`:

```python
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from trivia.models import Answer, InterestTopic, Question, QuizAttempt, WatchHistoryEntry
from trivia.services.llm_service import LLMError


SAMPLE_TAKEOUT = [
    {
        "title": "Watched Max Verstappen Overtake",
        "titleUrl": "https://www.youtube.com/watch?v=a1",
        "subtitles": [{"name": "F1 Official"}],
        "time": "2024-12-15T14:30:00.000Z",
    },
    {
        "title": "Watched Verstappen Wins Monaco",
        "titleUrl": "https://www.youtube.com/watch?v=a2",
        "subtitles": [{"name": "F1 Official"}],
        "time": "2024-12-14T10:15:00.000Z",
    },
    {
        "title": "Watched Black Holes Explained",
        "titleUrl": "https://www.youtube.com/watch?v=b1",
        "subtitles": [{"name": "Veritasium"}],
        "time": "2024-12-13T09:00:00.000Z",
    },
]


def upload_file(content=None, name="watch-history.json"):
    """Build a real in-memory upload.

    A bare io.BytesIO has no .name, so Django's test client sends it as a plain
    form value and request.FILES stays empty. SimpleUploadedFile is what makes
    the field actually a file, complete with a filename and content type.
    """
    if content is None:
        content = json.dumps(SAMPLE_TAKEOUT)
    if isinstance(content, str):
        content = content.encode("utf-8")
    return SimpleUploadedFile(name, content, content_type="application/json")


class BaseUserTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345678")
        self.other = User.objects.create_user(username="mallory", password="pw12345678")
        self.client.login(username="alice", password="pw12345678")

    def make_topic(self, user=None, label="F1", weight=0.8):
        return InterestTopic.objects.create(
            user=user or self.user, label=label, weight=weight
        )

    def make_attempt_with_question(self, user=None, correct="Verstappen"):
        user = user or self.user
        topic = self.make_topic(user=user)
        attempt = QuizAttempt.objects.create(user=user)
        question = Question.objects.create(
            user=user,
            attempt=attempt,
            topic=topic,
            prompt_text="Who won the 2021 F1 championship?",
            options=["Hamilton", "Verstappen", "Bottas", "Perez"],
            correct_answer=correct,
        )
        return attempt, question


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class AuthenticationTests(TestCase):
    def test_every_protected_view_redirects_anonymous_users(self):
        urls = [
            ("trivia:interests", {}),
            ("trivia:upload", {}),
            ("trivia:quiz", {"attempt_id": 1}),
            ("trivia:results", {"attempt_id": 1}),
        ]
        for name, kwargs in urls:
            with self.subTest(view=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response["Location"])

    def test_login_page_is_reachable(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_login_redirects_to_interests(self):
        User.objects.create_user(username="alice", password="pw12345678")
        response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "pw12345678"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/"))

    def test_bad_password_shows_form_error_not_crash(self):
        User.objects.create_user(username="alice", password="pw12345678")
        response = self.client.post(
            reverse("login"), {"username": "alice", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class UploadTests(BaseUserTestCase):
    def test_get_shows_form(self):
        response = self.client.get(reverse("trivia:upload"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_valid_upload_creates_entries_and_interests(self):
        response = self.client.post(
            reverse("trivia:upload"), {"file": upload_file()}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WatchHistoryEntry.objects.filter(user=self.user).count(), 3)
        self.assertEqual(InterestTopic.objects.filter(user=self.user).count(), 2)
        top = InterestTopic.objects.filter(user=self.user).first()
        self.assertEqual(top.label, "F1 Official")

    def test_reupload_replaces_rather_than_accumulates(self):
        """Uploading twice must not double-count channels."""
        self.client.post(reverse("trivia:upload"), {"file": upload_file()})
        self.client.post(reverse("trivia:upload"), {"file": upload_file()})
        self.assertEqual(WatchHistoryEntry.objects.filter(user=self.user).count(), 3)
        self.assertEqual(InterestTopic.objects.filter(user=self.user).count(), 2)

    def test_missing_file_is_a_form_error(self):
        response = self.client.post(reverse("trivia:upload"), {})
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_malformed_json_shows_friendly_error(self):
        """The original code returned a 500 traceback here."""
        response = self.client.post(
            reverse("trivia:upload"),
            {"file": upload_file(content="{not valid json")},
        )
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors
        self.assertIn("file", errors)
        self.assertIn("not valid JSON", str(errors["file"]))

    def test_wrong_file_type_rejected_before_parsing(self):
        response = self.client.post(
            reverse("trivia:upload"),
            {"file": upload_file(content="[]", name="Takeout-12345.zip")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_upload_with_no_videos_shows_error(self):
        """Uploading subscriptions.json must not silently create zero interests."""
        response = self.client.post(
            reverse("trivia:upload"),
            {"file": upload_file(content=json.dumps([{"title": "A Channel"}]))},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_upload_does_not_touch_other_users_data(self):
        self.make_topic(user=self.other, label="Theirs")
        self.client.post(reverse("trivia:upload"), {"file": upload_file()})
        self.assertTrue(
            InterestTopic.objects.filter(user=self.other, label="Theirs").exists()
        )


# ---------------------------------------------------------------------------
# Interests
# ---------------------------------------------------------------------------

class InterestsTests(BaseUserTestCase):
    def test_shows_only_own_interests(self):
        self.make_topic(user=self.user, label="Mine")
        self.make_topic(user=self.other, label="Theirs")
        response = self.client.get(reverse("trivia:interests"))
        labels = [t.label for t in response.context["topics"]]
        self.assertIn("Mine", labels)
        self.assertNotIn("Theirs", labels)


# ---------------------------------------------------------------------------
# Quiz generation — with the LLM mocked
# ---------------------------------------------------------------------------

class GenerateQuizTests(BaseUserTestCase):
    MOCK_QUESTIONS = [
        {
            "prompt_text": "Who won the 2021 F1 championship?",
            "options": ["Hamilton", "Verstappen", "Bottas", "Perez"],
            "correct_answer": "Verstappen",
        }
    ]

    def test_requires_interests_first(self):
        response = self.client.post(reverse("trivia:generate-quiz"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(QuizAttempt.objects.count(), 0)

    @patch("trivia.views.generate_questions")
    def test_creates_attempt_with_questions_linked(self, mock_generate):
        """Questions must belong to the attempt -- the bug the original plan had."""
        mock_generate.return_value = self.MOCK_QUESTIONS
        self.make_topic()

        response = self.client.post(reverse("trivia:generate-quiz"))

        self.assertEqual(response.status_code, 302)
        attempt = QuizAttempt.objects.get()
        self.assertEqual(attempt.user, self.user)
        self.assertEqual(attempt.questions.count(), 1)
        self.assertIsNotNone(attempt.questions.first().attempt)

    @patch("trivia.views.generate_questions")
    def test_questions_span_multiple_topics(self, mock_generate):
        mock_generate.return_value = self.MOCK_QUESTIONS
        for i in range(5):
            self.make_topic(label=f"Topic {i}")

        self.client.post(reverse("trivia:generate-quiz"))

        topics_used = set(
            Question.objects.values_list("topic__label", flat=True)
        )
        self.assertEqual(len(topics_used), 3)  # TOPICS_PER_QUIZ

    @patch("trivia.views.generate_questions")
    def test_get_is_not_allowed(self, mock_generate):
        self.make_topic()
        response = self.client.get(reverse("trivia:generate-quiz"))
        self.assertEqual(response.status_code, 405)

    @patch("trivia.views.generate_questions")
    def test_total_failure_deletes_empty_attempt_and_explains(self, mock_generate):
        """The original returned 201 with an empty quiz and no message."""
        mock_generate.side_effect = LLMError("ANTHROPIC_API_KEY is not set.")
        self.make_topic()

        response = self.client.post(reverse("trivia:generate-quiz"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(QuizAttempt.objects.count(), 0)  # no orphan attempt
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("ANTHROPIC_API_KEY" in m for m in messages))

    @patch("trivia.views.generate_questions")
    def test_partial_failure_keeps_the_quiz_and_warns(self, mock_generate):
        """One bad topic must not kill the whole quiz, but must be reported."""
        self.make_topic(label="Good Topic")
        self.make_topic(label="Bad Topic")

        def side_effect(label, num_questions=2):
            if label == "Bad Topic":
                raise LLMError("Rate limited")
            return self.MOCK_QUESTIONS

        mock_generate.side_effect = side_effect

        response = self.client.post(reverse("trivia:generate-quiz"), follow=True)

        self.assertEqual(QuizAttempt.objects.count(), 1)
        self.assertEqual(Question.objects.count(), 1)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("could not be reached" in m for m in messages))

    @patch("trivia.views.generate_questions")
    def test_unexpected_exception_does_not_crash_the_request(self, mock_generate):
        mock_generate.side_effect = RuntimeError("something unforeseen")
        self.make_topic()
        response = self.client.post(reverse("trivia:generate-quiz"), follow=True)
        self.assertEqual(response.status_code, 200)  # not a 500


# ---------------------------------------------------------------------------
# Quiz display
# ---------------------------------------------------------------------------

class QuizViewTests(BaseUserTestCase):
    def test_shows_attempt_questions(self):
        attempt, question = self.make_attempt_with_question()
        response = self.client.get(reverse("trivia:quiz", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 1)

    def test_cannot_view_another_users_attempt(self):
        """404, not 403 -- a 403 would confirm the attempt exists."""
        attempt, _ = self.make_attempt_with_question(user=self.other)
        response = self.client.get(reverse("trivia:quiz", args=[attempt.id]))
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_attempt_is_404(self):
        response = self.client.get(reverse("trivia:quiz", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_already_answered_questions_are_marked(self):
        attempt, question = self.make_attempt_with_question()
        Answer.objects.create(
            attempt=attempt, question=question, selected_answer="Verstappen"
        )
        response = self.client.get(reverse("trivia:quiz", args=[attempt.id]))
        self.assertEqual(response.context["answered_count"], 1)
        self.assertEqual(response.context["rows"][0]["answer"].question_id, question.id)


# ---------------------------------------------------------------------------
# Answer submission -- the security-critical view
# ---------------------------------------------------------------------------

class SubmitAnswerTests(BaseUserTestCase):
    def test_correct_answer_increments_score(self):
        attempt, question = self.make_attempt_with_question()
        response = self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Verstappen"},
        )
        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)

    def test_incorrect_answer_does_not_increment_score(self):
        attempt, question = self.make_attempt_with_question()
        self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Hamilton"},
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 0)

    def test_resubmitting_does_not_inflate_the_score(self):
        """The bug the original plan had: nothing stopped score farming."""
        attempt, question = self.make_attempt_with_question()
        url = reverse(
            "trivia:submit-answer",
            kwargs={"attempt_id": attempt.id, "question_id": question.id},
        )
        for _ in range(10):
            self.client.post(url, {"selected_answer": "Verstappen"})
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)
        self.assertEqual(Answer.objects.count(), 1)

    def test_resubmission_shows_previous_answer(self):
        attempt, question = self.make_attempt_with_question()
        url = reverse(
            "trivia:submit-answer",
            kwargs={"attempt_id": attempt.id, "question_id": question.id},
        )
        self.client.post(url, {"selected_answer": "Verstappen"})
        response = self.client.post(url, {"selected_answer": "Hamilton"})
        self.assertTrue(response.context["already_answered"])
        self.assertEqual(response.context["answer"].selected_answer, "Verstappen")

    def test_answer_not_in_options_is_rejected(self):
        attempt, question = self.make_attempt_with_question()
        self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Nonsense"},
        )
        self.assertEqual(Answer.objects.count(), 0)

    def test_cannot_answer_someone_elses_attempt(self):
        attempt, question = self.make_attempt_with_question(user=self.other)
        response = self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Verstappen"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Answer.objects.count(), 0)

    def test_cannot_answer_question_from_a_different_attempt(self):
        """The subtler variant: own attempt, foreign question id."""
        my_attempt, _ = self.make_attempt_with_question()
        their_attempt, their_question = self.make_attempt_with_question(
            user=self.other
        )
        response = self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": my_attempt.id,
                            "question_id": their_question.id}),
            {"selected_answer": "Verstappen"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Answer.objects.count(), 0)

    def test_does_not_leak_the_answer_key_for_unanswerable_requests(self):
        """The original returned question.correct_answer to anyone with an id."""
        _, their_question = self.make_attempt_with_question(user=self.other)
        response = self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": 99999, "question_id": their_question.id}),
            {"selected_answer": "Verstappen"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Verstappen", status_code=404)

    def test_feedback_reveals_answer_after_submitting(self):
        """Revealing it *after* a committed answer is correct, not a leak."""
        attempt, question = self.make_attempt_with_question()

        # Before any submission, the answer key must not be on the page.
        quiz_page = self.client.get(reverse("trivia:quiz", args=[attempt.id]))
        self.assertNotContains(quiz_page, "Verstappen")

        # Answer *wrong*: that is the case where the correct answer is disclosed.
        response = self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Hamilton"},
        )
        self.assertContains(response, "Verstappen")

    def test_feedback_does_not_disclose_answer_when_correct(self):
        """A right answer needs no key, and the partial must not print it."""
        attempt, question = self.make_attempt_with_question()
        response = self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Verstappen"},
        )
        self.assertContains(response, "Correct")
        self.assertNotContains(response, "The correct answer was")

    def test_get_is_not_allowed(self):
        attempt, question = self.make_attempt_with_question()
        response = self.client.get(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id})
        )
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# Completion and results
# ---------------------------------------------------------------------------

class CompleteAttemptTests(BaseUserTestCase):
    def test_completing_sets_timestamp_and_score(self):
        attempt, question = self.make_attempt_with_question()
        self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Verstappen"},
        )
        response = self.client.post(
            reverse("trivia:complete-attempt", args=[attempt.id])
        )
        self.assertEqual(response.status_code, 302)
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.completed_at)
        self.assertEqual(attempt.score, 1)

    def test_completing_twice_is_idempotent(self):
        attempt, _ = self.make_attempt_with_question()
        url = reverse("trivia:complete-attempt", args=[attempt.id])
        self.client.post(url)
        first = attempt.completed_at
        self.client.post(url)
        attempt.refresh_from_db()
        self.assertEqual(attempt.completed_at, first)

    def test_cannot_complete_another_users_attempt(self):
        attempt, _ = self.make_attempt_with_question(user=self.other)
        response = self.client.post(
            reverse("trivia:complete-attempt", args=[attempt.id])
        )
        self.assertEqual(response.status_code, 404)


class ResultsTests(BaseUserTestCase):
    def test_shows_score_breakdown(self):
        attempt, question = self.make_attempt_with_question()
        self.client.post(
            reverse("trivia:submit-answer",
                    kwargs={"attempt_id": attempt.id, "question_id": question.id}),
            {"selected_answer": "Verstappen"},
        )
        self.client.post(reverse("trivia:complete-attempt", args=[attempt.id]))
        response = self.client.get(reverse("trivia:results", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["correct"], 1)
        self.assertEqual(response.context["total"], 1)

    def test_cannot_view_another_users_results(self):
        attempt, _ = self.make_attempt_with_question(user=self.other)
        response = self.client.get(reverse("trivia:results", args=[attempt.id]))
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# LLM service
# ---------------------------------------------------------------------------

class LLMServiceTests(TestCase):
    def test_raises_clear_error_when_api_key_missing(self):
        """Importing llm_service must not raise -- only calling it should."""
        from trivia.services import llm_service

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            llm_service._client = None
            with self.assertRaises(LLMError) as ctx:
                llm_service.get_client()
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_mock_mode_returns_valid_questions_without_api(self):
        from trivia.services import llm_service

        with patch.dict("os.environ", {"WATCHTRIVIA_MOCK_LLM": "True"}):
            questions = llm_service.generate_questions("Formula 1", num_questions=2)
        self.assertEqual(len(questions), 2)
        for question in questions:
            self.assertEqual(len(question["options"]), 4)
            self.assertIn(question["correct_answer"], question["options"])

    def test_validation_rejects_wrong_option_count(self):
        from trivia.services.llm_service import _validate_questions

        with self.assertRaises(LLMError):
            _validate_questions(
                [{"prompt_text": "Q?", "options": ["A", "B"], "correct_answer": "A"}],
                "Topic", 2,
            )

    def test_validation_rejects_answer_not_in_options(self):
        from trivia.services.llm_service import _validate_questions

        with self.assertRaises(LLMError):
            _validate_questions(
                [{
                    "prompt_text": "Q?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "E",
                }],
                "Topic", 2,
            )

    def test_validation_drops_bad_items_and_keeps_good_ones(self):
        from trivia.services.llm_service import _validate_questions

        result = _validate_questions(
            [
                {"prompt_text": "", "options": ["A", "B", "C", "D"],
                 "correct_answer": "A"},
                {"prompt_text": "Good?", "options": ["A", "B", "C", "D"],
                 "correct_answer": "B"},
            ],
            "Topic", 5,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["prompt_text"], "Good?")

    def test_validation_rejects_non_list_payload(self):
        from trivia.services.llm_service import _validate_questions

        with self.assertRaises(LLMError):
            _validate_questions({"prompt_text": "Q?"}, "Topic", 2)
```

### Why `@patch` the LLM

```python
class GenerateQuizTests(TestCase):
    @patch("trivia.views.generate_questions")
    def test_generates_questions_for_each_topic(self, mock_generate):
        mock_generate.return_value = [{"prompt_text": "Q?", "options": [],
                                       "correct_answer": ""}]
        # ... arrange, act, assert ...
```

Three reasons this is not optional:

1. **Cost.** A test suite that calls the real API on every run bills real money and
   takes real time.
2. **Determinism.** An LLM might return three options instead of four. A test that
   depends on the model's good behaviour is a test that fails at random.
3. **Speed.** The mock returns instantly.

Note the patch target is `"trivia.views.generate_questions"`, not
`"trivia.services.llm_service.generate_questions"`. `views.py` does
`from .services.llm_service import generate_questions`, which binds the name into the
`views` module namespace at import time. Patching the service module would have no
effect on the already-bound name.

> [!TIP]
> If a patch appears to do nothing, you are almost certainly patching the wrong path.
> The rule: patch **where the name is looked up**, which is the module that calls it.

### The Three Tests That Matter Most

If you only keep three from this part, keep these:

| Test | Bug it prevents |
|------|-----------------|
| `test_cannot_answer_someone_elses_attempt` | Answer-key leak to any authenticated user |
| `test_cannot_answer_question_from_a_different_attempt` | Scoring a question not in the quiz |
| `test_resubmitting_does_not_inflate_the_score` | Unbounded score inflation |

All three correspond to real defects in the original plan's code.

---

## Running Tests

```bash
# Everything
python manage.py test

# Just the trivia app, verbose
python manage.py test trivia -v 2

# One file
python manage.py test trivia.tests.test_takeout_parser -v 2

# One class
python manage.py test trivia.tests.test_views.SubmitAnswerTests -v 2

# One method
python manage.py test trivia.tests.test_views.SubmitAnswerTests.test_resubmitting_does_not_inflate_the_score
```

The `-v 2` flag shows each test name and result. Expected output:

```
test_strips_watched_prefix ... ok
test_strips_only_the_first_watched_prefix ... ok
test_parses_zulu_suffix ... ok
test_converts_offsets_to_utc ... ok
test_malformed_json_raises ... ok
test_resubmitting_does_not_inflate_the_score ... ok
test_cannot_answer_someone_elses_attempt ... ok
test_cannot_answer_question_from_a_different_attempt ... ok

Ran 76 tests in 1.412s

OK
```

### Measuring Coverage

Coverage is a standard library module, so no extra dependency is needed:

```bash
python -m coverage run manage.py test trivia
python -m coverage report --include="trivia/*"
python -m coverage html   # opens a browsable report
```

Aim for the **service layer and views** to be near 100%. Model field declarations are
hard to cover meaningfully and do not need to be.

---

## Test Naming Conventions

```python
# BAD — vague, tells you nothing when it fails
def test_rank(self): ...
def test_api(self): ...

# GOOD — reads like a specification
def test_empty_input_returns_empty_list(self): ...
def test_cannot_answer_someone_elses_attempt(self): ...
def test_resubmitting_does_not_inflate_the_score(self): ...
```

A good test name tells you **what broke** without reading the body. If
`test_resubmitting_does_not_inflate_the_score` fails, you know immediately that score
integrity regressed — you do not need to open the file.

### Arrange-Act-Assert

Every test follows the same three phases:

```python
def test_correct_answer_increments_score(self):
    # ARRANGE
    attempt, question = self.make_attempt_with_question()

    # ACT
    self.client.post(url, {"selected_answer": "Verstappen"})

    # ASSERT
    attempt.refresh_from_db()
    self.assertEqual(attempt.score, 1)
```

The `refresh_from_db()` is required — the in-memory `attempt` still holds the old value
because `views.py` saved a different instance.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`SimpleTestCase`** | No database; fastest; blocks accidental queries |
| **`TestCase`** | Real database, auto-rollback between tests |
| **`setUp()`** | Fresh data before each test method |
| **`client`** | Simulates HTTP requests without a server |
| **`assertRedirects`** | Assert a 302 and optionally follow it |
| **`subTest`** | Continue a test after one case fails, reporting each |
| **`IntegrityError`** | The database rejected a constraint violation |
| **`@patch`** | Replace a function; required for LLM calls |
| **Patching target** | Patch where the name is *looked up*, not where it is defined |
| **Arrange-Act-Assert** | The standard three-phase test structure |

---

**→ Continue to [Part 8: The HTMX Frontend](./08_htmx_frontend.md)**
