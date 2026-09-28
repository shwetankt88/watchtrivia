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
