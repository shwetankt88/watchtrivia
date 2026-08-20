# Part 8: The React Frontend

---

## Why React?

Django can serve HTML on its own (using templates), but Watchtrivia benefits from a **Single-Page Application (SPA)** — a page that never fully reloads, updating only the parts that change:

| Approach | How it works | User experience |
|----------|-------------|-----------------|
| **Django Templates** | Server renders full HTML per request | Page flashes white on every action |
| **React SPA** | Server sends JSON; browser updates the DOM | Instant, app-like transitions |

React is the right choice here because the quiz flow — upload → view interests → answer questions → see score — is a stateful, multi-step interaction that benefits from client-side state management.

### How React Differs from Vanilla JavaScript

In vanilla JS, you **manually** find DOM elements and mutate them:

```javascript
// Vanilla JS — imperative
document.getElementById("score").textContent = "5";
document.getElementById("quiz").style.display = "block";
```

In React, you **declare** what the UI should look like for a given state, and React figures out the DOM mutations:

```jsx
// React — declarative
const [score, setScore] = useState(0);

return <p>Score: {score}</p>;   // React updates the DOM when score changes
```

You never touch the DOM directly. You change **state**, and React re-renders.

---

## Setting Up the Frontend

### Scaffolding with Vite

From the project root (`watchtrivia/`):

```powershell
mkdir frontend
cd frontend
npm create vite@latest . -- --template react
npm install
```

**What is Vite?** A modern build tool that replaces older tools like Create React App:

| Feature | Create React App | Vite |
|---------|-----------------|------|
| Dev server startup | ~10 seconds | <500ms |
| Hot Module Replacement | Slow (rebundles everything) | Instant (only reloads changed module) |
| Build tool | Webpack | Rollup (production) + esbuild (dev) |
| Status | Deprecated (2023) | Actively maintained |

### Install Axios

```powershell
npm install axios
```

**Axios vs `fetch`:**

| Feature | `fetch` (built-in) | `axios` |
|---------|-------------------|---------|
| JSON parsing | Manual: `response.json()` | Automatic: `response.data` |
| Error handling | Only rejects on network failure | Rejects on 4xx/5xx too |
| Request interceptors | No | Yes |
| Cookie handling | `credentials: "include"` | `withCredentials: true` |

Both work. Axios is slightly more ergonomic for API calls, which is why the tutorial uses it.

### What Vite Created

```
frontend/
├── index.html          ← the single HTML page (entry point)
├── package.json        ← dependencies and scripts
├── vite.config.js      ← Vite configuration
├── public/             ← static assets (served as-is)
└── src/
    ├── main.jsx        ← JavaScript entry point (renders <App />)
    ├── App.jsx         ← root component (we'll rewrite this)
    ├── App.css         ← styles (we'll rewrite this)
    └── index.css       ← global styles
```

> [!NOTE]
> **`index.html` is the only HTML file.** React renders everything inside
> `<div id="root"></div>`. The browser loads this one page, then JavaScript
> takes over — hence "Single-Page Application."

---

## The API Client

Create `src/api.js`:

```javascript
import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api",
  withCredentials: true,   // sends/receives the Django session cookie
});

export default api;
```

### Line-by-Line Breakdown

```javascript
const api = axios.create({ ... });
```

`axios.create()` creates a **configured instance**. Every request made with `api.get(...)` or `api.post(...)` automatically:
- Prepends `http://localhost:8000/api` to the URL
- Includes cookies (`withCredentials: true`)

Without this, every API call would need:
```javascript
// WITHOUT axios.create — repetitive and error-prone
axios.post("http://localhost:8000/api/upload-history/", data, {
  withCredentials: true
});
axios.get("http://localhost:8000/api/interests/", {
  withCredentials: true
});
```

With it:
```javascript
// WITH axios.create — clean and DRY
api.post("/upload-history/", data);
api.get("/interests/");
```

### Why `withCredentials: true`?

Browsers don't send cookies to a different origin by default (security). Your frontend runs on `localhost:5173` but the API is on `localhost:8000` — different ports = different origins. `withCredentials: true` tells the browser: "Yes, send cookies to this cross-origin server."

This is the client-side counterpart to the CORS configuration we set up in Part 6. Both sides must agree:
- **Server (Django):** "I allow requests from `localhost:5173`" → `CORS_ALLOWED_ORIGINS`
- **Client (Axios):** "I'll send my cookies to this server" → `withCredentials: true`

---

## Understanding React Fundamentals

Before reading the main component, let's cover the React concepts it uses.

### JSX — HTML Inside JavaScript

JSX looks like HTML but it's JavaScript:

```jsx
// This JSX:
const element = <h1 className="title">Hello, {name}</h1>;

// Compiles to this JavaScript:
const element = React.createElement("h1", { className: "title" }, "Hello, ", name);
```

Key differences from HTML:

| HTML | JSX | Why |
|------|-----|-----|
| `class="..."` | `className="..."` | `class` is a reserved word in JS |
| `for="..."` | `htmlFor="..."` | `for` is a reserved word in JS |
| `onclick="..."` | `onClick={...}` | camelCase event handlers |
| `style="color: red"` | `style={{ color: "red" }}` | Object, not string |
| Self-closing tags optional | Self-closing required | `<input />`, `<br />` |

### `useState` — Reactive State

```jsx
const [count, setCount] = useState(0);
//     ↑        ↑                  ↑
//   value   setter fn       initial value
```

- `count` is the current value
- `setCount` is a function that updates it **and triggers a re-render**
- `useState(0)` sets the initial value to `0`

```jsx
// When you call setCount, React re-renders the component
setCount(5);        // count is now 5, component re-renders
setCount(c => c+1); // function form for updates based on previous value
```

> [!IMPORTANT]
> **State updates are asynchronous.** After calling `setCount(5)`, `count`
> is still the old value until the next render. Never read state right after
> setting it and expect the new value.

### Conditional Rendering

React uses plain JavaScript to conditionally show UI:

```jsx
// Pattern 1: && (show or hide)
{isLoading && <p>Loading...</p>}
// If isLoading is true → renders <p>Loading...</p>
// If isLoading is false → renders nothing

// Pattern 2: ternary (either/or)
{isLoggedIn ? <Dashboard /> : <LoginForm />}
```

### List Rendering with `.map()`

```jsx
{items.map((item) => (
  <li key={item.id}>{item.name}</li>
))}
```

`.map()` transforms an array of data into an array of JSX elements. The `key` prop is **required** — React uses it to efficiently update lists. Without it, React re-renders the entire list on every change.

> [!WARNING]
> **Never use array index as `key`** if the list can be reordered or filtered.
> Use a stable, unique identifier like `item.id`. Using index as key causes
> subtle bugs when items are added, removed, or reordered.

### `async/await` — Handling API Calls

```jsx
const handleUpload = async () => {
  try {
    const response = await api.post("/upload-history/", formData);
    setInterests(response.data);    // success → update state
  } catch (err) {
    console.error(err);              // failure → log error
  }
};
```

- `async` marks the function as asynchronous
- `await` pauses execution until the API call completes
- `try/catch` handles network errors, 4xx/5xx responses, etc.

---

## The Main Component

Replace `src/App.jsx`:

```jsx
import { useState } from "react";
import api from "./api";
import "./App.css";

function App() {
  const [interests, setInterests] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [attemptId, setAttemptId] = useState(null);
  const [status, setStatus] = useState("idle");

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setStatus("uploading");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await api.post("/upload-history/", formData);
      setInterests(response.data);
      setStatus("ready");
    } catch (err) {
      console.error(err);
      setStatus("idle");
    }
  };

  const handleGenerateQuiz = async () => {
    setStatus("generating");
    try {
      const response = await api.post("/generate-quiz/");
      setAttemptId(response.data.attempt_id);
      setQuestions(response.data.questions);
      setStatus("quiz");
    } catch (err) {
      console.error(err);
      setStatus("ready");
    }
  };

  const handleAnswer = async (questionId, selectedAnswer) => {
    const response = await api.post(`/attempts/${attemptId}/submit-answer/`, {
      question_id: questionId,
      selected_answer: selectedAnswer,
    });
    alert(response.data.is_correct ? "Correct!" : `Wrong - it was ${response.data.correct_answer}`);
  };

  return (
    <div className="app">
      <h1>Watchtrivia</h1>

      {status === "idle" && (
        <div>
          <p>Upload your Google Takeout watch-history.json to get started.</p>
          <input type="file" accept=".json" onChange={handleFileUpload} />
        </div>
      )}

      {status === "uploading" && <p>Processing your watch history...</p>}

      {(status === "ready" || status === "generating") && (
        <div>
          <h2>Your top interests</h2>
          <ul>
            {interests.map((topic) => (
              <li key={topic.id}>{topic.label} - {(topic.weight * 100).toFixed(0)}%</li>
            ))}
          </ul>
          <button onClick={handleGenerateQuiz} disabled={status === "generating"}>
            {status === "generating" ? "Generating quiz..." : "Generate my quiz"}
          </button>
        </div>
      )}

      {status === "quiz" && (
        <div>
          <h2>Your quiz</h2>
          {questions.map((q) => (
            <div key={q.id} className="question-card">
              <p><strong>{q.topic_label}:</strong> {q.prompt_text}</p>
              {q.options.map((option) => (
                <button key={option} onClick={() => handleAnswer(q.id, option)}>{option}</button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default App;
```

---

## Deep Dive: How the Component Works

### The State Machine

This component is a **state machine** with four states:

```
                    ┌──────────┐
                    │   idle   │  ← initial state
                    └────┬─────┘
                         │ user selects a file
                         ▼
                    ┌──────────┐
                    │uploading │  ← processing watch history
                    └────┬─────┘
              success │      │ error
                      ▼      ▼
                ┌──────────┐  ┌──────────┐
                │  ready   │  │   idle   │  ← back to start on error
                └────┬─────┘  └──────────┘
                     │ user clicks "Generate"
                     ▼
                ┌──────────────┐
                │  generating  │  ← LLM is working
                └────┬─────────┘
              success │      │ error
                      ▼      ▼
                 ┌────────┐  ┌──────────┐
                 │  quiz  │  │  ready   │  ← back to interests on error
                 └────────┘  └──────────┘
```

Each state maps to a different rendered UI:

| State | What the user sees |
|-------|-------------------|
| `idle` | File upload input |
| `uploading` | "Processing your watch history..." message |
| `ready` | Interest list + "Generate my quiz" button |
| `generating` | Interest list + disabled "Generating quiz..." button |
| `quiz` | Question cards with answer buttons |

### File Upload Flow

```jsx
const handleFileUpload = async (event) => {
  // 1. Get the file from the input element
  const file = event.target.files[0];
  if (!file) return;

  // 2. Transition to "uploading" state
  setStatus("uploading");

  // 3. Create a FormData object (browser API for multipart uploads)
  const formData = new FormData();
  formData.append("file", file);

  try {
    // 4. POST to Django — Django receives this in request.FILES["file"]
    const response = await api.post("/upload-history/", formData);

    // 5. Django returns the computed interests → store in state
    setInterests(response.data);

    // 6. Transition to "ready" state → shows interests + quiz button
    setStatus("ready");
  } catch (err) {
    console.error(err);
    setStatus("idle");  // error → back to upload screen
  }
};
```

### `FormData` — How File Uploads Work

```javascript
const formData = new FormData();
formData.append("file", file);
```

`FormData` is a browser API that constructs `multipart/form-data` — the encoding required for file uploads. When Axios sees a `FormData` body, it automatically:
1. Sets `Content-Type: multipart/form-data`
2. Adds a boundary string to separate form fields
3. Streams the file data efficiently

On the Django side, the file arrives in `request.FILES["file"]` — the key `"file"` matches what we passed to `formData.append("file", ...)`.

### Quiz Generation Flow

```jsx
const handleGenerateQuiz = async () => {
  setStatus("generating");     // disable the button, show loading text
  try {
    const response = await api.post("/generate-quiz/");
    setAttemptId(response.data.attempt_id);   // save for submitting answers
    setQuestions(response.data.questions);      // store questions
    setStatus("quiz");                          // show quiz UI
  } catch (err) {
    console.error(err);
    setStatus("ready");        // error → stay on interests page
  }
};
```

Note how `setStatus("generating")` disables the button:

```jsx
<button onClick={handleGenerateQuiz} disabled={status === "generating"}>
  {status === "generating" ? "Generating quiz..." : "Generate my quiz"}
</button>
```

This prevents double-clicking — the user can't fire multiple LLM requests by hammering the button.

### Answer Submission Flow

```jsx
const handleAnswer = async (questionId, selectedAnswer) => {
  const response = await api.post(`/attempts/${attemptId}/submit-answer/`, {
    question_id: questionId,
    selected_answer: selectedAnswer,
  });
  alert(response.data.is_correct ? "Correct!" : `Wrong - it was ${response.data.correct_answer}`);
};
```

Template literals (`` `...${variable}...` ``) embed `attemptId` into the URL. The response comes back with `is_correct` (boolean) and `correct_answer` (string).

> [!TIP]
> The `alert()` here is a placeholder — a production app would show inline
> feedback (green/red highlighting, score counter, etc.) instead of a
> browser alert. This is a natural improvement once the basic flow works.

### Understanding `key` Props

```jsx
{questions.map((q) => (
  <div key={q.id} className="question-card">
```

React uses `key` to track which list items changed between renders:

| Without `key` | With `key` |
|--------------|-----------|
| React compares by **position** | React compares by **identity** |
| Reordering = re-render everything | Reordering = just move DOM nodes |
| Can cause stale state bugs | Correct behavior guaranteed |

---

## Adding Basic Styles

Replace `src/App.css`:

```css
.app {
  max-width: 700px;
  margin: 2rem auto;
  padding: 0 1rem;
  font-family: system-ui, -apple-system, sans-serif;
}

h1 {
  font-size: 2rem;
  margin-bottom: 1.5rem;
}

h2 {
  font-size: 1.4rem;
  margin-bottom: 1rem;
}

.question-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.question-card button {
  display: block;
  width: 100%;
  padding: 0.6rem;
  margin-top: 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 0.95rem;
  text-align: left;
}

.question-card button:hover {
  background-color: #f0f0f0;
  border-color: #999;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

input[type="file"] {
  margin-top: 0.5rem;
}

ul {
  padding-left: 1.5rem;
}

li {
  margin-bottom: 0.3rem;
}
```

These are intentionally minimal — functional, readable, and easy to extend. Styling is not the focus of this tutorial; the structure and logic are.

---

## Running the Frontend

```powershell
cd frontend
npm run dev
```

Vite starts a dev server on `http://localhost:5173` with **Hot Module Replacement (HMR)** — edit `App.jsx`, save, and the browser updates instantly without losing state.

> [!WARNING]
> **The frontend won't work on its own.** It needs the Django backend running
> on port 8000 and a valid session cookie (you must be logged in via
> `/admin/`). See Part 9 for running both servers together.

---

## Component Architecture Concepts

### Why One File Works Here

This app uses a single `App.jsx` component. For a tutorial, this is fine. In a production app, you'd split it:

```
src/
├── components/
│   ├── FileUpload.jsx      ← upload UI
│   ├── InterestList.jsx    ← interests display
│   ├── QuizCard.jsx        ← single question
│   └── QuizResults.jsx     ← score screen
├── App.jsx                 ← orchestrates components
└── api.js                  ← API client
```

Each component would receive data and callbacks via **props**:

```jsx
// App.jsx passes data down
<InterestList interests={interests} onGenerateQuiz={handleGenerateQuiz} />

// InterestList.jsx receives it
function InterestList({ interests, onGenerateQuiz }) {
  return (
    <div>
      <ul>
        {interests.map(t => <li key={t.id}>{t.label}</li>)}
      </ul>
      <button onClick={onGenerateQuiz}>Generate my quiz</button>
    </div>
  );
}
```

This is **data-down, actions-up** — the parent owns the state, children receive read-only props and trigger callbacks to update the parent.

### When to Split Components

Split a component when:
1. **It's too long** (>200 lines is a warning sign)
2. **It has distinct responsibilities** (upload vs quiz vs results)
3. **Parts are reusable** (a `QuizCard` could be used elsewhere)
4. **Testing becomes hard** (smaller components = easier to test)

---

## Common Pitfalls

### CORS Errors

```
Access to XMLHttpRequest at 'http://localhost:8000/api/interests/'
from origin 'http://localhost:5173' has been blocked by CORS policy
```

**Fix:** Ensure Django's `CORS_ALLOWED_ORIGINS` in `settings.py` includes `"http://localhost:5173"` (Part 6).

### 403 Forbidden

```json
{"detail": "Authentication credentials were not provided."}
```

**Fix:** You need a session cookie. Log in at `http://localhost:8000/admin/` in the **same browser** before using the React app.

### Cookie Not Sent

If requests succeed from the admin but fail from React, check:
1. `withCredentials: true` in `api.js`
2. `CORS_ALLOW_CREDENTIALS = True` in `settings.py` (if not using `CORS_ALLOWED_ORIGINS`)
3. Both servers running in the same browser

---

## Key Concepts Recap

| Concept | What it means |
|---------|--------------|
| **SPA** | Single-Page Application — one HTML page, JavaScript handles routing |
| **Vite** | Modern build tool — instant dev server, fast builds |
| **`useState`** | React hook for declaring reactive state |
| **`async/await`** | JavaScript syntax for handling asynchronous operations |
| **`FormData`** | Browser API for constructing file upload payloads |
| **`axios.create()`** | Creates a pre-configured HTTP client instance |
| **`withCredentials`** | Tells the browser to send cookies cross-origin |
| **`key` prop** | Unique identifier React uses to track list items |
| **Conditional rendering** | `{condition && <JSX>}` pattern for show/hide |
| **Props** | Read-only data passed from parent to child component |

---

**→ Continue to [Part 9: Running It All & What's Next](./09_running_and_next_steps.md)**
