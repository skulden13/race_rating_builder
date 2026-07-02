import tempfile
import unittest
from pathlib import Path

from helpers import FakeRatingProvider, participant
from trail_rating_builder.matching import build_rating
from trail_rating_builder.output import write_markdown


class OutputTests(unittest.TestCase):
    def test_writes_markdown_table(self):
        rows = build_rating(
            [participant()],
            FakeRatingProvider(
                {
                    "SMITH Will": [
                        {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                    ]
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            write_markdown(path, "Mestia Ultra 2026", "https://my.raceresult.com/123456/", rows, "male", "ULTRA 70")
            text = path.read_text(encoding="utf-8")
        self.assertIn("| 1 | 700 | Advanced 2 | Will SMITH | 1086 |", text)
        self.assertIn("ITRA rating", text)

    def test_writes_markdown_checked_count_when_limited(self):
        rows = build_rating(
            [participant()],
            FakeRatingProvider(
                {
                    "SMITH Will": [
                        {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                    ]
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            write_markdown(path, "Mestia Ultra 2026", "https://my.raceresult.com/123456/", rows, "male", "ULTRA 70", checked_count=30)
            text = path.read_text(encoding="utf-8")
        self.assertIn("showing 1 of 30 checked participants", text)


if __name__ == "__main__":
    unittest.main()
