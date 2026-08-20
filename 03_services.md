# Part 3: Services — Parsing, Ranking, and the LLM

---

## The Service Layer Pattern

Django's default architecture puts logic in **views**. This works for small apps, but Watchtrivia has three distinct pieces of business logic:

1. **Parsing** YouTube Takeout data
2. **Ranking** user interests from watch history
3. **Generating** quiz questions via an LLM

If you stuffed all of this into views, each view function would be hundreds of lines long and impossible to test without making HTTP requests. The **service layer pattern** solves this:

```
┌─────────────────┐         ┌───────────────────┐         ┌──────────────┐
│   View (thin)   │ ──────→ │  Service (logic)  │ ──────→ │  Model (data)│
│ Handles HTTP    │         │ Pure Python        │         │ Database ORM │
│ request/response│         │ Independently      │         │              │
│                 │         │ testable           │         │              │
└─────────────────┘         └───────────────────┘         └──────────────┘
```

**The rule: Views handle HTTP. Services handle logic. Models handle data.**

### Setting Up the Services Package

Create the directory structure:

```powershell
# From the backend/ directory
mkdir trivia\services
```

Create the following files:
- `trivia/services/__init__.py` (empty file — makes it a Python package)
- `trivia/services/takeout_parser.py`
- `trivia/services/interest_ranker.py`
- `trivia/services/llm_service.py`

---

## Service 1: Parsing Google Takeout Data

### What is Google Takeout?

Google Takeout (`takeout.google.com`) lets you export your data from any Google service. For YouTube, you can export your watch history as a JSON file. Here's what the raw data looks like:

```json
[
  {
    "header": "YouTube",
    "title": "Watched Max Verstappen's Incredible Overtake",
    "titleUrl": "https://www.youtube.com/watch?v=abc123",
    "subtitles": [
      {
        "name": "F1 Official",
        "url": "https://www.youtube.com/channel/UCB_..."
      }
    ],
    "time": "2024-12-15T14:30:00.000Z",
    "products": ["YouTube"]
  },
  {
    "header": "YouTube",
    "title": "Watched How Black Holes Really Work",
    "titleUrl": "https://www.youtube.com/watch?v=def456",
    "subtitles": [
      {
        "name": "Veritasium",
        "url": "https://www.youtube.com/channel/UCD..."
      }
    ],
    "time": "2024-12-14T10:15:00.000Z"
  }
]
```

### The Parser

`trivia/services/takeout_parser.py`:

```python
import json
from datetime import datetime


def parse_takeout_json(file_obj):
    """
    Parse a Google Takeout watch-history.json file.
    
    Args:
        file_obj: A file-like object (from request.FILES or open())
        
    Returns:
        List of dicts, each with keys:
        - video_title (str)
        - channel_name (str)
        - watched_at (datetime or None)
    """
    raw_data = json.load(file_obj)
    entries = []

    for item in raw_data:
        # Skip non-video entries (ads, deleted videos, etc.)
        if "titleUrl" not in item or "watch?v=" not in item.get("titleUrl", ""):
            continue

        # Google prepends "Watched " to every title — remove it
        title = item.get("title", "").replace("Watched ", "", 1)

        # Channel name is in the subtitles array
        channel = ""
        if item.get("subtitles"):
            channel = item["subtitles"][0].get("name", "")

        # Parse the ISO timestamp
        watched_at = None
        if item.get("time"):
            try:
                watched_at = datetime.fromisoformat(
                    item["time"].replace("Z", "+00:00")
                )
            except ValueError:
                pass  # skip unparseable timestamps

        entries.append({
            "video_title": title,
            "channel_name": channel,
            "watched_at": watched_at,
        })

    return entries
```

### Line-by-Line Breakdown

#### `json.load(file_obj)`

`json.load()` reads from a **file-like object** (anything with a `.read()` method), while `json.loads()` reads from a **string**. Django's `request.FILES` gives you file-like objects, so `json.load()` is the right choice.

#### The Filter: `"watch?v=" not in item.get("titleUrl", "")`

Google Takeout includes more than just regular videos — it includes ads, deleted videos, and other artifacts. These lack a `titleUrl` or have a non-standard URL. We filter for `watch?v=` to keep only actual YouTube videos.

#### `item.get("title", "").replace("Watched ", "", 1)`

- `dict.get(key, default)` returns the default if the key is missing (instead of raising `KeyError`)
- `.replace("Watched ", "", 1)` — the `1` means "replace only the first occurrence." Without it, a title like "Watched I Watched Every Star Wars Movie" would become "I Every Star Wars Movie"

#### `datetime.fromisoformat(item["time"].replace("Z", "+00:00"))`

Google's timestamps look like `"2024-12-15T14:30:00.000Z"`. The `Z` means UTC, but Python's `fromisoformat()` (before 3.11) doesn't understand `Z` — it expects `+00:00`. So we replace it.

> [!NOTE]
> **This file has zero Django imports.** That's intentional. By keeping it as pure Python,
> you can test it with plain `pytest` in milliseconds — no database, no server, no Django
> test runner needed. This is the biggest advantage of the service layer pattern.

---

## Service 2: Ranking Interests

### The Algorithm (v1: Channel Frequency)

The simplest way to figure out what a user is interested in: **count which channels they watch most**.

`trivia/services/interest_ranker.py`:

```python
from collections import Counter


def rank_interests(watch_entries, top_n=5):
    """
    Rank user interests by channel frequency.
    
    Args:
        watch_entries: List of dicts with 'channel_name' key
        top_n: Number of top interests to return
        
    Returns:
        List of dicts with 'label' (channel name) and 'weight' (0.0 to 1.0)
    """
    # Count videos per channel, ignoring entries with no channel name
    channel_counts = Counter(
        entry["channel_name"]
        for entry in watch_entries
        if entry.get("channel_name")
    )

    if not channel_counts:
        return []

    # Normalize to weights (0.0 to 1.0)
    total = sum(channel_counts.values())
    top_channels = channel_counts.most_common(top_n)

    return [
        {"label": channel, "weight": round(count / total, 3)}
        for channel, count in top_channels
    ]
```

### Understanding `Counter`

`Counter` is from Python's `collections` module — it counts occurrences of items:

```python
from collections import Counter

c = Counter(["F1", "F1", "F1", "Finance", "Gaming"])
# Counter({'F1': 3, 'Finance': 1, 'Gaming': 1})

c.most_common(2)
# [('F1', 3), ('Finance', 1)]
```

### The Weight Calculation

If a user watched 100 videos total and 30 were from "F1 Official":

```
weight = 30 / 100 = 0.3
```

This means 30% of their watch history is F1 content. The weight is a **proportion**, not an absolute count — this makes it comparable across users with different history sizes.

### Future Upgrade: TF-IDF + K-Means (v2)

Channel frequency is crude — it tells you "you watch a lot of F1 Official" but can't distinguish between F1 race highlights, F1 technical analysis, and F1 news.

The v2 approach (using `scikit-learn`) would:

1. **TF-IDF** (Term Frequency-Inverse Document Frequency) on video **titles** to find important words
2. **K-Means clustering** to group similar titles into topics
3. Return topic labels instead of channel names

```python
# v2 preview (we'll build this in Part 10)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

def rank_interests_v2(watch_entries, n_clusters=5):
    titles = [e["video_title"] for e in watch_entries]
    
    vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(titles)
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    kmeans.fit(tfidf_matrix)
    
    # Extract top terms per cluster as topic labels
    # ... (full implementation in Part 10)
```

> [!TIP]
> **Start simple, iterate.** Ship v1 (channel frequency), verify the end-to-end
> flow works, then upgrade to v2. This is a core engineering principle — avoid
> premature complexity.

---

## Service 3: Generating Questions with the LLM

### The Anthropic Claude API

Claude is an LLM made by Anthropic. We use it to generate trivia questions based on a user's interests.

`trivia/services/llm_service.py`:

```python
import json
import os
import anthropic

# Initialize the client once (module level)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You generate multiple-choice trivia questions.
Return ONLY valid JSON, no other text, no markdown code fences.
Format: a JSON list of objects, each with keys:
"prompt_text" (string), "options" (list of 4 strings), "correct_answer" (string, must exactly match one option).
"""


def generate_questions(topic_label, num_questions=3):
    """
    Generate trivia questions about a topic using Claude.
    
    Args:
        topic_label: The interest topic to generate questions about
        num_questions: How many questions to generate
        
    Returns:
        List of dicts, each with keys:
        - prompt_text (str): The question text
        - options (list of str): 4 multiple-choice options
        - correct_answer (str): The correct option (exact match)
        
    Raises:
        json.JSONDecodeError: If the LLM returns invalid JSON after retry
        anthropic.APIError: If the API call fails
    """
    user_prompt = f"Generate {num_questions} trivia questions about: {topic_label}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()

    try:
        questions = json.loads(raw_text)
    except json.JSONDecodeError:
        # Retry with a sharper prompt
        retry_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_text},
                {
                    "role": "user",
                    "content": "That wasn't valid JSON. Return ONLY the JSON list, nothing else.",
                },
            ],
        )
        raw_text = retry_response.content[0].text.strip()
        questions = json.loads(raw_text)

    return questions
```

### Key Design Decisions Explained

#### 1. Module-Level Client Initialization

```python
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
```

The `Anthropic` client is created once when the module is first imported, not inside each function call. This avoids recreating the HTTP connection pool on every request.

#### 2. System Prompt Engineering

```python
SYSTEM_PROMPT = """You generate multiple-choice trivia questions.
Return ONLY valid JSON, no other text, no markdown code fences.
Format: a JSON list of objects, each with keys: ...
"""
```

The system prompt:
- **Defines the role**: "You generate trivia questions"
- **Constrains the output format**: "Return ONLY valid JSON"
- **Specifies the schema**: Exact keys and types expected

> [!IMPORTANT]
> LLMs are non-deterministic — the same prompt can produce different outputs.
> The tighter your format constraints, the more reliable the parsing.
> Always validate the output structure in your code.

#### 3. The Retry Pattern

```python
try:
    questions = json.loads(raw_text)
except json.JSONDecodeError:
    # Retry with conversation history
    retry_response = client.messages.create(
        messages=[
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": raw_text},  # show it its own output
            {"role": "user", "content": "That wasn't valid JSON. Return ONLY the JSON list."},
        ],
    )
```

Sometimes the LLM wraps its JSON in markdown code fences (` ```json ... ``` `) or adds prose. The retry:

1. Shows the LLM its own broken output (`"assistant"` message)
2. Asks it to fix it
3. This usually works because the LLM can see what went wrong

If the retry also fails, `json.loads()` raises `JSONDecodeError`, which the view catches with `try/except`.

### Loading the API Key

The API key comes from the environment variable `ANTHROPIC_API_KEY`. You set this in `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

To load `.env` files automatically, add to `watchtrivia/settings.py`:

```python
from dotenv import load_dotenv
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")
```

> [!CAUTION]
> **Never hardcode API keys in source code.** Even in a private repo, keys in code
> are a security risk. Always use environment variables loaded from `.env` (development)
> or the hosting platform's secrets manager (production).

---

## How the Three Services Work Together

Here's the data flow when a user uploads their watch history and takes a quiz:

```
User uploads watch-history.json
        ↓
┌─────────────────────────────────────┐
│     takeout_parser.parse_takeout_json()   │
│     Input:  JSON file                      │
│     Output: List of {title, channel, time} │
└─────────────────┬───────────────────┘
                  ↓
        Saved to WatchHistoryEntry table
                  ↓
┌─────────────────────────────────────┐
│     interest_ranker.rank_interests()       │
│     Input:  List of watch entries          │
│     Output: Top N {label, weight}          │
└─────────────────┬───────────────────┘
                  ↓
        Saved to InterestTopic table
                  ↓
        User clicks "Generate Quiz"
                  ↓
┌─────────────────────────────────────┐
│     llm_service.generate_questions()       │
│     Input:  Topic label string             │
│     Output: List of {prompt, options, ans} │
│     (Called once per interest topic)        │
└─────────────────┬───────────────────┘
                  ↓
        Saved to Question table
        QuizAttempt created
                  ↓
        Quiz displayed to user
```

---

## Testing Your Services

Since services are pure Python (no Django dependencies for parser and ranker), you can test them instantly:

```python
# Quick smoke test in the Django shell
python manage.py shell

>>> from trivia.services.interest_ranker import rank_interests
>>> entries = [
...     {"channel_name": "F1"},
...     {"channel_name": "F1"},
...     {"channel_name": "Gaming"},
... ]
>>> rank_interests(entries, top_n=2)
[{'label': 'F1', 'weight': 0.667}, {'label': 'Gaming', 'weight': 0.333}]
```

We'll write proper unit tests in Part 7.

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **Service layer** | Business logic in plain Python modules, separate from views |
| **Pure functions** | Functions with no side effects — easy to test |
| **`json.load()` vs `json.loads()`** | File-like object vs string |
| **`Counter`** | Python's built-in counting dict |
| **System prompt** | Instruction to the LLM about its role and output format |
| **Retry pattern** | Try once, if it fails, try again with more context |
| **Environment variables** | Secrets loaded from `.env`, never hardcoded |

---

**→ Continue to [Part 4: Serializers and Views](./04_serializers_and_views.md)**
