import io
import json
import pathlib

from django.test import SimpleTestCase

from trivia.services.interest_ranker import rank_interests, renormalize
from trivia.services.takeout_parser import parse_takeout_json

SAMPLE_DATA = (
    pathlib.Path(__file__).resolve().parents[3] / "sample-data" / "watch-history.json"
)


def entries(*channels):
    """Build a watch-entry list from channel names."""
    return [{"channel_name": channel} for channel in channels]


class RankInterestsTests(SimpleTestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(rank_interests([]), [])

    def test_entries_without_channel_names_are_ignored(self):
        result = rank_interests(
            [{"channel_name": ""}, {"channel_name": "F1"}, {}], top_n=5
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label"], "F1")

    def test_ranks_by_frequency_descending(self):
        result = rank_interests(
            entries("F1", "F1", "F1", "Finance"), top_n=2
        )
        self.assertEqual(result[0]["label"], "F1")
        self.assertEqual(result[1]["label"], "Finance")

    def test_top_n_limits_results(self):
        result = rank_interests(entries(*[f"Channel {i}" for i in range(20)]), top_n=3)
        self.assertEqual(len(result), 3)

    def test_weight_is_share_of_total_history(self):
        result = rank_interests(entries("A", "A", "A", "B"), top_n=2)
        self.assertAlmostEqual(result[0]["weight"], 0.75, places=2)
        self.assertAlmostEqual(result[1]["weight"], 0.25, places=2)


class WeightSemanticsTests(SimpleTestCase):
    """Pin down exactly what weight means.

    Weights express each interest's share of the WHOLE history, so they only
    sum to 1.0 when top_n covers every channel. These tests use 6 channels and
    top_n=3, where the distinction is real.
    """

    def setUp(self):
        self.data = entries(*(["A"] * 30 + ["B"] * 20 + ["C"] * 10 + ["D"] * 5
                              + ["E"] * 3 + ["F"] * 2))

    def test_weights_do_not_sum_to_one_when_top_n_truncates(self):
        result = rank_interests(self.data, top_n=3)
        self.assertEqual(len(result), 3)
        self.assertLess(sum(item["weight"] for item in result), 1.0)

    def test_weight_denominator_is_full_history_not_top_n(self):
        """30 of 70 videos is 0.429, not 30/60 (the top-3 total)."""
        result = rank_interests(self.data, top_n=3)
        self.assertAlmostEqual(result[0]["weight"], 30 / 70, places=2)

    def test_weights_sum_to_one_when_top_n_covers_everything(self):
        result = rank_interests(entries("A", "A", "B"), top_n=5)
        self.assertAlmostEqual(sum(item["weight"] for item in result), 1.0, places=2)

    def test_renormalize_makes_returned_set_sum_to_one(self):
        result = renormalize(rank_interests(self.data, top_n=3))
        self.assertAlmostEqual(sum(item["weight"] for item in result), 1.0, places=2)

    def test_renormalize_handles_empty_input(self):
        self.assertEqual(renormalize([]), [])

    def test_min_share_drops_weak_interests(self):
        data = entries(*(["A"] * 90 + ["B"] * 6 + ["C"] * 4))
        result = rank_interests(data, top_n=5, min_share=0.1)
        self.assertEqual([item["label"] for item in result], ["A"])


class ShippedSampleDataTests(SimpleTestCase):
    """The file the tutorial tells users to download must actually work.

    80 videos across 6 channels, so the top 5 cover 97.5% of the history and
    the weights are exact fractions of 80.
    """

    def test_sample_file_parses_into_80_entries(self):
        with SAMPLE_DATA.open(encoding="utf-8") as handle:
            parsed = parse_takeout_json(handle)
        self.assertEqual(len(parsed), 80)
        self.assertTrue(all(entry["video_title"] for entry in parsed))
        self.assertTrue(all(entry["channel_name"] for entry in parsed))

    def test_sample_file_ranks_into_the_expected_five_interests(self):
        with SAMPLE_DATA.open(encoding="utf-8") as handle:
            parsed = parse_takeout_json(handle)
        result = rank_interests(parsed, top_n=5)
        self.assertEqual(
            [item["label"] for item in result],
            [
                "F1 Official",
                "Veritasium",
                "Corey Schafer",
                "Fireship",
                "Kurzgesagt",
            ],
        )
        self.assertAlmostEqual(result[0]["weight"], 30 / 80, places=4)

    def test_sample_file_renormalizes_to_a_full_set(self):
        with SAMPLE_DATA.open(encoding="utf-8") as handle:
            parsed = parse_takeout_json(handle)
        result = renormalize(rank_interests(parsed, top_n=5))
        self.assertAlmostEqual(sum(item["weight"] for item in result), 1.0, places=4)
