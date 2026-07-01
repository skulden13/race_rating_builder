#!/usr/bin/env python3
"""Build a RaceResult participant rating from ITRA Performance Index."""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import certifi
import requests
from dotenv import load_dotenv
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


ITRA_FIND_URL = "https://itra.run/Runners/FindARunner"
ITRA_FIND_API = "https://itra.run/api/runner/find"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)


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
    itra_index: int | None
    itra_level: str
    itra_runner_id: int | None
    itra_gender: str
    itra_age_group: str
    match_status: str
    match_score: int
    candidates: int


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9]+", " ", value).casefold()
    return clean_text(value)


def split_raceresult_name(display_name: str) -> tuple[str, str]:
    if "," in display_name:
        last, first = display_name.split(",", 1)
        return clean_text(first), clean_text(last)
    parts = clean_text(display_name).split()
    if len(parts) <= 1:
        return clean_text(display_name), ""
    return " ".join(parts[:-1]), parts[-1]


def gender_from_age_group(age_group: str) -> str:
    age_group = clean_text(age_group).upper()
    if age_group.startswith("M"):
        return "male"
    if age_group.startswith("F"):
        return "female"
    return ""


def canonical_gender(value: str) -> str:
    value = clean_text(value).casefold()
    if value in {"m", "male", "men"}:
        return "male"
    if value in {"f", "female", "women"}:
        return "female"
    return value


def age_group_number(value: str) -> str:
    return re.sub(r"^[MF]\s*", "", clean_text(value), flags=re.I).strip()


class ItraClient:
    def __init__(self, delay: float = 0.35, insecure: bool = False) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.delay = delay
        self.verify: bool | str = False if insecure else certifi.where()
        self.csrf_token: str | None = None
        self.cache: dict[str, list[dict[str, Any]]] = {}

    def ensure_token(self) -> None:
        if self.csrf_token:
            return
        response = self.session.get(ITRA_FIND_URL, timeout=30, verify=self.verify)
        response.raise_for_status()
        match = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
            response.text,
        )
        if not match:
            raise RuntimeError("Could not find ITRA CSRF token on Find a Runner page.")
        self.csrf_token = match.group(1)

    def find_runner(self, name: str, count: int = 10) -> list[dict[str, Any]]:
        name = clean_text(name)
        if len(name) < 2:
            return []
        if name in self.cache:
            return self.cache[name]

        self.ensure_token()
        echo_token = str(time.time())
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
            timeout=30,
            verify=self.verify,
        )
        if response.status_code == 403:
            self.csrf_token = None
            self.ensure_token()
            return self.find_runner(name, count=count)
        response.raise_for_status()

        payload = response.json()
        decrypted = decrypt_itra_payload(payload)
        results = decrypted.get("Results") or []
        self.cache[name] = results
        if self.delay:
            time.sleep(self.delay)
        return results


def decrypt_itra_payload(payload: dict[str, str]) -> dict[str, Any]:
    ciphertext = base64.b64decode(payload["response1"])
    iv = base64.b64decode(payload["response2"])
    key = base64.b64decode(payload["response3"])
    plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext), AES.block_size)
    return json.loads(plaintext.decode("utf-8"))


def get_raceresult_event_id(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/(\d+)(?:/|$)", parsed.path)
    if not match:
        raise ValueError(f"Could not extract RaceResult event id from URL: {url}")
    return match.group(1)


def fetch_raceresult_participants(url: str, insecure: bool = False) -> tuple[str, list[Participant]]:
    event_id = get_raceresult_event_id(url)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    verify: bool | str = False if insecure else certifi.where()
    base = f"https://my.raceresult.com/{event_id}/participants"

    config = session.get(f"{base}/config", params={"lang": "en"}, timeout=30, verify=verify)
    config.raise_for_status()
    config_json = config.json()
    event_name = clean_text(config_json.get("eventname")) or f"RaceResult {event_id}"
    server = config_json.get("server") or "my.raceresult.com"
    list_config = (config_json.get("TabConfig", {}).get("Lists") or [])[0]
    listname = list_config["Name"]
    contest = list_config.get("Contest", "0")

    list_url = f"https://{server}/{event_id}/participants/list"
    list_response = session.get(
        list_url,
        params={
            "key": config_json["key"],
            "listname": listname,
            "page": "participants",
            "contest": contest,
            "r": "all",
            "l": list_config.get("Leader", 999999),
            "fav": "",
            "openedGroups": "{}",
        },
        timeout=30,
        verify=verify,
    )
    list_response.raise_for_status()
    list_json = list_response.json()

    participants: list[Participant] = []
    for contest_key, rows in flatten_raceresult_data(list_json.get("data", {})):
        contest_name = contest_key.split("_", 1)[1] if "_" in contest_key else contest_key
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                continue
            first, last = split_raceresult_name(row[3])
            age_group = clean_text(row[4])
            participants.append(
                Participant(
                    bib=clean_text(row[0]),
                    race_result_id=clean_text(row[1]),
                    display_name=clean_text(row[3]),
                    first_name=first,
                    last_name=last,
                    age_group=age_group,
                    gender=gender_from_age_group(age_group),
                    club=clean_text(row[5]),
                    contest=clean_text(contest_name),
                )
            )
    return event_name, participants


def flatten_raceresult_data(data: Any) -> Iterable[tuple[str, list[list[Any]]]]:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                yield str(key), value
            else:
                yield from flatten_raceresult_data(value)


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
    if p_first and p_first in c_first or c_first and c_first in p_first:
        score += 12
    if p_last and p_last in c_last or c_last and c_last in p_last:
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


def best_itra_match(participant: Participant, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int, str]:
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


def build_rating(participants: list[Participant], itra: ItraClient) -> list[RatingRow]:
    rows: list[RatingRow] = []
    for participant in participants:
        query = f"{participant.last_name} {participant.first_name}".strip()
        candidates = itra.find_runner(query)
        if not candidates:
            candidates = itra.find_runner(f"{participant.first_name} {participant.last_name}".strip())
        match, score, status = best_itra_match(participant, candidates)
        use_index = match is not None and status != "name_mismatch"
        rows.append(
            RatingRow(
                rank=None,
                participant=participant,
                itra_index=int(match["Pi"]) if use_index and str(match.get("Pi", "")).isdigit() else None,
                itra_level=clean_text(match.get("PiIndex")) if use_index else "",
                itra_runner_id=int(match["RunnerId"]) if use_index and match.get("RunnerId") else None,
                itra_gender=clean_text(match.get("Gender")) if match else "",
                itra_age_group=clean_text(match.get("AgeGroup")) if match else "",
                match_status=status,
                match_score=score,
                candidates=len(candidates),
            )
        )

    rows.sort(key=lambda row: (row.itra_index is not None, row.itra_index or -1), reverse=True)
    rank = 1
    for row in rows:
        if row.itra_index is not None:
            row.rank = rank
            rank += 1
    return rows


def format_index(row: RatingRow) -> str:
    if row.itra_index is None:
        return "n/a" if row.match_status != "no_profile" else "no profile"
    return str(row.itra_index)


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
    with path.open("w", encoding="utf-8") as file:
        file.write(f"# {event_name} - ITRA Performance Index rating\n\n")
        file.write(
            f"> Source: {source_url} + itra.run/Runners/FindARunner - collected {today} - "
            f"{gender}, {contest}, {participant_text}.\n\n"
        )
        file.write("| # | ITRA Index | Level | Name | Bib | Gender | Age group | Club | Match |\n")
        file.write("|---|-----------:|-------|------|-----|--------|-----------|------|-------|\n")
        for row in rows:
            rank = str(row.rank) if row.rank is not None else "-"
            name = f"{row.participant.first_name} {row.participant.last_name}".strip()
            club = row.participant.club or "-"
            level = row.itra_level or "-"
            file.write(
                f"| {rank} | {format_index(row)} | {level} | {name} | {row.participant.bib} | "
                f"{row.participant.gender or '-'} | {row.participant.age_group or '-'} | {club} | "
                f"{row.match_status} |\n"
            )


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


def flatten_row(row: RatingRow) -> dict[str, Any]:
    data = asdict(row)
    participant = data.pop("participant")
    return {**data, **{f"participant_{key}": value for key, value in participant.items()}}


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


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "url",
        nargs="?",
        default=os.getenv("PARTICIPANTS_LIST_URL"),
        help="RaceResult event URL, for example https://my.raceresult.com/407493/. Env: PARTICIPANTS_LIST_URL",
    )
    parser.add_argument(
        "--contest",
        default=os.getenv("CONTEST") or None,
        help="Contest/race name to include, for example 'ULTRA 70'. Env: CONTEST",
    )
    parser.add_argument(
        "--gender",
        choices=["all", "male", "female"],
        default=env_choice("GENDER", {"all", "male", "female"}, "all"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=env_int("ITRA_RATING_LIMIT"),
        help="Show only the top N rows after all filtered participants are checked. Env: ITRA_RATING_LIMIT",
    )
    parser.add_argument(
        "--first",
        type=int,
        default=env_int("PARTICIPANTS_LIST_FIRST"),
        help="Check only the first N participants after contest/gender filtering. Env: PARTICIPANTS_LIST_FIRST",
    )
    parser.add_argument(
        "--format",
        choices=["md", "csv", "json"],
        default=env_choice("OUTPUT_FORMAT", {"md", "csv", "json"}, "md"),
    )
    parser.add_argument(
        "--output",
        default=os.getenv("OUTPUT_PATH") or None,
        help="Output file. Defaults to output/<event>_itra.<format>. Env: OUTPUT_PATH",
    )
    parser.add_argument(
        "--itra-delay",
        type=float,
        default=env_float("ITRA_REQUEST_DELAY", 0.35),
        help="Delay between ITRA requests in seconds. Env: ITRA_REQUEST_DELAY",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=env_bool("ITRA_REQUEST_INSECURE"),
        help="Disable TLS certificate verification. Env: ITRA_REQUEST_INSECURE",
    )
    args = parser.parse_args()
    if not args.url:
        parser.error("url is required, either as an argument or PARTICIPANTS_LIST_URL in .env")
    return args


def main() -> int:
    args = parse_args()
    event_name, participants = fetch_raceresult_participants(args.url, insecure=args.insecure)

    if args.contest:
        wanted = clean_text(args.contest).casefold()
        participants = [p for p in participants if p.contest.casefold() == wanted]
    if args.gender != "all":
        participants = [p for p in participants if p.gender == args.gender]
    if args.first is not None:
        participants = participants[: args.first]
    if not participants:
        raise SystemExit("No participants matched the requested filters.")

    itra = ItraClient(delay=args.itra_delay, insecure=args.insecure)
    rows = build_rating(participants, itra)
    checked_count = len(rows)
    if args.limit is not None:
        rows = rows[: args.limit]

    output = Path(args.output) if args.output else default_output_path(event_name, args.format)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "md":
        write_markdown(output, event_name, args.url, rows, args.gender, args.contest or "all contests", checked_count)
    elif args.format == "csv":
        write_csv(output, rows)
    else:
        write_json(output, event_name, args.url, rows)

    checked_suffix = f" after checking {checked_count}" if checked_count != len(rows) else ""
    print(f"Wrote {len(rows)} rows{checked_suffix} to {output}")
    return 0


def default_output_path(event_name: str, fmt: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", event_name.casefold()).strip("_") or "itra_rating"
    return Path("output") / f"{slug}_itra.{fmt}"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.exceptions.SSLError as exc:
        raise SystemExit(f"TLS verification failed: {exc}\nRetry with --insecure only if you trust the network.") from exc
