from __future__ import annotations

import os

from .text import clean_text


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value in (None, ""):
        return None
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return float(value)


def env_choice(name: str, choices: set[str], default: str) -> str:
    value = clean_text(os.getenv(name)).casefold()
    return value if value in choices else default
