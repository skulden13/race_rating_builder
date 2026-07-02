import unittest

from trail_rating_builder.sources.raceresult import (
    flatten_raceresult_data,
    get_raceresult_event_id,
    split_raceresult_name,
)
from trail_rating_builder.text import age_group_number, canonical_gender


class RaceResultParserTests(unittest.TestCase):
    def test_extracts_raceresult_event_id(self):
        self.assertEqual(get_raceresult_event_id("https://my.raceresult.com/123456/"), "123456")
        self.assertEqual(get_raceresult_event_id("https://my.raceresult.com/123456/participants"), "123456")

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


if __name__ == "__main__":
    unittest.main()
