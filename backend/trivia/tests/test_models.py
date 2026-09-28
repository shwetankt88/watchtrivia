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
            attempt=self.attempt, question=self.question, selected_answer="B"
        )
        Answer.objects.create(
            attempt=retake, question=retake_question, selected_answer="B"
        )

        self.assertEqual(Answer.objects.count(), 2)
        self.assertEqual(
            Answer.objects.filter(is_correct=True).count(), 1
        )


class InterestTopicConstraintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345678")

    def test_same_label_cannot_be_created_twice_for_one_user(self):
        InterestTopic.objects.create(user=self.user, label="F1", weight=0.5)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InterestTopic.objects.create(user=self.user, label="F1", weight=0.4)

    def test_two_users_may_share_a_label(self):
        other = User.objects.create_user(username="bob", password="pw12345678")
        InterestTopic.objects.create(user=self.user, label="F1", weight=0.5)
        InterestTopic.objects.create(user=other, label="F1", weight=0.9)


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
        rendered = str(entry)
        self.assertNotIn("x" * 100, rendered)
        self.assertTrue(rendered.startswith("x" * 50))
        self.assertIn("Some Channel", rendered)
