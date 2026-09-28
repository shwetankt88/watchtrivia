# Watchtrivia

Upload your YouTube Takeout watch history, and it builds a quiz from what you
actually watch. Channels become "interests", interests become questions, and
you find out how much you were paying attention.

## What it is

- Django 6 + HTMX (server-rendered, works without JavaScript)
- Takeout `watch-history.json` parsing, with device-dedupe
- Interest ranking by channel share of your history
- Claude-generated questions per interest, with retries and validation
- Optional JSON API (Django REST Framework) at `/api/`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
cp .env.example .env      # then edit .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/accounts/login/ and sign in.

## Configuration

`.env` in `backend/`:

| Variable | Meaning |
| --- | --- |
| `ANTHROPIC_API_KEY` | Required for real questions. Blank means questions cannot be generated. |
| `ANTHROPIC_MODEL` | Defaults to `claude-sonnet-4-6`. |
| `WATCHTRIVIA_MOCK_LLM` | `True` generates placeholder questions locally. No key, no network, no cost. |
| `DJANGO_SECRET_KEY` | Generated for you in `.env.example`. |
| `DEBUG` | `True` for local development. |

## Tests

```bash
cd backend
python manage.py test trivia
```

No API key and no network access needed: the LLM service is either mocked or
short-circuited by `WATCHTRIVIA_MOCK_LLM`.

## Sample data

`sample-data/watch-history.json` is a synthetic 80-video history across six
channels. `python manage.py test trivia.tests.test_interest_ranker` parses and
ranks it, so the shipped file cannot silently rot.

## Layout

```
backend/
  manage.py
  watchtrivia/          settings, root URLs
  trivia/
    models.py           users' history, interests, attempts, questions, answers
    views.py            HTML flow + the data functions the API reuses
    api_views.py        DRF endpoints
    services/           takeout_parser, interest_ranker, llm_service
    templates/          pages and HTMX partials
    tests/              parser, ranker, models, views, API
sample-data/            synthetic Takeout export
```

The tutorial that produced this project is in `01_*.md` … `10_*.md`.
