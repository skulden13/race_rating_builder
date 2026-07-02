from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse

import certifi
import requests

from ..http import USER_AGENT
from ..models import Participant
from ..text import clean_text


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


def get_raceresult_event_id(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/(\d+)(?:/|$)", parsed.path)
    if not match:
        raise ValueError(f"Could not extract RaceResult event id from URL: {url}")
    return match.group(1)


def flatten_raceresult_data(data: Any) -> Iterable[tuple[str, list[list[Any]]]]:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                yield str(key), value
            else:
                yield from flatten_raceresult_data(value)


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
