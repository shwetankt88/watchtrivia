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

    def make_attempt_with_question(self, user=None, correct="Verstappen",
                                   options=None, prompt="Who won the 2021 F1 championship?"):
        user = user or self.user
        topic = self.make_topic(user=user)
        attempt = QuizAttempt.objects.create(user=user)
        question = Question.objects.create(
            user=user,
            attempt=attempt,
            topic=topic,
            prompt_text=prompt,
            options=options or ["Hamilton", "Verstappen", "Bottas", "Perez"],
            correct_answer=correct,
        )
        return attempt, question

    def answer_url(self, attempt, question):
        return reverse(
            "trivia:submit-answer",
            kwargs={"attempt_id": attempt.id, "question_id": question.id},
        )

    def submit(self, attempt, question, selected_answer, htmx=True, **extra):
        """POST an answer the way the quiz page does.

        HTMX sets HX-Request on every request it makes, and the view returns
        the feedback partial only for those. Tests that assert on the rendered
        fragment therefore go through this helper; the one test covering the
        no-JavaScript path passes htmx=False.
        """
        headers = {"hx-request": "true"} if htmx else {}
        return self.client.post(
            self.answer_url(attempt, question),
            {"selected_answer": selected_answer},
            headers=headers,
            **extra,
        )


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

    def test_empty_state_when_no_interests(self):
        response = self.client.get(reverse("trivia:interests"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["topics"]), [])


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

    @patch("trivia.services.question_cache.generate_questions")
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

    @patch("trivia.services.question_cache.generate_questions")
    def test_questions_span_multiple_topics(self, mock_generate):
        mock_generate.return_value = self.MOCK_QUESTIONS
        for i in range(5):
            self.make_topic(label=f"Topic {i}")

        self.client.post(reverse("trivia:generate-quiz"))

        topics_used = set(
            Question.objects.values_list("topic__label", flat=True)
        )
        self.assertEqual(len(topics_used), 3)  # TOPICS_PER_QUIZ

    @patch("trivia.services.question_cache.generate_questions")
    def test_get_is_not_allowed(self, mock_generate):
        self.make_topic()
        response = self.client.get(reverse("trivia:generate-quiz"))
        self.assertEqual(response.status_code, 405)

    @patch("trivia.services.question_cache.generate_questions")
    def test_total_failure_deletes_empty_attempt_and_explains(self, mock_generate):
        """The original returned 201 with an empty quiz and no message."""
        mock_generate.side_effect = LLMError("ANTHROPIC_API_KEY is not set.")
        self.make_topic()

        response = self.client.post(reverse("trivia:generate-quiz"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(QuizAttempt.objects.count(), 0)  # no orphan attempt
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("ANTHROPIC_API_KEY" in m for m in messages))

    @patch("trivia.services.question_cache.generate_questions")
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

    @patch("trivia.services.question_cache.generate_questions")
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
        response = self.submit(attempt, question, "Verstappen")
        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)

    def test_incorrect_answer_does_not_increment_score(self):
        attempt, question = self.make_attempt_with_question()
        self.submit(attempt, question, "Hamilton")
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 0)

    def test_resubmitting_does_not_inflate_the_score(self):
        """The bug the original plan had: nothing stopped score farming."""
        attempt, question = self.make_attempt_with_question()
        for _ in range(10):
            self.submit(attempt, question, "Verstappen")
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)
        self.assertEqual(Answer.objects.count(), 1)

    def test_resubmission_shows_previous_answer(self):
        attempt, question = self.make_attempt_with_question()
        self.submit(attempt, question, "Verstappen")
        response = self.submit(attempt, question, "Hamilton")
        self.assertTrue(response.context["already_answered"])
        self.assertEqual(response.context["answer"].selected_answer, "Verstappen")

    def test_answer_not_in_options_is_rejected(self):
        attempt, question = self.make_attempt_with_question()
        response = self.submit(attempt, question, "Nonsense")
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Answer.objects.count(), 0)

    def test_cannot_answer_someone_elses_attempt(self):
        attempt, question = self.make_attempt_with_question(user=self.other)
        response = self.submit(attempt, question, "Verstappen")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Answer.objects.count(), 0)

    def test_cannot_answer_question_from_a_different_attempt(self):
        """The subtler variant: own attempt, foreign question id."""
        my_attempt, _ = self.make_attempt_with_question()
        their_attempt, their_question = self.make_attempt_with_question(
            user=self.other
        )
        response = self.submit(my_attempt, their_question, "Verstappen")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Answer.objects.count(), 0)

    def test_does_not_leak_the_answer_key_for_unanswerable_requests(self):
        """The original returned question.correct_answer to anyone with an id."""
        _, their_question = self.make_attempt_with_question(user=self.other)
        response = self.client.post(
            reverse(
                "trivia:submit-answer",
                kwargs={"attempt_id": 99999, "question_id": their_question.id},
            ),
            {"selected_answer": "Verstappen"},
            headers={"hx-request": "true"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Verstappen", status_code=404)

    def test_feedback_reveals_answer_after_submitting(self):
        """Revealing it *after* a committed answer is correct, not a leak.

        The correct answer here ("Zebra") is deliberately NOT one of the
        options, so a substring search for it is a real leak test rather than
        a match against the visible choice list.
        """
        attempt, question = self.make_attempt_with_question(
            correct="Zebra",
            options=["Alpha", "Beta", "Gamma", "Delta"],
            prompt="Which animal is this?",
        )

        # Before any submission, the answer key must not be on the page.
        quiz_page = self.client.get(reverse("trivia:quiz", args=[attempt.id]))
        self.assertNotContains(quiz_page, "Zebra")

        # Answer *wrong*: that is the case where the correct answer is disclosed.
        response = self.submit(attempt, question, "Alpha")
        self.assertContains(response, "Zebra")

    def test_feedback_does_not_disclose_answer_when_correct(self):
        """A right answer needs no key, and the partial must not print it."""
        attempt, question = self.make_attempt_with_question()
        response = self.submit(attempt, question, "Verstappen")
        self.assertContains(response, "Correct")
        self.assertNotContains(response, "The correct answer was")

    def test_get_is_not_allowed(self):
        attempt, question = self.make_attempt_with_question()
        response = self.client.get(self.answer_url(attempt, question))
        self.assertEqual(response.status_code, 405)

    def test_htmx_request_gets_a_fragment_not_a_redirect(self):
        attempt, question = self.make_attempt_with_question()
        response = self.submit(attempt, question, "Verstappen", htmx=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["answered_count"], 1)
        self.assertEqual(response.context["total_questions"], 1)

    def test_non_htmx_request_redirects_back_to_the_quiz(self):
        """Without JS, the same view must return a real page, not a fragment."""
        attempt, question = self.make_attempt_with_question()
        response = self.submit(attempt, question, "Verstappen", htmx=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(f"/quiz/{attempt.id}/"))

    def test_non_htmx_invalid_answer_redirects_with_a_message(self):
        attempt, question = self.make_attempt_with_question()
        response = self.submit(attempt, question, "Nonsense", htmx=False,
                               follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Answer.objects.count(), 0)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("choose one of the options" in m for m in messages))


# ---------------------------------------------------------------------------
# Completion and results
# ---------------------------------------------------------------------------

class CompleteAttemptTests(BaseUserTestCase):
    def test_completing_sets_timestamp_and_score(self):
        attempt, question = self.make_attempt_with_question()
        self.client.post(
            self.answer_url(attempt, question), {"selected_answer": "Verstappen"}
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
        attempt.refresh_from_db()
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
            self.answer_url(attempt, question), {"selected_answer": "Verstappen"}
        )
        self.client.post(reverse("trivia:complete-attempt", args=[attempt.id]))
        response = self.client.get(reverse("trivia:results", args=[attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["correct"], 1)
        self.assertEqual(response.context["total"], 1)

    def test_total_counts_questions_not_answers(self):
        """An abandoned quiz must not report 1/1 when it was 1/2."""
        attempt, question = self.make_attempt_with_question()
        Question.objects.create(
            user=self.user,
            attempt=attempt,
            topic=question.topic,
            prompt_text="Unanswered?",
            options=["A", "B", "C", "D"],
            correct_answer="A",
        )
        self.client.post(
            self.answer_url(attempt, question), {"selected_answer": "Verstappen"}
        )
        response = self.client.get(reverse("trivia:results", args=[attempt.id]))
        self.assertEqual(response.context["total"], 2)
        self.assertEqual(response.context["answered"], 1)
        self.assertEqual(response.context["unanswered"], 1)

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

    def test_mock_mode_falls_back_for_an_unknown_topic(self):
        from trivia.services import llm_service

        with patch.dict("os.environ", {"WATCHTRIVIA_MOCK_LLM": "True"}):
            questions = llm_service.generate_questions("Knitting", num_questions=1)
        self.assertEqual(len(questions), 1)
        self.assertIn("Knitting", questions[0]["prompt_text"])

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
