from django.contrib import admin

from .models import Answer, InterestTopic, Question, QuizAttempt, WatchHistoryEntry


@admin.register(WatchHistoryEntry)
class WatchHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("video_title", "channel_name", "user", "watched_at")
    list_filter = ("user", "channel_name")
    search_fields = ("video_title", "channel_name")
    date_hierarchy = "watched_at"
    list_select_related = ("user",)
    list_per_page = 50


@admin.register(InterestTopic)
class InterestTopicAdmin(admin.ModelAdmin):
    list_display = ("label", "weight", "user")
    list_filter = ("user",)
    search_fields = ("label",)
    list_editable = ("weight",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "started_at", "completed_at", "score", "is_complete")
    list_filter = ("user", "completed_at")
    date_hierarchy = "started_at"
    readonly_fields = ("started_at", "score")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("prompt_text", "topic", "attempt", "user", "created_at")
    list_filter = ("topic", "attempt")
    search_fields = ("prompt_text", "correct_answer")
    readonly_fields = ("created_at",)
    list_select_related = ("topic", "attempt", "user")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_answer", "is_correct", "answered_at")
    list_filter = ("is_correct", "attempt")
    readonly_fields = ("is_correct", "answered_at")
    list_select_related = ("attempt", "question")
