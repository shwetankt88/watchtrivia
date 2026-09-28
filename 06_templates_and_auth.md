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
