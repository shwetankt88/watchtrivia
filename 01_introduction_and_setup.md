# Watchtrivia — The Complete Tutorial

## Part 1: Introduction & Project Setup

---

### What is Watchtrivia?

Watchtrivia is a full-stack web application that:

1. Accepts a user's **YouTube watch history** (exported via Google Takeout)
2. **Analyzes** that history to identify their top interests
3. Uses an **LLM (Claude)** to generate personalized trivia questions
4. Lets the user **take a quiz** and tracks their score

By the end of this tutorial you will have built:

| Layer | Technology | What it does |
|-------|-----------|--------------|
| **Backend** | Django + Django REST Framework | Models, business logic, REST API, admin panel |
| **Frontend** | React (Vite) | Single-page app that talks to the API |
| **AI/ML** | Anthropic Claude API + scikit-learn | Question generation + interest clustering |
| **Database** | SQLite (dev) → PostgreSQL (prod) | Persistent storage |
| **Task Queue** | Celery + Redis | Background processing for slow LLM calls |

> [!NOTE]
> This tutorial is modeled after Django's official "Writing your first Django app" series.
> Each part builds on the last. Don't skip ahead — the concepts compound.

---

### What You Will Learn

#### Backend Development (Django)
- How Django's **MTV (Model-Template-View)** architecture works and how it compares to MVC
- **ORM (Object-Relational Mapping)** — how Python classes become database tables
- **Migrations** — version control for your database schema
- **The Admin Site** — Django's built-in CRUD interface
- **Django REST Framework (DRF)** — serializers, viewsets, permissions, authentication
- **Service layer pattern** — keeping business logic out of views
- **Testing** — unit tests, integration tests, API tests
- **Security** — CSRF, CORS, user isolation, input validation

#### Frontend Development (React)
- **Component architecture** — building UIs from reusable pieces
- **State management** with `useState` and `useEffect`
- **API integration** with Axios
- **Conditional rendering** — showing different UI based on app state
- **Form handling** — file uploads, user input

#### Full-Stack Integration
- How **REST APIs** connect frontend and backend
- **CORS (Cross-Origin Resource Sharing)** — why it exists and how to configure it
- **Session-based authentication** vs **Token-based authentication**
- **Environment variables** — managing secrets across environments
- **Deployment** — making it production-ready

---

### Prerequisites

Before starting, ensure you have:

| Tool | Minimum Version | Check Command | Purpose |
|------|----------------|---------------|---------|
| Python | 3.10+ | `python --version` | Backend runtime |
| pip | Latest | `pip --version` | Python package manager |
| Node.js | 18+ | `node --version` | Frontend runtime |
| npm | 9+ | `npm --version` | JavaScript package manager |
| Git | Any | `git --version` | Version control |
| A text editor | — | — | VS Code recommended |

You'll also need an **Anthropic API key** (for Claude). Sign up at [console.anthropic.com](https://console.anthropic.com).

---

### Understanding the Architecture Before We Start

Before writing a single line of code, let's understand what we're building and why each piece exists.

```
┌─────────────────────────────────────────────────────────┐
│                    THE USER'S BROWSER                    │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │           React Frontend (port 5173)              │  │
│  │                                                   │  │
│  │  Upload Page → Interests Page → Quiz Page         │  │
│  │                                                   │  │
│  │  Communicates via HTTP (axios) ──────────────┐    │  │
│  └───────────────────────────────────────────────┘   │  │
│                                                  │      │
└──────────────────────────────────────────────────│──────┘
                                                   │
                                          HTTP/JSON│
                                                   │
┌──────────────────────────────────────────────────▼──────┐
│              Django Backend (port 8000)                  │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │   URL Conf   │→│    Views     │→│  Serializers   │  │
│  │  (routing)   │  │ (endpoints) │  │ (JSON ↔ Model)│  │
│  └─────────────┘  └──────┬───────┘  └───────────────┘  │
│                          │                              │
│                   ┌──────▼───────┐                      │
│                   │   Services   │                      │
│                   │ (biz logic)  │                      │
│                   └──────┬───────┘                      │
│                          │                              │
│                   ┌──────▼───────┐   ┌──────────────┐   │
│                   │    Models    │   │  Admin Site   │   │
│                   │  (ORM/data) │   │  (built-in)   │   │
│                   └──────┬───────┘   └──────────────┘   │
│                          │                              │
└──────────────────────────│──────────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │   Database   │
                    │   (SQLite)   │
                    └──────────────┘
```

#### Why Django? (vs Flask, FastAPI, Express)

| Framework | Strengths | Weaknesses for this project |
|-----------|-----------|---------------------------|
| **Django** | Admin site, ORM, auth, migrations — all built in | Heavier, more opinionated |
| Flask | Lightweight, flexible | You'd build admin, ORM, auth, migrations yourself |
| FastAPI | Async-first, auto-docs | No admin site, no ORM, less ecosystem |
| Express (Node) | Same language as frontend | No ORM, no admin, no batteries |

Django is the right choice here because Watchtrivia needs **user accounts, an admin panel, database migrations, and a REST API** — Django gives you all of these out of the box.

#### What is a REST API?

REST (Representational State Transfer) is a set of conventions for how a client (frontend) talks to a server (backend) over HTTP:

| HTTP Method | Meaning | Example |
|------------|---------|---------|
| `GET` | Read data | `GET /api/interests/` → list all interests |
| `POST` | Create data | `POST /api/upload-history/` → upload watch history |
| `PUT` | Replace data | `PUT /api/interests/1/` → replace interest #1 |
| `PATCH` | Update part of data | `PATCH /api/interests/1/` → update one field |
| `DELETE` | Delete data | `DELETE /api/interests/1/` → delete interest #1 |

The frontend sends an HTTP request with JSON data; the backend responds with JSON. They never share memory or function calls directly — they communicate entirely through this HTTP+JSON contract.

---

### Projects vs. Apps — Django's Organizational Model

This is one of the first things that confuses newcomers, so let's be crystal clear:

- A **project** is the entire website — it holds settings (`settings.py`), the root URL configuration (`urls.py`), and the WSGI/ASGI entry point. You typically have **one project**.

- An **app** is a self-contained module that does one thing. A project can contain **many apps**. Apps are designed to be reusable — in theory, you could copy your `trivia` app into a different Django project and it would work.

```
watchtrivia/              ← the project root
├── backend/
│   ├── manage.py         ← Django's command-line utility
│   ├── watchtrivia/      ← the project package (settings, root URLs)
│   │   ├── __init__.py
│   │   ├── settings.py   ← all configuration lives here
│   │   ├── urls.py       ← root URL routing
│   │   ├── wsgi.py       ← entry point for production servers
│   │   └── asgi.py       ← entry point for async servers
│   └── trivia/           ← our app
│       ├── __init__.py
│       ├── admin.py      ← admin site registration
│       ├── apps.py       ← app configuration
│       ├── models.py     ← database models (the M in MTV)
│       ├── views.py      ← request handlers (the V in MTV)
│       ├── serializers.py ← JSON ↔ Model translation (DRF)
│       ├── urls.py       ← app-level URL routing
│       ├── services/     ← business logic (our addition)
│       │   ├── __init__.py
│       │   ├── takeout_parser.py
│       │   ├── interest_ranker.py
│       │   └── llm_service.py
│       ├── tests/        ← test suite
│       │   ├── __init__.py
│       │   ├── test_interest_ranker.py
│       │   └── test_models_and_api.py
│       └── migrations/   ← auto-generated schema changes
│           └── __init__.py
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx       ← main React component
        ├── App.css
        └── api.js        ← Axios HTTP client
```

> [!IMPORTANT]
> The `services/` directory is **not** a Django convention — it's a design pattern we're choosing.
> Django's official tutorial puts logic directly in views. That works for small apps,
> but Watchtrivia has parsing, ranking, and LLM calls — putting all of that in views
> would make them bloated and untestable. The service layer keeps views thin.

---

### Step 1: Create the Project Directory

Open your terminal and run:

```powershell
# You should already have this from git init
cd C:\Users\Administrator\OneDrive\Desktop\watchtrivia
mkdir backend
cd backend
```

### Step 2: Create a Virtual Environment

A **virtual environment** is an isolated Python installation. Without it, every Python project on your machine shares the same packages — upgrade one project's Django and you might break another.

```powershell
python -m venv venv
```

This creates a `venv/` folder containing a fresh Python installation. Activate it:

```powershell
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (Command Prompt)
venv\Scripts\activate.bat

# macOS / Linux
source venv/bin/activate
```

> [!TIP]
> You'll know it's active when your terminal prompt starts with `(venv)`.
> **Every time you open a new terminal**, you need to activate it again.
> Every `pip install` and `python` command in this tutorial assumes the venv is active.

#### What's inside the venv?

```
venv/
├── Include/        ← C header files (for compiling C extensions)
├── Lib/
│   └── site-packages/  ← this is where pip installs packages
├── Scripts/        ← python.exe, pip.exe, activate scripts
└── pyvenv.cfg      ← tells Python "this is a virtual environment"
```

When you run `python` with the venv active, it uses `venv/Scripts/python.exe` instead of your system Python. When you `pip install django`, it goes into `venv/Lib/site-packages/django/`, not your global Python.

### Step 3: Install Dependencies

```powershell
pip install django djangorestframework django-cors-headers python-dotenv anthropic scikit-learn
```

Let's understand **why each package exists**:

| Package | Purpose | Layer |
|---------|---------|-------|
| `django` | The web framework — models, views, admin, ORM, auth | Backend core |
| `djangorestframework` | Adds REST API capabilities to Django — serializers, viewsets, API views | API layer |
| `django-cors-headers` | Handles CORS headers so the React frontend can call the Django backend | Integration |
| `python-dotenv` | Loads `.env` files into environment variables (for API keys, secrets) | Configuration |
| `anthropic` | Official Python SDK for the Claude API | AI/ML |
| `scikit-learn` | Machine learning library (for TF-IDF + K-Means interest ranking) | AI/ML |

#### Freeze your dependencies

After installing, save the exact versions so anyone else can reproduce your environment:

```powershell
pip freeze > requirements.txt
```

This creates a file like:

```
Django==5.1.5
djangorestframework==3.15.2
django-cors-headers==4.6.0
...
```

Anyone else can now run `pip install -r requirements.txt` and get the **exact same versions**.

> [!WARNING]
> Never commit `venv/` to Git — it's large and platform-specific.
> Only commit `requirements.txt`. Add `venv/` to your `.gitignore`.

### Step 4: Create the Django Project

```powershell
django-admin startproject watchtrivia .
```

**The trailing `.` is critical.** Without it:

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
| `manage.py` | Django's command-line Swiss Army knife. You'll use it constantly: `manage.py runserver`, `manage.py migrate`, `manage.py createsuperuser`, etc. |
| `watchtrivia/__init__.py` | Makes `watchtrivia/` a Python package (can be empty) |
| `watchtrivia/settings.py` | **The single most important file.** Every Django configuration lives here: database, installed apps, middleware, auth, static files, etc. |
| `watchtrivia/urls.py` | The root URL configuration — the "table of contents" that maps URL patterns to views |
| `watchtrivia/wsgi.py` | **Web Server Gateway Interface** entry point. Production servers (Gunicorn, uWSGI) use this to talk to Django. |
| `watchtrivia/asgi.py` | **Asynchronous Server Gateway Interface** entry point. For WebSockets, long-polling, and async views. |

#### Deep Dive: How `manage.py` works

When you run `python manage.py runserver`, here's what happens:

1. Python executes `manage.py`
2. `manage.py` sets the `DJANGO_SETTINGS_MODULE` environment variable to `watchtrivia.settings`
3. It calls `django.core.management.execute_from_command_line()`
4. Django loads your settings, discovers your apps, and runs the requested command
5. For `runserver`, it starts a lightweight development HTTP server on port 8000

> [!CAUTION]
> `manage.py runserver` is a **development server only**. It's single-threaded, not
> security-hardened, and restarts on every code change. Never use it in production.
> Production uses Gunicorn or uWSGI (covered in the deployment section).

### Step 5: Create the Trivia App

```powershell
python manage.py startapp trivia
```

This creates:

| File | Purpose |
|------|---------|
| `trivia/__init__.py` | Makes it a Python package |
| `trivia/admin.py` | Where you register models with the admin site |
| `trivia/apps.py` | App configuration (name, label, etc.) |
| `trivia/models.py` | Database models — the heart of your app |
| `trivia/tests.py` | Test file (we'll replace this with a `tests/` package) |
| `trivia/views.py` | Request handlers |
| `trivia/migrations/` | Auto-generated database migration files |

> [!NOTE]
> **Don't name your app `quiz`** — it collides with Python's built-in `quiz` module.
> Django will refuse to create it. `trivia` avoids this entirely.

### Step 6: Verify the Installation

```powershell
python manage.py runserver
```

Visit `http://localhost:8000/` in your browser. You should see Django's "The install worked successfully!" rocket page.

**Congratulations — you have a running Django project.** It doesn't do anything yet, but the entire framework is loaded and operational.

Press `Ctrl+C` to stop the server.

### Step 7: Create .gitignore

Before committing anything, create a `.gitignore` in the project root:

```gitignore
# Python
venv/
__pycache__/
*.pyc
*.pyo
db.sqlite3

# Environment
.env
*.env

# IDE
.vscode/
.idea/

# Node
node_modules/
dist/

# OS
.DS_Store
Thumbs.db
```

### Step 8: Create .env File

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=your-key-here
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
```

> [!WARNING]
> **Never commit `.env` to Git.** It contains secrets. The `.gitignore` above
> already excludes it. If you accidentally commit it, rotate your keys immediately.

---

### Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Virtual environment** | Isolated Python installation per project |
| **`requirements.txt`** | Pinned dependency versions for reproducibility |
| **`manage.py`** | Django CLI — run server, create migrations, run tests |
| **Project** | Top-level configuration (settings, root URLs) |
| **App** | Self-contained feature module (models, views, URLs) |
| **`settings.py`** | Single source of truth for all Django config |

---

**→ Continue to [Part 2: Models and the Admin Site](./02_models_and_admin.md)**
