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
