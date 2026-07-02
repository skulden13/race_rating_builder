from __future__ import annotations

from typing import Any, Protocol

from .models import Participant, RatingRow
from .text import age_group_number, canonical_gender, clean_text, normalize_name


class RatingProvider(Protocol):
    provider: str

    def find_runner(self, name: str, count: int = 10) -> list[dict[str, Any]]:
        ...


def score_candidate(participant: Participant, candidate: dict[str, Any]) -> int:
    p_first = normalize_name(participant.first_name)
    p_last = normalize_name(participant.last_name)
    c_first = normalize_name(clean_text(candidate.get("FirstName")))
    c_last = normalize_name(clean_text(candidate.get("LastName")))

    score = 0
    if p_first and p_first == c_first:
        score += 45
    if p_last and p_last == c_last:
        score += 45
    if (p_first and p_first in c_first) or (c_first and c_first in p_first):
        score += 12
    if (p_last and p_last in c_last) or (c_last and c_last in p_last):
        score += 12
    if participant.gender and participant.gender == canonical_gender(clean_text(candidate.get("Gender"))):
        score += 15
    if age_group_number(participant.age_group) and age_group_number(participant.age_group) == age_group_number(clean_text(candidate.get("AgeGroup"))):
        score += 8
    if candidate.get("Pi") not in (None, "", 0):
        score += 3
    return score


def has_exact_name_match(participant: Participant, candidate: dict[str, Any]) -> bool:
    return (
        bool(participant.first_name)
        and bool(participant.last_name)
        and normalize_name(participant.first_name) == normalize_name(clean_text(candidate.get("FirstName")))
        and normalize_name(participant.last_name) == normalize_name(clean_text(candidate.get("LastName")))
    )


def best_rating_match(participant: Participant, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int, str]:
    if not candidates:
        return None, 0, "no_profile"
    scored = sorted(
        ((score_candidate(participant, candidate), candidate) for candidate in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    score, candidate = scored[0]
    if not has_exact_name_match(participant, candidate):
        return candidate, score, "name_mismatch"
    if score < 75:
        return candidate, score, "ambiguous"
    if len(scored) > 1 and scored[1][0] >= score - 8:
        return candidate, score, "ambiguous"
    return candidate, score, "matched"


def build_rating(participants: list[Participant], provider: RatingProvider) -> list[RatingRow]:
    rows: list[RatingRow] = []
    for participant in participants:
        query = f"{participant.last_name} {participant.first_name}".strip()
        candidates = provider.find_runner(query)
        if not candidates:
            candidates = provider.find_runner(f"{participant.first_name} {participant.last_name}".strip())
        match, score, status = best_rating_match(participant, candidates)
        use_index = match is not None and status != "name_mismatch"
        rows.append(
            RatingRow(
                rank=None,
                participant=participant,
                rating_index=int(match["Pi"]) if use_index and str(match.get("Pi", "")).isdigit() else None,
                rating_level=clean_text(match.get("PiIndex")) if use_index else "",
                provider_runner_id=int(match["RunnerId"]) if use_index and match.get("RunnerId") else None,
                provider_gender=clean_text(match.get("Gender")) if match else "",
                provider_age_group=clean_text(match.get("AgeGroup")) if match else "",
                match_status=status,
                match_score=score,
                candidates=len(candidates),
                provider=provider.provider,
            )
        )

    rows.sort(key=lambda row: (row.rating_index is not None, row.rating_index or -1), reverse=True)
    rank = 1
    for row in rows:
        if row.rating_index is not None:
            row.rank = rank
            rank += 1
    return rows
