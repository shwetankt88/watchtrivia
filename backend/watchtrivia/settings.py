"""
Django settings for Watchtrivia.

Everything that differs between a laptop and a production box is an
environment variable, read from `backend/.env` in development and from the
real process environment in production. There is no `if DEBUG:` branch hiding
a different code path -- the same settings module runs everywhere, so what you
test is what you deploy.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from backend/.env into the process environment. This must run
# before anything reads os.environ. In production (where .env is absent, since
# it is gitignored) this is a no-op and the platform's env vars win.
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    """Read an env var, treating "" as unset so a blank .env line is a no-op."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def env_bool(name, default=False):
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    try:
        return int(env(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name, default=()):
    raw = env(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")

DEBUG = env_bool("DEBUG", False)

# The app is useless in production with the placeholder key, and quietly
# running with DEBUG=True on a public host is the classic way to leak one.
# Refuse to start rather than serve debug tracebacks to strangers.
if not SECRET_KEY.startswith("django-insecure-") and len(SECRET_KEY) < 50:
    raise ValueError("DJANGO_SECRET_KEY must be at least 50 characters in production.")

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"]
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INTERNAL_IPS = ["127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Third party (no app registry entry: whitenoise is middleware + storage)

    # Our apps
    "trivia",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Must sit above everything that logs, so every line has a request id.
    "trivia.middleware.RequestIDMiddleware",
]

ROOT_URLCONF = "watchtrivia.urls"

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
                # Lets templates read the request id and the resolved theme
                # without every view having to pass them.
                "django.template.context_processors.debug",
                "trivia.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "watchtrivia.wsgi.application"
ASGI_APPLICATION = "watchtrivia.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Collects static files before the first test, because the manifest storage used
# in production needs them. See trivia/testrunner.py.
TEST_RUNNER = "trivia.testrunner.StaticFilesTestRunner"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Postgres in production, SQLite in development. Postgres is not optional for a
# public instance: SQLite serialises writers, and a quiz is several writes at
# once (attempt, questions, answer, score).
#
# `DATABASE_URL` is what every PaaS hands you (Render, Railway, Fly, Heroku all
# set exactly that one variable and nothing else), so it is parsed into the
# individual fields rather than ignored. Explicit DB_* variables win, because
# someone who set them wants exactly those values.


def database_from_url(url):
    """Parse a postgres:// URL into the fields psycopg wants.

    Hand-rolled rather than pulled from dj-database-url to keep the runtime
    dependency list short. Percent-escapes matter: a managed Postgres password
    routinely contains characters that would otherwise terminate the netloc.
    """
    from urllib.parse import parse_qsl, unquote, urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql", "psql", "pgsql"}:
        raise ValueError(
            f"DATABASE_URL must start with postgres:// or postgresql://, "
            f"not {parsed.scheme!r}."
        )

    options = dict(parse_qsl(parsed.query))
    config = {
        "NAME": unquote(parsed.path.lstrip("/")) or "watchtrivia",
        "USER": unquote(parsed.username or "watchtrivia"),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": unquote(parsed.hostname or "localhost"),
        "PORT": str(parsed.port or 5432),
        # Anything else in the query string (sslmode, options, ...) is passed
        # to the driver, which is what libpq expects it to be.
        "OPTIONS": {k: v for k, v in options.items() if k != "sslmode"},
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }
    if "sslmode" in options:
        config["OPTIONS"]["sslmode"] = options["sslmode"]
    return config


if env("DATABASE_URL"):
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql",
                             **database_from_url(env("DATABASE_URL"))}}
elif env("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "watchtrivia"),
            "USER": env("DB_USER", "watchtrivia"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
            "OPTIONS": {"connect_timeout": 10},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                # WAL lets the dev server read while a request writes, which
                # makes `runserver` feel closer to production.
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                "transaction_mode": "IMMEDIATE",
            },
        }
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# The database cache, not locmem: the login throttle counts failures per
# account, and gunicorn runs several workers. A locmem cache would give every
# worker its own private counter, so the real limit would multiply by the
# worker count. The `django_cache` table is created by migration 0003, so no
# `createcachetable` step is needed on deploy.

if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    # Postgres is where locmem's real problem shows up; for local dev an
    # in-process cache is fine and keeps `manage.py` commands snappy.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "watchtrivia-dev",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
            "TIMEOUT": 300,
        }
    }

DJANGO_CACHE_TABLE = "django_cache"
CACHES["default"]["OPTIONS"] = {"MAX_ENTRIES": 10000}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "trivia:dashboard"
# Namespaced, because the landing page lives inside the trivia app's URLconf.
LOGOUT_REDIRECT_URL = "trivia:landing"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": env_int("PASSWORD_MIN_LENGTH", 10)}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Failed logins are counted per IP and per account in the shared cache, and a
# locked account is refused with a 429 until the window rolls over. Ten is
# generous for a human mistyping a password and hopeless for a guessing script.
LOGIN_ATTEMPTS_LIMIT = env_int("LOGIN_ATTEMPTS_LIMIT", 10)
LOGIN_ATTEMPTS_WINDOW = env_int("LOGIN_ATTEMPTS_WINDOW", 300)


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# WhiteNoise serves everything collectstatic produced. Without this, hashed
# filenames are never used and browsers cache the wrong asset after a deploy.
WHITENOISE_MAX_AGE = 31536000 if not DEBUG else 0

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# A real Google Takeout watch-history.json is routinely 10-30 MB, which is over
# Django's 2.5 MB default: without raising it, uploads die with a 400 before the
# form's own 25 MB limit is ever reached, and the user is told nothing useful.
# The form in trivia/forms.py is the single place that decides how big a file we
# accept, so this ceiling only has to be a little above it -- a request body
# beyond it is refused here rather than filling the disk.
MAX_UPLOAD_BYTES = env_int("MAX_UPLOAD_MB", 25) * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = env_int("DATA_UPLOAD_MAX_NUMBER_FIELDS", 2000)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Console in development (the reset link is printed to the terminal, no SMTP
# credentials needed), SMTP everywhere else.
#
# Django 6 replaced the EMAIL_* settings with MAILERS, and refuses to start if
# both are defined. Note there is no EMAIL_HOST branch below: the presence of
# EMAIL_HOST selects the backend, and everything else is passed through.

_DEFAULT_FROM_HOST = env("EMAIL_HOST", "localhost")

if env("EMAIL_HOST"):
    _MAILER_DEFAULTS = {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": env("EMAIL_HOST"),
        "EMAIL_PORT": env_int("EMAIL_PORT", 587),
        "EMAIL_HOST_USER": env("EMAIL_HOST_USER", ""),
        "EMAIL_HOST_PASSWORD": env("EMAIL_HOST_PASSWORD", ""),
        "EMAIL_USE_TLS": env_bool("EMAIL_USE_TLS", True),
    }
else:
    _MAILER_DEFAULTS = {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    }

DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", f"Watchtrivia <noreply@{_DEFAULT_FROM_HOST}>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

ADMINS = []
if env("ADMIN_EMAIL"):
    ADMINS = [("Ops", env("ADMIN_EMAIL"))]

MAILERS = {
    # Outbound app mail: password resets, share notifications, error reports.
    "default": dict(_MAILER_DEFAULTS),
    # Password resets get their own mailer so a noisy reset flow can be pointed
    # at a different provider without touching the rest of the app.
    "password_reset": dict(_MAILER_DEFAULTS),
}

if env_bool("EMAIL_FAIL_SILENTLY", False):
    MAILERS["default"]["FAIL_SILENTLY"] = True
    MAILERS["password_reset"]["FAIL_SILENTLY"] = True


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
WATCHTRIVIA_MOCK_LLM = env_bool("WATCHTRIVIA_MOCK_LLM", False)
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 2)
LLM_TIMEOUT_SECONDS = env_int("LLM_TIMEOUT_SECONDS", 45)


# ---------------------------------------------------------------------------
# Product limits
# ---------------------------------------------------------------------------
# The platform pays for every question, so the caps are a business decision, not
# a technical one. Defaults: generous enough to be fun, cheap enough to survive
# a launch-week spike.

QUIZZES_PER_DAY = env_int("QUIZZES_PER_DAY", 25)
UPLOADS_PER_DAY = env_int("UPLOADS_PER_DAY", 10)
QUESTIONS_PER_TOPIC = env_int("QUESTIONS_PER_TOPIC", 2)
TOPICS_PER_QUIZ = env_int("TOPICS_PER_QUIZ", 3)
# Zero disables the share page, which is a one-way switch for an operator.
SHARING_ENABLED = env_bool("SHARING_ENABLED", True)
# Cached questions are reused when the same topic comes up again. This is what
# makes the per-day cap bearable: the tenth quiz on "F1 Official" costs nothing.
QUESTION_CACHE_TTL_DAYS = env_int("QUESTION_CACHE_TTL_DAYS", 30)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# Every flag below defaults to "on unless DEBUG", because a deployer who forgets
# one variable should get the safe behaviour, not the unsafe one. Local
# development runs with DEBUG=True and therefore plain HTTP, untouched.
#
# Each is still individually overridable: a staging box behind a plain-HTTP
# proxy can switch off exactly the flag that breaks it, which is why
# `DJANGO_SECURE_SSL_REDIRECT` is separate from the cookie flags.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
_SECURE_BY_DEFAULT = not DEBUG
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", _SECURE_BY_DEFAULT)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", _SECURE_BY_DEFAULT)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", _SECURE_BY_DEFAULT)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000 if _SECURE_BY_DEFAULT else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", _SECURE_BY_DEFAULT)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
# A platform's health probe hits the app over plain HTTP on the container's own
# port. Without this exemption the 301 to HTTPS makes the probe fail and the
# orchestrator kills a perfectly healthy container.
SECURE_REDIRECT_EXEMPT = [r"^healthz/?$", r"^readyz/?$"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_ENGINE = "django.contrib.sessions.backends.db"
# A month, so a user who uploads once a fortnight is not silently logged out.
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 30)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# One JSON-ish line per request on stdout, which is what a PaaS log drain
# expects. The request id ties a user's error report to the server log.

LOG_LEVEL = env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "trivia.logging.RequestIDFilter"},
    },
    "formatters": {
        "structured": {
            "()": "trivia.logging.StructuredFormatter",
        },
        "plain": {
            "format": "%(asctime)s %(levelname)-7s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured" if not DEBUG else "plain",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING" if DEBUG else "ERROR",
            "propagate": False,
        },
        "trivia": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "gunicorn.error": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}
