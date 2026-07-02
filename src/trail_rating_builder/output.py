from __future__ import annotations

import csv
import datetime as dt
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import RatingRow


def format_index(row: RatingRow) -> str:
    if row.rating_index is None:
        return "n/a" if row.match_status != "no_profile" else "no profile"
    return str(row.rating_index)


def write_markdown(
    path: Path,
    event_name: str,
    source_url: str,
    rows: list[RatingRow],
    gender: str,
    contest: str,
    checked_count: int | None = None,
) -> None:
    today = dt.date.today().isoformat()
    participant_text = f"{len(rows)} participants"
    if checked_count is not None and checked_count != len(rows):
        participant_text = f"showing {len(rows)} of {checked_count} checked participants"
    provider = rows[0].provider.upper() if rows else "ITRA"
    with path.open("w", encoding="utf-8") as file:
        file.write(f"# {event_name} - {provider} rating\n\n")
        file.write(
            f"> Source: {source_url} + provider: {provider} - collected {today} - "
            f"{gender}, {contest}, {participant_text}.\n\n"
        )
        file.write(f"| # | {provider} Index | Level | Name | Bib | Gender | Age group | Club | Match |\n")
        file.write("|---|-----------:|-------|------|-----|--------|-----------|------|-------|\n")
        for row in rows:
            rank = str(row.rank) if row.rank is not None else "-"
            name = f"{row.participant.first_name} {row.participant.last_name}".strip()
            club = row.participant.club or "-"
            level = row.rating_level or "-"
            file.write(
                f"| {rank} | {format_index(row)} | {level} | {name} | {row.participant.bib} | "
                f"{row.participant.gender or '-'} | {row.participant.age_group or '-'} | {club} | "
                f"{row.match_status} |\n"
            )


def flatten_row(row: RatingRow) -> dict[str, Any]:
    data = asdict(row)
    participant = data.pop("participant")
    return {**data, **{f"participant_{key}": value for key, value in participant.items()}}


def write_csv(path: Path, rows: list[RatingRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(flatten_row(rows[0]).keys()) if rows else [])
        writer.writeheader()
        for row in rows:
            writer.writerow(flatten_row(row))


def write_json(path: Path, event_name: str, source_url: str, rows: list[RatingRow]) -> None:
    payload = {
        "event": event_name,
        "source_url": source_url,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rows": [flatten_row(row) for row in rows],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_output_path(event_name: str, fmt: str, provider: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", event_name.casefold()).strip("_") or "trail_rating"
    return Path("output") / f"{slug}_{provider}.{fmt}"
