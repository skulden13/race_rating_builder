import unittest
from unittest.mock import Mock, patch

from helpers import FakeRatingProvider, participant
from trail_rating_builder.matching import best_rating_match, build_rating, score_candidate


class MatchingTests(unittest.TestCase):
    def test_scores_exact_candidate_highest(self):
        p = participant()
        exact = {
            "FirstName": "Will",
            "LastName": "SMITH",
            "Gender": "Male",
            "AgeGroup": " 35-39",
            "Pi": 700,
        }
        other = {"FirstName": "Martin", "LastName": "LAWRENCE", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 500}
        self.assertGreater(score_candidate(p, exact), score_candidate(p, other))

    def test_best_match_marks_missing_profile(self):
        match, score, status = best_rating_match(participant(), [])
        self.assertIsNone(match)
        self.assertEqual(score, 0)
        self.assertEqual(status, "no_profile")

    def test_best_match_marks_ambiguous_close_candidates(self):
        candidates = [
            {"RunnerId": 1, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700},
            {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 690},
        ]
        match, _, status = best_rating_match(participant(), candidates)
        self.assertEqual(match["RunnerId"], 1)
        self.assertEqual(status, "ambiguous")

    def test_best_match_rejects_name_mismatch(self):
        candidates = [
            {"RunnerId": 1, "FirstName": "Martin", "LastName": "LAWRENCE", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 364}
        ]
        match, _, status = best_rating_match(participant("Jackie", "CHAN", "M40-44"), candidates)
        self.assertEqual(match["RunnerId"], 1)
        self.assertEqual(status, "name_mismatch")

    def test_build_rating_does_not_rank_name_mismatch(self):
        rows = build_rating(
            [participant("Martin", "LAWRENCE", "M40-44")],
            FakeRatingProvider(
                {
                    "LAWRENCE Martin": [
                        {"RunnerId": 1, "FirstName": "Jackie", "LastName": "CHAN", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 364, "PiIndex": "Intermediate 4"}
                    ]
                }
            ),
        )
        self.assertIsNone(rows[0].rating_index)
        self.assertIsNone(rows[0].rank)
        self.assertEqual(rows[0].match_status, "name_mismatch")

    def test_build_rating_sorts_by_rating_index(self):
        participants = [
            participant("Martin", "LAWRENCE", "M35-39"),
            participant("Will", "SMITH", "M35-39"),
        ]
        provider = FakeRatingProvider(
            {
                "LAWRENCE Martin": [
                    {"RunnerId": 1, "FirstName": "Martin", "LastName": "LAWRENCE", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 468, "PiIndex": "Intermediate 2"}
                ],
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ],
            }
        )
        rows = build_rating(participants, provider)
        self.assertEqual([row.participant.last_name for row in rows], ["SMITH", "LAWRENCE"])
        self.assertEqual([row.rank for row in rows], [1, 2])

    def test_build_rating_uses_progress_bar_when_enabled(self):
        participants = [participant("Will", "SMITH", "M35-39")]
        provider = FakeRatingProvider(
            {
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ]
            }
        )
        tqdm_mock = Mock(side_effect=lambda items, **_: items)

        with patch("trail_rating_builder.matching.tqdm", tqdm_mock):
            rows = build_rating(participants, provider, show_progress=True)

        tqdm_mock.assert_called_once_with(participants, desc="Rating requests", unit="runner", disable=False)
        self.assertEqual(rows[0].rating_index, 700)


if __name__ == "__main__":
    unittest.main()
