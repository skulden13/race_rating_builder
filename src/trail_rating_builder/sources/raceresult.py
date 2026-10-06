from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import certifi
import requests

from ..http import USER_AGENT
from ..models import Participant
from ..text import canonical_gender, clean_text


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


def clean_raceresult_group_name(value: str) -> str:
    return re.sub(r"^#\d+_", "", clean_text(value))


def get_raceresult_event_id(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/(\d+)(?:/|$)", parsed.path)
    if not match:
        raise ValueError(f"Could not extract RaceResult event id from URL: {url}")
    return match.group(1)


def get_raceresult_host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or "my.raceresult.com"


class RaceResultTabParser(HTMLParser):
    def __init__(self, event_id: str):
        super().__init__()
        self.event_id = event_id
        self.participant_tab = ""
        self.href = ""
        self.label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href") or ""
            self.label = []

    def handle_data(self, data: str) -> None:
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            path = urlparse(urljoin(f"https://my.raceresult.com/{self.event_id}/", self.href)).path
            match = re.fullmatch(rf"/{self.event_id}/([^/]+)/?", path)
            if match and clean_text("".join(self.label)).casefold() == "participants":
                self.participant_tab = match.group(1)
            self.href = ""


def flatten_raceresult_data(data: Any) -> Iterable[tuple[str, list[list[Any]]]]:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                yield str(key), value
            else:
                yield from flatten_raceresult_data(value)


def flatten_raceresult_groups(data: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], list[list[Any]]]]:
    if isinstance(data, dict):
        for key, value in data.items():
            group_path = (*path, clean_raceresult_group_name(str(key)))
            if isinstance(value, list):
                yield group_path, value
            else:
                yield from flatten_raceresult_groups(value, group_path)


def contest_from_group_path(path: tuple[str, ...]) -> str:
    for group in path:
        if canonical_gender(group) not in {"male", "female"}:
            return group
    return path[-1] if path else ""


def gender_from_group_path(path: tuple[str, ...]) -> str:
    for group in reversed(path):
        gender = canonical_gender(group)
        if gender in {"male", "female"}:
            return gender
    return ""


def raceresult_contest_filters(list_json: dict[str, Any]) -> list[str]:
    group_filters = list_json.get("groupFilters")
    if not isinstance(group_filters, list):
        return []
    for group_filter in group_filters:
        if not isinstance(group_filter, dict):
            continue
        values = group_filter.get("Values")
        if group_filter.get("Type") == 1 and isinstance(values, list):
            return [clean_text(value) for value in values if clean_text(value)]
    return []


def raceresult_filter_param(contest_filter: str) -> str:
    return f"{contest_filter}\f\f<Ignore>"


def parse_raceresult_row(row: list[Any], contest_name: str, group_gender: str = "") -> Participant | None:
    if len(row) < 6:
        return None
    first, last = split_raceresult_name(row[3])
    fourth_column = clean_text(row[4])
    fifth_column = clean_text(row[5])
    if gender_from_age_group(fourth_column):
        age_group = fourth_column
        club = fifth_column
    else:
        age_group = fifth_column
        club = clean_text(row[6]) if len(row) > 6 else ""
    gender = gender_from_age_group(age_group) or group_gender
    return Participant(
        bib=clean_text(row[0]),
        race_result_id=clean_text(row[1]),
        display_name=clean_text(row[3]),
        first_name=first,
        last_name=last,
        age_group=age_group,
        gender=gender,
        club=club,
        contest=clean_text(contest_name),
    )


def parse_raceresult_participants(list_json: dict[str, Any]) -> list[Participant]:
    participants: list[Participant] = []
    for group_path, rows in flatten_raceresult_groups(list_json.get("data", {})):
        contest_name = contest_from_group_path(group_path)
        group_gender = gender_from_group_path(group_path)
        for row in rows:
            if not isinstance(row, list):
                continue
            participant = parse_raceresult_row(row, contest_name, group_gender)
            if participant:
                participants.append(participant)
    return participants


def fetch_raceresult_list(
    session: requests.Session,
    url: str,
    key: str,
    list_config: dict[str, Any],
    contest: str,
    verify: bool | str,
    filter_value: str = "",
    page: str = "participants",
) -> dict[str, Any]:
    params = {
        "key": key,
        "listname": list_config["Name"],
        "page": page,
        "contest": contest,
        "r": "all",
        "l": list_config.get("Leader", 999999),
        "fav": "",
        "openedGroups": "{}",
        "term": "",
    }
    if filter_value:
        params["f"] = raceresult_filter_param(filter_value)
    response = session.get(url, params=params, timeout=30, verify=verify)
    response.raise_for_status()
    return response.json()


def fetch_raceresult_participants(url: str, insecure: bool = False) -> tuple[str, list[Participant]]:
    event_id = get_raceresult_event_id(url)
    host = get_raceresult_host(url)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    verify: bool | str = False if insecure else certifi.where()
    event_base = f"https://{host}/{event_id}"
    path_parts = urlparse(url).path.strip("/").split("/")
    page = path_parts[1] if len(path_parts) > 1 else "participants"
    base = f"{event_base}/{page}"

    config = session.get(f"{base}/config", params={"lang": "en"}, timeout=30, verify=verify)
    if config.status_code == 404:
        config_json = {"error": f"tab not found: {page}"}
    else:
        config.raise_for_status()
        config_json = config.json()
    if config_json.get("error") == f"tab not found: {page}":
        event_page = session.get(f"{event_base}/", timeout=30, verify=verify)
        event_page.raise_for_status()
        parser = RaceResultTabParser(event_id)
        parser.feed(event_page.text)
        if not parser.participant_tab:
            raise ValueError(f"Could not find a RaceResult Participants tab for event {event_id}.")
        page = parser.participant_tab
        config = session.get(f"{event_base}/{page}/config", params={"lang": "en"}, timeout=30, verify=verify)
        config.raise_for_status()
        config_json = config.json()
    if config_json.get("error"):
        raise ValueError(f"RaceResult configuration error: {config_json['error']}")
    event_name = clean_text(config_json.get("eventname")) or f"RaceResult {event_id}"
    server = config_json.get("server") or "my.raceresult.com"
    lists = config_json.get("TabConfig", {}).get("Lists") or []
    if not lists:
        raise ValueError(f"No published RaceResult lists found for event {event_id} on tab {page}.")
    list_config = lists[0]
    contest = list_config.get("Contest", "0")

    list_url = f"https://{server}/{event_id}/{page}/list"
    list_json = fetch_raceresult_list(session, list_url, config_json["key"], list_config, contest, verify, page=page)
    contest_filters = raceresult_contest_filters(list_json)
    if contest_filters:
        participants = []
        for contest_filter in contest_filters:
            filtered_json = fetch_raceresult_list(
                session,
                list_url,
                config_json["key"],
                list_config,
                contest,
                verify,
                contest_filter,
                page=page,
            )
            participants.extend(parse_raceresult_participants(filtered_json))
    else:
        participants = parse_raceresult_participants(list_json)
    return event_name, participants
