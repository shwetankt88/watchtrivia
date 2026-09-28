# Watchtrivia — The Complete Tutorial

## Part 1: Introduction & Project Setup

---

### What is Watchtrivia?

Watchtrivia is a web application that:

1. Accepts a user's **YouTube watch history** (exported via Google Takeout)
2. **Analyzes** that history to identify their top interests
3. Uses an **LLM (Claude)** to generate personalized trivia questions
4. Lets the user **take a quiz** and tracks their score

By the end of this tutorial you will have built:

| Layer | Technology | What it does |
|-------|-----------|--------------|
| **Backend** | Django | Models, business logic, auth, admin panel, template rendering |
| **Frontend** | Django Templates + HTMX | Server-rendered UI with dynamic updates, no build step |
| **AI** | Anthropic Claude API | Trivia question generation |
| **Database** | SQLite (dev) → PostgreSQL (prod) | Persistent storage |

That's it. **Three Python packages, no Node.js, no build tooling, no CORS.**

---

### Why This Plan Looks Different From The Original

This tutorial was originally written with Django REST Framework and a React SPA. That
version was archived, and this one replaces it. The reasons are worth stating up front,
because they shape every decision that follows:

**1. The React version had no way for a user to log in.**
Parts 4–7 enforced `IsAuthenticated` on every endpoint, but no login endpoint was ever
built. The only documented way in was "log in through `/admin/` first." The app was
demoable by you and unusable by anyone else. Server-rendered Django gets
`/accounts/login/` from `django.contrib.auth` in **one line of config**.

**2. Splitting the frontend into a separate origin created problems that then had to be
solved.** Different port means different origin means CORS headers, credentialed
requests, CSRF tokens in custom headers, a second dev server to keep running, and a
production deployment that needs two hosts. None of that work buys you anything for an
app that is private, logged-in, and has four pages.

**3. The security guidance contradicted the code.** The original plan spent a section
warning that viewsets must scope queries to `request.user`, then shipped an
answer-submission view that did not. It also exposed the answer key to any authenticated
user. This version fixes those holes rather than warning about them.

**4. It promised things it never built.** A background task queue and a
TF-IDF/K-Means clustering upgrade appeared in the stack table and were never implemented.
This plan only lists what it actually builds. The clustering idea is preserved as a
clearly-labelled optional extension in [Part 3](./03_services.md) instead of a promise.

What is *kept* from the original: the service-layer pattern, the model design, the parser
and ranker, the `save()` override for auto-scoring, the admin site, and the testing
discipline. Those were good.

---

### What You Will Learn

#### Backend Development (Django)
- How Django's **MTV (Model-Template-View)** architecture works and how it compares to MVC
- **ORM (Object-Relational Mapping)** — how Python classes become database tables
- **Migrations** — version control for your database schema
- **The Admin Site** — Django's built-in CRUD interface
- **Forms** — validation, CSRF protection, and error rendering
- **The service layer pattern** — keeping business logic out of views
- **Testing** — unit tests, integration tests, view tests
- **Security** — user data isolation, input validation, secret management

#### Frontend (Templates + HTMX)
- **Server-rendered HTML** — the default Django way, and why it suits this app
- **HTMX** — adding interactivity by swapping HTML fragments over `fetch()`
- **Partial templates** — reusable pieces of markup rendered server-side
- **Progressive enhancement** — a working app without JavaScript

#### Full-Stack Thinking
- Why **separation of concerns** beats **separation of processes**
- How **sessions and cookies** authenticate a browser
- How to **deploy** a single Django app

---

### Prerequisites

Before starting, ensure you have:

| Tool | Minimum Version | Check Command | Purpose |
|------|----------------|---------------|---------|
| Python | 3.11+ | `python3 --version` | Backend runtime |
| pip | Latest | `pip --version` | Python package manager |
| Git | Any | `git --version` | Version control |
| A text editor | — | — | VS Code recommended |

You'll also need an **Anthropic API key** for Claude. Sign up at
[console.anthropic.com](https://console.anthropic.com).

> [!NOTE]
> **No Node.js required.** This is the single biggest practical difference from the
> original plan. If you were told to install Node 18+ and npm 9+, ignore that.

---

### Understanding the Architecture Before We Start

```
┌──────────────────────────────────────────────────────────────┐
│                      THE USER'S BROWSER                       │
│                                                              │
│   Full page load, or an HTMX fragment swap. Either way the   │
│   server returns finished HTML.                              │
└───────────────────────────┬──────────────────────────────────┘
                            │  HTTP (same origin, same port)
                            │  cookies carry the session
┌───────────────────────────▼──────────────────────────────────┐
│                    Django Application                        │
│                       (port 8000)                             │
│                                                              │
│   ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│   │  URL Conf   │──▶│    Views     │──▶│     Forms        │  │
│   │  (routing)  │   │ (endpoints)  │   │ (validate input) │  │
│   └─────────────┘   └──────┬───────┘   └──────────────────┘  │
│                            │                                 │
│                     ┌──────▼───────┐                         │
│                     │   Services   │                         │
│                     │ (biz logic)  │                         │
│                     └──────┬───────┘                         │
│                            │                                 │
│   ┌─────────────┐   ┌──────▼───────┐   ┌──────────────────┐  │
│   │  Templates  │◀──│    Models    │   │    Admin Site    │  │
│   │    (HTML)   │   │  (ORM/data)  │   │    (built-in)    │  │
│   └─────────────┘   └──────┬───────┘   └──────────────────┘  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                     ┌──────▼───────┐
                     │   Database   │
                     │   (SQLite)   │
                     └──────────────┘
```

One process. One port. One origin. No CORS, because there is no second origin.

#### Why Server-Rendered Instead of a Separate SPA?

| Concern | Django templates + HTMX | Separate React SPA |
|---------|------------------------|--------------------|
| **Languages to maintain** | Python, HTML, CSS | Python, JS, HTML, CSS |
| **Dev servers to run** | 1 | 2 |
| **CORS configuration** | Not needed | Required, and easy to misconfigure |
| **CSRF handling** | `{% csrf_token %}` | Read cookie, set header, handle errors |
| **Auth** | `@login_required`, built-in login page | Custom endpoints, token storage |
| **Build step** | None | npm install, bundler, dev server |
| **Deployment** | One container | Two hosts or a reverse proxy |
| **Works without JS** | Yes | No — blank page |
| **Suits live/real-time UI** | Awkward | Excellent |
| **Suits a 4-page logged-in app** | Excellent | Overkill |

A SPA earns its complexity when there is heavy client-side state, real-time collaboration,
offline support, or a public unauthenticated surface. Watchtrivia has none of those. It
has four pages behind a login.

> [!TIP]
> If you later need the same backend to serve a mobile app or a third-party client,
> [Part 10](./10_optional_drf_api.md) adds a JSON API. The backend work in Parts 1–7 is
> identical either way — which is the point of putting the logic in a service layer.

#### What Is HTMX?

HTMX is a ~14kb JavaScript library that lets you make a request and swap the returned HTML
into the page, using plain HTML attributes:

```html
<button hx-post="/submit-answer/" hx-target="#feedback" hx-swap="innerHTML">
  Submit
</button>
```

Click it, HTMX posts the form, Django returns a small HTML fragment, and HTMX drops that
fragment into `#feedback`. The server stays the source of truth. You write no client-side
state machine, no JSON parsing, no rendering logic.

---

### Projects vs. Apps — Django's Organizational Model

- A **project** is the entire site — it holds `settings.py`, the root URL configuration,
  and the WSGI/ASGI entry point. You have **one**.
- An **app** is a self-contained module that does one thing. A project contains **many
  apps**, and in theory you could copy `trivia` into another Django project and it would
  work.

```
watchtrivia/                    ← the project root
├── backend/
│   ├── manage.py               ← Django's command-line utility
│   ├── .env                    ← secrets (git-ignored)
│   ├── watchtrivia/            ← the project package
│   │   ├── __init__.py
│   │   ├── settings.py         ← all configuration
│   │   ├── urls.py             ← root URL routing
│   │   ├── wsgi.py
│   │   └── asgi.py
│   └── trivia/                 ← our app
│       ├── __init__.py
│       ├── admin.py            ← admin registrations
│       ├── apps.py
│       ├── models.py           ← database models
│       ├── views.py            ← request handlers
│       ├── forms.py            ← input validation
│       ├── urls.py             ← app-level routing
│       ├── services/           ← business logic
│       │   ├── __init__.py
│       │   ├── takeout_parser.py
│       │   ├── interest_ranker.py
│       │   └── llm_service.py
│       ├── templates/
│       │   └── trivia/
│       │       ├── base.html
│       │       ├── login.html
│       │       ├── upload.html
│       │       ├── interests.html
│       │       ├── quiz.html
│       │       ├── results.html
│       │       └── partials/
│       │           ├── question_card.html
│       │           └── interest_list.html
│       ├── static/trivia/
│       │   └── style.css
│       ├── tests/              ← test suite
│       │   ├── __init__.py
│       │   ├── test_takeout_parser.py
│       │   ├── test_interest_ranker.py
│       │   ├── test_models.py
│       │   └── test_views.py
│       └── migrations/
│           └── __init__.py
├── sample-data/
│   └── watch-history.json      ← sample data so you can test offline
└── .gitignore
```

> [!IMPORTANT]
> The `services/` directory is **not** a Django convention — it is a design pattern we
> are choosing. Django's official tutorial puts logic directly in views. That works for
> small apps, but Watchtrivia has parsing, ranking, and LLM calls. Stuffing all of that
> into views would make them bloated and impossible to test without making HTTP requests.

---

### Step 1: Create the Project Directory

```bash
mkdir watchtrivia/backend
cd watchtrivia/backend
```

### Step 2: Create a Virtual Environment

A **virtual environment** is an isolated Python installation. Without it, every project on
your machine shares the same packages — upgrading one project's Django can break another's.

```bash
python3 -m venv .venv
```

Activate it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (Command Prompt)
.venv\Scripts\activate.bat
```

> [!TIP]
> You will know it is active when your prompt starts with `(.venv)`. **Every new terminal
> needs it activated again.** Every `pip install` and `python` command below assumes it is.

#### What is inside `.venv/`?

```
.venv/
├── lib/python3.x/site-packages/   ← where pip installs packages
├── bin/                            ← python, pip, activate scripts
└── pyvenv.cfg                      ← marks this as a virtual environment
```

When you run `python` with the venv active, it uses `.venv/bin/python` instead of your
system Python. When you `pip install django`, it lands in
`.venv/lib/python3.x/site-packages/django/`, not your global site-packages.

> [!WARNING]
> Never commit `.venv/` to Git. It is large and platform-specific. Commit
> `requirements.txt` instead — you will create it in Step 4.

### Step 3: Install Dependencies

```bash
pip install django python-dotenv anthropic
```

Three packages. Here is why each one exists:

| Package | Purpose | Why it is unavoidable |
|---------|---------|----------------------|
| `django` | The web framework — models, ORM, admin, auth, templates, migrations | You cannot build this app without it |
| `python-dotenv` | Loads `.env` files into environment variables | So your API key isn't hardcoded in source |
| `anthropic` | Official Python SDK for the Claude API | So you don't hand-roll HTTPS requests and JSON |

That is the entire dependency list. No `djangorestframework`, no `django-cors-headers`, no
`scikit-learn`, no Celery, no Redis — because this plan does not build a JSON API, does
not serve a second origin, and does not cluster anything.

> [!NOTE]
> The original plan installed `scikit-learn` and never used it, and listed Celery and
> Redis in its stack table without ever implementing either. That is the kind of drift
> this rewrite is trying to eliminate.

### Step 4: Freeze Your Dependencies

```bash
pip freeze > requirements.txt
```

```
Django==6.1
anthropic==0.x.y
python-dotenv==1.x.y
```

Anyone can now run `pip install -r requirements.txt` and get the exact same versions.

### Step 5: Create the Django Project

```bash
django-admin startproject watchtrivia .
```

**The trailing `.` is critical.**

```
# WITHOUT the dot — creates nested directories (annoying)
backend/
└── watchtrivia/
    ├── manage.py
    └── watchtrivia/
        └── settings.py

# WITH the dot — flat structure (what we want)
backend/
├── manage.py
└── watchtrivia/
    └── settings.py
```

#### What did `startproject` create?

| File | Purpose |
|------|---------|
| `manage.py` | Django's CLI. `runserver`, `migrate`, `test`, `createsuperuser`, and more |
| `watchtrivia/__init__.py` | Makes the directory a Python package (can be empty) |
| `watchtrivia/settings.py` | **The most important file.** All configuration lives here |
| `watchtrivia/urls.py` | Root URL configuration — the table of contents |
| `watchtrivia/wsgi.py` | Web Server Gateway Interface entry point, for Gunicorn/uWSGI |
| `watchtrivia/asgi.py` | Asynchronous entry point, for WebSockets and async views |

#### Deep Dive: How `manage.py` Works

When you run `python manage.py runserver`:

1. Python executes `manage.py`
2. It sets the `DJANGO_SETTINGS_MODULE` environment variable to `watchtrivia.settings`
3. It calls `django.core.management.execute_from_command_line()`
4. Django loads settings, discovers apps, and runs the command
5. For `runserver`, it starts a development HTTP server on port 8000

> [!CAUTION]
> `manage.py runserver` is a **development server only**. It is single-threaded, not
> security-hardened, and restarts on code changes. Never use it in production.
> Production uses Gunicorn — covered in [Part 9](./09_running_and_next_steps.md).

### Step 6: Create the Trivia App

```bash
python manage.py startapp trivia
```

| File | Purpose |
|------|---------|
| `trivia/__init__.py` | Makes it a Python package |
| `trivia/admin.py` | Where you register models with the admin |
| `trivia/apps.py` | App configuration |
| `trivia/models.py` | Database models |
| `trivia/views.py` | Request handlers |
| `trivia/tests.py` | We will replace this with a `tests/` package in Part 7 |
| `trivia/migrations/` | Auto-generated schema changes |

> [!NOTE]
> **Don't name your app `quiz`.** It collides with a known PyPI package name and causes
> confusing import errors. `trivia` avoids the problem entirely.

### Step 7: Create the Directory Scaffold

Django only creates `apps.py`, `models.py`, `tests.py`, `views.py`, and `migrations/`. You
need a few more:

```bash
mkdir trivia/services
mkdir trivia/templates/trivia/partials
mkdir trivia/static/trivia
mkdir trivia/tests
```

Then create empty `__init__.py` files:

```bash
touch trivia/services/__init__.py
touch trivia/tests/__init__.py
```

On Windows PowerShell, use `New-Item -ItemType File` instead of `touch`.

### Step 8: Verify the Installation

```bash
python manage.py runserver
```

Visit `http://localhost:8000/`. You should see Django's rocket page reading
"The install worked successfully!"

Press `Ctrl+C` to stop the server.

### Step 9: Create `.gitignore`

In the project root (`watchtrivia/`):

```gitignore
# Python
.venv/
venv/
__pycache__/
*.py[cod]
*.egg-info/

# Database
db.sqlite3
db.sqlite3-journal
*.sqlite3

# Environment
.env
*.env

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

> [!NOTE]
> There is no `node_modules/` or `dist/` here, because there is no Node.

### Step 10: Create the `.env` File

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=your-key-here
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
ANTHROPIC_MODEL=claude-sonnet-4-6
WATCHTRIVIA_MOCK_LLM=False
```

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `DJANGO_SECRET_KEY` | Django's master signing secret |
| `DEBUG` | `True` in development, `False` in production |
| `ANTHROPIC_MODEL` | Which Claude model to call. Currently `claude-sonnet-4-6` |
| `WATCHTRIVIA_MOCK_LLM` | Set `True` to generate fake questions without an API key |

> [!IMPORTANT]
> **`WATCHTRIVIA_MOCK_LLM` is not in the original plan and it matters.** Without it, you
> cannot exercise the upload → generate → answer flow at all until you have a working API
> key and a funded account. With it, the entire application is testable offline, and your
> LLM tests never make billable network calls. We build it in Part 3.

> [!WARNING]
> **Never commit `.env` to Git.** The `.gitignore` above excludes it. If you accidentally
> commit it, rotate your keys immediately.

### Step 11: Create Sample Data

You do not need a real Google Takeout export to develop this app. A small sample file lets
you test the whole flow immediately:

```bash
mkdir -p ../sample-data
```

Then create `sample-data/watch-history.json` — the full contents are given in
[Part 3](./03_services.md#the-raw-takeout-format). It contains 24 entries across 6
channels, so the ranker has something meaningful to rank.

---

### Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Virtual environment** | Isolated Python installation per project |
| **`requirements.txt`** | Pinned dependency versions for reproducibility |
| **`manage.py`** | Django CLI — run server, make migrations, run tests |
| **Project** | Top-level configuration (settings, root URLs) |
| **App** | Self-contained feature module (models, views, URLs, templates) |
| **`settings.py`** | Single source of truth for all Django config |
| **Server-rendered** | Django returns finished HTML rather than JSON |
| **HTMX** | Swap HTML fragments over `fetch()` using HTML attributes |

---

**→ Continue to [Part 2: Models and the Admin Site](./02_models_and_admin.md)**
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
# Part 3: Services — Parsing, Ranking, and the LLM

---

## The Service Layer Pattern

Django's default architecture puts logic in **views**. That works for small apps, but
Watchtrivia has three distinct pieces of business logic:

1. **Parsing** YouTube Takeout data
2. **Ranking** user interests from watch history
3. **Generating** quiz questions via an LLM

Stuffed into views, each view would be hundreds of lines and impossible to test without
making HTTP requests. The **service layer pattern** solves this:

```
┌─────────────────┐         ┌───────────────────┐         ┌──────────────┐
│   View (thin)   │ ──────→ │  Service (logic)  │ ──────→ │  Model (data)│
│ Handles HTTP    │         │ Pure Python       │         │ Database ORM │
│ request/response│         │ Independently     │         │              │
│                 │         │ testable          │         │              │
└─────────────────┘         └───────────────────┘         └──────────────┘
```

**The rule: Views handle HTTP. Services handle logic. Models handle data.**

> [!IMPORTANT]
> A service should not import from `django.db`, `django.http`, or `django.shortcuts`.
> If `takeout_parser.py` needs a database query, the logic is in the wrong place. This
> constraint is what makes the services testable in milliseconds with no database, no
> server, and no Django test runner.

### The Package

`trivia/services/` contains:

| File | Responsibility | Django imports? |
|------|----------------|-----------------|
| `__init__.py` | Empty — makes it a package | No |
| `takeout_parser.py` | Takeout JSON → list of dicts | **No** |
| `interest_ranker.py` | Watch entries → ranked topics | **No** |
| `llm_service.py` | Topic label → generated questions | **No** |

Zero Django imports in all three. That is a design constraint, not a coincidence.

---

## Service 1: Parsing Google Takeout Data

### What is Google Takeout?

Google Takeout (`takeout.google.com`) exports your data from any Google service. For
YouTube, the watch history comes as JSON (`watch-history.json`) or as a set of per-month
files (`watch-history/watch-history-2024-12.json`). **This tutorial handles the single
combined file.** The per-month variant is an array of arrays rather than an array of
objects, and needs a one-line flattening change — noted at the end of this section.

### The Raw Takeout Format

```json
[
  {
    "header": "YouTube",
    "title": "Watched Max Verstappen's Incredible Overtake",
    "titleUrl": "https://www.youtube.com/watch?v=abc123",
    "subtitles": [
      { "name": "F1 Official", "url": "https://www.youtube.com/channel/UCB_..." }
    ],
    "time": "2024-12-15T14:30:00.000Z",
    "products": ["YouTube"]
  },
  {
    "header": "YouTube",
    "title": "Watched How Black Holes Really Work",
    "titleUrl": "https://www.youtube.com/watch?v=def456",
    "subtitles": [
      { "name": "Veritasium", "url": "https://www.youtube.com/channel/UCD..." }
    ],
    "time": "2024-12-14T10:15:00.000Z"
  },
  {
    "header": "YouTube",
    "title": "Watched [Deleted video]",
    "subtitles": [{ "name": "Some Channel" }]
  },
  {
    "header": "YouTube",
    "title": "Visited the YouTube homepage",
    "titleUrl": "https://www.youtube.com/?gl=US&hl=en"
  }
]
```

Notice the last two entries. Real Takeout exports contain **ads, deleted videos, and
non-video activity**. The parser must filter them out.

### The Parser

`trivia/services/takeout_parser.py`:

```python
"""Parse Google Takeout YouTube watch history exports.

Pure Python — no Django imports. Raise TakeoutParseError on anything the
caller is expected to handle; let genuinely unexpected bugs propagate.
"""

import json
from datetime import datetime, timezone

# Google prefixes every real video title with "Watched ".
TITLE_PREFIX = "Watched "

# Only these URL shapes correspond to an actual watched video.
VIDEO_URL_MARKER = "watch?v="


class TakeoutParseError(Exception):
    """Raised when an uploaded file is not a usable Takeout export."""


def parse_takeout_json(file_obj):
    """Parse a Google Takeout watch-history.json file.

    Args:
        file_obj: A file-like object (from request.FILES or open()).

    Returns:
        A list of dicts, each with keys:
            video_title (str)
            channel_name (str)  — may be ""
            watched_at   (datetime | None)  — timezone-aware UTC, or None

    Raises:
        TakeoutParseError: The file is not valid JSON, is not a list, or
            contains no usable video entries.
    """
    try:
        raw_data = json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise TakeoutParseError(
            f"That file is not valid JSON (problem at character {exc.pos}). "
            "Make sure you upload the watch-history.json from your Takeout archive."
        ) from exc
    except UnicodeDecodeError as exc:
        raise TakeoutParseError(
            "That file is not UTF-8 text. Takeout exports are always JSON, "
            "so an archive you extracted without a JSON file is the usual cause."
        ) from exc

    if not isinstance(raw_data, list):
        raise TakeoutParseError(
            "Expected a JSON list of watch-history entries at the top level, "
            f"but found {type(raw_data).__name__}."
        )

    entries = []
    for item in raw_data:
        if not isinstance(item, dict):
            continue

        title_url = item.get("titleUrl") or ""
        # Ads, deleted videos, and homepage visits have no watch?v= URL.
        if VIDEO_URL_MARKER not in title_url:
            continue

        title = _clean_title(item.get("title", ""))
        if not title:
            continue

        entries.append(
            {
                "video_title": title,
                "channel_name": _extract_channel(item),
                "watched_at": _parse_timestamp(item.get("time")),
            }
        )

    if not entries:
        raise TakeoutParseError(
            "No YouTube videos found in that file. Make sure it is the "
            "watch-history.json from your Google Takeout export, not your "
            "subscriptions, comments, or search history."
        )

    return entries


def parse_takeout_monthly_json(file_obj):
    """Parse the per-month Takeout layout, which nests one list inside another.

    Google exports either a flat array (newer) or an array of per-month
    arrays (older, still common). This handles the older shape.
    """
    try:
        raw_data = json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise TakeoutParseError(f"That file is not valid JSON: {exc}") from exc

    if not isinstance(raw_data, list):
        raise TakeoutParseError("Expected a JSON list at the top level.")

    flattened = []
    for chunk in raw_data:
        if isinstance(chunk, list):
            flattened.extend(chunk)
        elif isinstance(chunk, dict):
            flattened.append(chunk)

    import io
    return parse_takeout_json(io.StringIO(json.dumps(flattened)))


def _clean_title(raw_title):
    """Strip Google's "Watched " prefix — but only the first occurrence.

    A title like "Watched I Watched Every Star Wars Movie" must become
    "I Watched Every Star Wars Movie", not "I Every Star Wars Movie".
    """
    title = raw_title.strip()
    if title.startswith(TITLE_PREFIX):
        title = title[len(TITLE_PREFIX):]
    return title.strip()


def _extract_channel(item):
    """Pull the channel name out of the subtitles array."""
    subtitles = item.get("subtitles")
    if not isinstance(subtitles, list) or not subtitles:
        return ""
    first = subtitles[0]
    if not isinstance(first, dict):
        return ""
    return (first.get("name") or "").strip()


def _parse_timestamp(raw_time):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    Accepts a trailing "Z" as well as an explicit offset, and treats a
    timestamp with no offset as UTC (which is what Google means).
    """
    if not raw_time or not isinstance(raw_time, str):
        return None

    text = raw_time.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
```

### Why Every One of Those Defences Exists

The original plan's parser was twelve lines and would crash the request with an HTTP 500
on any of the following, all of which occur in real Takeout exports:

| Defect in original | Consequence | Fix |
|--------------------|-------------|-----|
| `json.load()` unguarded | Malformed or HTML file → `JSONDecodeError` → **500** | Catch, re-raise as `TakeoutParseError` → 400 |
| Non-dict items assumed | `item.get` on a string → `AttributeError` → **500** | `isinstance(item, dict)` check |
| `title` not stripped after prefix removal | `"Watched  Foo"` → `" Foo"` with a leading space | `_clean_title` strips both ends |
| No "no videos found" check | Uploading `subscriptions.json` silently creates zero interests, and the user sees "Upload succeeded" and an empty page with no explanation | Raise `TakeoutParseError` |
| Naive datetimes stored | `RuntimeWarning: received a naive datetime`, and a timezone bug that surfaces months later | `_parse_timestamp` always returns aware UTC |
| `subtitles[0]` assumed to be a dict | Malformed entry → `AttributeError` → **500** | Type-checked |

The general principle: **a parser's job is not just to succeed, it is to fail
loudly and specifically.** A user who uploads the wrong file should be told which file
they should upload, not shown a 500 traceback.

### The Monthly Variant

`parse_takeout_monthly_json` handles the older layout. It re-serialises the flattened
list to reuse the single-file parser rather than duplicating the filtering logic — a
small, honest trade of a little memory for one source of truth.

> [!TIP]
> Prefer handling both shapes in one function by checking whether the first element is a
> list, rather than exposing two public entry points. Two public functions means callers
> must know which layout they have, and someone will eventually pick wrong.

### Line-by-Line Notes

**`json.load(file_obj)` vs `json.loads(string)`**
`json.load()` reads from a file-like object (anything with `.read()`). `json.loads()`
reads from a string. `request.FILES` gives you file-like objects, so `json.load()` is
correct.

**`TITLE_PREFIX` slice vs `str.replace`**
```python
if title.startswith(TITLE_PREFIX):
    title = title[len(TITLE_PREFIX):]
```
The original used `.replace("Watched ", "", 1)`. The `1` limited it to the first
occurrence, which was correct, but `replace` also matches the prefix anywhere in the
string. `startswith` is precisely the intent.

**The `Z` suffix**
Google emits `"2024-12-15T14:30:00.000Z"`. Python 3.11+ `datetime.fromisoformat()`
handles `Z` natively, so the replacement is no longer strictly necessary — but it is
harmless, explicit, and keeps the code correct if the project is ever run on 3.9 or 3.10.

> [!NOTE]
> The original plan's explanation here was outdated: it claimed `fromisoformat` "before
> 3.11 doesn't understand Z" while presenting this as a permanent requirement. The
> code is still right; the reasoning was stale.

**Why `.astimezone(timezone.utc)`**
A Takeout export can contain local-time offsets. Storing everything in UTC means
`watched_at` values are directly comparable and sortable. Django stores naive datetimes
in SQLite under `USE_TZ=True` and converts on read; handing it aware UTC datetimes is
the correct input.

### Testing the Parser Right Now

```bash
python manage.py shell
```

```python
import io, json
from trivia.services.takeout_parser import parse_takeout_json, TakeoutParseError

sample = json.dumps([
    {"title": "Watched F1 Grand Prix Highlights",
     "titleUrl": "https://www.youtube.com/watch?v=abc",
     "subtitles": [{"name": "F1 Official"}],
     "time": "2024-12-15T14:30:00.000Z"},
    {"title": "Watched Python Tutorial",
     "titleUrl": "https://www.youtube.com/watch?v=def",
     "subtitles": [{"name": "Corey Schafer"}],
     "time": "2024-12-14T10:15:00.000Z"},
    {"title": "Visited the YouTube homepage",
     "titleUrl": "https://www.youtube.com/?gl=US"},
])

entries = parse_takeout_json(io.StringIO(sample))
print(entries)
# [{'video_title': 'F1 Grand Prix Highlights', 'channel_name': 'F1 Official',
#   'watched_at': datetime.datetime(2024, 12, 15, 14, 30, tzinfo=datetime.timezone.utc)},
#  ...]

try:
    parse_takeout_json(io.StringIO("not json at all"))
except TakeoutParseError as e:
    print("Correctly rejected:", e)
```

Part 7 turns these into permanent tests.

---

## Service 2: Ranking Interests

### The Algorithm: Channel Frequency

The simplest useful signal: **count which channels someone watches most.**

`trivia/services/interest_ranker.py`:

```python
"""Rank a user's interests from their watch history.

Pure Python — no Django imports.
"""

from collections import Counter


def rank_interests(watch_entries, top_n=5, min_share=0.0):
    """Rank user interests by channel frequency.

    Args:
        watch_entries: List of dicts with a 'channel_name' key. Entries with
            a missing or blank channel name are ignored.
        top_n: Maximum number of interests to return.
        min_share: Drop interests whose share of total watch history is below
            this threshold. 0.0 disables filtering.

    Returns:
        A list of dicts with 'label' (str) and 'weight' (float), sorted by
        weight descending.

    Weight semantics — read this before using the numbers:
        weight = (videos from this channel) / (total videos with a channel)
    Weights therefore express each interest's share of the user's whole
    channel-tagged history. They sum to at most 1.0, and sum to exactly 1.0
    only when `top_n` is at least the number of distinct channels. If you
    need them to sum to 1.0 over the returned set, divide each by the sum
    of the returned weights.
    """
    channel_counts = Counter(
        entry.get("channel_name", "")
        for entry in watch_entries
        if entry.get("channel_name")
    )

    if not channel_counts:
        return []

    total = sum(channel_counts.values())
    ranked = channel_counts.most_common(top_n)

    results = [
        {"label": channel, "weight": round(count / total, 3)}
        for channel, count in ranked
    ]

    if min_share > 0:
        results = [item for item in results if item["weight"] >= min_share]

    return results


def renormalize(ranked):
    """Rescale weights so a returned set sums to 1.0.

    Use this when you need the displayed percentages to add up to 100%.
    Without it, weights express share of the *whole* history, so truncating
    to top_n leaves a remainder (see the weight semantics note above).

    Args:
        ranked: Output of rank_interests().

    Returns:
        A new list with rescaled weights, order preserved.
    """
    total = sum(item["weight"] for item in ranked)
    if not total:
        return ranked
    return [
        {**item, "weight": round(item["weight"] / total, 3)}
        for item in ranked
    ]
```

### Understanding `Counter`

```python
from collections import Counter

c = Counter(["F1", "F1", "F1", "Finance", "Gaming"])
# Counter({'F1': 3, 'Finance': 1, 'Gaming': 1})

c.most_common(2)
# [('F1', 3), ('Finance', 1)]
```

### The Weight Calculation — Precisely

If a user watched 100 videos total and 30 were from "F1 Official":

```
weight = 30 / 100 = 0.3
```

30% of their watch history is F1 content. A **proportion**, not an absolute count, which
makes weights comparable across users with very different history sizes.

> [!IMPORTANT]
> **The denominator is the whole history, not the top N.**
>
> With 6 channels and `top_n=5`, the returned weights sum to `0.971`, not `1.0`. This is
> intentional and correct: the missing 0.029 is the sixth channel, which exists in the
> data but was not returned.
>
> The original plan's test suite contained a test named
> `test_weights_are_normalized_proportions` that asserted weights sum to 1.0. It passed
> **by accident** — it used 2 channels with `top_n=2`, so the top-N happened to cover the
> entire history. The same test with 6 channels would have failed.
>
> If you actually want the returned set to sum to 1.0, call `renormalize()` — defined
> alongside `rank_interests` above, with no external dependencies:
>
> ```python
> topics = renormalize(rank_interests(entries, top_n=5))
> ```
>
> Part 7 tests both the raw semantics and `renormalize`, so the behaviour is pinned
> rather than accidental.

### Optional Extension: TF-IDF + K-Means

Channel frequency is crude. It tells you "you watch a lot of F1 Official" but cannot
distinguish F1 race highlights from F1 technical analysis. A clustering approach groups
video **titles** by vocabulary instead:

```python
# pip install scikit-learn
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer


def rank_interests_by_cluster(watch_entries, n_clusters=5, random_state=42):
    """Cluster video titles by vocabulary and label clusters by top terms.

    Returns the same [{'label', 'weight'}] shape as rank_interests(), so it
    is a drop-in replacement.

    Note: with fewer entries than clusters, or near-duplicate titles, KMeans
    emits ConvergenceWarning and may produce empty clusters. Guard with
    `if len(titles) < n_clusters * 2: fall back to channel frequency`.
    """
    titles = [e.get("video_title", "") for e in watch_entries if e.get("video_title")]
    if len(titles) < n_clusters * 2:
        return rank_interests(watch_entries, top_n=n_clusters)

    vectorizer = TfidfVectorizer(
        max_features=1000,
        stop_words="english",
        min_df=2,          # ignore words appearing in only one title
    )
    matrix = vectorizer.fit_transform(titles)

    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    kmeans.fit(matrix)

    terms = vectorizer.get_feature_names_out()
    results = []
    for cluster_id in range(n_clusters):
        indices = [i for i, label in enumerate(kmeans.labels_) if label == cluster_id]
        if not indices:
            continue
        centroid = kmeans.cluster_centers_[cluster_id]
        top_terms = [
            terms[i]
            for i in centroid.argsort()[::-1][:3]
            if centroid[i] > 0
        ]
        if not top_terms:
            continue
        results.append({
            "label": " / ".join(top_terms).title(),
            "weight": round(len(indices) / len(titles), 3),
        })

    return sorted(results, key=lambda item: item["weight"], reverse=True)[:n_clusters]
```

> [!NOTE]
> **This is an extension, not part of the core build.** The original plan installed
> `scikit-learn`, listed it in the stack table, previewed this function, and then never
> built it — leaving a reader with an unused dependency and a promise. Here it is
> explicitly optional, and `scikit-learn` is not in `requirements.txt`.
>
> It lives in this file rather than a separate module so it can import `rank_interests`
> for its fallback path. If you adopt it in production, move it to
> `interest_clusterer.py` and keep the two independent.

### Why Start With Channel Frequency

- **It works immediately** on any history size, including ten videos.
- **It is interpretable.** "You watched 30% F1 Official" is a claim you can show a user
  and get agreement on. Cluster labels like "racing / speed / apex" are harder to trust.
- **It has no failure modes** on small or sparse data. KMeans needs enough documents to
  form distinct clusters and warns when it cannot.
- **It gives the LLM a better prompt.** "Formula 1" produces markedly better trivia than
  "racing / speed / apex".

Ship v1, verify the end-to-end flow, then consider clustering. Avoid premature
complexity.

---

## Service 3: Generating Questions with the LLM

### The Anthropic Claude API

Claude is an LLM made by Anthropic. We use it to generate trivia questions about a user's
interests.

`trivia/services/llm_service.py`:

```python
"""Generate trivia questions with Claude.

Pure Python — no Django imports. Reads configuration from environment
variables, which Django populates from .env in Part 6.
"""

import json
import logging
import os
import random

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You generate multiple-choice trivia questions about a topic.

Return ONLY a valid JSON array. No prose, no explanation, no markdown code fences.

Format: a JSON array of objects, each with exactly these keys:
  "prompt_text"    (string) - the question
  "options"        (array of exactly 4 distinct strings) - the answer choices
  "correct_answer" (string) - MUST be byte-for-byte identical to one entry in "options"

Rules:
  - Exactly one option is correct.
  - Options must be plausible and of similar length to each other.
  - Never number the options or prefix them with A/B/C/D.
  - Do not make the correct option systematically longer or more specific.
  - Questions must be answerable without seeing the options."""

_client = None


class LLMError(Exception):
    """Raised when questions could not be generated, for any reason."""


def get_client():
    """Return a lazily-constructed Anthropic client.

    Built on first use rather than at import time so that importing this
    module never raises when ANTHROPIC_API_KEY is absent. That matters for
    the test suite and for the mock mode below.
    """
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env and "
                "restart the server, or set WATCHTRIVIA_MOCK_LLM=True to "
                "generate placeholder questions without calling the API."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def mock_enabled():
    return os.environ.get("WATCHTRIVIA_MOCK_LLM", "").lower() in {"1", "true", "yes"}


def generate_questions(topic_label, num_questions=3, model=None):
    """Generate multiple-choice trivia questions about a topic.

    Args:
        topic_label: The interest topic to generate questions about.
        num_questions: How many questions to generate.
        model: Override the Claude model ID. Defaults to $ANTHROPIC_MODEL
            or claude-sonnet-4-6.

    Returns:
        A list of dicts, each with:
            prompt_text    (str)
            options        (list[str], exactly 4)
            correct_answer (str, exactly matching one entry in options)

    Raises:
        LLMError: The API call failed, the response was not valid JSON after
            one retry, or the response did not match the required schema.
    """
    if mock_enabled():
        return _mock_questions(topic_label, num_questions)

    model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    user_prompt = f"Generate {num_questions} trivia questions about: {topic_label}"

    raw_text = _request(model, [
        {"role": "user", "content": user_prompt},
    ])

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON for %r; retrying once.", topic_label)
        raw_text = _request(model, [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": raw_text},
            {
                "role": "user",
                "content": (
                    "That was not valid JSON. Return ONLY the JSON array of "
                    "question objects, with no surrounding text or code fences."
                ),
            },
        ])
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Claude returned invalid JSON twice for topic {topic_label!r}."
            ) from exc

    return _validate_questions(payload, topic_label, num_questions)


def _request(model, messages):
    """Call the Messages API and return the response text, unwrapping errors."""
    try:
        response = get_client().messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.8,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.APIError as exc:
        raise LLMError(f"Anthropic API error: {exc}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc

    blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
    if not blocks:
        raise LLMError("Claude returned a response with no text content.")

    return blocks[0].text.strip()


def _validate_questions(payload, topic_label, num_questions):
    """Check the LLM's output actually matches the schema we promised.

    The system prompt asks for a specific shape. Asking is not the same as
    receiving, and a malformed question stored in the database becomes a
    broken quiz that no later code can repair. Validate at the boundary.
    """
    if not isinstance(payload, list):
        raise LLMError(
            f"Expected a JSON list of questions for {topic_label!r}, "
            f"got {type(payload).__name__}."
        )
    if not payload:
        raise LLMError(f"Claude returned no questions for {topic_label!r}.")

    valid = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            logger.warning("Question %d for %r is not an object; skipping.", index, topic_label)
            continue

        prompt_text = item.get("prompt_text")
        options = item.get("options")
        correct_answer = item.get("correct_answer")

        if not isinstance(prompt_text, str) or not prompt_text.strip():
            logger.warning("Question %d for %r has no prompt_text; skipping.", index, topic_label)
            continue
        if not isinstance(options, list) or len(options) != 4:
            logger.warning(
                "Question %d for %r has %s options, expected 4; skipping.",
                index, topic_label, len(options) if isinstance(options, list) else "no",
            )
            continue
        if not all(isinstance(opt, str) and opt.strip() for opt in options):
            logger.warning("Question %d for %r has a non-string option; skipping.", index, topic_label)
            continue
        if not isinstance(correct_answer, str) or correct_answer not in options:
            logger.warning(
                "Question %d for %r has correct_answer %r that is not one of "
                "its options; skipping.",
                index, topic_label, correct_answer,
            )
            continue

        valid.append({
            "prompt_text": prompt_text.strip(),
            "options": [opt.strip() for opt in options],
            "correct_answer": correct_answer.strip(),
        })

    if not valid:
        raise LLMError(
            f"None of Claude's {len(payload)} responses for {topic_label!r} "
            "matched the required schema."
        )

    return valid[:num_questions]


_MOCK_TOPICS = {
    "formula 1": [
        ("Which driver holds the record for most Formula 1 Grand Prix wins?",
         ["Michael Schumacher", "Lewis Hamilton", "Sebastian Vettel", "Max Verstappen"],
         "Lewis Hamilton"),
        ("What is the official tyre supplier of Formula 1?",
         ["Pirelli", "Goodyear", "Michelin", "Bridgestone"],
         "Pirelli"),
    ],
    "python programming": [
        ("Which keyword defines a function in Python?",
         ["function", "def", "lambda", "func"],
         "def"),
    ],
    "space astronomy": [
        ("Which planet has the shortest day in our solar system?",
         ["Mercury", "Jupiter", "Mars", "Venus"],
         "Jupiter"),
    ],
}


def _mock_questions(topic_label, num_questions):
    """Deterministic-ish placeholder questions, so the app works with no API key.

    Lets you exercise upload -> interests -> quiz -> scoring end to end with
    zero cost and zero network calls, and keeps the test suite free.
    """
    key = topic_label.strip().lower()
    template = _MOCK_TOPICS.get(key) or [
        (
            f"Which statement about {topic_label} is true?",
            [
                f"It is widely discussed in the context of {topic_label}.",
                f"It has no connection to {topic_label}.",
                f"It predates the invention of {topic_label}.",
                f"It is the opposite of {topic_label}.",
            ],
            f"It is widely discussed in the context of {topic_label}.",
        ),
    ]

    questions = []
    for index in range(num_questions):
        prompt_text, options, correct_answer = template[index % len(template)]
        questions.append({
            "prompt_text": prompt_text,
            "options": list(options),
            "correct_answer": correct_answer,
        })
    return questions
```

### Key Design Decisions Explained

#### 1. Lazy Client Construction

```python
def get_client():
    global _client
    if _client is None:
        ...
        _client = anthropic.Anthropic(api_key=api_key)
    return _client
```

The original plan created the client at module level:

```python
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
```

That means **importing the module raises `TypeError` when no API key is set** — because
`Anthropic(None)` refuses a `None` key. Since `views.py` imports `llm_service` at module
scope, and `views.py` is imported by `urls.py`, and `urls.py` is imported by Django at
startup, **the entire application fails to boot** without a key. You cannot run
migrations, cannot run the test suite, and cannot even reach the login page.

Constructing on first use means a missing key is a clean `LLMError` raised at the moment
someone actually tries to generate a quiz. This is the single most important fix in this
section.

#### 2. A Custom Exception Instead of Leaking Library Errors

Every failure mode — missing key, network failure, rate limit, malformed JSON, schema
violation — surfaces as `LLMError`. Views catch one exception type and can present a
useful message. The original plan let `anthropic.APIError` and `json.JSONDecodeError`
escape, so the view's `except` clause had to know about two unrelated libraries, and
anything else (a schema violation, say) became an unhandled 500.

#### 3. Output Validation

The original plan's own comment said:

> "Always validate the output structure in your code."

…and then did not. It called `json.loads()` and handed the result straight to
`Question.objects.create(options=q["options"], correct_answer=q["correct_answer"])`. A
response with three options, or a `correct_answer` that is not among the options, or a
missing `prompt_text` key, produced either a `KeyError` 500 or a **permanently broken
question row** that no later code can fix, because the quiz renders from the database.

`_validate_questions` checks every field, logs precisely why each item was rejected, and
raises if nothing survived. Real LLMs occasionally return five options, or a
`correct_answer` that differs from the options only in trailing punctuation. Better to
drop that one question and keep the quiz.

#### 4. The Retry Pattern

```python
try:
    payload = json.loads(raw_text)
except json.JSONDecodeError:
    raw_text = _request(model, [
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": raw_text},        # show it its own output
        {"role": "user", "content": "That was not valid JSON. Return ONLY the JSON array."},
    ])
```

Sometimes the model wraps JSON in markdown fences or adds a sentence of preamble. The
retry shows it its own broken output and asks it to fix it, which works far more often
than re-asking from scratch — the model can see what went wrong.

**Retry exactly once.** The original plan did this correctly and it is worth preserving:
an infinite retry loop against a paid API during a traffic spike is an expensive outage.

#### 5. `temperature=0.8`

The default is `1.0`. Trivia questions benefit from some variety — asking for
questions about "Formula 1" three times should not produce three near-identical items.
`0.8` keeps variety without the incoherence of the maximum.

#### 6. Mock Mode

```python
if mock_enabled():
    return _mock_questions(topic_label, num_questions)
```

Setting `WATCHTRIVIA_MOCK_LLM=True` short-circuits the API entirely. This is what makes
the rest of the tutorial followable without a paid account, and it means the view tests
in Part 7 never make network calls or cost money.

The mock deliberately includes a generic fallback so it works for **any** topic label,
including ones a real user uploads.

#### 7. The Model Is Configurable

```python
model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
```

Model IDs change as providers release new versions. Hardcoding one in a function body
means every model upgrade is a code change and a deploy. Reading it from the environment
means it is a config change. `claude-sonnet-4-6` is the current production baseline;
newer models (such as `claude-opus-4-8`) can be swapped in without touching code.

---

## How the Three Services Work Together

```
User uploads watch-history.json
        ↓
┌──────────────────────────────────────────────────┐
│  takeout_parser.parse_takeout_json(file)          │
│  Input:  uploaded file                            │
│  Output: [{video_title, channel_name, watched_at}]│
│  Raises: TakeoutParseError on bad input           │
└──────────────────┬───────────────────────────────┘
                   ↓
        bulk_create into WatchHistoryEntry
                   ↓
┌──────────────────────────────────────────────────┐
│  interest_ranker.rank_interests(entries, top_n=5) │
│  Input:  parsed entries                           │
│  Output: [{label, weight}] sorted desc            │
└──────────────────┬───────────────────────────────┘
                   ↓
        bulk_create into InterestTopic
                   ↓
User clicks "Generate my quiz"
        ↓
┌──────────────────────────────────────────────────┐
│  llm_service.generate_questions(label, n=2)       │
│  Input:  topic label string                       │
│  Output: [{prompt_text, options, correct_answer}] │
│  Raises: LLMError on any failure                  │
└──────────────────┬───────────────────────────────┘
                   ↓
        create QuizAttempt, then create Questions
        linked to that attempt
                   ↓
        user answers → Answer rows → score updates
```

Notice the failure behaviour at each arrow. The parser can raise `TakeoutParseError`
(becomes a form error, HTTP 400). The ranker cannot fail on well-formed input. The LLM
can raise `LLMError` (becomes a message on the page, HTTP 502, and the attempt is
cleaned up rather than left half-populated). Part 4 implements all three behaviours.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Service layer** | Business logic in plain Python, separate from views |
| **Pure function** | No side effects, no Django imports — trivially testable |
| **Custom exception** | One failure type a caller can catch, instead of N library types |
| **Lazy initialisation** | Build expensive objects on first use, not at import |
| **Boundary validation** | Never trust external input, including LLM output |
| **Bounded retry** | Retry once, then give up — never loop against a paid API |
| **`json.load()` vs `json.loads()`** | File-like object vs string |
| **`Counter`** | Python's built-in counting dict |
| **Mock mode** | A no-cost code path that lets the app run without an API key |
| **Environment variables** | Secrets and config loaded from `.env`, never hardcoded |

---

**→ Continue to [Part 4: Forms and Views](./04_forms_and_views.md)**
# Part 4: Forms and Views

---

## Where Does Validation Live?

The original plan used Django REST Framework serializers for input validation. With a
server-rendered frontend, **Django forms** do that job natively — and they bring CSRF
handling, error rendering, and field-level validation for free.

| Concern | DRF serializer (original) | Django form (this plan) |
|---------|--------------------------|-------------------------|
| Validate input | `serializer.is_valid(raise_exception=True)` | `form.is_valid()` |
| Render errors | Hand-write JSON error responses | `{{ form.errors }}` in a template |
| CSRF protection | Manual — read cookie, set header | `{% csrf_token %}` |
| File uploads | `request.FILES` | `forms.FileField` |
| Output format | JSON | Rendered HTML |

Forms also work identically if you later add the JSON API in Part 10, which is one
reason they are the right choice for a project that might grow a second frontend.

---

## The Forms

`trivia/forms.py`:

```python
from django import forms

# Google Takeout watch-history exports are large but finite. 25 MB comfortably
# holds a decade of heavy watching and is small enough to parse in one go.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class WatchHistoryUploadForm(forms.Form):
    """Validates a Google Takeout watch-history.json upload.

    A plain Form, not a ModelForm: we are not creating a single model
    instance here, we are validating a file and then bulk-creating hundreds
    of rows from it.
    """

    file = forms.FileField(
        label="watch-history.json",
        help_text=(
            "Export your data from Google Takeout, then unzip it and upload "
            "the watch-history.json file from the YouTube folder."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]

        if uploaded.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f"That file is {uploaded.size / 1024 / 1024:.1f} MB. "
                f"The limit is {MAX_UPLOAD_BYTES / 1024 / 1024:.0f} MB."
            )

        name = (uploaded.name or "").lower()
        if not name.endswith(".json"):
            raise forms.ValidationError(
                "That does not look like a .json file. Takeout archives are "
                "zipped — unzip it first, then upload the .json inside."
            )

        return uploaded


class AnswerForm(forms.Form):
    """Validates one submitted answer against a specific question's options.

    Not a ModelForm either: the choice set is dynamic, because it comes from
    the question's JSONField rather than from a fixed list in the model.
    """

    def __init__(self, *args, question, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        self.fields["selected_answer"] = forms.ChoiceField(
            choices=[(opt, opt) for opt in question.options],
            widget=forms.RadioSelect,
            label="Your answer",
        )

    def clean_selected_answer(self):
        return self.cleaned_data["selected_answer"]
```

### Why `forms.Form` and Not `forms.ModelForm`

`ModelForm` is for creating or updating **one** model instance from form fields, and it
infers its fields and validation from the model. Neither form here does that:

- The upload form validates a *file* and then triggers a `bulk_create` of many
  `WatchHistoryEntry` rows. There is no single model to map onto.
- The answer form's choices are **dynamic** — they come from `question.options`, a
  `JSONField`, which `ModelForm` cannot introspect.

Reaching for `ModelForm` out of habit and then fighting it is a common source of
unnecessary code.

### Why Validate the Extension AND the Size

Both checks exist because of specific real failures:

- **Size.** `json.load()` reads the entire file into memory, then builds a list of dicts
  in memory, then `bulk_create` builds a list of model instances. A multi-gigabyte
  upload can exhaust the server's RAM. Django's own
  `DATA_UPLOAD_MAX_MEMORY_SIZE` (2.5 MB default) does not apply to file uploads, so
  nothing upstream stops this.
- **Extension.** Users upload `Takeout-123456789.zip` directly, or
  `subscriptions.json`, or `my-account.json`. Catching it here produces "unzip it
  first" instead of a confusing parse error from deep inside the parser.

> [!NOTE]
> The extension check is a **usability** check, not a security control. It is trivially
> bypassed by renaming a file, and that is fine — `parse_takeout_json` validates the
> actual content. Never rely on a filename to decide whether input is safe.

---

## The Views

`trivia/views.py`:

```python
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AnswerForm, WatchHistoryUploadForm
from .models import (
    Answer,
    InterestTopic,
    Question,
    QuizAttempt,
    WatchHistoryEntry,
)
from .services.interest_ranker import rank_interests
from .services.llm_service import LLMError, generate_questions
from .services.takeout_parser import TakeoutParseError, parse_takeout_json

logger = logging.getLogger(__name__)

# How many interest topics to draw questions from.
TOPICS_PER_QUIZ = 3
# How many questions to request per topic.
QUESTIONS_PER_TOPIC = 2


# ---------------------------------------------------------------------------
# Upload & interests
# ---------------------------------------------------------------------------

@login_required
def upload_history(request):
    """Accept a Takeout watch-history.json upload and recompute interests."""
    if request.method == "POST":
        form = WatchHistoryUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                entries = parse_takeout_json(form.cleaned_data["file"])
            except TakeoutParseError as exc:
                # Not a form-level problem (the file exists and is .json), so we
                # attach it to the field rather than using form.add_error on
                # "file" -- same result, clearer intent.
                form.add_error("file", str(exc))
            else:
                topics = _process_upload(request.user, entries)
                messages.success(
                    request,
                    f"Imported {len(entries):,} videos and "
                    f"found {len(topics)} interests.",
                )
                return redirect("trivia:interests")
    else:
        form = WatchHistoryUploadForm()

    return render(request, "trivia/upload.html", {"form": form})


def _process_upload(user, entries):
    """Persist parsed entries, replace the user's interests, return the new topics.

    This is a pure data function: it takes no `request` and touches no session
    or message framework, so the API layer in Part 10 can call it too.

    Wrapped in a transaction: a half-applied upload — new watch rows but stale
    interests — is worse than no upload at all, because the user has no way to
    tell it happened.
    """
    with transaction.atomic():
        # A re-upload replaces history rather than accumulating duplicates,
        # otherwise interests get computed over stale entries forever.
        WatchHistoryEntry.objects.filter(user=user).delete()

        WatchHistoryEntry.objects.bulk_create(
            [
                WatchHistoryEntry(user=user, **entry)
                for entry in entries
            ],
            batch_size=500,
        )

        ranked = rank_interests(entries, top_n=5)

        InterestTopic.objects.filter(user=user).delete()
        topics = InterestTopic.objects.bulk_create(
            [
                InterestTopic(user=user, label=item["label"], weight=item["weight"])
                for item in ranked
            ]
        )

    return topics


@login_required
def interests(request):
    """Show the user's computed interest topics."""
    topics = InterestTopic.objects.filter(user=request.user)
    return render(
        request,
        "trivia/interests.html",
        {"topics": topics},
    )


# ---------------------------------------------------------------------------
# Quiz lifecycle
# ---------------------------------------------------------------------------

@login_required
@require_POST
def generate_quiz(request):
    """Create a QuizAttempt with LLM-generated questions from top interests."""
    topics = list(InterestTopic.objects.filter(user=request.user)[:TOPICS_PER_QUIZ])
    if not topics:
        messages.error(
            request,
            "You have no interests yet. Upload your watch history first.",
        )
        return redirect("trivia:upload")

    attempt = QuizAttempt.objects.create(user=request.user)
    questions, failures = _build_questions(attempt, topics)

    if not questions:
        # Every topic failed. Leaving an empty attempt in the database would
        # show the user a quiz with no questions and no explanation.
        attempt.delete()
        messages.error(
            request,
            "Could not generate any questions. "
            + (
                failures[0]
                if failures
                else "Please try again in a moment."
            ),
        )
        return redirect("trivia:interests")

    if failures:
        # Partial success is still a usable quiz, but say so rather than
        # pretending everything worked.
        messages.warning(
            request,
            f"Generated {len(questions)} questions, but {len(failures)} topic(s) "
            "could not be reached. Try again for a full quiz.",
        )

    return redirect("trivia:quiz", attempt_id=attempt.id)


def _build_questions(attempt, topics):
    """Call the LLM once per topic. Returns (questions, failure_messages).

    One failing topic must not kill the whole quiz, but a silent failure is
    worse than a visible one -- so every failure is recorded and surfaced to
    the user rather than swallowed by a bare `except Exception: continue`.
    """
    questions = []
    failures = []

    for topic in topics:
        try:
            generated = generate_questions(
                topic.label,
                num_questions=QUESTIONS_PER_TOPIC,
            )
        except LLMError as exc:
            logger.warning("LLM generation failed for topic %r: %s", topic.label, exc)
            failures.append(str(exc))
            continue
        except Exception:
            # Genuinely unexpected -- log the traceback so it is debuggable,
            # but do not let one topic take down the request.
            logger.exception("Unexpected error generating questions for %r", topic.label)
            failures.append(
                f"An unexpected error occurred while generating questions "
                f"for '{topic.label}'."
            )
            continue

        for item in generated:
            questions.append(
                Question(
                    user=attempt.user,
                    attempt=attempt,
                    topic=topic,
                    prompt_text=item["prompt_text"],
                    options=item["options"],
                    correct_answer=item["correct_answer"],
                )
            )

    if questions:
        Question.objects.bulk_create(questions)

    return questions, failures


@login_required
def quiz(request, attempt_id):
    """Render the questions for one attempt, with whatever is already answered."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("user"),
        pk=attempt_id,
        user=request.user,          # <-- ownership check
    )
    questions = list(attempt.questions.select_related("topic"))
    answers = {a.question_id: a for a in attempt.answers.all()}

    # Build the pairing the template needs here rather than making the
    # template do dict lookups. See the note in Part 8.
    rows = [{"question": q, "answer": answers.get(q.id)} for q in questions]

    return render(
        request,
        "trivia/quiz.html",
        {"attempt": attempt, "rows": rows, "answered_count": len(answers)},
    )


@login_required
@require_POST
def submit_answer(request, attempt_id, question_id):
    """Record one answer and return the rendered feedback fragment.

    Responds to HTMX with an HTML partial; falls back to a redirect for
    non-JS requests, so the whole quiz works with JavaScript disabled.
    """
    # Both lookups are ownership-scoped. The question must belong to THIS
    # attempt, not merely to this user -- otherwise a user can pair their own
    # attempt with a question id from a different attempt and score it.
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)
    question = get_object_or_404(
        Question,
        pk=question_id,
        attempt=attempt,
        user=request.user,
    )

    existing = Answer.objects.filter(attempt=attempt, question=question).first()
    if existing:
        # The unique constraint would reject this anyway; catching it here
        # lets the user see what they already chose instead of a 500.
        return _render_answer_feedback(
            request, attempt, question, existing, already_answered=True
        )

    form = AnswerForm(request.POST, question=question)
    if not form.is_valid():
        return _render_answer_feedback(
            request, attempt, question, None, form=form
        )

    with transaction.atomic():
        answer = Answer.objects.create(
            attempt=attempt,
            question=question,
            selected_answer=form.cleaned_data["selected_answer"],
        )
        if answer.is_correct:
            # Re-aggregate from the answers rather than incrementing a
            # counter, so the score is always correct even if a previous
            # write was lost or an answer was edited in the admin.
            attempt.score = attempt.answers.filter(is_correct=True).count()
            attempt.save(update_fields=["score"])

    return _render_answer_feedback(request, attempt, question, answer)


def _render_answer_feedback(request, attempt, question, answer, form=None,
                            already_answered=False):
    """Render the small fragment HTMX swaps in after an answer.

    The non-HTMX branch is what makes "works without JavaScript" true. Without
    it, a JS-disabled browser navigates to this view and is shown a bare HTML
    fragment with no <html>, no navbar, and no way back -- technically a
    response, practically a dead end.
    """
    if not request.headers.get("HX-Request"):
        if form is not None and not form.is_valid():
            # Nothing was recorded, so send them back to fix the input rather
            # than silently dropping a bad submission.
            messages.error(request, "Please choose one of the options.")
        elif already_answered:
            messages.info(request, "You already answered that question.")
        return redirect("trivia:quiz", attempt_id=attempt.id)

    context = {
        "attempt": attempt,
        "question": question,
        "answer": answer,
        "form": form,
        "already_answered": already_answered,
        "total_questions": attempt.questions.count(),
        "answered_count": attempt.answers.count(),
    }
    return render(request, "trivia/partials/answer_feedback.html", context)


@login_required
@require_POST
def complete_attempt(request, attempt_id):
    """Mark an attempt finished and show the score."""
    attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)

    if attempt.completed_at is None:
        attempt.completed_at = timezone.now()
        attempt.score = attempt.answers.filter(is_correct=True).count()
        attempt.save(update_fields=["completed_at", "score"])

    return redirect("trivia:results", attempt_id=attempt.id)


@login_required
def results(request, attempt_id):
    """Show a finished attempt's score and the questions the user missed."""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("user"),
        pk=attempt_id,
        user=request.user,
    )
    answers = (
        attempt.answers.select_related("question", "question__topic")
        .order_by("question_id")
    )
    correct = answers.filter(is_correct=True).count()
    return render(
        request,
        "trivia/results.html",
        {
            "attempt": attempt,
            "answers": answers,
            # The score is out of every question in the attempt, not just the
            # ones answered. Using answers.count() here would report 2/3 for a
            # user who got 2 of 6 right and abandoned the rest.
            "total": attempt.questions.count(),
            "correct": correct,
            # Kept separately so the template can say "you left 3 unanswered"
            # instead of silently treating them as wrong.
            "answered": answers.count(),
            "unanswered": attempt.questions.count() - answers.count(),
        },
    )
```

---

## Every Security Fix, Explained

The original plan's views had four defects. Each is visible in the code above, marked
where it occurs.

### 1. Cross-User Question Access — the Serious One

```python
# ORIGINAL — no ownership check on the question at all
question = Question.objects.get(id=serializer.validated_data["question_id"])
```

Any authenticated user could POST any `question_id` and receive
`{"is_correct": ..., "correct_answer": "..."}` — **the full answer key for every
question in the database**, by incrementing an integer. The original plan had a whole
section warning that viewsets must scope queries to `request.user`, then shipped this.

The fix is two constraints, not one:

```python
question = get_object_or_404(
    Question,
    pk=question_id,
    attempt=attempt,      # belongs to THIS attempt
    user=request.user,    # and belongs to THIS user
)
```

`attempt=attempt` matters as much as `user=request.user`. Without it, a user could pair
their own attempt with a question id from an old attempt, or from a topic they have since
deleted interest in, and the quiz would score it.

> [!IMPORTANT]
> The feedback fragment reveals `correct_answer` **after** the user has answered. That is
> correct and intended — you always find out the answer once you have committed. The
> original plan's design was sound here; the bug was that "after answering" was not
> actually enforced.

### 2. `.get()` Raising `DoesNotExist` — 500 Instead of 404

```python
# ORIGINAL
attempt = QuizAttempt.objects.get(id=attempt_id, user=request.user)
# → DoesNotExist exception → unhandled → HTTP 500 with a stack trace
```

```python
# THIS PLAN
attempt = get_object_or_404(QuizAttempt, pk=attempt_id, user=request.user)
# → HTTP 404 "Not Found"
```

`get_object_or_404` is `get()` plus an exception handler. It is the single most-used
function in idiomatic Django, and its absence is one of the clearest signals that code
was written without thinking about the failure path.

### 3. Unlimited Score Inflation

```python
# ORIGINAL — no guard
answer = Answer.objects.create(...)
if answer.is_correct:
    attempt.score += 1
    attempt.save()
```

Nothing stopped repeated POSTs of the same `question_id` to the same `attempt_id`, each
incrementing the score. On a six-question quiz a user could reach any score they liked.

The fix is threefold:

| Layer | Mechanism |
|-------|-----------|
| Database | `UniqueConstraint` on `Answer(attempt, question)` from Part 2 |
| View | `Answer.objects.filter(...).first()` early-return showing the prior answer |
| Model | `save()` override recomputes `is_correct`, so the value cannot be forged |

The view's early-return also improves UX: instead of a 500 from the constraint, the user
sees the answer they already gave.

### 4. `except Exception: continue` Swallowing Every Failure

```python
# ORIGINAL
for topic in topics:
    try:
        raw_questions = generate_questions(topic.label, num_questions=2)
    except Exception:
        continue          # ← a missing API key, a rate limit, and a bug are
                         #    all indistinguishable from each other here
```

If `ANTHROPIC_API_KEY` was unset, the user got `201 Created` with an empty question list
and no error message. The page rendered "Your quiz" with nothing on it. The most likely
cause of a completely broken app produced zero diagnostics.

This version:

- Catches `LLMError` specifically and **records the message** for display.
- Catches bare `Exception` separately and **logs the traceback** with
  `logger.exception(...)`, so genuine bugs are debuggable, while still not killing the
  request.
- Distinguishes **partial** failure (some questions generated → show them, warn the user)
  from **total** failure (delete the empty attempt, show the reason).
- Never leaves an empty `QuizAttempt` in the database.

> [!TIP]
> The rule this encodes: **an empty result is a failure.** If your code produces nothing,
> something went wrong, and the user should be told what. A silent `continue` converts a
> diagnosable bug into an unexplainable UI.

### Two Further Improvements

**Score is re-aggregated, not incremented.**

```python
attempt.score = attempt.answers.filter(is_correct=True).count()
```

The original did `attempt.score += 1`. Incrementing assumes every prior write succeeded.
Re-counting is idempotent: running it twice, or recovering from a partially failed
request, gives the same answer. It is one extra cheap query on a table with a handful of
rows.

**Uploads delete previous history.**

```python
WatchHistoryEntry.objects.filter(user=user).delete()
```

The original appended. Upload a second, corrected Takeout file and you would compute
interests over the union of both, permanently. Since `InterestTopic` is replaced on every
upload, keeping stale `WatchHistoryEntry` rows means the interests shown no longer
correspond to the data that produced them. Deleting first makes the operation idempotent:
uploading the same file twice gives the same result.

> [!NOTE]
> If you want to support *merging* multiple Takeout exports instead, delete this line —
> but then dedupe on `(user, video_title, watched_at)`, or the same video watched on three
> devices will be counted three times and inflate its channel's weight.

---

## Transactions — Why `transaction.atomic()`

```python
with transaction.atomic():
    WatchHistoryEntry.objects.filter(user=user).delete()
    WatchHistoryEntry.objects.bulk_create(...)
    InterestTopic.objects.filter(user=user).delete()
    topics = InterestTopic.objects.bulk_create(...)
```

Without it, an exception halfway through — a database full, a lock timeout, a network
blip — leaves the user with new watch rows but stale interests, or worse, with their
interests deleted and nothing to replace them. Neither state is recoverable by the user,
and neither is visible: the page would just show stale or empty data.

`atomic()` means all of it happens or none of it does.

**Caveat:** the LLM call in `generate_quiz` happens *outside* any transaction, on
purpose. Holding a database transaction open across a 30-second network call locks rows
for 30 seconds and will exhaust your connection pool under any real traffic. The pattern
is: do slow external work first, then take a short transaction for the database writes.

The correct production fix is a background task queue. That is a genuine enhancement for
a real deployment, and it is explicitly **not** in this plan — see the honest scope note
in Part 9.

---

## `bulk_create` and `batch_size`

```python
WatchHistoryEntry.objects.bulk_create(
    [WatchHistoryEntry(user=user, **entry) for entry in entries],
    batch_size=500,
)
```

Instead of one `INSERT` per entry — 50,000 queries for a large Takeout export —
`bulk_create` batches them. `batch_size=500` bounds each statement's parameter count,
which matters because SQLite has a limit on bound parameters per statement (999 by
default on older builds) and very long single statements can exceed
`max_query_length` on PostgreSQL.

> [!WARNING]
> `bulk_create` does **not** call `save()` on each object. Our `Answer.save()` override
> that computes `is_correct` would be silently skipped. This is why `Answer` is created
> one at a time in `submit_answer` (a handful of rows, and the override is required),
> while `WatchHistoryEntry` — which has no `save()` override — uses `bulk_create`.
>
> In Django 4.1+ you can pass `objs` to `bulk_create` to have it call `save()` on each
> object, but that defeats the performance benefit.

---

## View Types Used

| Decorator / helper | Purpose |
|--------------------|---------|
| `@login_required` | Redirect anonymous users to the login page |
| `get_object_or_404` | Fetch one object, or return HTTP 404 |
| `render(request, template, context)` | Render an HTML template |
| `redirect("namespace:name", arg=...)` | HTTP 302 to a named URL |
| `messages.success/error/warning` | Queue a one-request flash message |
| `@require_POST` | Return 405 for anything but POST |

### `@login_required` Versus DRF's `IsAuthenticated`

Both send anonymous users away. The difference is where they go and what they get:

| | `@login_required` | `IsAuthenticated` |
|---|---|---|
| Anonymous → | Redirect (302) to `LOGIN_URL` | 403 or 401 JSON |
| Browser sees | The login page | A JSON error body |
| Designed for | Server-rendered HTML | API clients |

For HTMX, a 302 to the login page works: HTMX follows redirects and swaps the returned
login HTML in. If you want a nicer experience, return `401` from an `htmx:trigger` event
in Part 8.

> [!TIP]
> Add `@require_POST` above `@login_required` on any view that only handles POST. The
> decorator order matters: `@require_POST` must be **above** `@login_required`, so an
> anonymous GET is rejected for the right reason.

---

## HTTP Status Codes

| Code | Constant | Meaning | Used When |
|------|----------|---------|-----------|
| 200 | `HTTP_200_OK` | Success | Default for GET, and for our HTMX fragments |
| 302 | `HTTP_302_FOUND` | Redirect | After upload, after redirect-to-quiz |
| 400 | `HTTP_400_BAD_REQUEST` | Client error | Invalid input, failed form validation |
| 403 | `HTTP_403_FORBIDDEN` | Not allowed | Authenticated but no permission |
| 404 | `HTTP_404_NOT_FOUND` | Not found | Wrong id, **or someone else's id** |
| 405 | `HTTP_405_METHOD_NOT_ALLOWED` | Wrong method | GET on a POST-only view |
| 500 | `HTTP_500_INTERNAL_SERVER_ERROR` | Server error | Unhandled exception — a bug |

> [!NOTE]
> `get_object_or_404` returning 404 for *someone else's* object rather than 403 is
> deliberate. A 403 would confirm the object exists, which leaks information. 404 is
> indistinguishable from "no such object", which is what you want.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`forms.Form`** | Validates non-model input; renders errors for templates |
| **`forms.FileField`** | File upload with size/type validation |
| **`clean_<field>()`** | Per-field validation, runs after the built-in checks |
| **`@login_required`** | Redirect anonymous users to the login page |
| **`get_object_or_404`** | Fetch one row or return 404 — never 500 |
| **`transaction.atomic()`** | All the writes happen, or none do |
| **`bulk_create`** | Batched insert; skips `save()` overrides |
| **`messages`** | Flash messages that survive one redirect |
| **Ownership scoping** | Every query filtered by `user=request.user` |
| **Idempotency** | Re-running an operation gives the same result |

---

**→ Continue to [Part 5: URL Configuration](./05_urls.md)**
# Part 5: URL Configuration

---

## How Django Routes Requests

When a request arrives, Django matches the path against patterns in a chain:

```
Request: POST http://localhost:8000/upload/
                                ↓
        ┌───────────────────────────────────────────────────┐
        │  watchtrivia/urls.py   (ROOT_URLCONF)              │
        │                                                    │
        │  path("admin/",   admin.site.urls)   ← no match   │
        │  path("accounts/", include(...))      ← no match   │
        │  path("", include("trivia.urls"))     ← MATCH      │
        │    passes the remainder ("upload/") onward          │
        └───────────────────────┬────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────────────┐
        │  trivia/urls.py                                    │
        │                                                    │
        │  path("upload/", views.upload_history, name="upload")  ← MATCH
        │    → calls upload_history(request)
        └───────────────────────────────────────────────────┘
```

Two-level routing keeps multi-app projects organized: each app owns its URLs, and the
project just delegates.

---

## App-Level URLs

Create `trivia/urls.py`:

```python
from django.urls import path

from . import views

app_name = "trivia"

urlpatterns = [
    path("", views.interests, name="interests"),
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
```

### The Complete URL Map

| URL | Method | View | Purpose |
|-----|--------|------|---------|
| `/` | GET | `interests` | Show the user's interests (the landing page) |
| `/upload/` | GET, POST | `upload_history` | Upload a Takeout file |
| `/generate-quiz/` | POST | `generate_quiz` | Build an attempt from top interests |
| `/quiz/<id>/` | GET | `quiz` | Render the attempt's questions |
| `/quiz/<id>/answer/<qid>/` | POST | `submit_answer` | Record one answer, return a fragment |
| `/quiz/<id>/complete/` | POST | `complete_attempt` | Close the attempt, go to results |
| `/results/<id>/` | GET | `results` | Show the final score |

### `path()` Parameters

```python
path("upload/", views.upload_history, name="upload")
#     ↑ URL pattern   ↑ View function              ↑ Name for reverse()
```

| Parameter | Purpose |
|-----------|---------|
| `"upload/"` | The pattern, relative to the parent `include()` |
| `views.upload_history` | The view to call on a match |
| `name="upload"` | Identifier for `reverse()` |

### URL Path Converters

```python
path("quiz/<int:attempt_id>/", views.quiz)
```

`<int:attempt_id>` captures part of the URL and passes it to the view as a **keyword
argument**, already converted to an `int`:

```
URL: /quiz/42/
          ^^
          attempt_id = 42 (an int, not the string "42")

def quiz(request, attempt_id):
    #                    ↑ attempt_id == 42
```

Because the converter is `int`, a request to `/quiz/abc/` does not match this pattern at
all — Django returns 404 before your view runs. That is one small safety property you get
for free.

| Converter | Matches | Example |
|-----------|---------|---------|
| `int` | Positive integers | `<int:id>` → `42` |
| `str` | Any non-empty string without `/` | `<str:slug>` → `"hello"` |
| `slug` | Letters, numbers, hyphens, underscores | `<slug:slug>` → `"my-post"` |
| `uuid` | UUID format | `<uuid:pk>` → `"075194d3-…"` |
| `path` | Any non-empty string including `/` | `<path:file>` → `"a/b.txt"` |

### `app_name` — Why Namespacing Matters

```python
app_name = "trivia"
```

Without it, URL names are global. If a second app also defines `name="upload"`, the
later one silently wins and `reverse("upload")` resolves to the wrong place — a bug that
only appears once you add the second app.

With `app_name`, names are namespaced and must be reversed as `"trivia:upload"`.

---

## Project-Level URLs

`watchtrivia/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("trivia.urls")),
]
```

| Line | What it does |
|------|--------------|
| `path("admin/", admin.site.urls)` | The admin site at `/admin/` |
| `path("accounts/", include("django.contrib.auth.urls"))` | Django's built-in login/logout/password pages |
| `path("", include("trivia.urls"))` | The app's URLs at the root |

### The `accounts/` Line Is the Whole Auth Story

```python
path("accounts/", include("django.contrib.auth.urls"))
```

One line. Django ships ready-made URL patterns, views, and templates for authentication.
You get, for free:

| URL | View | What it does |
|-----|------|--------------|
| `/accounts/login/` | `LoginView` | Login form; on success redirects to `LOGIN_REDIRECT_URL` |
| `/accounts/logout/` | `LogoutView` | Ends the session, redirects to `LOGOUT_REDIRECT_URL` |
| `/accounts/password_change/` | `PasswordChangeView` | Change your password |
| `/accounts/password_change/done/` | `PasswordChangeDoneView` | Confirmation page |

> [!IMPORTANT]
> **This is the fix for the original plan's biggest hole.** That version enforced
> `IsAuthenticated` on every endpoint and never built a login route, so the only way in
> was through `/admin/`. Every real user was locked out.
>
> `django.contrib.auth.urls` costs one line of configuration and two template overrides
> (Part 6). There is no reason to write a custom login view.

> [!NOTE]
> The built-in `LoginView` **requires** a `registration/login.html` template, even
> though it ships a default one. Creating it in `trivia/templates/registration/` lets
> you style it. Part 6 does this.

### Why the App URLs Are Mounted at Root

```python
path("", include("trivia.urls"))
```

The app's URLs therefore live at `/upload/`, `/quiz/1/`, and so on — no `/app/` prefix.
For a single-app project that is the right call: shorter URLs, and `/` can be the app's
landing page. In a multi-app project you would use a prefix like `path("trivia/", ...)`.

---

## URL Naming and `reverse()`

Every URL has a name, so you reference it instead of hardcoding a path:

```python
from django.urls import reverse

reverse("trivia:upload")                        # → "/upload/"
reverse("trivia:quiz", args=[42])               # → "/quiz/42/"
reverse("trivia:submit-answer", kwargs={         # → "/quiz/42/answer/7/
    "attempt_id": 42,
    "question_id": 7,
})
```

`args` takes positional values in URL order; `kwargs` takes them by name. Prefer
`kwargs` for readability.

Use `reverse()` in three places:

**In views, for redirects:**

```python
return redirect("trivia:interests")
return redirect("trivia:quiz", attempt_id=attempt.id)
```

**In templates, for links:**

```django
<a href="{% url 'trivia:quiz' attempt.id %}">Resume quiz</a>
```

**In tests, instead of hardcoded paths:**

```python
response = self.client.get(reverse("trivia:interests"))
```

> [!TIP]
> **Always use `reverse()` in tests.** If a URL pattern changes, only `urls.py` needs
> updating — every test keeps working. Hardcoded `"/api/interests/"` strings turn a
> one-line refactor into a hunt through the test suite.
>
> This matters most in the original plan, whose tests hardcoded paths like
> `self.client.get("/api/interests/")` while the tutorial simultaneously taught
> `reverse()` as best practice.

### `redirect()` Accepts a Name, Not a Path

```python
redirect("trivia:interests")                    # a name — reversed for you
redirect("/interests/")                          # a path — used verbatim
redirect(f"/quiz/{attempt.id}/")                 # an f-string path
```

Passing a name is better: it is checked at resolve time, so a typo raises
`NoReverseMatch` immediately rather than producing a 404 in production. Django also
raises `NoReverseMatch` for a name that does not exist, which turns a silent breakage
into a loud error.

---

## Slugs: When Your URLs Are Public

For a user-facing site you often want readable URLs:

```python
path("posts/<slug:slug>/", views.post_detail, name="post-detail")
```

```python
class Post(models.Model):
    slug = models.SlugField(unique=True)
    # ...
```

Django can generate the slug for you in `save()`:

```python
from django.utils.text import slugify

def save(self, *args, **kwargs):
    if not self.slug:
        base = slugify(self.title)[:50]
        slug, counter = base, 2
        while Post.objects.filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        self.slug = slug
    super().save(*args, **kwargs)
```

> [!NOTE]
> Watchtrivia uses plain integer IDs. Attempts and questions have no title to derive a
> slug from, and `/quiz/42/` is honest about what it is. Reach for slugs when the
> resource has a human-readable name.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`ROOT_URLCONF`** | Setting naming the top-level URL config file |
| **`path()`** | Maps a URL pattern to a view |
| **`include()`** | Delegates matching to another URLconf |
| **`<int:name>`** | Path converter; captures a URL segment as a typed argument |
| **`app_name`** | Namespaces URL names to avoid collisions between apps |
| **`name=`** | Identifier used by `reverse()` and `{% url %}` |
| **`reverse()`** | Look a URL up by name — never hardcode paths |
| **`args` vs `kwargs`** | Positional or named URL parameters |
| **`NoReverseMatch`** | Raised when a URL name cannot be resolved — fail loudly |

---

**→ Continue to [Part 6: Settings, Templates, and Authentication](./06_templates_and_auth.md)**
# Part 6: Settings, Templates, and Authentication

---

## Understanding `settings.py`

`settings.py` is Django's **single source of truth** for all configuration. Every
component — ORM, middleware, templates, auth, static files — is configured here.

The original plan devoted a full part to CORS configuration, session auth, and DRF
settings. All three are consequences of running the frontend on a different origin from
the backend. With a single Django server there is one origin, so this part is
correspondingly shorter. What remains is genuinely necessary.

---

## The Middleware Pipeline

Incoming requests pass through **middleware** — layers that run before and after your
view:

```
REQUEST comes in
    ↓
┌─ SecurityMiddleware ─────────────────────────┐
│  Adds security headers (HSTS, etc.)          │
├─ SessionMiddleware ──────────────────────────┤
│  Loads session data from the cookie          │
├─ CommonMiddleware ───────────────────────────┤
│  URL normalization, Content-Length           │
├─ CsrfViewMiddleware ────────────────────────┤
│  Validates CSRF token on POST requests       │
├─ AuthenticationMiddleware ───────────────────┤
│  Attaches request.user from the session      │
├─ MessageMiddleware ──────────────────────────┤
│  Enables the messages framework              │
├─ XFrameOptionsMiddleware ────────────────────┤
│  Prevents clickjacking                       │
└──────────────────────────────────────────────┘
    ↓
YOUR VIEW runs
    ↓
RESPONSE returns back through middleware in reverse
```

> [!NOTE]
> There is **no `CorsMiddleware`**. The original plan added
> `corsheaders.middleware.CorsMiddleware` because React ran on port 5173 while Django ran
> on 8000 — different origins, so browsers blocked the requests until Django added
> permissive headers. One origin needs no such thing.
>
> This is the concrete payoff of the server-rendered architecture: an entire
> configuration section, a dependency, and a class of production misconfiguration
> (someone setting `CORS_ALLOW_ALL_ORIGINS = True` "to make it work") all disappear.

---

## The Settings Changes

Edit `watchtrivia/settings.py`. The stock file Django generated needs these sections
replaced or added.

### 1. Imports and Environment Loading — at the very top

```python
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from backend/.env into the process environment.
load_dotenv(BASE_DIR / ".env")
```

`load_dotenv()` must run **before** anything reads `os.environ`. Putting it at the top
of the file guarantees that.

### 2. Security Settings

```python
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me",
)

DEBUG = os.environ.get("DEBUG", "True").lower() in {"1", "true", "yes"}

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
if not DEBUG:
    ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
```

**`SECRET_KEY`** signs sessions, CSRF tokens, and password-reset links. If it leaks, an
attacker can forge a session cookie for any user. Generate a real one with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> [!WARNING]
> The fallback string above is a **development convenience only**. It lets the app boot
> on a fresh clone without a `.env` file. In production, `DJANGO_SECRET_KEY` must be set
> in the environment — otherwise you are shipping a public secret key. Consider raising
> `ImproperlyConfigured` when `DEBUG=False` and the key is still the default.

**`DEBUG`** decides how much Django tells you when something breaks.

| `DEBUG=True` (development) | `DEBUG=False` (production) |
|---------------------------|----------------------------|
| Full traceback with source code | Generic "Server Error (500)" |
| Shows every SQL query and its timing | Nothing |
| Django serves static files | You must serve them yourself |
| No `ALLOWED_HOSTS` checking | `ALLOWED_HOSTS` enforced |

> [!CAUTION]
> **Never run with `DEBUG=True` in production.** The detailed error pages expose your
> source code, settings, environment variables, and SQL queries to anyone who can trigger
> an error. The first time a real user hits a bug in production is the worst possible
> moment to publish your database credentials.

**`ALLOWED_HOSTS`** prevents HTTP Host header attacks, where a request claims
`Host: evil.com` and Django serves your site to a request that did not come from your
domain. The bracketed `[::1]` is the IPv6 loopback.

### 3. `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "trivia",
]
```

Six built-ins plus your app. Django requires `auth` and `contenttypes` for the ORM to
resolve `settings.AUTH_USER_MODEL`, and `sessions` and `messages` for the features this
app uses.

> [!NOTE]
> No `rest_framework`, no `corsheaders`. Both are added in
> [Part 10](./10_optional_drf_api.md) if you decide you want a JSON API — and DRF
> would be the only one, since there is no second origin to configure CORS for.

### 4. `MIDDLEWARE`

The stock list is already correct. Verify `CsrfViewMiddleware` is present and **before**
`AuthenticationMiddleware`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

> [!IMPORTANT]
> **Middleware order matters.** `SessionMiddleware` must precede
> `AuthenticationMiddleware`, because the latter reads the session the former loads. If
> `request.user` is always `AnonymousUser` despite being logged in, this is the first
> thing to check.

### 5. Templates

```python
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
```

| Setting | Purpose |
|---------|---------|
| `DIRS` | Shared template directories, checked before app directories |
| `APP_DIRS` | Also look inside each app's `templates/` folder |
| `context_processors.request` | Makes `request` available in every template |
| `...auth` | Makes `user` available — needed for the nav bar |
| `...messages` | Makes `messages` available — needed for flash messages |

> [!TIP]
> The `auth` and `messages` context processors are why `base.html` can write
> `{{ user.username }}` and loop over `{% for message in messages %}` without any view
> passing those in. Forget them and you get a silent `VariableDoesNotExist`.

### 6. Static Files

```python
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
```

| Setting | Purpose |
|---------|---------|
| `STATIC_URL` | URL prefix for static files in templates |
| `STATIC_ROOT` | Where `collectstatic` puts everything, for production |

Our CSS lives in `trivia/static/trivia/style.css`, which the `AppDirectoriesFinder`
(enabled by default) already finds. So `STATICFILES_DIRS` is **not needed**, and it is
deliberately left out of the settings block above.

> [!WARNING]
> Do not add `STATICFILES_DIRS = [BASE_DIR / "static"]` "for completeness" unless you
> create the directory. Django checks every entry in that list at startup and raises
> `ImproperlyConfigured: The STATICFILES_DIRS setting should not contain the path
> .../backend/static, which does not exist` — a crash on `runserver`, `migrate`, and
> every management command, before you have written a line of app code.
>
> Add it only when you have a genuine project-wide asset directory, and create it first:
>
> ```bash
> mkdir -p backend/static
> ```
>
> App-level static files need no such setting. `trivia/static/trivia/style.css` is found
> automatically by the app directories finder.

`STATIC_ROOT` is the one that matters in production: `collectstatic` gathers every app's
static files into a single directory that a web server can serve directly.

### 7. Authentication Settings

```python
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "trivia:interests"
LOGOUT_REDIRECT_URL = "trivia:interests"
```

**`LOGIN_URL = "login"`** is what `@login_required` redirects to. Because
`django.contrib.auth.urls` is included under `accounts/`, the *URL name* is `login`
while the *path* is `/accounts/login/`. Django resolves the name for you.

| Setting | Value | Why |
|---------|-------|-----|
| `LOGIN_URL` | `"login"` | Where `@login_required` sends anonymous users |
| `LOGIN_REDIRECT_URL` | `"trivia:interests"` | Landing page after a successful login |
| `LOGOUT_REDIRECT_URL` | `"trivia:interests"` | Landing page after logout |

> [!NOTE]
> `LOGIN_REDIRECT_URL` accepts a URL **name**, not a path. Using a path here raises
> `NoReverseMatch`.

### 8. Database

The default is already correct for development:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

> [!IMPORTANT]
> `NAME` is `db.sqlite3` **inside `backend/`**, and `.gitignore` excludes it. For
> production, switch to PostgreSQL by installing `psycopg[binary]` and changing `ENGINE`
> to `django.db.backends.postgresql`. Your migrations run unchanged — that is the payoff
> of using the ORM instead of raw SQL.

### 9. Internationalization

```python
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
```

> [!NOTE]
> `USE_TZ = True` is the only supported behaviour in modern Django, and it matches the
> parser, which returns timezone-aware UTC datetimes. Keeping `TIME_ZONE = "UTC"`
> everywhere means naive/aware mismatches cannot occur.
>
> The original plan's parser returned datetimes that could be naive, which produced
> `RuntimeWarning: received a naive datetime while time zone support is active` — a
> warning that is easy to ignore and produces wrong results in any code that compares
> timestamps. Fixed in Part 3.

---

## What Disappeared, and Why

A concrete inventory of what the server-rendered approach removes:

| Removed | Original location | Reason |
|---------|-------------------|--------|
| `django-cors-headers` dependency | Part 1 install list | Only needed across origins |
| `CorsMiddleware` | `MIDDLEWARE` | Same |
| `CORS_ALLOWED_ORIGINS` | settings | Same |
| `CORS_ALLOW_CREDENTIALS` | settings | Same |
| `djangorestframework` dependency | Part 1 install list | No JSON API in the core app |
| `REST_FRAMEWORK` settings dict | settings | Same |
| Serializers and their validation logic | Part 4 | Django forms do it natively |
| `DefaultRouter` URL generation | Part 5 | No viewsets to route |
| `axios.create()` + `withCredentials` | Part 8 | Same origin; cookies just work |
| CSRF token read-and-header dance | Part 8 | `{% csrf_token %}` does it |
| Manual frontend state machine | Part 8 | Server is the state |
| `FormData` construction | Part 8 | Plain HTML `<form>` |
| Vite, npm, Node.js | Part 8 | No build step |
| Second dev server on :5173 | Part 9 | One server |
| `CSRF_TRUSTED_ORIGINS` | never mentioned | No cross-origin POSTs |

Fifteen distinct pieces of configuration, code, and infrastructure — none of which the
application needed.

---

## Deep Dive: How Session Authentication Works

This is the entire auth model, and it is worth understanding properly.

```
1. User submits username + password to /accounts/login/
2. Django checks the password hash and creates a session row in the database
3. Django sends the session ID back as a cookie

   Set-Cookie: sessionid=8f2a...; HttpOnly; Path=/; SameSite=Lax; Secure

4. On every subsequent request the browser sends that cookie automatically

   Cookie: sessionid=8f2a...

5. SessionMiddleware reads the cookie, looks up the session row,
   and AuthenticationMiddleware sets request.user
```

Then in a view:

```python
@login_required
def interests(request):
    # request.user is guaranteed to be a real User here
    topics = InterestTopic.objects.filter(user=request.user)
```

and in a template, thanks to the `auth` context processor:

```django
{% if user.is_authenticated %}
  <p>Hello, {{ user.username }}</p>
{% else %}
  <a href="{% url 'login' %}">Log in</a>
{% endif %}
```

### Why This Needs No JavaScript

The browser attaches the session cookie to same-origin requests automatically. `fetch()`
and `axios` only need `withCredentials` when talking to a *different* origin — which,
from `localhost:8000` to `localhost:8000`, never happens.

### CSRF Protection

Django requires a CSRF token on every POST:

```
1. Django sets a cookie:  csrftoken=xyz789
2. The form contains:     <input type="hidden" name="csrfmiddlewaretoken" value="xyz789">
3. Django checks the POST field against the cookie
4. An attacker's page on another domain can submit the form,
   but cannot read the cookie, so it cannot produce a matching token
```

In a template that is one tag:

```django
<form method="post">
  {% csrf_token %}
  ...
</form>
```

> [!WARNING]
> **Every `<form>` in this app needs `{% csrf_token %}`.** Omitting it produces
> `Forbidden (403) / CSRF verification failed`, which is at least a loud failure rather
> than a silent vulnerability.
>
> The original plan had no `{% csrf_token %}` anywhere, because its forms were built by
> React, which reads the `csrftoken` cookie in JavaScript and copies it into an
> `X-CSRFToken` header. That code is in the original Part 8; it is unnecessary here and
> is one more thing this architecture avoids.

---

## The Login Page

Django's `LoginView` needs a `registration/login.html` template. It ships a plain default,
so this is purely cosmetic — but it is what makes the app look finished.

`trivia/templates/registration/login.html`:

```django
{% extends "trivia/base.html" %}

{% block title %}Log in — Watchtrivia{% endblock %}

{% block content %}
<div class="auth-card">
  <h1>Log in</h1>

  {% if form.errors %}
    <div class="alert alert-error" role="alert">
      Your username and password didn't match. Please try again.
    </div>
  {% endif %}

  <form method="post" action="{% url 'login' %}">
    {% csrf_token %}
    {{ form.as_p }}
    <input type="hidden" name="next" value="{{ next }}">
    <button type="submit" class="btn btn-primary">Log in</button>
  </form>

  <p class="muted">
    No account? This is a private tool — create one with
    <code>python manage.py createsuperuser</code>.
  </p>
</div>
{% endblock %}
```

Three things to notice:

- `{% extends "trivia/base.html" %}` inherits the layout, so the navbar and styling come
  for free.
- `{{ form.as_p }}` renders every field with its label, input, and errors. No
  boilerplate, and it stays correct if you add a field.
- `<input type="hidden" name="next" value="{{ next }}">` is not optional. `LoginView`
  puts the page the user was trying to reach into `request.GET["next"]` and into the
  context. Without this field, a logged-out user deep-linking to `/quiz/7/` lands on
  `/` after logging in, losing their place.

> [!TIP]
> `{{ form.as_p }}` is fine for a login form. For anything with custom layout, render
  fields individually — `{{ form.username }}`, `{{ form.username.errors }}` — so you
> control the markup. Django 5.0 added `{{ form.field }}` as the default rendering.

### Creating Non-Superuser Accounts

`createsuperuser` is for you. Regular users are created from the admin site's
**Users** section, or in the shell:

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User

user = User.objects.create_user(username="alice", password="a-strong-password")
user.is_staff = False
user.is_superuser = False
user.save()
```

Users created this way can log in normally but cannot reach `/admin/`, which is what you
want for real accounts.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Middleware** | Layers that wrap every request and response; order matters |
| **`DEBUG`** | Verbose errors in development; must be `False` in production |
| **`SECRET_KEY`** | Master signing secret for sessions and CSRF |
| **`ALLOWED_HOSTS`** | Whitelist of valid Host headers |
| **`STATIC_ROOT`** | Where `collectstatic` gathers files for production |
| **Context processors** | Inject `request`, `user`, `messages` into every template |
| **Session auth** | Server stores the session; browser sends a cookie |
| **`LOGIN_REDIRECT_URL`** | Where users land after logging in |
| **`{% csrf_token %}`** | Required in every POST form |
| **Same-origin** | One server, one port, no CORS configuration |

---

**→ Continue to [Part 7: Testing](./07_testing.md)**
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
# Part 8: The Frontend — Django Templates + HTMX

---

## What This Part Replaces, and Why

The original plan's Part 8 was a React SPA: Vite, npm, Axios, `useState`, a four-state
client-side state machine, `FormData` construction, and `withCredentials` cookie
handling. Around 350 lines of JavaScript plus a second dev server.

This part is about 120 lines of HTML templates plus one 14kb script tag. It produces a
faster app, and it works with JavaScript disabled.

**What you give up:** client-side state management. If you later need the same backend to
serve a mobile app or a third-party client, [Part 10](./10_optional_drf_api.md) adds a
JSON API. The backend in Parts 1–7 is identical either way.

---

## The Idea

Instead of JavaScript deciding what the page looks like, **the server always knows**. You
mark a region of the page, and HTMX fetches a fresh copy of just that region.

```html
<!-- Normal Django: a full page reload -->
<a href="/upload/">Upload history</a>

<!-- With HTMX: swap only #main, no full reload -->
<a href="/upload/" hx-get="/upload/" hx-target="#main" hx-select="#main"
   hx-push-url="true">
  Upload history
</a>
```

Click it, HTMX requests `/upload/`, Django returns the full HTML page, and HTMX takes
the response's `#main` element (`hx-select`) and replaces the existing one (`hx-target`).
The navbar, styles, and footer stay untouched.

The server-rendered version is the default. HTMX is an enhancement layered on top.

> [!IMPORTANT]
> `hx-target` **and** `hx-select` are both required when the server returns a full page.
> Using only `hx-target` nests a second `<main>` inside the first. This is explained in
> full under [HTMX Response Targeting](#htmx-response-targeting) — read that section
> before writing your own swaps, because the failure is invisible when it happens.

---

## Installing HTMX

Add one line to `base.html`. The current release is 2.x:

```django
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
```

> [!TIP]
> For offline development, or to avoid a third-party CDN in production, download the
> file to `trivia/static/trivia/htmx.min.js` and use
> `{% static 'trivia/htmx.min.js' %}`. Serving it yourself removes an external
> dependency from your critical path.

### The Attributes You Will Use

| Attribute | Purpose |
|-----------|---------|
| `hx-get` | Issue a GET request |
| `hx-post` | Issue a POST request |
| `hx-target` | CSS selector for the element to update |
| `hx-swap` | How to insert: `innerHTML`, `outerHTML`, `beforeend`, `none` |
| `hx-trigger` | When to fire: `click`, `load`, `change`, `submit`, or `revealed` |
| `hx-swap-oob` | Update an element **outside** the target (out-of-band swaps) |
| `hx-indicator` | Element shown only while the request is in flight |
| `hx-confirm` | A confirmation dialog before sending |
| `hx-boost` | Upgrade a normal link/form to an AJAX swap |
| `hx-push-url` | Add the request URL to browser history |
| `hx-indicator` + `hx-disabled-elt` | Prevent double-submits |
| `hx-vals` | Add extra values to the request |
| `hx-ext` | Load an extension (e.g. `json-enc`) |

### CSRF Configuration

HTMX does **not** read Django's `csrftoken` cookie automatically. Add one line to
`base.html`, and every `hx-post` in the app inherits it:

```django
<head>
  <meta name="csrf-token" content="{{ csrf_token }}">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script>
    document.addEventListener('htmx:configRequest', (event) => {
      event.detail.headers['X-CSRFToken'] =
        document.querySelector('meta[name="csrf-token"]').content;
    });
  </script>
</head>
```

> [!NOTE]
> This is the *only* JavaScript in the entire application. It is three lines, it is
> required, and it is required **because** HTMX is used at all. With plain Django
> forms, `{% csrf_token %}` in the template is sufficient and this script does not
> exist.
>
> Note `document.addEventListener`, not `document.body.addEventListener`. This script is
> in `<head>`, and at that point in parsing `document.body` is still `null` — a
> `document.body.addEventListener(...)` call here throws a `TypeError` and the CSRF
> header is never added, so every `hx-post` fails with 403 and no error appears
> anywhere obvious. Listening on `document` works regardless of parse position.
>
> The original React version needed equivalent logic in an Axios interceptor, plus
> `withCredentials: true`, plus CORS configuration on the server, plus cookie
> `SameSite` handling — to achieve the same result as `{% csrf_token %}`.

---

## The Base Template

`trivia/templates/trivia/base.html`:

```django
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{% block title %}Watchtrivia{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'trivia/style.css' %}">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script>
    document.addEventListener('htmx:configRequest', (event) => {
      event.detail.headers['X-CSRFToken'] =
        document.querySelector('meta[name="csrf-token"]').content;
    });
  </script>
</head>
<body>
  <header class="site-header">
    <nav>
      <a class="brand" href="{% url 'trivia:interests' %}">Watchtrivia</a>
      <div class="nav-links">
        {% if user.is_authenticated %}
          <a href="{% url 'trivia:interests' %}">Interests</a>
          <a href="{% url 'trivia:upload' %}">Upload history</a>
          <form method="post" action="{% url 'logout' %}" class="inline-form">
            {% csrf_token %}
            <span class="muted">{{ user.username }}</span>
            <button type="submit" class="btn btn-link">Log out</button>
          </form>
        {% else %}
          <a href="{% url 'login' %}">Log in</a>
        {% endif %}
      </div>
    </nav>
  </header>

  {% if messages %}
    <div class="messages">
      {% for message in messages %}
        <div class="alert alert-{{ message.tags }}">{{ message }}</div>
      {% endfor %}
    </div>
  {% endif %}

  <main id="main" class="container">
    {% block content %}{% endblock %}
  </main>

  <footer class="site-footer">
    <p>Built with Django and HTMX.</p>
  </footer>
</body>
</html>
```

### Template Inheritance

`{% extends "trivia/base.html" %}` in a child template means "use this layout, fill in
these blocks." The child defines only what differs:

```django
{% extends "trivia/base.html" %}
{% block title %}Interests — Watchtrivia{% endblock %}
{% block content %}
  <h1>Your interests</h1>
{% endblock %}
```

Blocks you can override: `{% block name %}...{% endblock %}`. You can also define
`{{ block.super }}` to include the parent's content and add to it.

> [!IMPORTANT]
> `{{ messages }}` and `{{ user }}` work in **every** template with no view passing them,
> because of the `django.contrib.messages.context_processors.messages` and
> `django.contrib.auth.context_processors.auth` context processors configured in Part 6.

### The Messages Framework

`{% for message in messages %}` renders messages queued by `messages.success()` in a
view. This is how "Imported 3 videos and found 2 interests" survives the redirect from
`upload_history` to `interests` — a different view, so the context would otherwise be
lost.

`message.tags` yields `success`, `error`, `warning`, or `info`, which the CSS turns into
a colour.

### HTMX Response Targeting

Part 4's views render **full page templates** — a whole `<html>` document, not a
fragment. That matters, because `hx-swap="innerHTML"` takes the *entire response body*
and puts it inside the target.

So `hx-target="#main"` + `hx-swap="innerHTML"` against a full page response produces
this:

```html
<main id="main">              <!-- the original target -->
  <main id="main">            <!-- the full page that came back -->
    ...
  </main>
</main>
```

The page renders, and it looks like it worked — which is why this bug survives. But the
DOM is nested one level deeper on every navigation, `<head>` elements are landing inside
`<body>`, and every swap now pays the cost of parsing the entire document.

The fix is `hx-select`, and it is the single most important HTMX-plus-Django detail in
this part:

```django
<form method="post" action="{% url 'trivia:generate-quiz' %}"
      hx-post="{% url 'trivia:generate-quiz' %}"
      hx-target="#main"
      hx-select="#main"
      hx-push-url="true">
```

| Attribute | Role |
|-----------|------|
| `hx-target="#main"` | Which element on *my* page to replace |
| `hx-select="#main"` | Which element of *the response* to take |

With both, HTMX pulls the response's `<main id="main">` out of the full document and
swaps it in place. The navbar, footer, and stylesheet are never re-parsed.

The two attributes are independent and both are required. `hx-target` alone nests;
`hx-select` alone replaces the whole body.

**For genuine fragments, no `hx-select` is needed.** Part 4's `submit_answer` returns
`trivia/partials/answer_feedback.html`, which *is* the small element, so the question
card targets it directly:

```django
hx-target="#answer-feedback-{{ row.question.id }}"
```

Rule of thumb: `hx-select` when the server returns a full page, omit it when the server
returns a fragment.

---

## The Pages

### 1. Upload — `trivia/templates/trivia/upload.html`

```django
{% extends "trivia/base.html" %}

{% block title %}Upload history — Watchtrivia{% endblock %}

{% block content %}
<div class="card">
  <h1>Upload your watch history</h1>

  <ol class="steps">
    <li>Go to <a href="https://takeout.google.com/" target="_blank"
               rel="noopener noreferrer">Google Takeout</a> and request your
        YouTube data.</li>
    <li>Download the archive and unzip it.</li>
    <li>Find <code>Takeout/YouTube and YouTube Music/history/watch-history.json</code>.</li>
    <li>Upload it below.</li>
  </ol>

  <form method="post" enctype="multipart/form-data" class="upload-form">
    {% csrf_token %}
    {{ form.non_field_errors }}
    {% for field in form %}
      <div class="field">
        <label for="{{ field.id_for_label }}">{{ field.label }}</label>
        {{ field }}
        {% if field.help_text %}
          <p class="help-text">{{ field.help_text }}</p>
        {% endif %}
        {% for error in field.errors %}
          <p class="field-error">{{ error }}</p>
        {% endfor %}
      </div>
    {% endfor %}
    <button type="submit" class="btn btn-primary">Analyse my history</button>
  </form>

  <p class="muted">
    No Takeout export handy? The tutorial ships a sample at
    <code>sample-data/watch-history.json</code> — upload that to try the app.
  </p>
</div>
{% endblock %}
```

Three things to notice:

- **`enctype="multipart/form-data"`** is what makes the browser send the file. Without
  it Django receives an empty `request.FILES`. The original plan had to construct a
  `FormData` object in JavaScript to achieve this; it is one HTML attribute here.
- **Field errors are rendered explicitly** rather than using `{{ form.as_p }}`, so
  styling and layout stay under your control.
- **The "Watched" data never leaves your server.** There is no third-party upload. The
  LLM call in Part 3 sends only *topic labels* like `"F1 Official"` — never your watch
  history, never video titles. This is worth stating explicitly, because uploading
  browsing history to a website is a genuinely sensitive action.

### 2. Interests — `trivia/templates/trivia/interests.html`

```django
{% extends "trivia/base.html" %}

{% block title %}Your interests — Watchtrivia{% endblock %}

{% block content %}
<div class="card">
  <h1>Your top interests</h1>

  {% if topics %}
    <p class="muted">
      Based on your watch history. Weights show each channel's share of your
      channel-tagged viewing.
    </p>

    <ul class="interest-list">
      {% for topic in topics %}
        <li class="interest">
          <span class="interest-label">{{ topic.label }}</span>
          <span class="interest-weight">{{ topic.weight|floatformat:1 }}</span>
          <div class="bar" role="img"
               aria-label="{{ topic.label }}: weight {{ topic.weight|floatformat:2 }}">
            {% widthratio topic.weight 1 100 as pct %}
            <div class="bar-fill" style="width: {{ pct }}%"></div>
          </div>
        </li>
      {% endfor %}
    </ul>

    <form method="post" action="{% url 'trivia:generate-quiz' %}"
          hx-post="{% url 'trivia:generate-quiz' %}"
          hx-target="#main"
          hx-select="#main"
          hx-push-url="true"
          hx-indicator="#quiz-spinner"
          hx-disabled-elt="find button">
      {% csrf_token %}
      <button type="submit" class="btn btn-primary">
        Generate my quiz
      </button>
      <span id="quiz-spinner" class="htmx-indicator spinner">Generating questions…</span>
    </form>

    <p class="muted small">
      Generating a quiz calls the Claude API and may take 10–30 seconds.
    </p>
  {% else %}
    <div class="empty-state">
      <p>You have no interests yet.</p>
      <a class="btn btn-primary" href="{% url 'trivia:upload' %}">
        Upload your watch history
      </a>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `hx-disabled-elt="find button"`

The Generate button makes up to three LLM calls, so it is the most likely button in the
app to be double-clicked. `hx-disabled-elt` disables the matched element for the duration
of the request and re-enables it afterwards.

`find button` is an HTMX *extended selector*: it searches within the element carrying the
attribute — the form — and returns the first matching descendant. Plain `"this"` would
resolve to the `<form>` itself, and disabling a form is not the same as greying out the
control the user is looking at.

HTMX also re-enables it when the request completes, including on error, so there is no
stuck-button state to handle.

#### `hx-indicator`

`hx-indicator="#quiz-spinner"` shows that element only while the request is in flight.
HTMX adds an `.htmx-request` class to the `<body>` while any request is active, so your
CSS controls the styling:

```css
.htmx-indicator { opacity: 0; transition: opacity 200ms; }
.htmx-request .htmx-indicator { opacity: 1; }
```

This is the correct UX for a slow server-side operation. A React SPA doing a 30-second
`fetch` has no built-in way to show progress; you would end up hand-rolling one.

#### The Weight Bar

```django
{% widthratio topic.weight 1 100 as pct %}
<div class="bar-fill" style="width: {{ pct }}%"></div>
```

`weight` is a **fraction**: `0.375` means 37.5%. Django has no multiply filter, so the
template cannot compute `0.375 * 100`, and the obvious workaround is wrong:

```django
<!-- WRONG: |floatformat:2 gives "0.38", + "00%" gives "0.3800%" -->
<div class="bar-fill" style="width: {{ topic.weight|floatformat:2 }}00%"></div>
```

That renders a bar `0.38` percent wide — a hairline. The page still looks plausible, which
is what makes it nasty. `{% widthratio topic.weight 1 100 %}` is the built-in answer: it
computes `weight / 1 * 100` and rounds to an integer, giving `38`, so the bar is
`width: 38%`.

> [!NOTE]
> Weights are share of total history, so with more channels than `top_n=5` they sum to
> slightly under 1.0 (Part 3 explains why) — hence the top bar landing around 38% rather
> than 100%. That is correct. If you want them to total 100%, pass `renormalize(ranked)`
> in `_process_upload`.

### 3. Quiz — `trivia/templates/trivia/quiz.html`

```django
{% extends "trivia/base.html" %}

{% block title %}Your quiz — Watchtrivia{% endblock %}

{% block content %}
<div class="card">
  <div class="quiz-header">
    <h1>Your quiz</h1>
    <p class="muted">
      {{ answered_count }} of {{ rows|length }} answered
      &middot; score {{ attempt.score }}
    </p>
  </div>

  {# Each question card brings its own <form>. They must NOT be wrapped in a
     single outer <form> -- see the note below. #}
  {% for row in rows %}
    {% include "trivia/partials/question_card.html" with row=row %}
  {% endfor %}

  <form method="post" action="{% url 'trivia:complete-attempt' attempt.id %}"
        class="finish-form">
    {% csrf_token %}
    <button type="submit" class="btn btn-primary">Finish quiz</button>
  </form>
</div>
{% endblock %}
```

> [!IMPORTANT]
> **There is no outer `<form>` around the question cards.** Each card is its own form,
> because each one posts to a different URL (`submit-answer` needs both `attempt_id` and
> `question_id`).
>
> HTML forbids nesting `<form>` inside `<form>`, and browsers do not report it — they
> silently drop the inner `<form>` tags during parsing. The result is that every question
> card's fields end up belonging to the *outer* form, so submitting question 3's answer
> actually POSTs to `complete-attempt` with no `question_id` and no `selected_answer`.
> No error, no traceback, just a quiz that does not work.
>
> This is worth internalising: **invalid nesting fails silently, not loudly.** If a form
> posts to the wrong URL, suspect nesting before you suspect the view.

> [!NOTE]
> This loops over `rows`, not over `questions`. That requires a two-line change to the
> view — see the note below the question card. The naive alternative is a
> `{{ answers|get_item:question.id }}` lookup in the template, which needs a **custom
> template filter that does not exist by default**. Avoid it: when a template needs a
> dict lookup, the data is usually shaped wrong for the template.

The corresponding change in `quiz()` in `trivia/views.py` — build the exact structure
the template wants:

```python
@login_required
def quiz(request, attempt_id):
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("user"),
        pk=attempt_id,
        user=request.user,
    )
    questions = list(attempt.questions.select_related("topic"))
    answers = {a.question_id: a for a in attempt.answers.all()}
    rows = [{"question": q, "answer": answers.get(q.id)} for q in questions]

    return render(
        request,
        "trivia/quiz.html",
        {"attempt": attempt, "rows": rows, "answered_count": len(answers)},
    )
```

Now the template does no lookup at all, and the pairing logic is testable Python rather
than template gymnastics.

> [!TIP]
> This is a genuinely useful lesson, not just a workaround. If you ever *do* need a dict
> lookup in many templates, write a filter in
> `trivia/templatetags/trivia_extras.py`:
>
> ```python
> from django import template
>
> register = template.Library()
>
>
> @register.filter
> def get_item(dictionary, key):
>     """Look up a key in a dict from a template, tolerating None."""
>     if not dictionary:
>         return None
>     try:
>         return dictionary.get(key)
>     except AttributeError:
>         return None
> ```
>
> Remember to create an empty `trivia/templatetags/__init__.py`, and load it with
> `{% load trivia_extras %}`. Reach for this only when you need it in several places.

### 4. The Question Card — `trivia/templates/trivia/partials/question_card.html`

```django
<article class="question-card {% if row.answer %}answered{% endif %}"
         id="question-{{ row.question.id }}">

  <p class="question-meta">{{ row.question.topic.label }}</p>
  <h2 class="question-text">{{ row.question.prompt_text }}</h2>

  <form method="post"
        action="{% url 'trivia:submit-answer' attempt.id row.question.id %}"
        hx-post="{% url 'trivia:submit-answer' attempt.id row.question.id %}"
        hx-target="#answer-feedback-{{ row.question.id }}"
        hx-swap="innerHTML"
        hx-disabled-elt="find button">
    {% csrf_token %}

    <div class="options">
      {% for option in row.question.options %}
        <label class="option">
          <input type="radio" name="selected_answer" value="{{ option }}"
                 {% if row.answer %}disabled{% endif %}>
          <span>{{ option }}</span>
        </label>
      {% endfor %}
    </div>

    <button type="submit" class="btn btn-primary"
            {% if row.answer %}hidden{% endif %}>
      Submit answer
    </button>
  </form>

  <div id="answer-feedback-{{ row.question.id }}" class="answer-feedback">
    {% if row.answer %}
      {% include "trivia/partials/answer_feedback.html" with answer=row.answer question=row.question %}
    {% endif %}
  </div>
</article>
```

Two details worth noting:

- **`{% if row.answer %}disabled{% endif %}` on the radios** means an already-answered
  question cannot be changed from the UI. The database constraint in Part 2 is the real
  guarantee; this is the honest interface.
- **`hx-disabled-elt="find button"`** disables the submit button during the request.
  Without it, a fast double-click sends two POSTs, and the second one hits the
  `already_answered` branch.

> [!NOTE]
> **A known rough edge, stated rather than hidden.** `hx-target` points at the small
> feedback `<div>`, so only that div is replaced. The card's radios and its Submit
> button are *not* re-rendered, so after answering the button stays visible and the
> radios stay enabled.
>
> Clicking Submit again is therefore harmless — the view returns the `already_answered`
> branch, and the feedback div updates to say so — but it is not as polished as the
> button disappearing.
>
> Two ways to fix it, both reasonable:
>
> 1. Target the whole card (`hx-target="#question-{{ row.question.id }}"`
>    `hx-swap="outerHTML"`) and have the view render the card again. Simple, costs a
>    full re-render of one card.
> 2. Have the feedback partial hide the button out of band with
>    `hx-swap-oob="true"` on a `<button id="submit-{{ row.question.id }}">` inside it.
>    Cheaper, but the markup is more subtle.
>
> The first is what most production HTMX code does. It is left out here because the
> simpler version already demonstrates the technique, and the wart is a genuine
> illustration that server-rendered UI has edge cases too — they just fail into a working
> fallback rather than a blank screen.

### 5. The Answer Feedback Partial — `trivia/templates/trivia/partials/answer_feedback.html`

This is what `submit_answer` returns, and what HTMX swaps in:

```django
{% if already_answered %}
  <div class="feedback feedback-info">
    You already answered <strong>{{ answer.selected_answer }}</strong>.
  </div>
{% elif form.errors %}
  <div class="feedback feedback-error">
    <p>Pick one of the options.</p>
  </div>
{% elif answer %}
  {% if answer.is_correct %}
    <div class="feedback feedback-correct">
      <strong>Correct!</strong>
    </div>
  {% else %}
    <div class="feedback feedback-wrong">
      <strong>Not quite.</strong> The answer was
      <strong>{{ answer.correct_answer }}</strong>.
    </div>
  {% endif %}

  <p class="muted small">
    {{ answered_count }} of {{ total_questions }} answered &middot;
    score {{ attempt.score }}
  </p>
{% endif %}
```

> [!IMPORTANT]
> `{{ answer.correct_answer }}` is rendered **after** the user has submitted an answer.
> That is correct — you always learn the answer once you have committed. The bug in the
> original plan was that nothing verified a committed answer before revealing it: any
> authenticated user could harvest the entire answer key by iterating question IDs. Part
> 4's ownership-scoped lookups and Part 7's isolation tests close that.

The `already_answered` branch is what makes resubmitting a *friendly* outcome rather than
a 500 from the unique constraint.

### 6. Results — `trivia/templates/trivia/results.html`

```django
{% extends "trivia/base.html" %}

{% block title %}Results — Watchtrivia{% endblock %}

{% block content %}
<div class="card results">
  <h1>You scored {{ correct }} / {{ total }}</h1>

  {% if answered %}
    <p class="muted">
      {{ attempt.completed_at|date:"j M Y, H:i" }} &middot;
      {% if correct == total %}Perfect run.{% else %}Nice effort.{% endif %}
      {% if unanswered %}&middot; {{ unanswered }} left unanswered{% endif %}
    </p>
  {% else %}
    <p class="muted">You did not answer any questions in this attempt.</p>
  {% endif %}

  <h2>Review</h2>
  <ol class="review-list">
    {% for answer in answers %}
      <li class="review-item {% if answer.is_correct %}is-correct{% else %}is-wrong{% endif %}">
        <p class="review-question">{{ answer.question.prompt_text }}</p>
        <p class="review-answer">
          You said <strong>{{ answer.selected_answer }}</strong>
          {% if not answer.is_correct %}
            &middot; correct answer was
            <strong>{{ answer.question.correct_answer }}</strong>
          {% endif %}
        </p>
      </li>
    {% empty %}
      <li class="muted">Nothing to review.</li>
    {% endfor %}
  </ol>

  <div class="actions">
    <a class="btn btn-primary" href="{% url 'trivia:interests' %}">Try again</a>
    <a class="btn" href="{% url 'trivia:upload' %}">Upload new history</a>
  </div>
</div>
{% endblock %}
```

`{% empty %}` handles an empty list — the review section shows "Nothing to review"
rather than a bare heading.

> [!NOTE]
> Three different numbers, and they are not interchangeable:
>
> | Variable | Meaning |
> |----------|---------|
> | `total` | Questions **in the attempt** — the denominator of the score |
> | `correct` | Answers with `is_correct=True` — the numerator |
> | `answered` | Answers actually submitted |
> | `unanswered` | `total - answered` |
>
> The review list loops over `answers`, so unanswered questions never appear in it. That
> is intentional: there is nothing to review for a question that was never seen. The
> count is surfaced separately so skipping is visible rather than invisible.
>
> Getting `total` wrong is an easy and quiet bug — basing the score on `answered` makes
> an abandoned quiz look like a perfect one, because 2 correct out of 2 answered reads as
> "2 / 2" when it was really 2 / 6.

---

## Progressive Enhancement

Everything above works **with JavaScript disabled**, because every HTMX form has a
real `method` and `action`:

| With JS | Without JS |
|---------|-----------|
| `hx-post` swaps `#main` | The form POSTs and the server returns a full page |
| Answer feedback appears inline | The page reloads with the result rendered |
| "Generate quiz" shows a spinner | The page reloads to `/quiz/<id>/` |

This is a real property of the design, and it is why the `@require_POST` and
`get_object_or_404` choices in Part 4 matter: a non-JS submission hits exactly the same
view, so it gets exactly the same validation and error handling.

Progressive enhancement is the practical test of whether a server-rendered design is
sound. If turning off JavaScript breaks the app, the server was not doing enough work.

> [!TIP]
> The original plan used `alert()` to show whether an answer was right. That is a
> blocking modal that interrupts the flow — the user clicks OK to dismiss a one-word
> result. Inline feedback, in place, is the correct pattern, and it is what a
> per-question `hx-target` gives you.

### `hx-boost` for Page-Level Transitions

Add `hx-boost="true"` to a container and all links and forms inside it become AJAX
requests automatically:

```django
<main id="main" class="container" hx-boost="true">
```

To exclude an element from boosting, add `hx-boost="false"` to it. The HTMX docs
recommend putting `hx-boost="true"` on `<body>`, with opt-outs on elements that should
hard-navigate.

> [!WARNING]
> `hx-boost` upgrades `<a href>` and `<form>`, but it does **not** handle file uploads
> the way you might expect. For the upload form, use an explicit `hx-post` with
> `hx-encoding="multipart/form-data"`, or leave it as a normal form — the upload is not
> frequent enough to need a partial swap.

---

## The Stylesheet

`trivia/static/trivia/style.css`:

```css
:root {
  --bg: #f7f8fa;
  --surface: #ffffff;
  --text: #1a1d21;
  --muted: #6b7280;
  --border: #e5e7eb;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --correct: #16a34a;
  --correct-bg: #f0fdf4;
  --wrong: #dc2626;
  --wrong-bg: #fef2f2;
  --radius: 8px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.6;
}

/* ---------- Layout ---------- */

.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1.5rem;
}
.site-header nav {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brand { font-weight: 700; font-size: 1.15rem; text-decoration: none; color: var(--text); }
.nav-links { display: flex; align-items: center; gap: 1rem; }
.nav-links a { color: var(--muted); text-decoration: none; }
.nav-links a:hover { color: var(--text); }

.container { max-width: 760px; margin: 2rem auto; padding: 0 1.5rem; }

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.75rem;
}

.site-footer {
  max-width: 760px;
  margin: 3rem auto 2rem;
  padding: 0 1.5rem;
  color: var(--muted);
  font-size: 0.85rem;
}

/* ---------- Typography ---------- */

h1 { font-size: 1.6rem; margin: 0 0 1rem; }
h2 { font-size: 1.15rem; margin: 1.5rem 0 0.75rem; }
.muted { color: var(--muted); }
.small { font-size: 0.85rem; }

/* ---------- Forms ---------- */

.field { margin-bottom: 1.25rem; }
.field label { display: block; font-weight: 600; margin-bottom: 0.35rem; }
.field input[type="file"] { width: 100%; padding: 0.6rem; border: 1px solid var(--border);
                            border-radius: 6px; background: #fafafa; }
.help-text { font-size: 0.85rem; color: var(--muted); margin: 0.35rem 0 0; }
.field-error { color: var(--wrong); font-size: 0.9rem; margin: 0.35rem 0 0; }

.btn {
  display: inline-block;
  padding: 0.6rem 1.1rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text);
  font-size: 0.95rem;
  cursor: pointer;
  text-decoration: none;
}
.btn:hover { background: #f3f4f6; }
.btn-primary { background: var(--primary); border-color: var(--primary); color: #fff; }
.btn-primary:hover { background: var(--primary-hover); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-link { background: none; border: none; color: var(--muted); padding: 0;
            text-decoration: underline; }
.inline-form { display: inline; }

/* ---------- Alerts ---------- */

.messages { max-width: 760px; margin: 1rem auto 0; padding: 0 1.5rem; }
.alert { padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 0.5rem; font-size: 0.95rem; }
.alert-success { background: var(--correct-bg); color: var(--correct); }
.alert-error   { background: var(--wrong-bg);   color: var(--wrong); }
.alert-warning { background: #fffbeb; color: #92400e; }

/* ---------- Interests ---------- */

.interest-list { list-style: none; padding: 0; margin: 1.5rem 0; }
.interest { margin-bottom: 1rem; }
.interest-label { font-weight: 600; }
.interest-weight { float: right; color: var(--muted); font-variant-numeric: tabular-nums; }
.bar { height: 8px; background: var(--border); border-radius: 999px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--primary); border-radius: 999px;
            transition: width 300ms ease; }

/* ---------- Quiz ---------- */

.question-card { border: 1px solid var(--border); border-radius: var(--radius);
                 padding: 1.25rem; margin-bottom: 1.25rem; }
.question-card.answered { background: #fafafa; }
.question-meta { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em;
                 color: var(--muted); margin: 0 0 0.35rem; }
.question-text { font-size: 1.05rem; margin: 0 0 1rem; }

.options { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }
.option {
  display: flex; align-items: center; gap: 0.6rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
}
.option:hover { background: #f9fafb; }
.option input { margin: 0; }

.feedback { padding: 0.7rem 0.9rem; border-radius: 6px; margin: 0.75rem 0 0; font-size: 0.95rem; }
.feedback-correct { background: var(--correct-bg); color: var(--correct); }
.feedback-wrong   { background: var(--wrong-bg);   color: var(--wrong); }
.feedback-info    { background: #eff6ff;           color: #1d4ed8; }
.feedback-error   { background: var(--wrong-bg);   color: var(--wrong); }

/* ---------- Results ---------- */

.results h1 { font-size: 2rem; }
.review-list { padding-left: 1.25rem; }
.review-item { margin-bottom: 1rem; }
.review-item.is-correct .review-question::before { content: "✓ "; color: var(--correct); }
.review-item.is-wrong   .review-question::before { content: "✗ "; color: var(--wrong); }
.review-question { font-weight: 600; margin: 0 0 0.25rem; }
.review-answer { margin: 0; font-size: 0.9rem; color: var(--muted); }
.actions { display: flex; gap: 0.75rem; margin-top: 1.5rem; }

/* ---------- HTMX ---------- */

.htmx-indicator { opacity: 0; transition: opacity 200ms; }
.htmx-request .htmx-indicator { opacity: 1; }
.htmx-request.htmx-indicator { opacity: 1; }
.spinner { display: inline-block; margin-left: 0.75rem; font-size: 0.9rem;
           color: var(--muted); }

.htmx-swapping { opacity: 0.4; transition: opacity 150ms; }
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
```

### The `htmx-indicator` Mechanism

`hx-indicator` does not show anything by itself. It marks an element, and **HTMX adds
`.htmx-request` to `<body>`** while a request is in flight. Your CSS combines them:

```css
.htmx-indicator { opacity: 0; }              /* hidden by default */
.htmx-request .htmx-indicator { opacity: 1; } /* shown while requesting */
```

This means **one CSS rule handles every indicator in the app**, including ones you add
later. The original plan's `disabled={status === "generating"}` and conditional
`{status === "generating" ? "Generating quiz..." : "Generate my quiz"}` handle the same
problem with state that has to be kept in sync manually.

---

## The Final Line Count

| | React version | This version |
|---|---|---|
| Components / templates | `App.jsx`, ~350 lines | 7 templates, ~180 lines |
| API client | `api.js` + interceptors + CSRF | none |
| State management | 5 `useState` hooks, 4-state machine | none |
| Build tooling | Vite, npm, Node.js | none |
| Dev servers | 2 | 1 |
| Dependencies | `axios` | `htmx.org` (14kb) |
| Extra server config | CORS, CORS credentials, CSRF trusted origins | none |
| Works without JS | No | Yes |

---

## When HTMX Is the Wrong Choice

HTMX is not universally right. Move to a heavier client when you have:

| Signal | Example |
|--------|---------|
| Heavy client-side state | Drag-and-drop, a canvas, a live editor |
| Real-time collaboration | A quiz room with multiple players |
| Offline support | A service worker caching the quiz for a flight |
| Optimistic UI at scale | Reordering a list with instant feedback |
| A public unauthenticated surface | SEO-driven marketing pages |
| Multiple clients | The same backend serving a mobile app |

If any of those arrive, build the JSON API in Part 10 and put a real client in front of
it. The `trivia` app does not need to change — which is the practical payoff of the
service layer in Part 3.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Template inheritance** | `{% extends %}` + `{% block %}` avoids duplicating layout |
| **`{% url %}`** | Reverse a URL by name — never hardcode paths |
| **Context processors** | `user` and `messages` available in every template |
| **Messages framework** | Flash messages that survive one redirect |
| **HTMX** | Swap HTML fragments over `fetch()` using HTML attributes |
| **`hx-target` / `hx-swap`** | Where to put the response, and how |
| **`hx-select`** | Which part of a full-page response to take — required with `hx-target` |
| **`hx-indicator`** | Loading UI, driven by one CSS rule |
| **`hx-disabled-elt`** | Prevents double-submits without state |
| **Partial templates** | Reusable fragments in `partials/` |
| **Progressive enhancement** | Every `hx-post` form also works as a plain form |
| **Template filters** | `floatformat`, `length`, `date` shape values for display |

---

**→ Continue to [Part 9: Running It All](./09_running_and_next_steps.md)**
# Part 9: Running It All & What's Next

---

## The Terminal Layout

**One terminal.** That is the entire operational difference from the original plan,
which required two:

```
┌─────────────────────────────────────────────┐
│  Terminal 1: Django                         │
│                                             │
│  cd watchtrivia/backend                     │
│  source .venv/bin/activate                  │
│  python manage.py runserver                 │
│                                             │
│  → http://localhost:8000                    │
│    /            the app                     │
│    /upload/     upload watch history         │
│    /accounts/   log in                      │
│    /admin/      admin site                  │
└─────────────────────────────────────────────┘
```

No second dev server. No `npm run dev`. No proxy configuration.

---

## First Run

```bash
cd watchtrivia/backend
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 1. Confirm the environment file exists
cat .env
# ANTHROPIC_API_KEY=sk-ant-...
# DJANGO_SECRET_KEY=...
# DEBUG=True
# ANTHROPIC_MODEL=claude-sonnet-4-6
# WATCHTRIVIA_MOCK_LLM=False

# 2. Apply migrations
python manage.py migrate

# 3. Create a user to log in with
python manage.py createsuperuser

# 4. Confirm unmigrated model changes are absent (should print "No changes detected")
python manage.py makemigrations --check --dry-run

# 5. Run the test suite before you start
python manage.py test trivia

# 6. Start the server
python manage.py runserver
```

Visit `http://localhost:8000/`. You are redirected to `/accounts/login/`. Log in and you
land on your (empty) interests page.

> [!TIP]
> **Run the tests before the server.** If 76 tests pass, every moving part is working.
> Then when something breaks in the browser, you know it is your recent edit, not a
> pre-existing bug.

---

## Development Without an API Key

If you have no Anthropic key, or no credit, set this in `.env`:

```env
WATCHTRIVIA_MOCK_LLM=True
```

Restart the server. The entire flow — upload, interests, generate quiz, answer, score —
works with generated placeholder questions and zero network calls.

Toggle it off when you want to test real generation. This is why Part 3 built mock mode
into the service rather than leaving it as a test-only concern.

---

## Testing the Sample File

If you have no Takeout export, use the sample:

```bash
# The file ships with the tutorial at sample-data/watch-history.json
```

Or generate one covering 6 channels so the ranker has something to rank:

```python
# python manage.py shell
import json, random
from datetime import datetime, timedelta, timezone

CHANNELS = [
    ("F1 Official", 30),
    ("Veritasium", 18),
    ("Corey Schafer", 14),
    ("Fireship", 9),
    (" Kurzgesagt", 6),
    ("Some Random Vlog", 3),
]

random.seed(42)                      # reproducible
now = datetime.now(timezone.utc)
entries = []

for channel, count in CHANNELS:
    for i in range(count):
        entries.append({
            "header": "YouTube",
            "title": f"Watched {channel} episode {i + 1}",
            "titleUrl": f"https://www.youtube.com/watch?v=vid{i}{count}",
            "subtitles": [{"name": channel}],
            "time": (now - timedelta(days=i * 3)).isoformat().replace("+00:00", "Z"),
            "products": ["YouTube"],
        })

random.shuffle(entries)

with open("../sample-data/watch-history.json", "w") as fh:
    json.dump(entries, fh, indent=2)

print(f"Wrote {len(entries)} entries across {len(CHANNELS)} channels")
```

(The shipped `sample-data/watch-history.json` is exactly what that script produces, so
you only need one or the other.)

Upload it and you should see **five** interest bars — `top_n=5` caps the list — with
"F1 Official" highest at a weight of `0.375`.

You can confirm the expected numbers without the browser:

```bash
python -c "
import json, collections
d = json.load(open('../sample-data/watch-history.json'))
c = collections.Counter(e['subtitles'][0]['name'] for e in d)
for k, v in c.most_common(5): print(f'{k:20s} {v:3d}  {v/len(d):.3f}')
"
```

---

## The Full Flow, Manually

1. **Log in** at `/accounts/login/`
2. **Upload** `watch-history.json` at `/upload/`
   → Expect: "Imported 80 videos and found 5 interests."
3. **Interests** at `/` → five bars, F1 Official highest (0.375)
4. **Generate my quiz** → a 10–30 second wait with a spinner
   → Expect: redirect to `/quiz/1/` with 6 questions (3 topics × 2)
5. **Answer a question** → inline green or red feedback, no page reload
6. **Answer the same one again** → "You already answered …", score unchanged
7. **Finish quiz** → `/results/1/` with score and full review
8. **Try again** → a new attempt, questions regenerate, previous attempt still in history

### Things to Verify Deliberately

| Check | Expected |
|-------|----------|
| Upload `Takeout.zip` (not `.json`) | "That does not look like a .json file" |
| Upload `subscriptions.json` | "No YouTube videos found in that file" |
| Upload a text file renamed `.json` | "That file is not valid JSON" |
| Visit `/` logged out | Redirect to `/accounts/login/` |
| Log in, then log out, then visit `/quiz/1/` | Redirect to login |
| Second user, try `/quiz/1/` where 1 is another user's attempt | **404, not 403** |
| Answer the same question 5 times | Score stays at 1 |
| Disable JavaScript, submit an answer | Page reloads, still works |
| Set `WATCHTRIVIA_MOCK_LLM=True`, clear the API key | Quiz still generates |

The last two are the ones that prove the architecture is doing what it claims.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'django'`

The virtual environment is not active. Your prompt should start with `(.venv)`.

```bash
source .venv/bin/activate     # macOS / Linux
.venv\Scripts\activate        # Windows
```

### `TemplateDoesNotExist`

The template is in the wrong place or `APP_DIRS` is off. It should be at
`trivia/templates/trivia/upload.html`, and `INSTALLED_APPS` must contain `"trivia"`.

For `registration/login.html`, the path is
`trivia/templates/registration/login.html` — note the app is `trivia` but the
subdirectory is `registration`, because that is the namespace Django's auth views look
in.

### `Forbidden (403) / CSRF verification failed`

A `<form method="post">` is missing `{% csrf_token %}`. Every POST form in this app needs
it.

If the *HTMX* request fails instead, the `htmx:configRequest` script in `base.html` is
missing or malformed. Check the browser console.

### The generate button does nothing

In order of likelihood:

1. `ANTHROPIC_API_KEY` is unset and `WATCHTRIVIA_MOCK_LLM` is not `True` — check the
   messages area, which should say so
2. HTMX did not load — check the Network tab for the 404 on `htmx.org`
3. The form is missing `{% csrf_token %}`

### `400 Bad Request` and a CSRF error in the console

You are serving the page over HTTPS but Django does not trust the origin, or you have
`DEBUG=False` with `ALLOWED_HOSTS` set to only `localhost` and are browsing via a
tunnel hostname. Set `ALLOWED_HOSTS` to include the hostname you are actually using.

### Interests show but generating hangs

The LLM call is synchronous. Three topics × up to 30 seconds each is a real wait. If it
exceeds a minute, check for rate limiting on the Anthropic dashboard.

This is the known limitation of not using a task queue — see the scope note below.

### `no such table: trivia_question`

Migrations were not applied.

```bash
python manage.py migrate
```

---

## Deploying

### Checklist

| Item | Development | Production |
|------|-------------|------------|
| `DEBUG` | `True` | **`False`** |
| `SECRET_KEY` | dev fallback | random, from the environment |
| `ALLOWED_HOSTS` | localhost | your real domain |
| `DATABASES` | SQLite | PostgreSQL |
| Static files | Django serves them | `collectstatic` + a web server |
| WSGI server | `runserver` | Gunicorn |
| HTTPS | no | yes |
| `WATCHTRIVIA_MOCK_LLM` | your choice | `False` |
| `ANTHROPIC_API_KEY` | `.env` | secrets manager |

### PostgreSQL

```bash
pip install psycopg[binary]
```

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "watchtrivia"),
        "USER": os.environ.get("POSTGRES_USER", "watchtrivia"),
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}
```

Migrations run unchanged. This is the payoff of the ORM over raw SQL.

### Static Files and Gunicorn

```bash
pip install gunicorn
python manage.py collectstatic
```

```bash
gunicorn watchtrivia.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

> [!IMPORTANT]
> `--workers 3` means three processes. **Each LLM call blocks a worker for up to 30
> seconds.** Three concurrent quiz generations exhaust the pool, and users see 502s.
>
> For a real deployment, either raise the worker count substantially (cheap; each worker
> is idle most of the time) or — the correct fix — move generation to a background task.
> With `--workers 12` a small site handles bursts comfortably. With background workers,
> it handles any burst.

### Environment Variables in Production

```bash
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
export DEBUG=False
export ALLOWED_HOSTS=watchtrivia.example.com
export ANTHROPIC_API_KEY=sk-ant-...
export POSTGRES_PASSWORD=...
```

Do not ship a `.env` file to production. Use your platform's secret store.

---

## What This Plan Does Not Build

An honest inventory, because the original plan's biggest sin was promising things it
never delivered.

| Not built | Why | What it would take |
|-----------|-----|--------------------|
| **Background task queue** | The LLM call blocks the request | Celery + Redis, or a managed queue; `generate_quiz` becomes a 202 + polling |
| **TF-IDF / K-Means clustering** | Channel frequency is sufficient and interpretable | Optional extension given in Part 3; `scikit-learn` |
| **JSON API** | Not needed by a server-rendered frontend | Part 10 |
| **User registration** | This is a private tool | A signup view, email verification, password reset email |
| **Password reset by email** | Users are created by an admin | `django.contrib.auth` views + an email backend |
| **Pagination** | A Takeout export yields 5 interests, not 5,000 | `Paginator` on the admin and any list view |
| **Rate limiting** | Fine for a private tool | DRF throttling, or `django-ratelimit` |
| **Email verification / 2FA** | Overkill for this scope | `django-otp` or an external service |
| **Internationalisation** | English only | `django.po` files, `{% trans %}` |
| **Model custom user** | Django's default is fine | Only if you need profile fields |

The original plan's Part 1 stack table promised Celery, Redis, scikit-learn, and
djangorestframework. It delivered none of them, and a reader who followed it end to end
would have installed four packages they never used.

**The background task queue is the one real gap.** If you take this app further, that is
the first thing to add, and the natural shape is:

```python
# generate_quiz becomes:
#   create attempt → return 202 + attempt_id
#   enqueue task
# frontend polls GET /api/attempts/<id>/status/ every 2s
```

HTMX makes even that pleasant: `hx-get="..." hx-trigger="every 2s" hx-swap="outerHTML"`
on a status fragment that swaps itself for the quiz when ready. Roughly fifteen lines of
template, and no JavaScript.

---

## Where to Go Next

### Deepen the Django

- **Custom user model** — decide now if you ever will, because it is painful later
- **Signals** — `post_save` / `pre_delete` for cross-cutting behaviour
- **Managers** — encapsulate reusable querysets on the model
- **`select_related` / `prefetch_related`** — read the query counts, fix N+1s
- **Full-text search** — PostgreSQL's `SearchVector`, or Elasticsearch
- **Django REST Framework** — Part 10

### Deepen the frontend

- HTMX extensions: `json-enc`, `ws-sse` for live updates
- Hyperscript: small client-side logic without a framework
- Optimistic UI with `hx-swap-oob`
- A design system: this CSS is deliberately minimal

### Deepen the AI

- Prompt caching for the system prompt
- Streaming responses with Server-Sent Events
- Difficulty calibration based on answer history
- A `Question` model with `difficulty`, `times_asked`, `times_correct` — so you can
  generate *better* questions over time rather than the same ones repeatedly

### The Most Valuable Next Step

Write a management command that generates a batch of questions in advance:

```bash
python manage.py pregenerate_quizzes --days 7
```

It warms a cache so users never wait 30 seconds, and it gives you a natural place to add
retry logic, rate-limit handling, and progress reporting — all the things that a
synchronous request handler does badly.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`runserver`** | Development only; single-threaded, restarts on change |
| **`makemigrations --check`** | CI guard for unmigrated model changes |
| **`WATCHTRIVIA_MOCK_LLM`** | Test the full flow with no API key and no cost |
| **Progressive enhancement** | The app must work with JavaScript disabled |
| **`collectstatic`** | Gather static files for a production web server |
| **Gunicorn `--workers`** | Each blocking LLM call consumes a worker |
| **`DEBUG=False`** | Mandatory in production; error pages expose secrets otherwise |
| **Secrets manager** | Environment variables in production, never a `.env` file |
| **Scope honesty** | Document what is not built, and why |

---

**→ Continue to [Part 10: Optional JSON API with DRF](./10_optional_drf_api.md)**
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
