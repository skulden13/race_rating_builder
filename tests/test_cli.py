import os
import sys
import unittest
from unittest.mock import patch

from trail_rating_builder.cli import parse_args


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


if __name__ == "__main__":
    unittest.main()
