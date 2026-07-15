import tempfile
import unittest
from pathlib import Path

from helpers import FakeRatingProvider, participant
from trail_rating_builder.matching import build_rating
from trail_rating_builder.output import default_output_path, write_markdown


class OutputTests(unittest.TestCase):
    def test_default_output_path_includes_contest_and_gender(self):
        path = default_output_path("Mestia Ultra 2026", "ULTRA 70", "male", "md", "itra")
        self.assertEqual(path, Path("output/mestia_ultra_2026_ultra_70_male_itra.md"))

    def test_writes_markdown_table(self):
        rows = build_rating(
            [participant()],
            FakeRatingProvider(
                {
                    "SMITH Will": [
                        {
                            "RunnerId": 2,
                            "FirstName": "Will",
                            "LastName": "SMITH",
                            "Gender": "Male",
                            "AgeGroup": " 35-39",
                            "Nationality": "USA",
                            "Pi": 700,
                            "PiIndex": "Advanced 2",
                        }
                    ]
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            write_markdown(path, "Mestia Ultra 2026", "https://my.raceresult.com/123456/", rows, "male", "ULTRA 70")
            text = path.read_text(encoding="utf-8")
        self.assertIn("| 1 | 700 | Advanced 2 | [Will SMITH](https://itra.run/RunnerSpace/2) | 1086 |", text)
        self.assertIn("| Gender | Nationality | Age group | Club | Match |", text)
        self.assertIn("| male | USA | M35-39 | Bad Boys | matched |", text)
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
