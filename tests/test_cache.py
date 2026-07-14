import tempfile
import unittest
from pathlib import Path

from helpers import FakeRatingProvider, participant
from trail_rating_builder.cache import (
    CachedRatingProvider,
    build_cache_key,
    load_cached_rating,
    rows_from_payload,
    rows_to_payload,
    save_cached_rating,
)
from trail_rating_builder.matching import build_rating


class CacheTests(unittest.TestCase):
    def test_cache_key_changes_with_effective_request_params(self):
        base = {
            "url": "https://my.raceresult.com/123456/",
            "source": "raceresult",
            "provider": "itra",
            "contest": "MARATHON",
            "gender": "male",
            "first": None,
        }
        male = build_cache_key(base)
        female = build_cache_key({**base, "gender": "female"})
        self.assertNotEqual(male, female)
        self.assertEqual(male, build_cache_key(base))

    def test_cached_rows_round_trip(self):
        rows = build_rating(
            [participant("Will", "SMITH")],
            FakeRatingProvider(
                {
                    "SMITH Will": [
                        {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                    ]
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            key = "abc123"
            save_cached_rating(Path(tmpdir), key, {"event_name": "Event", "rows": rows_to_payload(rows)})
            cached = load_cached_rating(Path(tmpdir), key)
        restored = rows_from_payload(cached["rows"])
        self.assertEqual(restored[0].participant.last_name, "SMITH")
        self.assertEqual(restored[0].rating_index, 700)

    def test_provider_response_cache_reuses_search_results(self):
        result = [
            {
                "RunnerId": 2,
                "FirstName": "Will",
                "LastName": "SMITH",
                "Gender": "Male",
                "AgeGroup": " 35-39",
                "Pi": 700,
                "PiIndex": "Advanced 2",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            first_provider = FakeRatingProvider({"SMITH Will": result})
            first_cached_provider = CachedRatingProvider(first_provider, cache_dir)
            self.assertEqual(first_cached_provider.find_runner("SMITH Will"), result)
            self.assertEqual(first_provider.queries, ["SMITH Will"])

            second_provider = FakeRatingProvider({})
            second_cached_provider = CachedRatingProvider(second_provider, cache_dir)
            self.assertEqual(second_cached_provider.find_runner("SMITH Will"), result)
            self.assertEqual(second_provider.queries, [])

    def test_provider_response_cache_refreshes_search_results(self):
        old_result = [
            {
                "RunnerId": 2,
                "FirstName": "Will",
                "LastName": "SMITH",
                "Gender": "Male",
                "AgeGroup": " 35-39",
                "Pi": 700,
                "PiIndex": "Advanced 2",
            }
        ]
        new_result = [
            {
                "RunnerId": 2,
                "FirstName": "Will",
                "LastName": "SMITH",
                "Gender": "Male",
                "AgeGroup": " 35-39",
                "Pi": 710,
                "PiIndex": "Advanced 2",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            CachedRatingProvider(FakeRatingProvider({"SMITH Will": old_result}), cache_dir).find_runner("SMITH Will")

            provider = FakeRatingProvider({"SMITH Will": new_result})
            cached_provider = CachedRatingProvider(provider, cache_dir, refresh=True)
            self.assertEqual(cached_provider.find_runner("SMITH Will"), new_result)
            self.assertEqual(provider.queries, ["SMITH Will"])


if __name__ == "__main__":
    unittest.main()
