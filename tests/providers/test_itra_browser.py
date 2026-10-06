import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from trail_rating_builder.providers.itra import ITRA_FIND_API, ITRA_FIND_URL
from trail_rating_builder.providers.itra_browser import ItraBrowserClient
from trail_rating_builder.cache import CachedRatingProvider


class ItraBrowserTests(unittest.TestCase):
    def setUp(self):
        self.client = ItraBrowserClient(delay=0)
        self.page = Mock()
        self.client._page = self.page
        self.page.locator.return_value.first.count.return_value = 1
        self.page.locator.return_value.first.input_value.return_value = "test-token"
        self.page.is_closed.return_value = False
        self.page.url = ITRA_FIND_URL
        self.page.title.return_value = "Find a Runner"
        self.addCleanup(self.client.close)

    def response(self, status=200, action=None, body='{"encrypted": true}'):
        return {"status": status, "action": action, "body": body}

    @patch("trail_rating_builder.providers.itra_browser.decrypt_itra_payload")
    def test_searches_in_verified_browser_and_reuses_response(self, decrypt):
        candidates = [{"FirstName": "Will", "LastName": "Smith", "Pi": 700}]
        decrypt.return_value = {"Results": candidates}
        self.page.evaluate.return_value = self.response()

        self.assertEqual(self.client.find_runner("Smith Will", count=3), candidates)
        self.assertEqual(self.client.find_runner("Smith Will", count=3), candidates)

        self.page.goto.assert_called_once()
        self.assertEqual(self.page.goto.call_args.args[0], ITRA_FIND_URL)
        self.page.on.assert_called_once_with("request", self.client._capture_search_token)
        self.page.evaluate.assert_called_once()
        data = self.page.evaluate.call_args.args[1]
        self.assertEqual(data["url"], ITRA_FIND_API)
        self.assertEqual(data["token"], "test-token")
        self.assertEqual(data["data"]["name"], "Smith Will")
        self.assertEqual(data["data"]["count"], "3")
        decrypt.assert_called_once_with({"encrypted": True})

    @patch("trail_rating_builder.providers.itra_browser.decrypt_itra_payload", return_value={"Results": []})
    def test_count_is_part_of_browser_response_cache(self, decrypt):
        self.page.evaluate.return_value = self.response()
        self.client.find_runner("Chan Jackie", count=3)
        self.client.find_runner("Chan Jackie", count=10)
        self.assertEqual(self.page.evaluate.call_count, 2)

    @patch("trail_rating_builder.providers.itra_browser.decrypt_itra_payload", return_value={"Results": []})
    def test_reopens_verification_for_challenge_even_with_success_status(self, decrypt):
        self.page.evaluate.side_effect = [self.response(status=202, action="challenge", body=""), self.response()]
        self.assertEqual(self.client.find_runner("Lawrence Martin"), [])
        self.assertEqual(self.page.goto.call_count, 2)
        self.assertEqual(self.page.evaluate.call_count, 2)

    def test_stops_after_repeated_denial_and_does_not_cache_failure(self):
        self.page.evaluate.return_value = self.response(status=405, action="captcha")
        with self.assertRaisesRegex(RuntimeError, "still denied"):
            self.client.find_runner("Smith Will")
        self.assertEqual(self.page.evaluate.call_count, 2)
        self.assertEqual(self.client._responses, {})

    def test_reports_manual_verification_timeout_without_searching(self):
        with patch("trail_rating_builder.providers.itra_browser.time.monotonic", side_effect=[0, 301]):
            with self.assertRaisesRegex(RuntimeError, "No ITRA CSRF token.*Find a Runner"):
                self.client.find_runner("Chan Jackie")
        self.page.evaluate.assert_not_called()

    def test_captures_token_from_manual_search_when_hidden_input_is_absent(self):
        self.page.locator.return_value.first.count.return_value = 0
        request = Mock(url=ITRA_FIND_API, headers={"x-csrf-token": "browser-search-token"})
        self.page.wait_for_timeout.side_effect = lambda _: self.client._capture_search_token(request)
        self.client.ensure_token()
        self.assertEqual(self.client.csrf_token, "browser-search-token")
        self.page.locator.return_value.first.input_value.assert_not_called()

    def test_does_not_capture_tokens_from_other_sites_or_endpoints(self):
        for url in ["https://other.example/api/runner/find", "https://itra.run/api/other"]:
            self.client._capture_search_token(Mock(url=url, headers={"x-csrf-token": "unrelated"}))
        self.assertIsNone(self.client.csrf_token)

    def test_page_load_failure_preserves_underlying_error(self):
        self.page.goto.side_effect = RuntimeError("net::ERR_CONNECTION_RESET")
        with self.assertRaisesRegex(RuntimeError, "Could not load.*ERR_CONNECTION_RESET"):
            self.client.ensure_token()

    def test_closed_page_reports_distinct_error(self):
        self.page.locator.return_value.first.count.side_effect = RuntimeError("Target closed")
        self.page.is_closed.return_value = True
        with self.assertRaisesRegex(RuntimeError, "browser page was closed"):
            self.client.ensure_token()

    def test_rejects_non_json_and_server_errors(self):
        for response, message in [(self.response(body="<html>Error</html>"), "non-JSON"),
                                  (self.response(status=500), "HTTP 500")]:
            with self.subTest(message=message):
                self.page.evaluate.return_value = response
                with self.assertRaisesRegex(RuntimeError, message):
                    self.client.find_runner("Lawrence Martin")
                self.assertEqual(self.client._responses, {})

    def test_empty_query_does_not_open_browser(self):
        self.assertEqual(self.client.find_runner(" "), [])
        self.page.goto.assert_not_called()

    @patch("trail_rating_builder.providers.itra_browser.decrypt_itra_payload")
    def test_disk_cache_reuses_response_without_opening_another_browser(self, decrypt):
        candidates = [{"FirstName": "Jackie", "LastName": "Chan", "Pi": 700}]
        decrypt.return_value = {"Results": candidates}
        self.page.evaluate.return_value = self.response()
        with tempfile.TemporaryDirectory() as directory:
            cached = CachedRatingProvider(self.client, Path(directory))
            self.assertEqual(cached.find_runner("Chan Jackie"), candidates)
            other = ItraBrowserClient(delay=0)
            self.addCleanup(other.close)
            with patch.object(other, "_start_browser") as start:
                self.assertEqual(CachedRatingProvider(other, Path(directory)).find_runner("Chan Jackie"), candidates)
                start.assert_not_called()

    def test_missing_playwright_reports_installation_commands(self):
        self.client._page = None
        with patch.dict(sys.modules, {"playwright.sync_api": None}):
            with self.assertRaisesRegex(RuntimeError, "requirements-browser.txt"):
                self.client._start_browser()

    def test_browser_starts_lazily_with_tls_verification(self):
        self.client._page = None
        api = Mock()
        playwright = api.sync_playwright.return_value.start.return_value
        with patch.dict(sys.modules, {"playwright.sync_api": api}):
            self.client._start_browser()
        playwright.chromium.launch.assert_called_once_with(headless=False)
        self.client._browser.new_context.assert_called_once_with(ignore_https_errors=False)

    def test_browser_start_failure_releases_playwright(self):
        self.client._page = None
        api = Mock()
        playwright = api.sync_playwright.return_value.start.return_value
        playwright.chromium.launch.side_effect = RuntimeError("missing browser")
        with patch.dict(sys.modules, {"playwright.sync_api": api}):
            with self.assertRaisesRegex(RuntimeError, "Could not open Chromium"):
                self.client._start_browser()
        playwright.stop.assert_called_once()

    def test_close_releases_resources_and_is_repeatable(self):
        browser, playwright = Mock(), Mock()
        self.client._browser = browser
        self.client._playwright = playwright
        self.client.close()
        self.client.close()
        browser.close.assert_called_once()
        playwright.stop.assert_called_once()
        self.assertIsNone(self.client._page)
        self.assertIsNone(self.client.csrf_token)


if __name__ == "__main__":
    unittest.main()
