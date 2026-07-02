from __future__ import annotations

import re
import unicodedata
from typing import Any


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


# normalize_name("Rémi Molaro-Maqua") => "remi molaro maqua"
# normalize_name(" Will.SMITH ") => "will smith"
# normalize_name("ÖZGÜÇ, Seda") => "ozguc seda"
def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9]+", " ", value).casefold()
    return clean_text(value)


def canonical_gender(value: str) -> str:
    value = clean_text(value).casefold()
    if value in {"m", "male", "men"}:
        return "male"
    if value in {"f", "female", "women"}:
        return "female"
    return value


def age_group_number(value: str) -> str:
    return re.sub(r"^[MF]\s*", "", clean_text(value), flags=re.I).strip()
