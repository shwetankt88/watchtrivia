# Part 9: Running It All & What's Next

---

## Running the Full Stack

You now have a complete application. Let's run both servers and test the full flow.

### Terminal Layout

You need **two terminals** running simultaneously:

```
┌─────────────────────────────┬─────────────────────────────┐
│     Terminal 1: Backend     │     Terminal 2: Frontend    │
│                             │                             │
│  cd backend                 │  cd frontend                │
│  venv\Scripts\Activate.ps1  │  npm run dev                │
│  python manage.py runserver │                             │
│                             │                             │
│  → http://localhost:8000    │  → http://localhost:5173    │
└─────────────────────────────┴─────────────────────────────┘
```

### Step 1: Start the Backend

```powershell
cd C:\Users\Administrator\OneDrive\Desktop\watchtrivia\backend

# Activate the virtual environment
venv\Scripts\Activate.ps1

# Apply any pending migrations
python manage.py migrate

# Create an admin user (only needed once)
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

You should see:

```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
August 18, 2026 - 15:00:00
Django version 5.1.5, using settings 'watchtrivia.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

### Step 2: Start the Frontend

Open a **new terminal** (keep the backend running):

```powershell
cd C:\Users\Administrator\OneDrive\Desktop\watchtrivia\frontend

npm run dev
```

You should see:

```
  VITE v5.x.x  ready in 300ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

### Step 3: Test the Full Flow

1. **Log into the admin site.** Open `http://localhost:8000/admin/` in your browser and log in with your superuser credentials. This sets a **session cookie** in your browser.

2. **Open the React app.** In the **same browser**, navigate to `http://localhost:5173`. The session cookie carries over because both URLs are on `localhost`.

3. **Get your watch history.** Go to [Google Takeout](https://takeout.google.com):
   - Deselect everything
   - Select only **YouTube and YouTube Music**
   - Under "Multiple formats," ensure **JSON** is selected
   - Click "Next step" → "Create export"
   - Download and extract the archive
   - Find `Takeout/YouTube and YouTube Music/history/watch-history.json`

4. **Upload and play:**
   - Click the file input and select `watch-history.json`
   - Wait for processing → your top interests appear
   - Click "Generate my quiz" → LLM generates questions
   - Answer the quiz questions

---

## Understanding the Full Request Flow

When you upload a file, here's what happens across the entire stack:

```
  Browser (React)                    Django Backend                    External
  ──────────────                    ──────────────                    ────────
       │
       │  1. User selects watch-history.json
       │
       │  2. React creates FormData, POSTs to /api/upload-history/
       │─────────────────────────────────►│
       │                                  │  3. CORS middleware checks origin
       │                                  │  4. Auth middleware checks session cookie
       │                                  │  5. URL router → upload_watch_history view
       │                                  │  6. View calls parse_takeout_json(file)
       │                                  │  7. Parser extracts video titles, channels
       │                                  │  8. View calls bulk_create → saves to SQLite
       │                                  │  9. View calls rank_interests → top 5
       │                                  │ 10. View saves InterestTopic rows
       │                                  │ 11. Serializer converts topics → JSON
       │◄─────────────────────────────────│
       │  12. React receives JSON, sets state
       │  13. Component re-renders → shows interests
       │
       │  14. User clicks "Generate my quiz"
       │─────────────────────────────────►│
       │                                  │ 15. View gets top 3 interests
       │                                  │ 16. For each interest:
       │                                  │     17. LLM service calls Claude ──────►│ Anthropic API
       │                                  │     18. Claude returns JSON questions ◄──│
       │                                  │     19. View saves Question rows
       │                                  │ 20. Serializer converts questions → JSON
       │◄─────────────────────────────────│
       │  21. React shows quiz cards
       │
       │  22. User clicks an answer option
       │─────────────────────────────────►│
       │                                  │ 23. View creates Answer (auto-scores via save())
       │                                  │ 24. If correct, increments attempt.score
       │◄─────────────────────────────────│
       │  25. React shows correct/incorrect feedback
```

---

## The Authentication Workaround

Right now, the React app depends on logging into `/admin/` to get a session cookie. This is a valid development workflow, but not production-ready.

Here's why it works:

```
1. Browser visits localhost:8000/admin/
2. User enters username + password
3. Django creates a session → stores in DB
4. Django sends Set-Cookie: sessionid=abc123
5. Browser stores the cookie for localhost
6. Browser visits localhost:5173 (React app)
7. React calls localhost:8000/api/interests/
8. Browser sends Cookie: sessionid=abc123 (same host: localhost)
9. Django looks up session → finds the user → request.user is set
```

This breaks in production because the frontend and backend would be on **different domains** (e.g., `app.watchtrivia.com` vs `api.watchtrivia.com`). The "What's Next" section below covers proper auth solutions.

---

## A Note on the Database

Everything above runs on Django's default **SQLite** — a file-based database (`db.sqlite3`). This is perfect for development but has limitations:

| Feature | SQLite | PostgreSQL | MongoDB |
|---------|--------|-----------|---------|
| Concurrency | Single writer | Multiple writers | Multiple writers |
| Scalability | Single server | Scales vertically | Scales horizontally |
| Schema | Strict (relational) | Strict (relational) | Flexible (document) |
| Best for | Dev, small apps | Production web apps | Variable-shaped data |
| Django ORM | Full support | Full support | No ORM (use `pymongo`) |

### The Polyglot Persistence Plan

The original design calls for **polyglot persistence** — using different databases for different data shapes:

```
┌─────────────────────────────────────────────┐
│              Django Application              │
│                                             │
│  ┌───────────────┐   ┌───────────────────┐  │
│  │  PostgreSQL    │   │     MongoDB       │  │
│  │  (relational)  │   │    (document)     │  │
│  │               │   │                   │  │
│  │  • User       │   │  • WatchHistory   │  │
│  │  • QuizAttempt│   │  • Question       │  │
│  │  • Answer     │   │    (flexible JSON) │  │
│  │  • InterestTopic│ │                   │  │
│  └───────────────┘   └───────────────────┘  │
└─────────────────────────────────────────────┘
```

**Why MongoDB for watch history and questions?**
- Watch history entries from Google Takeout have variable fields — some have subtitles, some don't, some have extra metadata
- LLM-generated questions have flexible option counts and metadata
- Neither needs Django's admin or ORM features
- MongoDB handles this variable-shaped data naturally

**Why PostgreSQL for the rest?**
- Users need Django's authentication system (built on the ORM)
- Quiz attempts and answers have strict, relational structure
- The admin site requires ORM-backed models

This isn't wired up yet — the SQLite version must work solidly first.

---

## Running Tests

Before building new features, make sure everything passes:

```powershell
cd backend
venv\Scripts\Activate.ps1

# Run the full test suite
python manage.py test trivia -v 2
```

Expected output:

```
test_empty_input_returns_empty_list ... ok
test_entries_without_channel_names_are_ignored ... ok
test_ranks_by_frequency_descending ... ok
test_weights_are_normalized_proportions ... ok
test_top_n_limits_results ... ok
test_correct_answer_is_marked_correct ... ok
test_incorrect_answer_is_marked_incorrect ... ok
test_case_insensitive_matching ... ok
test_whitespace_is_trimmed ... ok
test_unauthenticated_request_is_rejected ... ok
test_user_only_sees_their_own_interests ... ok
test_response_format ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.234s

OK
```

> [!IMPORTANT]
> **Always run tests before and after making changes.** If tests pass before
> your change and fail after, your change broke something. This is the
> whole point of having tests.

---

## What's Left to Build

The core app works end to end. Here are the natural next features, roughly in order of priority:

### 1. Proper Authentication API

**Problem:** Users must log into `/admin/` to get a session — this is a developer-only workflow.

**Solution:** Add signup/login/logout API endpoints for the React app.

```python
# What you'd add to trivia/views.py:
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

@api_view(["POST"])
def signup(request):
    username = request.data.get("username")
    password = request.data.get("password")
    user = User.objects.create_user(username=username, password=password)
    login(request, user)
    return Response({"id": user.id, "username": user.username}, status=201)

@api_view(["POST"])
def login_view(request):
    user = authenticate(
        username=request.data.get("username"),
        password=request.data.get("password")
    )
    if user:
        login(request, user)
        return Response({"id": user.id, "username": user.username})
    return Response({"error": "Invalid credentials"}, status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({"message": "Logged out"})
```

On the React side, you'd add login/signup forms and call these endpoints instead of relying on the admin.

**Alternative:** Switch from session authentication to **token authentication** (DRF's `TokenAuthentication` or JWT via `djangorestframework-simplejwt`). Tokens work better when the frontend and backend are on different domains.

### 2. Background Task Processing (Celery)

**Problem:** `generate_quiz` calls the LLM synchronously — the user stares at a loading screen for 10–30 seconds while Claude generates questions for each topic.

**Solution:** Move LLM calls to a **Celery background task** so the response returns immediately and the user gets notified when the quiz is ready.

```
Without Celery (current):
  POST /generate-quiz/  ──────[30s of LLM calls]──────►  201 Created

With Celery:
  POST /generate-quiz/  ──►  202 Accepted (task_id: abc)
                              │
                              └──► Celery worker picks up task
                                   └──► Calls Claude for each topic
                                        └──► Saves questions to DB
                                             └──► Marks task complete

  GET /quiz-status/abc/  ──►  200 {"status": "complete", "questions": [...]}
```

This requires:
- **Redis** as a message broker (Celery sends tasks to Redis, workers pick them up)
- **Celery** installed and configured
- A polling or WebSocket mechanism on the frontend

### 3. MongoDB Integration

**Problem:** Watch history and LLM-generated questions have variable shapes that don't fit neatly into a relational schema.

**Solution:** Use `pymongo` directly for these collections while keeping relational data in PostgreSQL/SQLite.

```python
# Example: storing watch history in MongoDB
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client.watchtrivia

def save_watch_history(user_id, entries):
    db.watch_history.insert_many([
        {"user_id": user_id, **entry} for entry in entries
    ])
```

### 4. Smarter Interest Ranking (TF-IDF + K-Means)

**Problem:** The current ranker just counts videos per channel. If you watch 100 videos on one channel about 5 different topics, it reports one interest ("that channel") instead of five.

**Solution:** Use **TF-IDF** (Term Frequency–Inverse Document Frequency) on video titles to find meaningful keywords, then **K-Means clustering** to group them into topics.

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

def rank_interests_v2(watch_entries, n_clusters=5):
    titles = [e["video_title"] for e in watch_entries if e.get("video_title")]
    
    # TF-IDF: find distinctive words across all titles
    vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(titles)
    
    # K-Means: group similar titles into clusters
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    clusters = kmeans.fit_predict(tfidf_matrix)
    
    # Extract the top keywords per cluster as the topic label
    feature_names = vectorizer.get_feature_names_out()
    topics = []
    for i in range(n_clusters):
        center = kmeans.cluster_centers_[i]
        top_words = [feature_names[j] for j in center.argsort()[-3:][::-1]]
        count = (clusters == i).sum()
        topics.append({
            "label": " / ".join(top_words),
            "weight": round(count / len(titles), 3),
        })
    
    return sorted(topics, key=lambda t: t["weight"], reverse=True)
```

### 5. Results Screen

**Problem:** After completing a quiz, there's no summary — the user just sees the last question.

**Solution:** Add a results page that shows:
- Final score (e.g., "7/10")
- Per-topic breakdown (e.g., "F1: 3/4, Finance: 2/3, Cooking: 2/3")
- Which questions were right/wrong
- A "Try Again" button

This would require:
- A new API endpoint: `GET /api/attempts/<id>/results/`
- A new `status` state in the React component (e.g., `"results"`)
- A serializer that includes answers with correct/incorrect flags

---

## Deployment Checklist

When you're ready to deploy to a real server, here's what changes:

| Development | Production |
|-------------|-----------|
| `python manage.py runserver` | **Gunicorn** or **uWSGI** (multi-process WSGI server) |
| `DEBUG = True` | `DEBUG = False` (never expose debug pages publicly) |
| SQLite (`db.sqlite3`) | **PostgreSQL** (concurrent writes, backups) |
| `SECRET_KEY` in code | `SECRET_KEY` from **environment variable** |
| `ALLOWED_HOSTS = []` | `ALLOWED_HOSTS = ["yourdomain.com"]` |
| Vite dev server | `npm run build` → serve `dist/` via **Nginx** |
| No HTTPS | **HTTPS everywhere** (Let's Encrypt) |
| No static file serving | `python manage.py collectstatic` → Nginx serves static files |

### Minimal Production `settings.py` Changes

```python
import os

DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = ["yourdomain.com", "www.yourdomain.com"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": "5432",
    }
}

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

> [!CAUTION]
> **Never deploy with `DEBUG = True`.** It exposes full stack traces, 
> settings values, and database queries to anyone who triggers an error.
> This is a serious security vulnerability.

---

## What You've Built

Looking back, here's the complete architecture you've built across nine parts:

```
┌──────────────────────────────────────────────────────────────┐
│                          Watchtrivia                          │
│                                                              │
│  ┌─────────────────────┐     ┌─────────────────────────────┐ │
│  │   React Frontend    │     │       Django Backend         │ │
│  │                     │     │                              │ │
│  │  App.jsx            │────►│  URLs → Views → Services    │ │
│  │  ├─ Upload handler  │◄────│  ├─ upload_watch_history    │ │
│  │  ├─ Interest list   │     │  ├─ generate_quiz           │ │
│  │  ├─ Quiz cards      │     │  ├─ submit_answer           │ │
│  │  └─ api.js (Axios)  │     │  └─ complete_attempt        │ │
│  │                     │     │                              │ │
│  │  State machine:     │     │  Services:                  │ │
│  │  idle → uploading   │     │  ├─ takeout_parser.py       │ │
│  │  → ready            │     │  ├─ interest_ranker.py      │ │
│  │  → generating       │     │  └─ llm_service.py (Claude) │ │
│  │  → quiz             │     │                              │ │
│  └─────────────────────┘     │  Models (ORM):              │ │
│                               │  ├─ WatchHistoryEntry       │ │
│                               │  ├─ InterestTopic           │ │
│                               │  ├─ Question                │ │
│                               │  ├─ QuizAttempt             │ │
│                               │  └─ Answer                  │ │
│                               │                              │ │
│                               │  Admin Site (built-in CRUD)  │ │
│                               │  Test Suite (12 tests)       │ │
│                               └──────────────┬───────────────┘ │
│                                              │                 │
│                                       ┌──────▼──────┐         │
│                                       │   SQLite    │         │
│                                       └─────────────┘         │
└──────────────────────────────────────────────────────────────┘
```

### What You've Learned

| Part | Topic | Key takeaway |
|------|-------|-------------|
| 1 | Project setup | Django projects vs apps, virtual environments |
| 2 | Models & admin | ORM, migrations, built-in CRUD admin |
| 3 | Services | Service layer pattern, keeping views thin |
| 4 | Serializers & views | DRF, JSON ↔ model translation, API design |
| 5 | URL configuration | Request routing, URL namespacing |
| 6 | Settings | CORS, middleware, authentication configuration |
| 7 | Testing | Unit tests, integration tests, API tests |
| 8 | React frontend | SPA, state management, API integration |
| 9 | Full stack | End-to-end flow, deployment, next steps |

---

## Final Advice

1. **Get the simple version working first.** The current channel-frequency ranker and synchronous LLM calls are intentionally simple. Make them work, deploy, get users — then optimize.

2. **Write tests before adding features.** When you add auth endpoints, write the tests first: "unauthenticated signup returns 201," "duplicate username returns 400," etc. The tests will guide your implementation.

3. **Read the Django and DRF docs.** This tutorial covers a slice of what both frameworks offer. The [Django documentation](https://docs.djangoproject.com/) and [DRF documentation](https://www.django-rest-framework.org/) are some of the best in the industry — use them.

4. **Deploy early.** Don't wait until everything is perfect. A deployed simple app teaches you more about production issues (CORS, HTTPS, environment variables, database migrations) than a perfect local app ever will.

---

**Congratulations — you've completed the Watchtrivia tutorial.** 🎉

Each "What's Next" item above is a natural follow-up project. Pick the one that interests you most and start building.
