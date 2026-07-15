from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any

import certifi
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from ..http import USER_AGENT
from ..text import clean_text


ITRA_FIND_URL = "https://itra.run/Runners/FindARunner"
ITRA_FIND_API = "https://itra.run/api/runner/find"
ITRA_RUNNER_URL = "https://itra.run/RunnerSpace/{runner_id}"
LOGGER = logging.getLogger(__name__)


class ItraClient:
    provider = "itra"

    def __init__(self, delay: float = 0.5, insecure: bool = False, timeout: float = 30, max_403_retries: int = 1) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.delay = delay
        self.timeout = timeout
        self.max_403_retries = max_403_retries
        self.verify: bool | str = False if insecure else certifi.where()
        self.csrf_token: str | None = None
        self.cache: dict[str, list[dict[str, Any]]] = {}

    def ensure_token(self) -> None:
        if self.csrf_token:
            return
        LOGGER.debug("Requesting ITRA CSRF token.")
        response = self.session.get(ITRA_FIND_URL, timeout=self.timeout, verify=self.verify)
        response.raise_for_status()
        match = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
            response.text,
        )
        if not match:
            raise RuntimeError("Could not find ITRA CSRF token on Find a Runner page.")
        self.csrf_token = match.group(1)
        LOGGER.debug("Received ITRA CSRF token.")

    def find_runner(self, name: str, count: int = 10, retry_count: int = 0) -> list[dict[str, Any]]:
        name = clean_text(name)
        if len(name) < 2:
            return []
        if name in self.cache:
            return self.cache[name]

        self.ensure_token()
        echo_token = str(time.time())
        LOGGER.debug("Searching ITRA runner profiles for %r.", name)
        response = self.session.post(
            ITRA_FIND_API,
            data={
                "name": name,
                "nationality": "",
                "start": "1",
                "count": str(count),
                "echoToken": echo_token,
            },
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://itra.run",
                "Referer": ITRA_FIND_URL,
                "X-CSRF-TOKEN": self.csrf_token or "",
            },
            timeout=self.timeout,
            verify=self.verify,
        )
        if response.status_code == 403:
            LOGGER.warning("ITRA returned 403 for %r.", name)
            if retry_count >= self.max_403_retries:
                raise RuntimeError(
                    "ITRA returned 403 after refreshing the CSRF token. "
                    "Try again later, increase --itra-delay, or use cached results with --rebuild-rating."
                )
            self.csrf_token = None
            self.ensure_token()
            return self.find_runner(name, count=count, retry_count=retry_count + 1)
        response.raise_for_status()

        payload = response.json()
        decrypted = decrypt_itra_payload(payload)
        results = decrypted.get("Results") or []
        LOGGER.debug("ITRA returned %s candidates for %r.", len(results), name)
        self.cache[name] = results
        if self.delay:
            time.sleep(self.delay)
        return results

    def profile_url(self, candidate: dict[str, Any]) -> str:
        runner_id = clean_text(candidate.get("RunnerId"))
        if not runner_id:
            return ""
        return ITRA_RUNNER_URL.format(runner_id=runner_id)


def decrypt_itra_payload(payload: dict[str, str]) -> dict[str, Any]:
    ciphertext = base64.b64decode(payload["response1"])
    iv = base64.b64decode(payload["response2"])
    key = base64.b64decode(payload["response3"])
    plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext), AES.block_size)
    return json.loads(plaintext.decode("utf-8"))
