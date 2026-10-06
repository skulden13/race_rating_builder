import unittest
from unittest.mock import Mock, patch

from trail_rating_builder.sources.raceresult import (
    flatten_raceresult_data,
    flatten_raceresult_groups,
    fetch_raceresult_participants,
    get_raceresult_event_id,
    get_raceresult_host,
    gender_from_age_group,
    parse_raceresult_row,
    parse_raceresult_participants,
    raceresult_contest_filters,
    raceresult_filter_param,
    split_raceresult_name,
)
from trail_rating_builder.text import age_group_number, canonical_gender


class RaceResultFetchTests(unittest.TestCase):
    def response(self, payload=None, text="", status_code=200):
        response = Mock()
        response.json.return_value = payload
        response.text = text
        response.status_code = status_code
        return response

    def config(self):
        return {
            "key": "test-key",
            "eventname": "Test Trail Festival",
            "server": "my1.raceresult.com",
            "TabConfig": {"Lists": [{"Name": "Online|Participants", "Contest": "0", "Leader": 10}]},
        }

    def participant_list(self):
        return {"data": {"#1_ULTRA 62": [["101", "3", "Bib 101", "SMITH, Will", "USA", "M35-39", "Bad Boys"]]}}

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_existing_participants_endpoint_requires_no_discovery(self, session_class):
        session = session_class.return_value
        session.get.side_effect = [self.response(self.config()), self.response(self.participant_list())]

        name, participants = fetch_raceresult_participants("https://my1.raceresult.com/427872/")

        self.assertEqual(name, "Test Trail Festival")
        self.assertEqual(participants[0].first_name, "Will")
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args.args[0], "https://my1.raceresult.com/427872/participants/list")
        self.assertEqual(session.get.call_args.kwargs["params"]["page"], "participants")

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_discovers_results_tab_and_uses_it_for_filtered_lists(self, session_class):
        session = session_class.return_value
        session.get.side_effect = [
            self.response({"error": "tab not found: participants"}),
            self.response(text='<a href="/999/results">Participants</a><a href="/427872/results"><span>Participants</span></a>'),
            self.response(self.config()),
            self.response({"groupFilters": [{"Type": 1, "Values": ["ULTRA 62"]}]}),
            self.response(self.participant_list()),
        ]

        _, participants = fetch_raceresult_participants("https://my1.raceresult.com/427872/")

        self.assertEqual(len(participants), 1)
        self.assertEqual(participants[0].contest, "ULTRA 62")
        calls = session.get.call_args_list
        self.assertEqual(calls[2].args[0], "https://my1.raceresult.com/427872/results/config")
        for call in calls[3:]:
            self.assertEqual(call.args[0], "https://my1.raceresult.com/427872/results/list")
            self.assertEqual(call.kwargs["params"]["page"], "results")
        self.assertEqual(calls[4].kwargs["params"]["f"], "ULTRA 62\f\f<Ignore>")

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_discovers_participant_tab_after_http_404(self, session_class):
        missing = self.response(text="Not Found", status_code=404)
        missing.json.side_effect = ValueError("Not JSON")
        missing.raise_for_status.side_effect = RuntimeError("404")
        session_class.return_value.get.side_effect = [
            missing,
            self.response(text='<a href="results">Participants</a>'),
            self.response(self.config()),
            self.response(self.participant_list()),
        ]

        _, participants = fetch_raceresult_participants("https://my1.raceresult.com/427872/")

        self.assertEqual(len(participants), 1)
        missing.json.assert_not_called()

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_accepts_explicit_results_url(self, session_class):
        session = session_class.return_value
        session.get.side_effect = [self.response(self.config()), self.response(self.participant_list())]

        _, participants = fetch_raceresult_participants("https://my1.raceresult.com/427872/results")

        self.assertEqual(len(participants), 1)
        self.assertEqual(session.get.call_args_list[0].args[0], "https://my1.raceresult.com/427872/results/config")
        self.assertEqual(session.get.call_args.kwargs["params"]["page"], "results")

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_reports_missing_participant_tab(self, session_class):
        session_class.return_value.get.side_effect = [
            self.response({"error": "tab not found: participants"}),
            self.response(text='<a href="/427872/contact">Contact</a>'),
        ]

        with self.assertRaisesRegex(ValueError, "Could not find.*Participants tab"):
            fetch_raceresult_participants("https://my1.raceresult.com/427872/")

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_reports_configuration_errors_without_discovery(self, session_class):
        session = session_class.return_value
        session.get.return_value = self.response({"error": "Event unavailable"})

        with self.assertRaisesRegex(ValueError, "Event unavailable"):
            fetch_raceresult_participants("https://my1.raceresult.com/427872/")
        self.assertEqual(session.get.call_count, 1)

    @patch("trail_rating_builder.sources.raceresult.requests.Session")
    def test_reports_empty_published_lists(self, session_class):
        config = self.config()
        config["TabConfig"]["Lists"] = []
        session_class.return_value.get.return_value = self.response(config)

        with self.assertRaisesRegex(ValueError, "No published RaceResult lists"):
            fetch_raceresult_participants("https://my1.raceresult.com/427872/")


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

    def test_nationality_codes_are_not_age_groups(self):
        for nationality in ["FRA", "FIN", "MAR", "MEX"]:
            with self.subTest(nationality=nationality):
                self.assertEqual(gender_from_age_group(nationality), "")
                parsed = parse_raceresult_row(
                    ["445", "151", "Bib 445", "SMITH, Will", nationality, "M35-39", "Test Club"],
                    "TRAIL", "female",
                )
                self.assertEqual(parsed.gender, "male")
                self.assertEqual(parsed.age_group, "M35-39")
                self.assertEqual(parsed.club, "Test Club")

    def test_french_female_row_keeps_age_group_and_club(self):
        parsed = parse_raceresult_row(
            ["446", "152", "Bib 446", "CHAN, Jackie", "FRA", "F35-39", "Test Club"], "TRAIL"
        )
        self.assertEqual(parsed.gender, "female")
        self.assertEqual(parsed.age_group, "F35-39")
        self.assertEqual(parsed.club, "Test Club")

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
