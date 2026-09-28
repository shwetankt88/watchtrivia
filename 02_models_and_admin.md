# Part 2: Models and the Admin Site

---

## What Are Models?

In Django, a **model** is a Python class that defines the structure of a database table.
Each class attribute is a column. Django's **ORM (Object-Relational Mapper)** translates
between Python objects and SQL — you never write raw SQL.

```
Python Class (Model)          ←→        Database Table
─────────────────────                   ──────────────────
class InterestTopic:                    CREATE TABLE trivia_interesttopic (
    label = CharField()                     id INTEGER PRIMARY KEY,
    weight = FloatField()                   label VARCHAR(100),
    user = ForeignKey()                     weight REAL,
                                             user_id INTEGER REFERENCES auth_user(id)
                                         );
```

### Why Not Write SQL Directly?

| Approach | Pros | Cons |
|----------|------|------|
| Raw SQL | Maximum control, any database feature | Database-specific, error-prone, no migration tracking |
| Django ORM | Database-agnostic, type-safe, auto-migrations | Can't express every query; learning curve |
| SQLAlchemy | More flexible | Not integrated with Django's admin, auth, or templates |

The ORM is right here because it integrates with the admin site, migrations, and
authentication — all features we need.

---

## Designing Watchtrivia's Data

```
┌──────────────┐
│     User     │ (Django's built-in auth_user table)
└──────┬───────┘
       │ one user has...
       │
       ├──── many ──→ WatchHistoryEntry   (one per video watched)
       ├──── many ──→ InterestTopic       (computed from watch history)
       ├──── many ──→ QuizAttempt         (one per quiz session)
       │                     │
       │                     ├──── many ──→ Question    (one per question in that attempt)
       │                     │                    │
       │                     └──── many ──→ Answer    (one per question answered)
       │                                          │
       └──── many ──→ Question (via topic) ───────┘
```

### Entity Definitions

| Model | Purpose | Key Fields |
|-------|---------|------------|
| **WatchHistoryEntry** | Each video from Google Takeout | `video_title`, `channel_name`, `watched_at` |
| **InterestTopic** | A computed interest + weight for a user | `label`, `weight` |
| **QuizAttempt** | One quiz session | `started_at`, `completed_at`, `score` |
| **Question** | An LLM-generated question **within one attempt** | `attempt`, `prompt_text`, `options`, `correct_answer` |
| **Answer** | One submitted answer | `attempt`, `question`, `selected_answer`, `is_correct` |

### Two Design Decisions the Original Plan Got Wrong

The original plan's entity table showed `Question` and `Answer` as siblings hanging off
`User`, with no relationship between a quiz attempt and its questions. That looks
tidier. It is also wrong, and it caused two real bugs. Both fixes are in the model code
below, and both are explained where they appear.

**Problem 1 — questions are not attached to the attempt that contains them.**
The original `Question` model had `user` and `topic`, but no `attempt`. Consequences:

- You can never reconstruct which questions a user was actually shown.
- Questions accumulate forever. Generate a quiz three times, and you have three orphaned
  sets with no way to tell them apart.
- Nothing validates that a submitted `question_id` belongs to the submitted `attempt_id`.
  A user can pair their own attempt with a question from a different attempt — or from a
  topic they no longer have — and the system accepts it.

**Fix:** add `attempt = ForeignKey(QuizAttempt, ...)` to `Question`.

**Problem 2 — nothing stops the same question being answered twice.**
Nothing in the original schema prevents POSTing the same answer repeatedly to the same
attempt. Each submission increments `attempt.score`, so a user could reach an arbitrarily
high score on a six-question quiz. Any scoreboard built on this is meaningless.

**Fix:** a `UniqueConstraint` on `(attempt, question)`, enforced by the database.

---

## Writing the Models

Replace `trivia/models.py` entirely:

```python
from django.conf import settings
from django.db import models


def normalize_answer(value):
    """Normalize an answer string for tolerant comparison.

    Collapses internal whitespace and lowercases, so that "  Red  Bull " and
    "red bull" compare equal. Users retype answers; the LLM may pad them.
    """
    return " ".join(str(value).split()).casefold()


class WatchHistoryEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watch_history",
    )
    video_title = models.CharField(max_length=500)
    channel_name = models.CharField(max_length=255, blank=True)
    watched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-watched_at", "-id"]

    def __str__(self):
        return f"{self.video_title[:50]} ({self.channel_name})"


class InterestTopic(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interests",
    )
    label = models.CharField(max_length=100)
    weight = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-weight"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "label"],
                name="unique_interest_label_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.weight:.2f}) - {self.user}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Attempt by {self.user} on {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def is_complete(self):
        return self.completed_at is not None


class Question(models.Model):
    """A trivia question belonging to one specific quiz attempt."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True,
    )
    topic = models.ForeignKey(
        InterestTopic,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    prompt_text = models.TextField()
    options = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.prompt_text[:60]

    def grades_correctly(self, value):
        """Whether `value` would be accepted as the correct answer for this question."""
        return normalize_answer(value) == normalize_answer(self.correct_answer)


class Answer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    selected_answer = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_answer_per_question_per_attempt",
            ),
        ]

    def __str__(self):
        mark = "correct" if self.is_correct else "wrong"
        return f"{self.question_id}: {self.selected_answer} ({mark})"

    def save(self, *args, **kwargs):
        self.is_correct = (
            normalize_answer(self.selected_answer)
            == normalize_answer(self.question.correct_answer)
        )
        super().save(*args, **kwargs)
```

### `normalize_answer` — a Shared Helper

Notice `Question.grades_correctly()` and `Answer.save()` both need the same comparison
logic. Rather than duplicating `.strip().lower()` in two places, we define
`normalize_answer()` once at the top of the module and call it from both.

`casefold()` is preferred over `lower()` for case-insensitive comparison because it
handles Unicode correctly (German ß, Turkish dotless i).

> [!NOTE]
> The original plan compared with `.strip().lower()` only, so `"Red Bull"` and
> `"Red  Bull"` (two spaces) would be marked wrong. Since the correct answer is generated
> by an LLM and typed by a human, tolerant comparison is worth the two lines.

---

## Line-by-Line Explanation

### The `User` ForeignKey Pattern

```python
user = models.ForeignKey(
    settings.AUTH_USER_MODEL,    # 1
    on_delete=models.CASCADE,    # 2
    related_name="watch_history" # 3
)
```

**Line 1: `settings.AUTH_USER_MODEL`**

Why not `from django.contrib.auth.models import User`? Because if you ever swap Django's
default `User` model for a custom one, every `ForeignKey(User)` in your code breaks.
`settings.AUTH_USER_MODEL` is a string reference (`"auth.User"` by default) that Django
resolves at runtime — it always points to the active User model.

> [!TIP]
> **Always use `settings.AUTH_USER_MODEL`.** This saves you a painful migration later.

**Line 2: `on_delete=models.CASCADE`**

"What happens to this row when its User is deleted?"

| Option | Behavior | When to use |
|--------|----------|-------------|
| `CASCADE` | Delete this row too | Child data meaningless without its parent |
| `PROTECT` | Block the deletion | Data you must never lose |
| `SET_NULL` | Set the FK to NULL | Optional relationships (needs `null=True`) |
| `SET_DEFAULT` | Set a default value | Rare |
| `DO_NOTHING` | Do nothing | Almost never |

We use `CASCADE` throughout: watch history, interests, and attempts are meaningless
without a user.

**Line 3: `related_name="watch_history"`**

Creates a readable reverse relation. Without it you'd write
`user.watchhistoryentry_set.all()`. With it:

```python
entry.user          # forward: child → parent
user.watch_history.all()   # reverse: parent → children
```

### Field Types

| Field | SQL Type | Python Type | When to use |
|-------|----------|-------------|-------------|
| `CharField(max_length=N)` | `VARCHAR(N)` | `str` | Short text with a known max length |
| `TextField()` | `TEXT` | `str` | Long text |
| `IntegerField()` | `INTEGER` | `int` | Whole numbers |
| `FloatField()` | `REAL` | `float` | Approximate numbers (use `DecimalField` for money) |
| `BooleanField()` | `BOOLEAN` | `bool` | True/False flags |
| `DateTimeField()` | `DATETIME` | `datetime` | Timestamps |
| `JSONField()` | `JSON` | `dict` or `list` | Flexible structured data |
| `ForeignKey()` | `INTEGER + FK` | Model instance | Many-to-one relationship |

### Field Options

| Option | Meaning | Example |
|--------|---------|---------|
| `blank=True` | Field may be empty **in forms** | `channel_name = CharField(blank=True)` |
| `null=True` | Column allows **NULL in the database** | `watched_at = DateTimeField(null=True)` |
| `default=X` | Default when none provided | `score = IntegerField(default=0)` |
| `auto_now_add=True` | Set on creation, never changes | `created_at` |
| `auto_now=True` | Set on every save | `updated_at` |

> [!WARNING]
> **`blank` and `null` are different things.**
> - `blank=True` → validation only (forms accept empty strings)
> - `null=True` → database only (column allows NULL)
> - For `CharField`, use `blank=True` alone
> - For `DateTimeField` and `ForeignKey`, use both `null=True, blank=True`

### Why `Question.attempt` Is Nullable

```python
attempt = models.ForeignKey(QuizAttempt, ..., null=True, blank=True)
```

If it were non-null, you could not save a `Question` before its `QuizAttempt` exists. In
Part 4 the attempt is always created first, so in practice this will always be set — but
`null=True` means the admin site and the shell can create a question standalone, and it
means adding the field later to a populated database does not require a default value.

> [!IMPORTANT]
> Nullable means a question *can* exist without an attempt. Your **views** must therefore
> scope by `attempt` explicitly rather than assuming every question has one. Part 4 does
> this, and Part 7 tests it.

### The `Meta` Inner Class and Constraints

`Meta` configures table-level behaviour, not column-level.

| Option | Purpose | Example |
|--------|---------|---------|
| `ordering` | Default sort order | `["-weight"]` |
| `verbose_name` | Human-readable singular name | `"watch history entry"` |
| `unique_together` | Compound unique constraint | `[("user", "label")]` |
| `constraints` | Advanced constraints, incl. `UniqueConstraint` | see below |
| `db_table` | Override the table name | `"my_custom_table"` |

We use `UniqueConstraint` rather than `unique_together` because it supports a `name=`
argument. A named constraint produces a readable database error message
(`duplicate key value violates unique constraint "unique_answer_per_question_per_attempt"`)
and a readable entry in `python manage.py showmigrations`, whereas an unnamed
`unique_together` produces an opaque auto-generated name.

> [!NOTE]
> `UniqueConstraint` on `(user, label)` for `InterestTopic` also protects against
> duplicate interests. Since views call `.delete()` before re-creating topics on each
> upload, this should never fire — which is exactly why it is worth having. It turns a
> latent race condition into a loud error instead of silent duplicate rows.

### The `__str__` Method

```python
def __str__(self):
    return f"{self.video_title[:50]} ({self.channel_name})"
```

Controls how the object appears in the admin list views, the Django shell, debugging
output, and ForeignKey dropdowns. Without it you'd see `WatchHistoryEntry object (1)`.

### Overriding `save()` — Business Logic in the Model

```python
def save(self, *args, **kwargs):
    self.is_correct = (
        normalize_answer(self.selected_answer)
        == normalize_answer(self.question.correct_answer)
    )
    super().save(*args, **kwargs)
```

Every time an `Answer` is saved, `is_correct` is recomputed. The caller never has to
remember to check correctness.

> [!IMPORTANT]
> **Always call `super().save()`** in your override, or the object is never written to
> the database. Forwarding `*args, **kwargs` keeps Django's internal flags (like
> `update_fields`) working.

> [!WARNING]
> This pattern has a real cost worth knowing: `self.question.correct_answer` triggers a
> database query on **every** save, because Django does not cache a reverse relation you
> have not accessed. For a six-question quiz that is irrelevant. For a 10,000-row
> `bulk_create` it is 10,000 extra queries. Part 4 uses `bulk_create` for
> `WatchHistoryEntry` (no `save()` override, so no problem) and saves `Answer` objects
> one at a time, which is correct here.
>
> It also means `Answer.objects.update(is_correct=True)` bypasses the override
> entirely. Never bulk-update `is_correct`.

### Properties

```python
@property
def is_complete(self):
    return self.completed_at is not None
```

A `@property` is a computed attribute that behaves like a field for reading but is not
stored in the database and cannot be filtered on. Use it for derived values that are
cheap to compute. If a property is expensive, store it as a real field instead.

---

## Register the App

Django does not know about `trivia` until you register it in
`watchtrivia/settings.py`:

```python
INSTALLED_APPS = [
    "django.contrib.admin",          # The admin site
    "django.contrib.auth",           # User authentication
    "django.contrib.contenttypes",   # Framework for content types
    "django.contrib.sessions",       # Session management
    "django.contrib.messages",       # Flash messages
    "django.contrib.staticfiles",    # Serving CSS/JS/images

    # Our apps
    "trivia",                        # The Watchtrivia app
]
```

> [!NOTE]
> There is no `rest_framework` and no `corsheaders` here. Both existed in the original
> plan purely to support the separate React frontend. Part 10 adds `rest_framework` back
> if you decide you want a JSON API.

### What Does Registering an App Actually Do?

When Django starts, it iterates `INSTALLED_APPS` and for each one:

1. Imports the app's `apps.py` configuration
2. Discovers `models.py` and registers the models with the ORM
3. Discovers `admin.py` and registers admin classes
4. Discovers `migrations/` for schema tracking
5. Makes the app's `templates/` and `static/` directories findable

Skip this and your models, admin registrations, and migrations are invisible.

---

## Migrations — Version Control for Your Database

### What Are Migrations?

Every time you change a model, Django needs to update the database schema. **Migrations**
are Python files describing those changes.

### Step 1: Generate

```bash
python manage.py makemigrations trivia
```

### Step 2: Apply

```bash
python manage.py migrate
```

### The Workflow

```
1. Edit models.py
        ↓
2. python manage.py makemigrations
   → Generates trivia/migrations/0001_initial.py
        ↓
3. Review the generated file (recommended)
        ↓
4. python manage.py migrate
   → Executes the SQL against the database
        ↓
5. Commit BOTH models.py AND the migration file
```

> [!IMPORTANT]
> **Always commit migration files to Git.** They are not build artifacts — they are the
> source of truth for your schema history. Your production server needs them.

### Useful Migration Commands

| Command | Purpose |
|---------|---------|
| `makemigrations` | Generate new migrations |
| `migrate` | Apply all pending migrations |
| `showmigrations` | List all migrations and their status |
| `sqlmigrate trivia 0001` | Show the SQL a migration would run |
| `migrate trivia 0001` | Roll back to a specific point |
| `makemigrations --check` | Exit non-zero if changes are unmigrated (good for CI) |

### What `0001_initial.py` Looks Like

```python
class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="QuizAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("score", models.IntegerField(default=0)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quiz_attempts",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        # ... more CreateModel operations
    ]
```

### Adding a Constraint to an Existing Model

Our `Answer` model has a `UniqueConstraint`. If you added it to a model that already has
rows, Django will ask you to name a one-off constraint to resolve duplicates:

```bash
python manage.py makemigrations trivia
# You are trying to add a unique constraint named
# "unique_answer_per_question_per_attempt" on trivia.Answer, but the
# migration will not work if there are duplicate rows.
#
# 1. Generate a migration to create the model's constraints
# 2. Generate a one-off migration to delete duplicates
```

In a fresh project with no data this never comes up. In production it does, and you want
to know about it early rather than at deploy time.

---

## The Admin Site

Django's admin gives you full CRUD for every registered model, for free. This is one of
Django's best features.

### Register Models

Replace `trivia/admin.py`:

```python
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
```

### Admin Options Explained

| Option | What it does |
|--------|--------------|
| `list_display` | Columns in the list view |
| `list_filter` | Sidebar filters for narrowing results |
| `search_fields` | Fields searchable via the search box |
| `list_per_page` | Rows per page (default 100) |
| `readonly_fields` | Fields that cannot be edited |
| `ordering` | Default sort order |
| `list_editable` | Fields editable directly in the list view |
| `date_hierarchy` | Date-based drill-down navigation |
| `list_select_related` | Fields to prefetch — **fewer database queries per row** |

> [!TIP]
> `list_select_related` is the admin's biggest performance lever. The admin list view
> renders 100 rows by default; without `list_select_related`, each `ForeignKey`
> displayed in `list_display` triggers a separate query, so one page can issue 300+
> queries. With it, Django fetches the related rows in a single join. The Django admin
> displays a query count in the header — use it.

### The `@admin.register` Decorator

```python
# Style 1: decorator (preferred)
@admin.register(WatchHistoryEntry)
class WatchHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("video_title",)

# Style 2: explicit registration
class WatchHistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("video_title",)
admin.site.register(WatchHistoryEntry, WatchHistoryEntryAdmin)
```

### Create a Superuser

```bash
python manage.py createsuperuser
```

Then run the server and visit `http://localhost:8000/admin/`.

> [!TIP]
> The admin is for **you** — the developer or operator. End users interact through the
> normal site at `http://localhost:8000/`. Part 6 wires up a real login page so those
> users are not limited to superusers.

---

## Playing with the ORM in the Shell

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User
from trivia.models import InterestTopic, QuizAttempt, Question

user = User.objects.create_user(username="test", password="test123")

topic = InterestTopic.objects.create(user=user, label="Formula 1", weight=0.85)
InterestTopic.objects.all()
# <QuerySet [<InterestTopic: Formula 1 (0.85) - test>]>

InterestTopic.objects.filter(weight__gte=0.5)
user.interests.all()

topic.weight = 0.9
topic.save()
topic.delete()
```

### Common ORM Query Patterns

| Pattern | Code | SQL Equivalent |
|---------|------|----------------|
| Get all | `Model.objects.all()` | `SELECT * FROM table` |
| Filter | `Model.objects.filter(field=val)` | `SELECT * WHERE field = val` |
| Exclude | `Model.objects.exclude(field=val)` | `SELECT * WHERE field != val` |
| Get one | `Model.objects.get(id=1)` | `SELECT * WHERE id = 1 LIMIT 1` |
| Count | `Model.objects.count()` | `SELECT COUNT(*) FROM table` |
| Order by | `Model.objects.order_by("-field")` | `SELECT * ORDER BY field DESC` |
| Exists | `Model.objects.filter(...).exists()` | `SELECT EXISTS(...)` |
| First | `Model.objects.first()` | `SELECT * LIMIT 1` |
| Create | `Model.objects.create(**kwargs)` | `INSERT` |
| Bulk create | `Model.objects.bulk_create([...])` | One batched `INSERT` |

### Field Lookups (the `__` Syntax)

| Lookup | Meaning | Example |
|--------|---------|---------|
| `__exact` | Exact match (default) | `filter(label__exact="F1")` |
| `__iexact` | Case-insensitive exact | `filter(label__iexact="f1")` |
| `__contains` | Contains substring | `filter(label__contains="F1")` |
| `__icontains` | Case-insensitive contains | `filter(label__icontains="f1")` |
| `__gt` / `__gte` | Greater than / or equal | `filter(weight__gte=0.5)` |
| `__lt` / `__lte` | Less than / or equal | `filter(weight__lt=0.5)` |
| `__in` | In a list | `filter(id__in=[1, 2, 3])` |
| `__range` | Between two values | `filter(weight__range=(0.3, 0.8))` |
| `__isnull` | Is NULL | `filter(watched_at__isnull=True)` |

### Chaining Lookups Across Relationships

```python
# Questions belonging to a completed attempt of this user
Question.objects.filter(attempt__user=user, attempt__completed_at__isnull=False)

# Answers the user got wrong
Answer.objects.filter(attempt__user=user, is_correct=False)

# Interests for which at least one question was generated
InterestTopic.objects.filter(questions__isnull=False).distinct()
```

> [!NOTE]
> Always use `.distinct()` when reverse relations could produce duplicate rows. Joining
> across a one-to-many relation multiplies the result set, and without `distinct()` you
> get the same `InterestTopic` back several times.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Model** | Python class mapping to a database table |
| **Field** | Class attribute mapping to a column |
| **ForeignKey** | Many-to-one relationship between tables |
| **`related_name`** | Readable name for the reverse relation |
| **`UniqueConstraint`** | Database-enforced uniqueness, optionally named |
| **Migration** | Versioned, reviewable schema change |
| **`makemigrations` / `migrate`** | Generate / apply schema changes |
| **Admin site** | Built-in CRUD UI |
| **`__str__`** | How an object displays as text |
| **`save()` override** | Compute derived data on every save |
| **`@property`** | Computed attribute, not stored, not filterable |
| **QuerySet** | Lazy, chainable database query builder |

---

**→ Continue to [Part 3: Services — Parsing, Ranking, and the LLM](./03_services.md)**
