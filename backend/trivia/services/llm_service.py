"""Generate trivia questions with Claude.

Pure Python — no Django imports. Reads configuration from environment
variables, which Django populates from .env in Part 6.
"""

import json
import logging
import os

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
    except anthropic.APIConnectionError as exc:
        raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc
    except anthropic.APIError as exc:
        raise LLMError(f"Anthropic API error: {exc}") from exc

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
