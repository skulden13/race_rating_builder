import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from itra_rating_builder import (
    Participant,
    age_group_number,
    best_itra_match,
    build_rating,
    canonical_gender,
    decrypt_itra_payload,
    flatten_raceresult_data,
    get_raceresult_event_id,
    parse_args,
    score_candidate,
    split_raceresult_name,
    write_markdown,
)


class FakeItraClient:
    def __init__(self, responses):
        self.responses = responses
        self.queries = []

    def find_runner(self, name, count=10):
        self.queries.append(name)
        return self.responses.get(name, [])


def participant(first="Will", last="SMITH", age_group="M35-39"):
    return Participant(
        bib="1086",
        race_result_id="76",
        display_name=f"{last}, {first}",
        first_name=first,
        last_name=last,
        age_group=age_group,
        gender="male" if age_group.startswith("M") else "female",
        club="Race For Ukraine",
        contest="ULTRA 70",
    )


class ParserTests(unittest.TestCase):
    def test_extracts_raceresult_event_id(self):
        self.assertEqual(get_raceresult_event_id("https://my.raceresult.com/407493/"), "407493")
        self.assertEqual(get_raceresult_event_id("https://my.raceresult.com/407493/participants"), "407493")

    def test_splits_raceresult_display_name(self):
        self.assertEqual(split_raceresult_name("SMITH, Will"), ("Will", "SMITH"))
        self.assertEqual(split_raceresult_name("Will SMITH"), ("Will", "SMITH"))

    def test_normalizes_gender_and_age_group(self):
        self.assertEqual(canonical_gender("Male"), "male")
        self.assertEqual(canonical_gender("F"), "female")
        self.assertEqual(age_group_number("M35-39"), "35-39")
        self.assertEqual(age_group_number(" 35-39"), "35-39")

    def test_flattens_raceresult_data(self):
        data = {"#2_ULTRA 70": [["1086"]], "nested": {"#3_TRAIL": [["1401"]]}}
        self.assertEqual(list(flatten_raceresult_data(data)), [("#2_ULTRA 70", [["1086"]]), ("#3_TRAIL", [["1401"]])])

    def test_parse_args_uses_env_defaults(self):
        env = {
            "PARTICIPANTS_LIST_URL": "https://my.raceresult.com/407493/",
            "CONTEST": "ULTRA 70",
            "GENDER": "female",
            "PARTICIPANTS_LIST_FIRST": "5",
            "ITRA_RATING_LIMIT": "12",
            "OUTPUT_FORMAT": "json",
            "OUTPUT_PATH": "output/report.json",
            "ITRA_REQUEST_DELAY": "0.1",
            "ITRA_REQUEST_INSECURE": "true",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["itra_rating_builder.py"]):
            args = parse_args()
        self.assertEqual(args.url, "https://my.raceresult.com/407493/")
        self.assertEqual(args.contest, "ULTRA 70")
        self.assertEqual(args.gender, "female")
        self.assertEqual(args.first, 5)
        self.assertEqual(args.limit, 12)
        self.assertEqual(args.format, "json")
        self.assertEqual(args.output, "output/report.json")
        self.assertEqual(args.itra_delay, 0.1)
        self.assertTrue(args.insecure)


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
        match, score, status = best_itra_match(participant(), [])
        self.assertIsNone(match)
        self.assertEqual(score, 0)
        self.assertEqual(status, "no_profile")

    def test_best_match_marks_ambiguous_close_candidates(self):
        candidates = [
            {"RunnerId": 1, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700},
            {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 690},
        ]
        match, _, status = best_itra_match(participant(), candidates)
        self.assertEqual(match["RunnerId"], 1)
        self.assertEqual(status, "ambiguous")

    def test_best_match_rejects_partial_first_name_match(self):
        candidates = [
            {"RunnerId": 1, "FirstName": "Martin", "LastName": "LAWRENCE", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 364}
        ]
        match, _, status = best_itra_match(participant("Jackie", "CHAN", "M40-44"), candidates)
        self.assertEqual(match["RunnerId"], 1)
        self.assertEqual(status, "name_mismatch")

    def test_build_rating_does_not_rank_name_mismatch(self):
        rows = build_rating(
            [participant("Martin", "LAWRENCE", "M40-44")],
            FakeItraClient(
                {
                    "LAWRENCE Martin": [
                        {"RunnerId": 1, "FirstName": "Jackie", "LastName": "CHAN", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 364, "PiIndex": "Intermediate 4"}
                    ]
                }
            ),
        )
        self.assertIsNone(rows[0].itra_index)
        self.assertIsNone(rows[0].rank)
        self.assertEqual(rows[0].match_status, "name_mismatch")

    def test_build_rating_sorts_by_itra_index(self):
        participants = [
            participant("Martin", "LAWRENCE", "M35-39"),
            participant("Will", "SMITH", "M35-39"),
        ]
        itra = FakeItraClient(
            {
                "LAWRENCE Martin": [
                    {"RunnerId": 1, "FirstName": "Martin", "LastName": "LAWRENCE", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 468, "PiIndex": "Intermediate 2"}
                ],
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ],
            }
        )
        rows = build_rating(participants, itra)
        self.assertEqual([row.participant.last_name for row in rows], ["SMITH", "LAWRENCE"])
        self.assertEqual([row.rank for row in rows], [1, 2])


class OutputAndCryptoTests(unittest.TestCase):
    def test_decrypts_itra_payload_shape(self):
        key = b"0123456789abcdef"
        iv = b"abcdef0123456789"
        plaintext = json.dumps({"ResultCount": 1, "Results": [{"Pi": 700}]}).encode()
        ciphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plaintext, AES.block_size))
        payload = {
            "response1": base64.b64encode(ciphertext).decode(),
            "response2": base64.b64encode(iv).decode(),
            "response3": base64.b64encode(key).decode(),
        }
        self.assertEqual(decrypt_itra_payload(payload)["Results"][0]["Pi"], 700)

    def test_writes_markdown_table(self):
        rows = build_rating(
            [participant()],
            FakeItraClient(
                {
                    "SMITH Will": [
                        {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                    ]
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            write_markdown(path, "Mestia Ultra 2026", "https://my.raceresult.com/407493/", rows, "male", "ULTRA 70")
            text = path.read_text(encoding="utf-8")
        self.assertIn("| 1 | 700 | Advanced 2 | Will SMITH | 1086 |", text)

    def test_writes_markdown_checked_count_when_limited(self):
        rows = build_rating(
            [participant()],
            FakeItraClient(
                {
                    "SMITH Will": [
                        {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                    ]
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            write_markdown(path, "Mestia Ultra 2026", "https://my.raceresult.com/407493/", rows, "male", "ULTRA 70", checked_count=30)
            text = path.read_text(encoding="utf-8")
        self.assertIn("showing 1 of 30 checked participants", text)


if __name__ == "__main__":
    unittest.main()
