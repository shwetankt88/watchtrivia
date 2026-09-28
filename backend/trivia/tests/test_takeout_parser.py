import io
import json
from datetime import datetime, timezone

from django.test import SimpleTestCase

from trivia.services.takeout_parser import (
    TakeoutParseError,
    parse_takeout_json,
    parse_takeout_monthly_json,
)


def make_entry(title, video_id="abc", channel="Test Channel", time=None):
    """Build one raw Takeout entry."""
    entry = {
        "header": "YouTube",
        "title": title,
        "titleUrl": f"https://www.youtube.com/watch?v={video_id}",
        "subtitles": [{"name": channel}],
    }
    if time is not None:
        entry["time"] = time
    return entry


def parse(raw):
    return parse_takeout_json(io.StringIO(json.dumps(raw)))


class ParseTitleTests(SimpleTestCase):
    def test_strips_watched_prefix(self):
        result = parse([make_entry("Watched F1 Highlights")])
        self.assertEqual(result[0]["video_title"], "F1 Highlights")

    def test_strips_only_the_first_watched_prefix(self):
        """A title legitimately containing 'Watched' must survive intact."""
        result = parse([make_entry("Watched I Watched Every Star Wars Movie")])
        self.assertEqual(
            result[0]["video_title"], "I Watched Every Star Wars Movie"
        )

    def test_strips_whitespace_after_prefix(self):
        """Google emits 'Watched  Foo' with two spaces on some accounts."""
        result = parse([make_entry("Watched  Double Space")])
        self.assertEqual(result[0]["video_title"], "Double Space")

    def test_leaves_untitled_entries_out(self):
        with self.assertRaises(TakeoutParseError):
            parse([make_entry("Watched   ")])


class ParseFilteringTests(SimpleTestCase):
    def test_keeps_real_videos(self):
        result = parse([make_entry("Watched A", video_id="a")])
        self.assertEqual(len(result), 1)

    def test_skips_entries_without_watch_url(self):
        """Homepage visits and 'Watched [Deleted video]' have no watch?v= URL."""
        raw = [
            {"title": "Visited the YouTube homepage",
             "titleUrl": "https://www.youtube.com/?gl=US"},
            {"title": "Watched [Deleted video]", "subtitles": [{"name": "Gone"}]},
        ]
        with self.assertRaises(TakeoutParseError):
            parse(raw)

    def test_skips_non_dict_items(self):
        """A bare string in the array must not crash the parser."""
        result = parse(["a string", 42, None, make_entry("Watched Real", "r")])
        self.assertEqual(len(result), 1)

    def test_raises_when_no_videos_found(self):
        """Uploading subscriptions.json must fail loudly, not silently."""
        with self.assertRaises(TakeoutParseError):
            parse([{"title": "Some Channel", "titleUrl": "https://youtube.com/c/abc"}])


class ParseChannelTests(SimpleTestCase):
    def test_extracts_channel_name(self):
        result = parse([make_entry("Watched A", channel="F1 Official")])
        self.assertEqual(result[0]["channel_name"], "F1 Official")

    def test_missing_subtitles_gives_empty_string(self):
        raw = [{
            "title": "Watched A",
            "titleUrl": "https://www.youtube.com/watch?v=a",
        }]
        result = parse(raw)
        self.assertEqual(result[0]["channel_name"], "")

    def test_malformed_subtitles_give_empty_string(self):
        raw = [{
            "title": "Watched A",
            "titleUrl": "https://www.youtube.com/watch?v=a",
            "subtitles": ["not a dict"],
        }]
        result = parse(raw)
        self.assertEqual(result[0]["channel_name"], "")


class ParseTimestampTests(SimpleTestCase):
    def test_parses_zulu_suffix(self):
        result = parse([make_entry("Watched A", time="2024-12-15T14:30:00.000Z")])
        self.assertEqual(
            result[0]["watched_at"],
            datetime(2024, 12, 15, 14, 30, tzinfo=timezone.utc),
        )

    def test_converts_offsets_to_utc(self):
        result = parse([make_entry("Watched A", time="2024-12-13T10:15:00.000+05:30")])
        self.assertEqual(
            result[0]["watched_at"],
            datetime(2024, 12, 13, 4, 45, tzinfo=timezone.utc),
        )

    def test_treats_naive_timestamps_as_utc(self):
        result = parse([make_entry("Watched A", time="2024-12-15T14:30:00")])
        self.assertEqual(
            result[0]["watched_at"],
            datetime(2024, 12, 15, 14, 30, tzinfo=timezone.utc),
        )

    def test_always_returns_aware_datetimes(self):
        """USE_TZ=True means a naive datetime triggers a warning and wrong maths."""
        result = parse([make_entry("Watched A", time="2024-12-15T14:30:00Z")])
        self.assertIsNotNone(result[0]["watched_at"].tzinfo)

    def test_unparseable_timestamp_becomes_none(self):
        result = parse([make_entry("Watched A", time="last tuesday")])
        self.assertIsNone(result[0]["watched_at"])

    def test_missing_timestamp_becomes_none(self):
        result = parse([make_entry("Watched A")])
        self.assertIsNone(result[0]["watched_at"])


class ParseErrorTests(SimpleTestCase):
    def test_malformed_json_raises(self):
        with self.assertRaises(TakeoutParseError) as ctx:
            parse_takeout_json(io.StringIO("{not valid json"))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_json_object_at_top_level_raises(self):
        with self.assertRaises(TakeoutParseError):
            parse_takeout_json(io.StringIO('{"entries": []}'))

    def test_empty_list_raises(self):
        with self.assertRaises(TakeoutParseError):
            parse_takeout_json(io.StringIO("[]"))

    def test_error_message_names_the_right_file(self):
        """The user needs to know which file to upload, not just that it failed."""
        with self.assertRaises(TakeoutParseError) as ctx:
            parse_takeout_json(io.StringIO("[]"))
        self.assertIn("watch-history.json", str(ctx.exception))


class MonthlyVariantTests(SimpleTestCase):
    def test_flattens_nested_arrays(self):
        raw = [
            [make_entry("Watched A", "a", "Channel One")],
            [make_entry("Watched B", "b", "Channel Two")],
        ]
        result = parse_takeout_monthly_json(io.StringIO(json.dumps(raw)))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["channel_name"], "Channel One")
