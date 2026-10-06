from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from .itra import ITRA_FIND_API, ITRA_FIND_URL, ItraClient, decrypt_itra_payload
from ..text import clean_text


LOGGER = logging.getLogger(__name__)
TOKEN_SELECTOR = 'input[name="__RequestVerificationToken"]'


class ItraBrowserClient(ItraClient):
    """Keep requests in a visible browser where the user can complete verification."""

    def __init__(self, delay: float = 0.5, insecure: bool = False, timeout: float = 30,
                 verification_timeout: float = 300) -> None:
        super().__init__(delay=delay, insecure=insecure, timeout=timeout)
        self.verification_timeout = verification_timeout
        self._playwright = None
        self._browser = None
        self._page = None
        self._listening_for_token = False
        self._responses: dict[tuple[str, int], list[dict[str, Any]]] = {}

    def _start_browser(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Browser mode requires Playwright. Run: python -m pip install -r requirements-browser.txt "
                "and python -m playwright install chromium"
            ) from exc
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=False)
            context = self._browser.new_context(ignore_https_errors=self.verify is False)
            self._page = context.new_page()
            self._page.set_default_timeout(self.timeout * 1000)
        except Exception as exc:
            self.close()
            raise RuntimeError(
                "Could not open Chromium. Run python -m playwright install chromium "
                "and use browser mode in a desktop session."
            ) from exc

    def _capture_search_token(self, request: Any) -> None:
        if urlparse(request.url)._replace(query="", fragment="").geturl() != ITRA_FIND_API:
            return
        token = request.headers.get("x-csrf-token")
        if token:
            self.csrf_token = token

    def _page_description(self) -> str:
        try:
            if self._page.is_closed():
                return "The browser page was closed."
            return f"Current page: {self._page.url} (title: {self._page.title()})."
        except Exception:
            return "The browser page is unavailable."

    def ensure_token(self) -> None:
        if self.csrf_token:
            return
        self._start_browser()
        if not self._listening_for_token:
            self._page.on("request", self._capture_search_token)
            self._listening_for_token = True
        LOGGER.warning(
            "Complete any ITRA security check in the browser window. "
            "If Find a Runner loads but the script keeps waiting, search for a runner on that page. "
            "Waiting up to %s seconds for a CSRF token.", self.verification_timeout,
        )
        try:
            self._page.goto(ITRA_FIND_URL, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load ITRA Find a Runner. {self._page_description()} "
                f"Browser error: {exc}"
            ) from exc
        deadline = time.monotonic() + self.verification_timeout
        try:
            while not self.csrf_token and time.monotonic() < deadline:
                token_input = self._page.locator(TOKEN_SELECTOR).first
                if token_input.count():
                    self.csrf_token = token_input.input_value() or None
                if not self.csrf_token:
                    self._page.wait_for_timeout(250)
        except Exception as exc:
            raise RuntimeError(
                f"Could not read the ITRA CSRF token. {self._page_description()} Browser error: {exc}"
            ) from exc
        if not self.csrf_token:
            raise RuntimeError(
                f"No ITRA CSRF token was found within {self.verification_timeout} seconds. "
                f"{self._page_description()} Complete the security check and then search for a runner "
                "in the browser. If the page works but this error persists, ITRA's search integration "
                "may have changed; inspect the /api/runner/find request in browser DevTools."
            )

    def _request(self, name: str, count: int) -> dict[str, Any]:
        # Fetch inside the page so requests use the same browser session as verification.
        return self._page.evaluate(
            """async ({url, token, data, timeout}) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeout);
                try {
                    const response = await fetch(url, {
                        method: 'POST', credentials: 'same-origin', signal: controller.signal,
                        headers: {
                            'Accept': 'application/json, text/javascript, */*; q=0.01',
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-TOKEN': token
                        },
                        body: new URLSearchParams(data).toString()
                    });
                    return {status: response.status,
                            action: response.headers.get('x-amzn-waf-action'),
                            body: await response.text()};
                } finally { clearTimeout(timer); }
            }""",
            {
                "url": ITRA_FIND_API, "token": self.csrf_token,
                "timeout": self.timeout * 1000,
                "data": {"name": name, "nationality": "", "start": "1",
                         "count": str(count), "echoToken": str(time.time())},
            },
        )

    def find_runner(self, name: str, count: int = 10) -> list[dict[str, Any]]:
        name = clean_text(name)
        if len(name) < 2:
            return []
        cache_key = (name, count)
        if cache_key in self._responses:
            return self._responses[cache_key]
        for attempt in range(2):
            self.ensure_token()
            response = self._request(name, count)
            if response.get("action") in {"captcha", "challenge"} or response["status"] in {403, 405}:
                if attempt:
                    raise RuntimeError("ITRA still denied the browser request after manual verification. Try again later.")
                LOGGER.warning("ITRA requires renewed verification for %r; reopening Find a Runner.", name)
                self.csrf_token = None
                continue
            if not 200 <= response["status"] < 300:
                raise RuntimeError(f"ITRA browser request failed with HTTP {response['status']}.")
            try:
                payload = json.loads(response["body"])
            except (ValueError, TypeError) as exc:
                raise RuntimeError("ITRA returned a non-JSON response in browser mode.") from exc
            results = decrypt_itra_payload(payload).get("Results") or []
            self._responses[cache_key] = results
            if self.delay:
                self._page.wait_for_timeout(self.delay * 1000)
            return results
        raise RuntimeError("ITRA browser request failed.")

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            self._browser = None
            self._page = None
            self._listening_for_token = False
            self.csrf_token = None
            try:
                if self._playwright is not None:
                    self._playwright.stop()
            finally:
                self._playwright = None
                self.session.close()
