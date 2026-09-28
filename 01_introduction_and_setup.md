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
