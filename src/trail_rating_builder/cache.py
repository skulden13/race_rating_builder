from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Protocol

from .models import Participant, RatingRow
from .text import clean_text


CACHE_SCHEMA_VERSION = 1


def build_cache_key(params: Mapping[str, Any]) -> str:
    payload = {"schema": CACHE_SCHEMA_VERSION, **dict(params)}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def load_cached_rating(cache_dir: Path, key: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cached_rating(cache_dir: Path, key: str, payload: dict[str, Any]) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, key)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rows_to_payload(rows: list[RatingRow]) -> list[dict[str, Any]]:
    return [asdict(row) for row in rows]


def rows_from_payload(payload: list[dict[str, Any]]) -> list[RatingRow]:
    rows: list[RatingRow] = []
    for item in payload:
        data = dict(item)
        data["participant"] = Participant(**data["participant"])
        rows.append(RatingRow(**data))
    return rows


class RunnerSearchProvider(Protocol):
    provider: str

    def find_runner(self, name: str, count: int = 10) -> list[dict[str, Any]]:
        ...


class CachedRatingProvider:
    def __init__(self, provider: RunnerSearchProvider, cache_dir: Path, refresh: bool = False) -> None:
        self._provider = provider
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.provider = provider.provider

    def find_runner(self, name: str, count: int = 10) -> list[dict[str, Any]]:
        normalized_name = clean_text(name)
        key = build_cache_key(
            {
                "kind": "provider_response",
                "provider": self.provider,
                "name": normalized_name,
                "count": count,
            }
        )
        cached = None if self.refresh else load_cached_rating(self.cache_dir, key)
        if cached is not None:
            return cached["results"]

        results = self._provider.find_runner(name, count=count)
        save_cached_rating(
            self.cache_dir,
            key,
            {
                "provider": self.provider,
                "name": normalized_name,
                "count": count,
                "results": results,
            },
        )
        return results
