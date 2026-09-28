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
