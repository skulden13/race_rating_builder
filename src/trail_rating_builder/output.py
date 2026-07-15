from __future__ import annotations

import csv
import datetime as dt
import html
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
        file.write(f"# {event_name} - {contest} - {gender} - {provider} rating\n\n")
        file.write(
            f"> Source: {source_url} + provider: {provider} - collected {today} - "
            f"{gender}, {contest}, {participant_text}.\n\n"
        )
        file.write(f"| # | {provider} Index | Level | Name | Bib | Gender | Nationality | Age group | Club | Match |\n")
        file.write("|---|-----------:|-------|------|-----|--------|-------------|-----------|------|-------|\n")
        for row in rows:
            rank = str(row.rank) if row.rank is not None else "-"
            name = f"{row.participant.first_name} {row.participant.last_name}".strip()
            if row.provider_profile_url:
                name = f"[{name}]({row.provider_profile_url})"
            club = row.participant.club or "-"
            level = row.rating_level or "-"
            nationality = row.provider_nationality or "-"
            file.write(
                f"| {rank} | {format_index(row)} | {level} | {name} | {row.participant.bib} | "
                f"{row.participant.gender or '-'} | {nationality} | {row.participant.age_group or '-'} | {club} | "
                f"{row.match_status} |\n"
            )


def markdown_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        title = line.removeprefix("# ").strip()
        if title != line:
            return title
    return path.stem.replace("_", " ")


def write_output_index(output_dir: Path) -> Path:
    reports = sorted(path for path in output_dir.glob("*.md") if path.name.lower() != "index.md")
    index_path = output_dir / "index.html"
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with index_path.open("w", encoding="utf-8") as file:
        file.write("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trail Rating Reports</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: #d9e1ec;
      --accent: #0f766e;
      --accent-strong: #115e59;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    main {
      width: min(960px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }
    header {
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0;
      font-size: 32px;
      line-height: 1.15;
      font-weight: 750;
      letter-spacing: 0;
    }
    .meta {
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 14px;
    }
    .reports {
      display: grid;
      gap: 12px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .report {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 16px 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .report a {
      color: var(--accent);
      font-size: 16px;
      font-weight: 650;
      text-decoration: none;
    }
    .report a:hover { color: var(--accent-strong); text-decoration: underline; }
    .filename {
      flex: 0 1 auto;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
      text-align: right;
    }
    .empty {
      padding: 18px;
      color: var(--muted);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    @media (max-width: 640px) {
      main { width: min(100% - 24px, 960px); padding: 28px 0; }
      h1 { font-size: 26px; }
      .report { align-items: flex-start; flex-direction: column; gap: 8px; }
      .filename { text-align: left; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Trail Rating Reports</h1>
""")
        file.write(f'      <p class="meta">Generated {html.escape(generated_at)} UTC · {len(reports)} reports</p>\n')
        file.write("    </header>\n")
        if reports:
            file.write('    <ul class="reports">\n')
            for report in reports:
                title = markdown_title(report)
                escaped_name = html.escape(report.name)
                file.write(
                    f'      <li class="report"><a href="{escaped_name}">{html.escape(title)}</a>'
                    f'<span class="filename">{escaped_name}</span></li>\n'
                )
            file.write("    </ul>\n")
        else:
            file.write('    <p class="empty">No Markdown reports found.</p>\n')
        file.write("  </main>\n")
        file.write("</body>\n")
        file.write("</html>\n")
    return index_path


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


def slugify(value: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or fallback


def default_output_path(event_name: str, contest: str, gender: str, fmt: str, provider: str) -> Path:
    event_slug = slugify(event_name, "trail_rating")
    contest_slug = slugify(contest, "all_contests")
    gender_slug = slugify(gender, "all")
    return Path("output") / f"{event_slug}_{contest_slug}_{gender_slug}_{provider}.{fmt}"
