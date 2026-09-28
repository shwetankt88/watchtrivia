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

    An entry whose whole title was "Watched" carries no information — Google
    emits that when the video name is unavailable — so it is dropped.
    """
    title = (raw_title or "").strip()
    if title.startswith(TITLE_PREFIX):
        title = title[len(TITLE_PREFIX):]
    title = title.strip()
    if not title or title.casefold() == TITLE_PREFIX.strip().casefold():
        return ""
    return title


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
