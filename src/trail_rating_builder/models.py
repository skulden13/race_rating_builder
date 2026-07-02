from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Participant:
    bib: str
    race_result_id: str
    display_name: str
    first_name: str
    last_name: str
    age_group: str
    gender: str
    club: str
    contest: str


@dataclass
class RatingRow:
    rank: int | None
    participant: Participant
    rating_index: int | None
    rating_level: str
    provider_runner_id: int | None
    provider_gender: str
    provider_age_group: str
    match_status: str
    match_score: int
    candidates: int
    provider: str = "itra"
