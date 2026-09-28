# Part 3: Services — Parsing, Ranking, and the LLM

---

## The Service Layer Pattern

Django's default architecture puts logic in **views**. That works for small apps, but
Watchtrivia has three distinct pieces of business logic:

1. **Parsing** YouTube Takeout data
2. **Ranking** user interests from watch history
3. **Generating** quiz questions via an LLM

Stuffed into views, each view would be hundreds of lines and impossible to test without
making HTTP requests. The **service layer pattern** solves this:

```
┌─────────────────┐         ┌───────────────────┐         ┌──────────────┐
│   View (thin)   │ ──────→ │  Service (logic)  │ ──────→ │  Model (data)│
│ Handles HTTP    │         │ Pure Python       │         │ Database ORM │
│ request/response│         │ Independently     │         │              │
│                 │         │ testable          │         │              │
└─────────────────┘         └───────────────────┘         └──────────────┘
```

**The rule: Views handle HTTP. Services handle logic. Models handle data.**

> [!IMPORTANT]
> A service should not import from `django.db`, `django.http`, or `django.shortcuts`.
> If `takeout_parser.py` needs a database query, the logic is in the wrong place. This
> constraint is what makes the services testable in milliseconds with no database, no
> server, and no Django test runner.

### The Package

`trivia/services/` contains:

| File | Responsibility | Django imports? |
|------|----------------|-----------------|
| `__init__.py` | Empty — makes it a package | No |
| `takeout_parser.py` | Takeout JSON → list of dicts | **No** |
| `interest_ranker.py` | Watch entries → ranked topics | **No** |
| `llm_service.py` | Topic label → generated questions | **No** |

Zero Django imports in all three. That is a design constraint, not a coincidence.

---

## Service 1: Parsing Google Takeout Data

### What is Google Takeout?

Google Takeout (`takeout.google.com`) exports your data from any Google service. For
YouTube, the watch history comes as JSON (`watch-history.json`) or as a set of per-month
files (`watch-history/watch-history-2024-12.json`). **This tutorial handles the single
combined file.** The per-month variant is an array of arrays rather than an array of
objects, and needs a one-line flattening change — noted at the end of this section.

### The Raw Takeout Format

```json
[
  {
    "header": "YouTube",
    "title": "Watched Max Verstappen's Incredible Overtake",
    "titleUrl": "https://www.youtube.com/watch?v=abc123",
    "subtitles": [
      { "name": "F1 Official", "url": "https://www.youtube.com/channel/UCB_..." }
    ],
    "time": "2024-12-15T14:30:00.000Z",
    "products": ["YouTube"]
  },
  {
    "header": "YouTube",
    "title": "Watched How Black Holes Really Work",
    "titleUrl": "https://www.youtube.com/watch?v=def456",
    "subtitles": [
      { "name": "Veritasium", "url": "https://www.youtube.com/channel/UCD..." }
    ],
    "time": "2024-12-14T10:15:00.000Z"
  },
  {
    "header": "YouTube",
    "title": "Watched [Deleted video]",
    "subtitles": [{ "name": "Some Channel" }]
  },
  {
    "header": "YouTube",
    "title": "Visited the YouTube homepage",
    "titleUrl": "https://www.youtube.com/?gl=US&hl=en"
  }
]
```

Notice the last two entries. Real Takeout exports contain **ads, deleted videos, and
non-video activity**. The parser must filter them out.

### The Parser

`trivia/services/takeout_parser.py`:

```python
"""Parse Google Takeout YouTube watch history exports.

Pure Python — no Django imports. Raise TakeoutParseError on anything the
caller is expected to handle; let genuinely unexpected bugs propagate.
"""

import json
from datetime import datetime, timezone

# Google prefixes every real video title with "Watched ".
TITLE_PREFIX = "Watched "

# Only these URL shapes correspond to an actual watched video.
VIDEO_URL_MARKER = "watch?v="


class TakeoutParseError(Exception):
    """Raised when an uploaded file is not a usable Takeout export."""


def parse_takeout_json(file_obj):
    """Parse a Google Takeout watch-history.json file.

    Args:
        file_obj: A file-like object (from request.FILES or open()).

    Returns:
        A list of dicts, each with keys:
            video_title (str)
            channel_name (str)  — may be ""
            watched_at   (datetime | None)  — timezone-aware UTC, or None

    Raises:
        TakeoutParseError: The file is not valid JSON, is not a list, or
            contains no usable video entries.
    """
    try:
        raw_data = json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise TakeoutParseError(
            f"That file is not valid JSON (problem at character {exc.pos}). "
            "Make sure you upload the watch-history.json from your Takeout archive."
        ) from exc
    except UnicodeDecodeError as exc:
        raise TakeoutParseError(
            "That file is not UTF-8 text. Takeout exports are always JSON, "
            "so an archive you extracted without a JSON file is the usual cause."
        ) from exc

    if not isinstance(raw_data, list):
        raise TakeoutParseError(
            "Expected a JSON list of watch-history entries at the top level, "
            f"but found {type(raw_data).__name__}."
        )

    entries = []
    for item in raw_data:
        if not isinstance(item, dict):
            continue

        title_url = item.get("titleUrl") or ""
        # Ads, deleted videos, and homepage visits have no watch?v= URL.
        if VIDEO_URL_MARKER not in title_url:
            continue

        title = _clean_title(item.get("title", ""))
        if not title:
            continue

        entries.append(
            {
                "video_title": title,
                "channel_name": _extract_channel(item),
                "watched_at": _parse_timestamp(item.get("time")),
            }
        )

    if not entries:
        raise TakeoutParseError(
            "No YouTube videos found in that file. Make sure it is the "
            "watch-history.json from your Google Takeout export, not your "
            "subscriptions, comments, or search history."
        )

    return entries


def parse_takeout_monthly_json(file_obj):
    """Parse the per-month Takeout layout, which nests one list inside another.

    Google exports either a flat array (newer) or an array of per-month
    arrays (older, still common). This handles the older shape.
    """
    try:
        raw_data = json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise TakeoutParseError(f"That file is not valid JSON: {exc}") from exc

    if not isinstance(raw_data, list):
        raise TakeoutParseError("Expected a JSON list at the top level.")

    flattened = []
    for chunk in raw_data:
        if isinstance(chunk, list):
            flattened.extend(chunk)
        elif isinstance(chunk, dict):
            flattened.append(chunk)

    import io
    return parse_takeout_json(io.StringIO(json.dumps(flattened)))


def _clean_title(raw_title):
    """Strip Google's "Watched " prefix — but only the first occurrence.

    A title like "Watched I Watched Every Star Wars Movie" must become
    "I Watched Every Star Wars Movie", not "I Every Star Wars Movie".
    """
    title = raw_title.strip()
    if title.startswith(TITLE_PREFIX):
        title = title[len(TITLE_PREFIX):]
    return title.strip()


def _extract_channel(item):
    """Pull the channel name out of the subtitles array."""
    subtitles = item.get("subtitles")
    if not isinstance(subtitles, list) or not subtitles:
        return ""
    first = subtitles[0]
    if not isinstance(first, dict):
        return ""
    return (first.get("name") or "").strip()


def _parse_timestamp(raw_time):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    Accepts a trailing "Z" as well as an explicit offset, and treats a
    timestamp with no offset as UTC (which is what Google means).
    """
    if not raw_time or not isinstance(raw_time, str):
        return None

    text = raw_time.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
```

### Why Every One of Those Defences Exists

The original plan's parser was twelve lines and would crash the request with an HTTP 500
on any of the following, all of which occur in real Takeout exports:

| Defect in original | Consequence | Fix |
|--------------------|-------------|-----|
| `json.load()` unguarded | Malformed or HTML file → `JSONDecodeError` → **500** | Catch, re-raise as `TakeoutParseError` → 400 |
| Non-dict items assumed | `item.get` on a string → `AttributeError` → **500** | `isinstance(item, dict)` check |
| `title` not stripped after prefix removal | `"Watched  Foo"` → `" Foo"` with a leading space | `_clean_title` strips both ends |
| No "no videos found" check | Uploading `subscriptions.json` silently creates zero interests, and the user sees "Upload succeeded" and an empty page with no explanation | Raise `TakeoutParseError` |
| Naive datetimes stored | `RuntimeWarning: received a naive datetime`, and a timezone bug that surfaces months later | `_parse_timestamp` always returns aware UTC |
| `subtitles[0]` assumed to be a dict | Malformed entry → `AttributeError` → **500** | Type-checked |

The general principle: **a parser's job is not just to succeed, it is to fail
loudly and specifically.** A user who uploads the wrong file should be told which file
they should upload, not shown a 500 traceback.

### The Monthly Variant

`parse_takeout_monthly_json` handles the older layout. It re-serialises the flattened
list to reuse the single-file parser rather than duplicating the filtering logic — a
small, honest trade of a little memory for one source of truth.

> [!TIP]
> Prefer handling both shapes in one function by checking whether the first element is a
> list, rather than exposing two public entry points. Two public functions means callers
> must know which layout they have, and someone will eventually pick wrong.

### Line-by-Line Notes

**`json.load(file_obj)` vs `json.loads(string)`**
`json.load()` reads from a file-like object (anything with `.read()`). `json.loads()`
reads from a string. `request.FILES` gives you file-like objects, so `json.load()` is
correct.

**`TITLE_PREFIX` slice vs `str.replace`**
```python
if title.startswith(TITLE_PREFIX):
    title = title[len(TITLE_PREFIX):]
```
The original used `.replace("Watched ", "", 1)`. The `1` limited it to the first
occurrence, which was correct, but `replace` also matches the prefix anywhere in the
string. `startswith` is precisely the intent.

**The `Z` suffix**
Google emits `"2024-12-15T14:30:00.000Z"`. Python 3.11+ `datetime.fromisoformat()`
handles `Z` natively, so the replacement is no longer strictly necessary — but it is
harmless, explicit, and keeps the code correct if the project is ever run on 3.9 or 3.10.

> [!NOTE]
> The original plan's explanation here was outdated: it claimed `fromisoformat` "before
> 3.11 doesn't understand Z" while presenting this as a permanent requirement. The
> code is still right; the reasoning was stale.

**Why `.astimezone(timezone.utc)`**
A Takeout export can contain local-time offsets. Storing everything in UTC means
`watched_at` values are directly comparable and sortable. Django stores naive datetimes
in SQLite under `USE_TZ=True` and converts on read; handing it aware UTC datetimes is
the correct input.

### Testing the Parser Right Now

```bash
python manage.py shell
```

```python
import io, json
from trivia.services.takeout_parser import parse_takeout_json, TakeoutParseError

sample = json.dumps([
    {"title": "Watched F1 Grand Prix Highlights",
     "titleUrl": "https://www.youtube.com/watch?v=abc",
     "subtitles": [{"name": "F1 Official"}],
     "time": "2024-12-15T14:30:00.000Z"},
    {"title": "Watched Python Tutorial",
     "titleUrl": "https://www.youtube.com/watch?v=def",
     "subtitles": [{"name": "Corey Schafer"}],
     "time": "2024-12-14T10:15:00.000Z"},
    {"title": "Visited the YouTube homepage",
     "titleUrl": "https://www.youtube.com/?gl=US"},
])

entries = parse_takeout_json(io.StringIO(sample))
print(entries)
# [{'video_title': 'F1 Grand Prix Highlights', 'channel_name': 'F1 Official',
#   'watched_at': datetime.datetime(2024, 12, 15, 14, 30, tzinfo=datetime.timezone.utc)},
#  ...]

try:
    parse_takeout_json(io.StringIO("not json at all"))
except TakeoutParseError as e:
    print("Correctly rejected:", e)
```

Part 7 turns these into permanent tests.

---

## Service 2: Ranking Interests

### The Algorithm: Channel Frequency

The simplest useful signal: **count which channels someone watches most.**

`trivia/services/interest_ranker.py`:

```python
"""Rank a user's interests from their watch history.

Pure Python — no Django imports.
"""

from collections import Counter


def rank_interests(watch_entries, top_n=5, min_share=0.0):
    """Rank user interests by channel frequency.

    Args:
        watch_entries: List of dicts with a 'channel_name' key. Entries with
            a missing or blank channel name are ignored.
        top_n: Maximum number of interests to return.
        min_share: Drop interests whose share of total watch history is below
            this threshold. 0.0 disables filtering.

    Returns:
        A list of dicts with 'label' (str) and 'weight' (float), sorted by
        weight descending.

    Weight semantics — read this before using the numbers:
        weight = (videos from this channel) / (total videos with a channel)
    Weights therefore express each interest's share of the user's whole
    channel-tagged history. They sum to at most 1.0, and sum to exactly 1.0
    only when `top_n` is at least the number of distinct channels. If you
    need them to sum to 1.0 over the returned set, divide each by the sum
    of the returned weights.
    """
    channel_counts = Counter(
        entry.get("channel_name", "")
        for entry in watch_entries
        if entry.get("channel_name")
    )

    if not channel_counts:
        return []

    total = sum(channel_counts.values())
    ranked = channel_counts.most_common(top_n)

    results = [
        {"label": channel, "weight": round(count / total, 3)}
        for channel, count in ranked
    ]

    if min_share > 0:
        results = [item for item in results if item["weight"] >= min_share]

    return results


def renormalize(ranked):
    """Rescale weights so a returned set sums to 1.0.

    Use this when you need the displayed percentages to add up to 100%.
    Without it, weights express share of the *whole* history, so truncating
    to top_n leaves a remainder (see the weight semantics note above).

    Args:
        ranked: Output of rank_interests().

    Returns:
        A new list with rescaled weights, order preserved.
    """
    total = sum(item["weight"] for item in ranked)
    if not total:
        return ranked
    return [
        {**item, "weight": round(item["weight"] / total, 3)}
        for item in ranked
    ]
```

### Understanding `Counter`

```python
from collections import Counter

c = Counter(["F1", "F1", "F1", "Finance", "Gaming"])
# Counter({'F1': 3, 'Finance': 1, 'Gaming': 1})

c.most_common(2)
# [('F1', 3), ('Finance', 1)]
```

### The Weight Calculation — Precisely

If a user watched 100 videos total and 30 were from "F1 Official":

```
weight = 30 / 100 = 0.3
```

30% of their watch history is F1 content. A **proportion**, not an absolute count, which
makes weights comparable across users with very different history sizes.

> [!IMPORTANT]
> **The denominator is the whole history, not the top N.**
>
> With 6 channels and `top_n=5`, the returned weights sum to `0.971`, not `1.0`. This is
> intentional and correct: the missing 0.029 is the sixth channel, which exists in the
> data but was not returned.
>
> The original plan's test suite contained a test named
> `test_weights_are_normalized_proportions` that asserted weights sum to 1.0. It passed
> **by accident** — it used 2 channels with `top_n=2`, so the top-N happened to cover the
> entire history. The same test with 6 channels would have failed.
>
> If you actually want the returned set to sum to 1.0, call `renormalize()` — defined
> alongside `rank_interests` above, with no external dependencies:
>
> ```python
> topics = renormalize(rank_interests(entries, top_n=5))
> ```
>
> Part 7 tests both the raw semantics and `renormalize`, so the behaviour is pinned
> rather than accidental.

### Optional Extension: TF-IDF + K-Means

Channel frequency is crude. It tells you "you watch a lot of F1 Official" but cannot
distinguish F1 race highlights from F1 technical analysis. A clustering approach groups
video **titles** by vocabulary instead:

```python
# pip install scikit-learn
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer


def rank_interests_by_cluster(watch_entries, n_clusters=5, random_state=42):
    """Cluster video titles by vocabulary and label clusters by top terms.

    Returns the same [{'label', 'weight'}] shape as rank_interests(), so it
    is a drop-in replacement.

    Note: with fewer entries than clusters, or near-duplicate titles, KMeans
    emits ConvergenceWarning and may produce empty clusters. Guard with
    `if len(titles) < n_clusters * 2: fall back to channel frequency`.
    """
    titles = [e.get("video_title", "") for e in watch_entries if e.get("video_title")]
    if len(titles) < n_clusters * 2:
        return rank_interests(watch_entries, top_n=n_clusters)

    vectorizer = TfidfVectorizer(
        max_features=1000,
        stop_words="english",
        min_df=2,          # ignore words appearing in only one title
    )
    matrix = vectorizer.fit_transform(titles)

    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    kmeans.fit(matrix)

    terms = vectorizer.get_feature_names_out()
    results = []
    for cluster_id in range(n_clusters):
        indices = [i for i, label in enumerate(kmeans.labels_) if label == cluster_id]
        if not indices:
            continue
        centroid = kmeans.cluster_centers_[cluster_id]
        top_terms = [
            terms[i]
            for i in centroid.argsort()[::-1][:3]
            if centroid[i] > 0
        ]
        if not top_terms:
            continue
        results.append({
            "label": " / ".join(top_terms).title(),
            "weight": round(len(indices) / len(titles), 3),
        })

    return sorted(results, key=lambda item: item["weight"], reverse=True)[:n_clusters]
```

> [!NOTE]
> **This is an extension, not part of the core build.** The original plan installed
> `scikit-learn`, listed it in the stack table, previewed this function, and then never
> built it — leaving a reader with an unused dependency and a promise. Here it is
> explicitly optional, and `scikit-learn` is not in `requirements.txt`.
>
> It lives in this file rather than a separate module so it can import `rank_interests`
> for its fallback path. If you adopt it in production, move it to
> `interest_clusterer.py` and keep the two independent.

### Why Start With Channel Frequency

- **It works immediately** on any history size, including ten videos.
- **It is interpretable.** "You watched 30% F1 Official" is a claim you can show a user
  and get agreement on. Cluster labels like "racing / speed / apex" are harder to trust.
- **It has no failure modes** on small or sparse data. KMeans needs enough documents to
  form distinct clusters and warns when it cannot.
- **It gives the LLM a better prompt.** "Formula 1" produces markedly better trivia than
  "racing / speed / apex".

Ship v1, verify the end-to-end flow, then consider clustering. Avoid premature
complexity.

---

## Service 3: Generating Questions with the LLM

### The Anthropic Claude API

Claude is an LLM made by Anthropic. We use it to generate trivia questions about a user's
interests.

`trivia/services/llm_service.py`:

```python
"""Generate trivia questions with Claude.

Pure Python — no Django imports. Reads configuration from environment
variables, which Django populates from .env in Part 6.
"""

import json
import logging
import os
import random

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You generate multiple-choice trivia questions about a topic.

Return ONLY a valid JSON array. No prose, no explanation, no markdown code fences.

Format: a JSON array of objects, each with exactly these keys:
  "prompt_text"    (string) - the question
  "options"        (array of exactly 4 distinct strings) - the answer choices
  "correct_answer" (string) - MUST be byte-for-byte identical to one entry in "options"

Rules:
  - Exactly one option is correct.
  - Options must be plausible and of similar length to each other.
  - Never number the options or prefix them with A/B/C/D.
  - Do not make the correct option systematically longer or more specific.
  - Questions must be answerable without seeing the options."""

_client = None


class LLMError(Exception):
    """Raised when questions could not be generated, for any reason."""


def get_client():
    """Return a lazily-constructed Anthropic client.

    Built on first use rather than at import time so that importing this
    module never raises when ANTHROPIC_API_KEY is absent. That matters for
    the test suite and for the mock mode below.
    """
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env and "
                "restart the server, or set WATCHTRIVIA_MOCK_LLM=True to "
                "generate placeholder questions without calling the API."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def mock_enabled():
    return os.environ.get("WATCHTRIVIA_MOCK_LLM", "").lower() in {"1", "true", "yes"}


def generate_questions(topic_label, num_questions=3, model=None):
    """Generate multiple-choice trivia questions about a topic.

    Args:
        topic_label: The interest topic to generate questions about.
        num_questions: How many questions to generate.
        model: Override the Claude model ID. Defaults to $ANTHROPIC_MODEL
            or claude-sonnet-4-6.

    Returns:
        A list of dicts, each with:
            prompt_text    (str)
            options        (list[str], exactly 4)
            correct_answer (str, exactly matching one entry in options)

    Raises:
        LLMError: The API call failed, the response was not valid JSON after
            one retry, or the response did not match the required schema.
    """
    if mock_enabled():
        return _mock_questions(topic_label, num_questions)

    model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    user_prompt = f"Generate {num_questions} trivia questions about: {topic_label}"

    raw_text = _request(model, [
        {"role": "user", "content": user_prompt},
    ])

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON for %r; retrying once.", topic_label)
        raw_text = _request(model, [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": raw_text},
            {
                "role": "user",
                "content": (
                    "That was not valid JSON. Return ONLY the JSON array of "
                    "question objects, with no surrounding text or code fences."
                ),
            },
        ])
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Claude returned invalid JSON twice for topic {topic_label!r}."
            ) from exc

    return _validate_questions(payload, topic_label, num_questions)


def _request(model, messages):
    """Call the Messages API and return the response text, unwrapping errors."""
    try:
        response = get_client().messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.8,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.APIError as exc:
        raise LLMError(f"Anthropic API error: {exc}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc

    blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
    if not blocks:
        raise LLMError("Claude returned a response with no text content.")

    return blocks[0].text.strip()


def _validate_questions(payload, topic_label, num_questions):
    """Check the LLM's output actually matches the schema we promised.

    The system prompt asks for a specific shape. Asking is not the same as
    receiving, and a malformed question stored in the database becomes a
    broken quiz that no later code can repair. Validate at the boundary.
    """
    if not isinstance(payload, list):
        raise LLMError(
            f"Expected a JSON list of questions for {topic_label!r}, "
            f"got {type(payload).__name__}."
        )
    if not payload:
        raise LLMError(f"Claude returned no questions for {topic_label!r}.")

    valid = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            logger.warning("Question %d for %r is not an object; skipping.", index, topic_label)
            continue

        prompt_text = item.get("prompt_text")
        options = item.get("options")
        correct_answer = item.get("correct_answer")

        if not isinstance(prompt_text, str) or not prompt_text.strip():
            logger.warning("Question %d for %r has no prompt_text; skipping.", index, topic_label)
            continue
        if not isinstance(options, list) or len(options) != 4:
            logger.warning(
                "Question %d for %r has %s options, expected 4; skipping.",
                index, topic_label, len(options) if isinstance(options, list) else "no",
            )
            continue
        if not all(isinstance(opt, str) and opt.strip() for opt in options):
            logger.warning("Question %d for %r has a non-string option; skipping.", index, topic_label)
            continue
        if not isinstance(correct_answer, str) or correct_answer not in options:
            logger.warning(
                "Question %d for %r has correct_answer %r that is not one of "
                "its options; skipping.",
                index, topic_label, correct_answer,
            )
            continue

        valid.append({
            "prompt_text": prompt_text.strip(),
            "options": [opt.strip() for opt in options],
            "correct_answer": correct_answer.strip(),
        })

    if not valid:
        raise LLMError(
            f"None of Claude's {len(payload)} responses for {topic_label!r} "
            "matched the required schema."
        )

    return valid[:num_questions]


_MOCK_TOPICS = {
    "formula 1": [
        ("Which driver holds the record for most Formula 1 Grand Prix wins?",
         ["Michael Schumacher", "Lewis Hamilton", "Sebastian Vettel", "Max Verstappen"],
         "Lewis Hamilton"),
        ("What is the official tyre supplier of Formula 1?",
         ["Pirelli", "Goodyear", "Michelin", "Bridgestone"],
         "Pirelli"),
    ],
    "python programming": [
        ("Which keyword defines a function in Python?",
         ["function", "def", "lambda", "func"],
         "def"),
    ],
    "space astronomy": [
        ("Which planet has the shortest day in our solar system?",
         ["Mercury", "Jupiter", "Mars", "Venus"],
         "Jupiter"),
    ],
}


def _mock_questions(topic_label, num_questions):
    """Deterministic-ish placeholder questions, so the app works with no API key.

    Lets you exercise upload -> interests -> quiz -> scoring end to end with
    zero cost and zero network calls, and keeps the test suite free.
    """
    key = topic_label.strip().lower()
    template = _MOCK_TOPICS.get(key) or [
        (
            f"Which statement about {topic_label} is true?",
            [
                f"It is widely discussed in the context of {topic_label}.",
                f"It has no connection to {topic_label}.",
                f"It predates the invention of {topic_label}.",
                f"It is the opposite of {topic_label}.",
            ],
            f"It is widely discussed in the context of {topic_label}.",
        ),
    ]

    questions = []
    for index in range(num_questions):
        prompt_text, options, correct_answer = template[index % len(template)]
        questions.append({
            "prompt_text": prompt_text,
            "options": list(options),
            "correct_answer": correct_answer,
        })
    return questions
```

### Key Design Decisions Explained

#### 1. Lazy Client Construction

```python
def get_client():
    global _client
    if _client is None:
        ...
        _client = anthropic.Anthropic(api_key=api_key)
    return _client
```

The original plan created the client at module level:

```python
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
```

That means **importing the module raises `TypeError` when no API key is set** — because
`Anthropic(None)` refuses a `None` key. Since `views.py` imports `llm_service` at module
scope, and `views.py` is imported by `urls.py`, and `urls.py` is imported by Django at
startup, **the entire application fails to boot** without a key. You cannot run
migrations, cannot run the test suite, and cannot even reach the login page.

Constructing on first use means a missing key is a clean `LLMError` raised at the moment
someone actually tries to generate a quiz. This is the single most important fix in this
section.

#### 2. A Custom Exception Instead of Leaking Library Errors

Every failure mode — missing key, network failure, rate limit, malformed JSON, schema
violation — surfaces as `LLMError`. Views catch one exception type and can present a
useful message. The original plan let `anthropic.APIError` and `json.JSONDecodeError`
escape, so the view's `except` clause had to know about two unrelated libraries, and
anything else (a schema violation, say) became an unhandled 500.

#### 3. Output Validation

The original plan's own comment said:

> "Always validate the output structure in your code."

…and then did not. It called `json.loads()` and handed the result straight to
`Question.objects.create(options=q["options"], correct_answer=q["correct_answer"])`. A
response with three options, or a `correct_answer` that is not among the options, or a
missing `prompt_text` key, produced either a `KeyError` 500 or a **permanently broken
question row** that no later code can fix, because the quiz renders from the database.

`_validate_questions` checks every field, logs precisely why each item was rejected, and
raises if nothing survived. Real LLMs occasionally return five options, or a
`correct_answer` that differs from the options only in trailing punctuation. Better to
drop that one question and keep the quiz.

#### 4. The Retry Pattern

```python
try:
    payload = json.loads(raw_text)
except json.JSONDecodeError:
    raw_text = _request(model, [
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": raw_text},        # show it its own output
        {"role": "user", "content": "That was not valid JSON. Return ONLY the JSON array."},
    ])
```

Sometimes the model wraps JSON in markdown fences or adds a sentence of preamble. The
retry shows it its own broken output and asks it to fix it, which works far more often
than re-asking from scratch — the model can see what went wrong.

**Retry exactly once.** The original plan did this correctly and it is worth preserving:
an infinite retry loop against a paid API during a traffic spike is an expensive outage.

#### 5. `temperature=0.8`

The default is `1.0`. Trivia questions benefit from some variety — asking for
questions about "Formula 1" three times should not produce three near-identical items.
`0.8` keeps variety without the incoherence of the maximum.

#### 6. Mock Mode

```python
if mock_enabled():
    return _mock_questions(topic_label, num_questions)
```

Setting `WATCHTRIVIA_MOCK_LLM=True` short-circuits the API entirely. This is what makes
the rest of the tutorial followable without a paid account, and it means the view tests
in Part 7 never make network calls or cost money.

The mock deliberately includes a generic fallback so it works for **any** topic label,
including ones a real user uploads.

#### 7. The Model Is Configurable

```python
model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
```

Model IDs change as providers release new versions. Hardcoding one in a function body
means every model upgrade is a code change and a deploy. Reading it from the environment
means it is a config change. `claude-sonnet-4-6` is the current production baseline;
newer models (such as `claude-opus-4-8`) can be swapped in without touching code.

---

## How the Three Services Work Together

```
User uploads watch-history.json
        ↓
┌──────────────────────────────────────────────────┐
│  takeout_parser.parse_takeout_json(file)          │
│  Input:  uploaded file                            │
│  Output: [{video_title, channel_name, watched_at}]│
│  Raises: TakeoutParseError on bad input           │
└──────────────────┬───────────────────────────────┘
                   ↓
        bulk_create into WatchHistoryEntry
                   ↓
┌──────────────────────────────────────────────────┐
│  interest_ranker.rank_interests(entries, top_n=5) │
│  Input:  parsed entries                           │
│  Output: [{label, weight}] sorted desc            │
└──────────────────┬───────────────────────────────┘
                   ↓
        bulk_create into InterestTopic
                   ↓
User clicks "Generate my quiz"
        ↓
┌──────────────────────────────────────────────────┐
│  llm_service.generate_questions(label, n=2)       │
│  Input:  topic label string                       │
│  Output: [{prompt_text, options, correct_answer}] │
│  Raises: LLMError on any failure                  │
└──────────────────┬───────────────────────────────┘
                   ↓
        create QuizAttempt, then create Questions
        linked to that attempt
                   ↓
        user answers → Answer rows → score updates
```

Notice the failure behaviour at each arrow. The parser can raise `TakeoutParseError`
(becomes a form error, HTTP 400). The ranker cannot fail on well-formed input. The LLM
can raise `LLMError` (becomes a message on the page, HTTP 502, and the attempt is
cleaned up rather than left half-populated). Part 4 implements all three behaviours.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Service layer** | Business logic in plain Python, separate from views |
| **Pure function** | No side effects, no Django imports — trivially testable |
| **Custom exception** | One failure type a caller can catch, instead of N library types |
| **Lazy initialisation** | Build expensive objects on first use, not at import |
| **Boundary validation** | Never trust external input, including LLM output |
| **Bounded retry** | Retry once, then give up — never loop against a paid API |
| **`json.load()` vs `json.loads()`** | File-like object vs string |
| **`Counter`** | Python's built-in counting dict |
| **Mock mode** | A no-cost code path that lets the app run without an API key |
| **Environment variables** | Secrets and config loaded from `.env`, never hardcoded |

---

**→ Continue to [Part 4: Forms and Views](./04_forms_and_views.md)**
