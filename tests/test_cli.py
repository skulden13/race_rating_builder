import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from helpers import FakeRatingProvider, participant
from trail_rating_builder.cli import main, parse_args


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tqdm_patch = patch("trail_rating_builder.matching.tqdm", Mock(side_effect=lambda items, **_: items))
        self.tqdm_patch.start()
        self.addCleanup(self.tqdm_patch.stop)

    def test_parse_args_uses_env_defaults(self):
        env = {
            "PARTICIPANTS_SOURCE_URL": "https://my.raceresult.com/123456/",
            "PARTICIPANTS_SOURCE": "raceresult",
            "RATING_PROVIDER": "itra",
            "CONTEST": "ULTRA 70",
            "GENDER": "female",
            "PARTICIPANTS_SOURCE_FIRST": "5",
            "RATING_OUTPUT_LIMIT": "12",
            "OUTPUT_FORMAT": "json",
            "OUTPUT_PATH": "output/report.json",
            "ITRA_REQUEST_DELAY": "0.1",
            "RATING_REQUEST_INSECURE": "true",
            "CACHE_DIR": ".cache/test",
            "CACHE_DISABLED": "false",
            "CACHE_REFRESH": "false",
            "RATING_REBUILD": "false",
            "LOG_LEVEL": "debug",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["trail-rating-builder"]):
            args = parse_args()
        self.assertEqual(args.url, "https://my.raceresult.com/123456/")
        self.assertEqual(args.source, "raceresult")
        self.assertEqual(args.provider, "itra")
        self.assertEqual(args.contest, "ULTRA 70")
        self.assertEqual(args.gender, "female")
        self.assertEqual(args.first, 5)
        self.assertEqual(args.limit, 12)
        self.assertEqual(args.format, "json")
        self.assertEqual(args.output, "output/report.json")
        self.assertEqual(args.itra_delay, 0.1)
        self.assertTrue(args.insecure)
        self.assertEqual(args.cache_dir, ".cache/test")
        self.assertFalse(args.no_cache)
        self.assertFalse(args.refresh_cache)
        self.assertFalse(args.rebuild_rating)
        self.assertEqual(args.log_level, "debug")

    def test_main_uses_cached_rating_rows_on_second_run(self):
        provider = FakeRatingProvider(
            {
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            first_output = Path(tmpdir) / "first.md"
            second_output = Path(tmpdir) / "second.md"
            base_argv = [
                "trail-rating-builder",
                "https://my.raceresult.com/123456/",
                "--source",
                "raceresult",
                "--provider",
                "itra",
                "--contest",
                "ULTRA 70",
                "--gender",
                "male",
                "--cache-dir",
                str(cache_dir),
                "--log-level",
                "warning",
            ]

            fetch_mock = Mock(return_value=("Mock Event", [participant("Will", "SMITH")]))
            provider_mock = Mock(return_value=provider)
            with redirect_stdout(StringIO()), patch.object(sys, "argv", [*base_argv, "--output", str(first_output)]), patch(
                "trail_rating_builder.cli.fetch_participants", fetch_mock
            ), patch("trail_rating_builder.cli.get_provider", provider_mock):
                self.assertEqual(main(), 0)

            fetch_mock.reset_mock()
            provider_mock.reset_mock()
            with redirect_stdout(StringIO()), patch.object(sys, "argv", [*base_argv, "--output", str(second_output)]), patch(
                "trail_rating_builder.cli.fetch_participants", fetch_mock
            ), patch("trail_rating_builder.cli.get_provider", provider_mock):
                self.assertEqual(main(), 0)

            fetch_mock.assert_not_called()
            provider_mock.assert_not_called()
            self.assertIn("Will SMITH", second_output.read_text(encoding="utf-8"))

    def test_main_no_cache_bypasses_existing_cache(self):
        provider = FakeRatingProvider(
            {
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            first_output = Path(tmpdir) / "first.md"
            second_output = Path(tmpdir) / "second.md"
            base_argv = [
                "trail-rating-builder",
                "https://my.raceresult.com/123456/",
                "--source",
                "raceresult",
                "--provider",
                "itra",
                "--contest",
                "ULTRA 70",
                "--gender",
                "male",
                "--cache-dir",
                str(cache_dir),
                "--log-level",
                "warning",
            ]

            fetch_mock = Mock(return_value=("Mock Event", [participant("Will", "SMITH")]))
            provider_mock = Mock(return_value=provider)
            with redirect_stdout(StringIO()), patch.object(sys, "argv", [*base_argv, "--output", str(first_output)]), patch(
                "trail_rating_builder.cli.fetch_participants", fetch_mock
            ), patch("trail_rating_builder.cli.get_provider", provider_mock):
                self.assertEqual(main(), 0)

            fetch_mock.reset_mock()
            provider_mock.reset_mock()
            with redirect_stdout(StringIO()), patch.object(
                sys, "argv", [*base_argv, "--no-cache", "--output", str(second_output)]
            ), patch("trail_rating_builder.cli.fetch_participants", fetch_mock), patch(
                "trail_rating_builder.cli.get_provider", provider_mock
            ):
                self.assertEqual(main(), 0)

            fetch_mock.assert_called_once()
            provider_mock.assert_called_once()

    def test_main_reuses_provider_cache_across_different_report_filters(self):
        male_provider = FakeRatingProvider(
            {
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ]
            }
        )
        all_provider = FakeRatingProvider(
            {
                "CHAN Jackie": [
                    {"RunnerId": 3, "FirstName": "Jackie", "LastName": "CHAN", "Gender": "Female", "AgeGroup": " 35-39", "Pi": 680, "PiIndex": "Advanced 1"}
                ]
            }
        )
        participants = [
            participant("Will", "SMITH", "M35-39"),
            participant("Jackie", "CHAN", "F35-39"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            first_output = Path(tmpdir) / "male.md"
            second_output = Path(tmpdir) / "all.md"
            base_argv = [
                "trail-rating-builder",
                "https://my.raceresult.com/123456/",
                "--source",
                "raceresult",
                "--provider",
                "itra",
                "--contest",
                "ULTRA 70",
                "--cache-dir",
                str(cache_dir),
                "--log-level",
                "warning",
            ]

            fetch_mock = Mock(return_value=("Mock Event", participants))
            with redirect_stdout(StringIO()), patch.object(
                sys, "argv", [*base_argv, "--gender", "male", "--output", str(first_output)]
            ), patch("trail_rating_builder.cli.fetch_participants", fetch_mock), patch(
                "trail_rating_builder.cli.get_provider", Mock(return_value=male_provider)
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(male_provider.queries, ["SMITH Will"])

            with redirect_stdout(StringIO()), patch.object(
                sys, "argv", [*base_argv, "--gender", "all", "--output", str(second_output)]
            ), patch("trail_rating_builder.cli.fetch_participants", fetch_mock), patch(
                "trail_rating_builder.cli.get_provider", Mock(return_value=all_provider)
            ):
                self.assertEqual(main(), 0)

            self.assertEqual(all_provider.queries, ["CHAN Jackie"])
            output = second_output.read_text(encoding="utf-8")
            self.assertIn("Will SMITH", output)
            self.assertIn("Jackie CHAN", output)

    def test_main_rebuild_rating_reuses_provider_cache_for_changed_participant_table(self):
        first_provider = FakeRatingProvider(
            {
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ]
            }
        )
        second_provider = FakeRatingProvider(
            {
                "CHAN Jasmine": [
                    {"RunnerId": 3, "FirstName": "Jasmine", "LastName": "CHAN", "Gender": "Female", "AgeGroup": " 35-39", "Pi": 680, "PiIndex": "Advanced 1"}
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            first_output = Path(tmpdir) / "first.md"
            second_output = Path(tmpdir) / "second.md"
            base_argv = [
                "trail-rating-builder",
                "https://my.raceresult.com/123456/",
                "--source",
                "raceresult",
                "--provider",
                "itra",
                "--contest",
                "ULTRA 70",
                "--gender",
                "all",
                "--cache-dir",
                str(cache_dir),
                "--log-level",
                "warning",
            ]

            fetch_mock = Mock(return_value=("Mock Event", [participant("Will", "SMITH", "M35-39")]))
            with redirect_stdout(StringIO()), patch.object(sys, "argv", [*base_argv, "--output", str(first_output)]), patch(
                "trail_rating_builder.cli.fetch_participants", fetch_mock
            ), patch("trail_rating_builder.cli.get_provider", Mock(return_value=first_provider)):
                self.assertEqual(main(), 0)
            self.assertEqual(first_provider.queries, ["SMITH Will"])

            fetch_mock = Mock(
                return_value=(
                    "Mock Event",
                    [participant("Will", "SMITH", "M35-39"), participant("Jasmine", "CHAN", "F35-39")],
                )
            )
            with redirect_stdout(StringIO()), patch.object(
                sys, "argv", [*base_argv, "--rebuild-rating", "--output", str(second_output)]
            ), patch("trail_rating_builder.cli.fetch_participants", fetch_mock), patch(
                "trail_rating_builder.cli.get_provider", Mock(return_value=second_provider)
            ):
                self.assertEqual(main(), 0)

            fetch_mock.assert_called_once()
            self.assertEqual(second_provider.queries, ["CHAN Jasmine"])
            output = second_output.read_text(encoding="utf-8")
            self.assertIn("Will SMITH", output)
            self.assertIn("Jasmine CHAN", output)

    def test_main_logs_build_steps(self):
        provider = FakeRatingProvider(
            {
                "SMITH Will": [
                    {"RunnerId": 2, "FirstName": "Will", "LastName": "SMITH", "Gender": "Male", "AgeGroup": " 35-39", "Pi": 700, "PiIndex": "Advanced 2"}
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "results.md"
            argv = [
                "trail-rating-builder",
                "https://my.raceresult.com/123456/",
                "--source",
                "raceresult",
                "--provider",
                "itra",
                "--contest",
                "ULTRA 70",
                "--gender",
                "male",
                "--no-cache",
                "--output",
                str(output),
            ]
            fetch_mock = Mock(return_value=("Mock Event", [participant("Will", "SMITH", "M35-39")]))
            with self.assertLogs("trail_rating_builder.cli", level="INFO") as logs, redirect_stdout(StringIO()), patch.object(
                sys, "argv", argv
            ), patch("trail_rating_builder.cli.fetch_participants", fetch_mock), patch(
                "trail_rating_builder.cli.get_provider", Mock(return_value=provider)
            ):
                self.assertEqual(main(), 0)
            index_text = (output.parent / "index.md").read_text(encoding="utf-8")

        messages = "\n".join(logs.output)
        self.assertIn("Fetching participants from raceresult source.", messages)
        self.assertIn("Fetched 1 participants for Mock Event.", messages)
        self.assertIn("Building rating for 1 participants.", messages)
        self.assertIn("Writing md output", messages)
        self.assertIn("Updated Markdown index", messages)
        self.assertIn("Mock Event - ULTRA 70 - male - ITRA rating", index_text)


if __name__ == "__main__":
    unittest.main()
