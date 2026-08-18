import unittest

from trail_rating_builder.sources.raceresult import (
    flatten_raceresult_data,
    flatten_raceresult_groups,
    get_raceresult_event_id,
    get_raceresult_host,
    parse_raceresult_row,
    parse_raceresult_participants,
    raceresult_contest_filters,
    raceresult_filter_param,
    split_raceresult_name,
)
from trail_rating_builder.text import age_group_number, canonical_gender


class RaceResultParserTests(unittest.TestCase):
    def test_extracts_raceresult_event_id(self):
        self.assertEqual(get_raceresult_event_id("https://my.raceresult.com/123456/"), "123456")
        self.assertEqual(get_raceresult_event_id("https://my.raceresult.com/123456/participants"), "123456")

    def test_extracts_raceresult_host(self):
        self.assertEqual(get_raceresult_host("https://my4.raceresult.com/415501/"), "my4.raceresult.com")
        self.assertEqual(get_raceresult_host("/415501/"), "my.raceresult.com")

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

    def test_flattens_nested_raceresult_groups_with_full_path(self):
        data = {"#1_Extreme - 35km": {"#1_Male": [["101"]]}}
        self.assertEqual(list(flatten_raceresult_groups(data)), [(("Extreme - 35km", "Male"), [["101"]])])

    def test_parses_original_raceresult_row_layout(self):
        parsed = parse_raceresult_row(["1086", "76", "№ 1086", "SMITH, Will", "M35-39", "Bad Boys"], "ULTRA 70")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.first_name, "Will")
        self.assertEqual(parsed.last_name, "SMITH")
        self.assertEqual(parsed.age_group, "M35-39")
        self.assertEqual(parsed.gender, "male")
        self.assertEqual(parsed.club, "Bad Boys")
        self.assertEqual(parsed.contest, "ULTRA 70")

    def test_parses_raceresult_row_layout_with_nationality_column(self):
        parsed = parse_raceresult_row(
            ["101", "1", "№ 101", "ZAKARAIA, Ilia", "GEO", "M45-49", "Tbilisi Running Club"],
            "Extreme - 35km",
            "male",
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.first_name, "Ilia")
        self.assertEqual(parsed.last_name, "ZAKARAIA")
        self.assertEqual(parsed.age_group, "M45-49")
        self.assertEqual(parsed.gender, "male")
        self.assertEqual(parsed.club, "Tbilisi Running Club")
        self.assertEqual(parsed.contest, "Extreme - 35km")

    def test_extracts_contest_group_filters(self):
        list_json = {
            "groupFilters": [
                {
                    "Type": 1,
                    "Value": "Extreme - 35km",
                    "Values": ["Extreme - 35km", "SkyRace - 15km", "Trail - 10km"],
                },
                {"Type": 0, "Values": ["Male", "Female"]},
            ]
        }

        self.assertEqual(
            raceresult_contest_filters(list_json),
            ["Extreme - 35km", "SkyRace - 15km", "Trail - 10km"],
        )

    def test_builds_contest_filter_param_like_raceresult_frontend(self):
        self.assertEqual(raceresult_filter_param("SkyRace - 15km"), "SkyRace - 15km\f\f<Ignore>")

    def test_parses_skyrace_filtered_response(self):
        list_json = {
            "data": {
                "#2_SkyRace - 15km": {
                    "#1_Male": [
                        ["201", "11", "№ 201", "SMITH, Will", "USA", "M35-39", "Bad Boys", "C(#2b29b3)"]
                    ],
                    "#2_Female": [
                        ["202", "12", "№ 202", "CHAN, Jackie", "HKG", "F30-34", "Dragons", "C(#af0e91)"]
                    ],
                }
            }
        }

        participants = parse_raceresult_participants(list_json)

        self.assertEqual(len(participants), 2)
        self.assertEqual(participants[0].contest, "SkyRace - 15km")
        self.assertEqual(participants[0].gender, "male")
        self.assertEqual(participants[0].age_group, "M35-39")
        self.assertEqual(participants[1].contest, "SkyRace - 15km")
        self.assertEqual(participants[1].gender, "female")
        self.assertEqual(participants[1].age_group, "F30-34")


if __name__ == "__main__":
    unittest.main()
