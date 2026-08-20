# Part 6: Settings — CORS, Authentication, and DRF Configuration

---

## Understanding `settings.py`

`settings.py` is Django's **single source of truth** for all configuration. Every Django component — ORM, middleware, authentication, static files, email — is configured here.

### The Middleware Pipeline

When a request comes in, it passes through **middleware** — a chain of processing layers that run before (and after) your view:

```
REQUEST comes in
    ↓
┌─ SecurityMiddleware ──────────────────────┐
│  Adds security headers (HSTS, etc.)       │
├─ CorsMiddleware ──────────────────────────┤  ← We add this
│  Checks Origin header, adds CORS headers  │
├─ SessionMiddleware ───────────────────────┤
│  Loads session data from cookie           │
├─ CommonMiddleware ────────────────────────┤
│  URL normalization, Content-Length        │
├─ CsrfViewMiddleware ─────────────────────┤
│  Validates CSRF token on POST requests    │
├─ AuthenticationMiddleware ────────────────┤
│  Attaches request.user from session       │
├─ MessageMiddleware ───────────────────────┤
│  Flash messages                           │
├─ XFrameOptionsMiddleware ─────────────────┤
│  Prevents clickjacking                    │
└───────────────────────────────────────────┘
    ↓
YOUR VIEW runs
    ↓
RESPONSE goes back through middleware in reverse
```

> [!IMPORTANT]
> **Middleware order matters!** `CorsMiddleware` must come before `CommonMiddleware`
> because CORS headers need to be added to pre-flight OPTIONS requests,
> which `CommonMiddleware` might reject before CORS gets a chance to process them.

### The Updated Settings

Add and modify these sections in `watchtrivia/settings.py`:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-in-production"
)

DEBUG = os.environ.get("DEBUG", "True") == "True"

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'corsheaders',

    # Our apps
    'trivia',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',        # ADD: near the top
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# React dev server runs on port 5173
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]

# Allow credentials (session cookie) in cross-origin requests
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

---

## Deep Dive: CORS (Cross-Origin Resource Sharing)

### The Problem

Your React app runs on `http://localhost:5173`. Your Django API runs on `http://localhost:8000`. These are **different origins** (different ports = different origins).

Browsers enforce the **Same-Origin Policy**: JavaScript on one origin cannot make requests to a different origin. This prevents malicious websites from making API calls using your logged-in cookies.

```
http://localhost:5173  (React)
http://localhost:8000  (Django)
         ↑ different port = different origin
         → Browser BLOCKS the request by default
```

### The Solution

The server (Django) must explicitly tell the browser "I allow requests from this origin" by sending CORS response headers:

```
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
```

`django-cors-headers` adds these headers automatically based on your configuration.

### CORS Configuration Options

```python
# Allow specific origins (safest — use this)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",     # React dev server
    "https://watchtrivia.com",   # Production domain (add later)
]

# Allow credentials (cookies, auth headers)
CORS_ALLOW_CREDENTIALS = True

# Allow all origins (DANGEROUS — never use in production)
# CORS_ALLOW_ALL_ORIGINS = True
```

> [!WARNING]
> **Never use `CORS_ALLOW_ALL_ORIGINS = True` in production.** It means any website
> on the internet can make API calls to your backend. With credentials enabled,
> this is a critical security vulnerability.

### Pre-flight Requests (OPTIONS)

For "complex" requests (POST with JSON body), the browser first sends an **OPTIONS** request (called a "pre-flight") to ask the server if the real request is allowed:

```
1. Browser: OPTIONS /api/upload-history/
   Headers: Origin: http://localhost:5173
            Access-Control-Request-Method: POST
            
2. Server: 200 OK
   Headers: Access-Control-Allow-Origin: http://localhost:5173
            Access-Control-Allow-Methods: POST
            
3. Browser: (sees the CORS headers are OK)
   POST /api/upload-history/   ← now sends the real request
```

---

## Deep Dive: Authentication

### Session-Based Authentication (What We Use)

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

How it works:

```
1. User logs in (POST username + password)
2. Django creates a session record in the database
3. Django sends a session ID cookie to the browser
   Set-Cookie: sessionid=abc123; HttpOnly; Path=/
4. Browser sends this cookie with every subsequent request
   Cookie: sessionid=abc123
5. Django looks up the session → finds the user → sets request.user
```

**Pros:** Simple, works out of the box, Django admin uses it too.
**Cons:** Cookies are browser-only (not for mobile apps), requires CSRF protection, server stores session state.

### Token-Based Authentication (Alternative for Production)

For a production app with mobile clients, you'd switch to token auth:

```python
# Install: pip install djangorestframework-simplejwt
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}
```

With JWT:
1. User logs in → server returns an access token + refresh token
2. Frontend stores tokens in memory (not localStorage — XSS risk)
3. Frontend sends: `Authorization: Bearer <token>` with every request
4. Server validates the token without database lookup

We'll add this in Part 11 (Authentication endpoints for the React app).

### Permission Classes

```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

This makes **every endpoint require authentication by default**. Available permissions:

| Permission Class | Behavior |
|-----------------|----------|
| `AllowAny` | Anyone can access (no auth needed) |
| `IsAuthenticated` | Must be logged in |
| `IsAdminUser` | Must be a staff/superuser |
| `IsAuthenticatedOrReadOnly` | Logged in for writes, anyone for reads |

You can override per-view:

```python
@api_view(["GET"])
@permission_classes([AllowAny])  # Override: this endpoint is public
def public_view(request):
    ...
```

---

## Deep Dive: CSRF Protection

### What is CSRF?

**Cross-Site Request Forgery**: a malicious site tricks your browser into making a request to a different site where you're logged in.

```
1. You're logged into watchtrivia.com (session cookie in browser)
2. You visit evil.com
3. evil.com has: <form action="https://watchtrivia.com/api/delete-account/" method="POST">
4. Your browser sends the form WITH your session cookie
5. Django thinks it's you → deletes your account
```

### How Django Prevents It

Django requires a **CSRF token** on every POST/PUT/DELETE request:

```
1. Django sets a cookie: csrftoken=xyz789
2. Your JavaScript reads the cookie and adds a header: X-CSRFToken: xyz789
3. Django checks: does the header match the cookie?
4. evil.com can't read watchtrivia.com's cookies → can't send the header → blocked
```

> [!NOTE]
> DRF's `SessionAuthentication` enforces CSRF automatically.
> This means your React app needs to send the CSRF token header.
> We'll handle this in the frontend (Part 8) with Axios interceptors.

---

## Other Important Settings

### `SECRET_KEY`

```python
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "fallback-for-dev-only")
```

Used for cryptographic signing (sessions, CSRF tokens, password reset tokens). **Must be unique and secret in production.** Generate one with:

```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

### `DEBUG`

```python
DEBUG = os.environ.get("DEBUG", "True") == "True"
```

| `DEBUG=True` (development) | `DEBUG=False` (production) |
|---------------------------|---------------------------|
| Shows detailed error pages | Shows generic "Server Error" |
| Django serves static files | You must configure a web server for static files |
| Email errors print to console | Email errors can be sent to admins |

> [!CAUTION]
> **Never run with `DEBUG=True` in production.** The detailed error pages expose
> your source code, database queries, settings values, and environment variables.

### `ALLOWED_HOSTS`

```python
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# Production: ALLOWED_HOSTS = ["watchtrivia.com", "www.watchtrivia.com"]
```

Prevents **HTTP Host header attacks**. Django only accepts requests whose `Host` header matches this list. In production, set it to your actual domain.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Middleware** | Processing layers that wrap every request/response |
| **CORS** | Browser security policy; server must whitelist allowed origins |
| **Same-Origin Policy** | Browser blocks cross-origin requests by default |
| **Session authentication** | Server stores session, browser sends cookie |
| **Token authentication** | Client sends JWT token in header (stateless) |
| **CSRF** | Attack where a malicious site triggers requests using your cookies |
| **CSRF token** | A secret token that proves the request came from your own site |
| **`SECRET_KEY`** | Django's master secret for cryptographic operations |
| **`DEBUG`** | Controls error detail level; must be False in production |
| **`ALLOWED_HOSTS`** | Whitelist of valid hostnames to prevent Host header attacks |

---

**→ Continue to [Part 7: Testing](./07_testing.md)**
