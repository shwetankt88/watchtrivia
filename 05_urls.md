# Part 5: URL Configuration

---

## How Django Routes Requests

When a request hits Django, the URL is matched against patterns in a chain:

```
Browser request: POST http://localhost:8000/api/upload-history/
                                            ↓
        ┌───────────────────────────────────────────────────┐
        │  watchtrivia/urls.py (project-level, ROOT_URLCONF)│
        │                                                   │
        │  path('admin/', admin.site.urls)     ← no match  │
        │  path('api/', include('trivia.urls'))  ← MATCH!   │
        │    strips "api/" → passes "upload-history/" onward│
        └───────────────────────┬───────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────────────┐
        │  trivia/urls.py (app-level)                       │
        │                                                   │
        │  path("upload-history/", views.upload_watch_history) ← MATCH! │
        │    → calls upload_watch_history(request)           │
        └───────────────────────────────────────────────────┘
```

This two-level routing is how Django keeps multi-app projects organized. Each app manages its own URLs; the project just delegates.

---

## App-Level URLs

Create `trivia/urls.py`:

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router auto-generates URLs for ViewSets
router = DefaultRouter()
router.register("interests", views.InterestTopicViewSet, basename="interest")

urlpatterns = [
    # ViewSet-generated URLs (list + detail)
    path("", include(router.urls)),
    
    # Custom function-based view URLs
    path("upload-history/", views.upload_watch_history, name="upload-history"),
    path("generate-quiz/", views.generate_quiz, name="generate-quiz"),
    path(
        "attempts/<int:attempt_id>/submit-answer/",
        views.submit_answer,
        name="submit-answer",
    ),
    path(
        "attempts/<int:attempt_id>/complete/",
        views.complete_attempt,
        name="complete-attempt",
    ),
]
```

### Understanding `path()` Parameters

```python
path("upload-history/", views.upload_watch_history, name="upload-history")
#     ↑ URL pattern      ↑ View function              ↑ Name for reverse()
```

| Parameter | Purpose |
|-----------|---------|
| `"upload-history/"` | The URL pattern to match (relative to the parent `include()`) |
| `views.upload_watch_history` | The view function to call when matched |
| `name="upload-history"` | A name for reverse URL lookup (used in templates and tests) |

### URL Parameters: `<int:attempt_id>`

```python
path("attempts/<int:attempt_id>/submit-answer/", views.submit_answer)
```

`<int:attempt_id>` is a **path converter** — it captures part of the URL and passes it as a keyword argument to the view:

```
URL: /api/attempts/42/submit-answer/
                   ↑↑
                   captures "42" as attempt_id (integer)

def submit_answer(request, attempt_id):
    #                       ↑ attempt_id = 42
```

Available path converters:

| Converter | Matches | Example |
|-----------|---------|---------|
| `int` | Positive integers | `<int:id>` → `42` |
| `str` | Non-empty string (no `/`) | `<str:slug>` → `"hello-world"` |
| `slug` | ASCII letters, numbers, hyphens, underscores | `<slug:slug>` → `"my-post-1"` |
| `uuid` | UUID format | `<uuid:pk>` → `"075194d3-..."` |
| `path` | Non-empty string (including `/`) | `<path:file>` → `"dir/file.txt"` |

### DRF Routers — Auto-Generated URLs

```python
router = DefaultRouter()
router.register("interests", views.InterestTopicViewSet, basename="interest")
```

This single line generates **multiple URL patterns**:

| URL Pattern | HTTP Method | Action | Name |
|-------------|------------|--------|------|
| `/api/interests/` | `GET` | `list` — all interests | `interest-list` |
| `/api/interests/1/` | `GET` | `retrieve` — interest #1 | `interest-detail` |

If we used `ModelViewSet` instead of `ReadOnlyModelViewSet`, it would also generate:

| URL Pattern | HTTP Method | Action | Name |
|-------------|------------|--------|------|
| `/api/interests/` | `POST` | `create` | `interest-list` |
| `/api/interests/1/` | `PUT` | `update` | `interest-detail` |
| `/api/interests/1/` | `PATCH` | `partial_update` | `interest-detail` |
| `/api/interests/1/` | `DELETE` | `destroy` | `interest-detail` |

The `basename="interest"` parameter sets the name prefix for URL reversing.

### `include()` — Delegating URLs

```python
path("", include(router.urls))
```

`include()` takes a list of URL patterns and prepends the parent path. Since our parent (in `watchtrivia/urls.py`) is `"api/"`, the final URLs are:

- `/api/interests/`
- `/api/interests/1/`

---

## Project-Level URLs

`watchtrivia/urls.py`:

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('trivia.urls')),
]
```

### The Complete URL Map

| URL | Method | View | Purpose |
|-----|--------|------|---------|
| `/admin/` | ALL | Django admin | Admin interface |
| `/api/interests/` | GET | `InterestTopicViewSet.list` | List user's interests |
| `/api/interests/<id>/` | GET | `InterestTopicViewSet.retrieve` | Get one interest |
| `/api/upload-history/` | POST | `upload_watch_history` | Upload Takeout file |
| `/api/generate-quiz/` | POST | `generate_quiz` | Generate quiz from interests |
| `/api/attempts/<id>/submit-answer/` | POST | `submit_answer` | Submit one answer |
| `/api/attempts/<id>/complete/` | POST | `complete_attempt` | End the quiz |

### URL Naming and `reverse()`

Every URL has a `name` — this lets you reference URLs by name instead of hardcoding paths:

```python
from django.urls import reverse

# In tests:
url = reverse("upload-history")  # → "/api/upload-history/"
url = reverse("interest-list")   # → "/api/interests/"
url = reverse("submit-answer", kwargs={"attempt_id": 42})
# → "/api/attempts/42/submit-answer/"
```

> [!TIP]
> **Always use `reverse()` in tests** instead of hardcoding URLs. If you change
> a URL pattern, only the `urls.py` file needs updating — all tests still work.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **`ROOT_URLCONF`** | Setting that tells Django which file is the top-level URL config |
| **`path()`** | Maps a URL pattern to a view |
| **`include()`** | Delegates URL matching to another URLconf |
| **`<int:id>`** | Path converter that captures URL segments as typed arguments |
| **`DefaultRouter`** | DRF class that auto-generates CRUD URLs for ViewSets |
| **`basename`** | Prefix for auto-generated URL names |
| **`reverse()`** | Look up a URL by name (no hardcoded paths) |
| **`name`** | Identifier for reverse URL lookup |

---

**→ Continue to [Part 6: Settings — CORS, Auth, and DRF Config](./06_settings.md)**
