from django.urls import path

from . import auth_views, views

app_name = "trivia"

urlpatterns = [
    # The root is the pitch, not the app: a signed-out visitor who lands on a
    # login redirect has no idea what this is.
    path("", auth_views.landing, name="landing"),
    path("dashboard/", auth_views.dashboard, name="dashboard"),
    path("interests/", views.interests, name="interests"),
    path("upload/", views.upload_history, name="upload"),
    path("generate-quiz/", views.generate_quiz, name="generate-quiz"),
    path("quiz/<int:attempt_id>/", views.quiz, name="quiz"),
    path(
        "quiz/<int:attempt_id>/answer/<int:question_id>/",
        views.submit_answer,
        name="submit-answer",
    ),
    path(
        "quiz/<int:attempt_id>/complete/",
        views.complete_attempt,
        name="complete-attempt",
    ),
    path("results/<int:attempt_id>/", views.results, name="results"),
]
