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


if __name__ == "__main__":
    unittest.main()
