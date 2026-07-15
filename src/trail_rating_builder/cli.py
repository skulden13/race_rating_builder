from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from .cache import CachedRatingProvider, build_cache_key, load_cached_rating, rows_from_payload, rows_to_payload, save_cached_rating
from .config import env_bool, env_choice, env_float, env_int
from .matching import build_rating
from .output import default_output_path, write_csv, write_json, write_markdown
from .providers.itra import ItraClient
from .sources.raceresult import fetch_raceresult_participants
from .text import clean_text


SUPPORTED_PROVIDERS = {"itra"}
SUPPORTED_SOURCES = {"raceresult"}
LOG_LEVELS = {"debug", "info", "warning", "error"}
LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Build a ranked participant report from a participant source URL."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=os.getenv("PARTICIPANTS_SOURCE_URL") or os.getenv("PARTICIPANTS_LIST_URL"),
        help="Participant source URL. Env: PARTICIPANTS_SOURCE_URL",
    )
    parser.add_argument(
        "--source",
        choices=sorted(SUPPORTED_SOURCES),
        default=env_choice("PARTICIPANTS_SOURCE", SUPPORTED_SOURCES, "raceresult"),
        help="Participant source parser. Currently only RaceResult is supported. Env: PARTICIPANTS_SOURCE",
    )
    parser.add_argument(
        "--provider",
        choices=sorted(SUPPORTED_PROVIDERS),
        default=env_choice("RATING_PROVIDER", SUPPORTED_PROVIDERS, "itra"),
        help="Rating provider. Currently only ITRA is supported. Env: RATING_PROVIDER",
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
        default=env_int("RATING_OUTPUT_LIMIT"),
        help="Show only the top N rows after all filtered participants are checked. Env: RATING_OUTPUT_LIMIT",
    )
    parser.add_argument(
        "--first",
        type=int,
        default=env_int("PARTICIPANTS_SOURCE_FIRST") or env_int("PARTICIPANTS_LIST_FIRST"),
        help="Check only the first N participants after contest/gender filtering. Env: PARTICIPANTS_SOURCE_FIRST",
    )
    parser.add_argument(
        "--format",
        choices=["md", "csv", "json"],
        default=env_choice("OUTPUT_FORMAT", {"md", "csv", "json"}, "md"),
    )
    parser.add_argument(
        "--output",
        default=os.getenv("OUTPUT_PATH") or None,
        help="Output file. Defaults to output/<event>_<contest>_<gender>_<provider>.<format>. Env: OUTPUT_PATH",
    )
    parser.add_argument(
        "--itra-delay",
        type=float,
        default=env_float("ITRA_REQUEST_DELAY", 0.5),
        help="Delay between ITRA requests in seconds. Env: ITRA_REQUEST_DELAY",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=env_bool("RATING_REQUEST_INSECURE"),
        help="Disable TLS certificate verification. Env: RATING_REQUEST_INSECURE",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("CACHE_DIR") or ".cache/",
        help="Directory for cached rating data. Env: CACHE_DIR",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=env_bool("CACHE_DISABLED"),
        help="Disable cache reads and writes. Env: CACHE_DISABLED",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        default=env_bool("CACHE_REFRESH"),
        help="Ignore existing cache and write a fresh cache entry. Env: CACHE_REFRESH",
    )
    parser.add_argument(
        "--rebuild-rating",
        action="store_true",
        default=env_bool("RATING_REBUILD"),
        help="Ignore cached computed rating rows but reuse cached provider responses. Env: RATING_REBUILD",
    )
    parser.add_argument(
        "--log-level",
        choices=sorted(LOG_LEVELS),
        default=env_choice("LOG_LEVEL", LOG_LEVELS, "info"),
        help="Logging verbosity. Env: LOG_LEVEL",
    )
    args = parser.parse_args()
    if not args.url:
        parser.error("url is required, either as an argument or PARTICIPANTS_SOURCE_URL in .env")
    return args


def configure_logging(level: str) -> None:
    log_level = getattr(logging, level.upper())
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")
    logging.getLogger().setLevel(log_level)


def build_request_cache_params(args: argparse.Namespace) -> dict[str, object]:
    return {
        "kind": "rating_rows",
        "url": args.url,
        "source": args.source,
        "provider": args.provider,
        "contest": args.contest or "",
        "gender": args.gender,
        "first": args.first,
    }


def fetch_participants(args: argparse.Namespace):
    if args.source == "raceresult":
        return fetch_raceresult_participants(args.url, insecure=args.insecure)
    raise ValueError(f"Unsupported participant source: {args.source}")


def get_provider(args: argparse.Namespace) -> ItraClient:
    if args.provider == "itra":
        return ItraClient(delay=args.itra_delay, insecure=args.insecure)
    raise ValueError(f"Unsupported provider: {args.provider}")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    cache_key = build_cache_key(build_request_cache_params(args))
    cache_dir = Path(args.cache_dir)
    LOGGER.debug("Cache key: %s", cache_key)
    LOGGER.debug("Cache directory: %s", cache_dir)

    if args.no_cache:
        LOGGER.info("Cache disabled; fetching participants and querying provider directly.")
    elif args.refresh_cache:
        LOGGER.info("Refreshing rating rows and provider responses.")
    elif args.rebuild_rating:
        LOGGER.info("Rebuilding rating rows while reusing cached provider responses.")

    cached = None if args.no_cache or args.refresh_cache or args.rebuild_rating else load_cached_rating(cache_dir, cache_key)

    if cached:
        LOGGER.info("Loaded cached rating rows.")
        event_name = cached["event_name"]
        rows = rows_from_payload(cached["rows"])
    else:
        LOGGER.info("Fetching participants from %s source.", args.source)
        event_name, participants = fetch_participants(args)
        LOGGER.info("Fetched %s participants for %s.", len(participants), event_name)

        if args.contest:
            wanted = clean_text(args.contest).casefold()
            before_count = len(participants)
            participants = [p for p in participants if p.contest.casefold() == wanted]
            LOGGER.info("Contest filter %r kept %s of %s participants.", args.contest, len(participants), before_count)
        if args.gender != "all":
            before_count = len(participants)
            participants = [p for p in participants if p.gender == args.gender]
            LOGGER.info("Gender filter %r kept %s of %s participants.", args.gender, len(participants), before_count)
        if args.first is not None:
            before_count = len(participants)
            participants = participants[: args.first]
            LOGGER.info("First-participants limit kept %s of %s participants.", len(participants), before_count)
        if not participants:
            raise SystemExit("No participants matched the requested filters.")

        LOGGER.info("Creating %s provider.", args.provider)
        provider = get_provider(args)
        if not args.no_cache:
            LOGGER.info("Provider response cache enabled at %s.", cache_dir / "provider_responses")
            provider = CachedRatingProvider(provider, cache_dir / "provider_responses", refresh=args.refresh_cache)
        LOGGER.info("Building rating for %s participants.", len(participants))
        rows = build_rating(participants, provider, show_progress=True)
        LOGGER.info("Built %s rating rows.", len(rows))
        if not args.no_cache:
            LOGGER.info("Saving computed rating rows to cache.")
            save_cached_rating(
                cache_dir,
                cache_key,
                {
                    "event_name": event_name,
                    "cache_params": build_request_cache_params(args),
                    "rows": rows_to_payload(rows),
                },
            )
    checked_count = len(rows)
    if args.limit is not None:
        LOGGER.info("Applying output limit: %s rows from %s checked rows.", args.limit, checked_count)
        rows = rows[: args.limit]

    output = (
        Path(args.output)
        if args.output
        else default_output_path(event_name, args.contest or "all contests", args.gender, args.format, args.provider)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Writing %s output to %s.", args.format, output)
    if args.format == "md":
        write_markdown(output, event_name, args.url, rows, args.gender, args.contest or "all contests", checked_count)
    elif args.format == "csv":
        write_csv(output, rows)
    else:
        write_json(output, event_name, args.url, rows)
    LOGGER.info("Finished writing report.")

    checked_suffix = f" after checking {checked_count}" if checked_count != len(rows) else ""
    print(f"Wrote {len(rows)} rows{checked_suffix} to {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.exceptions.SSLError as exc:
        raise SystemExit(f"TLS verification failed: {exc}\nRetry with --insecure only if you trust the network.") from exc
