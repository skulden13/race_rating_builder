# Trail Rating Builder

Build a ranked participant report from a participant source page using an external trail-running rating provider.

The project is structured for multiple participant sources and multiple rating providers. Currently, only the RaceResult source and ITRA provider are implemented. UTMB Index support is planned but not implemented yet. The default output is Markdown because it matches the existing human-readable report style in `output/results.md`. CSV and JSON are also available for spreadsheets or later processing.

<p align="center">
  <img src="./avatar.jpg" alt="Bot Avatar" width="512">
</p>

## Install

Use a project-local virtual environment. This keeps dependencies out of the global Python installation.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional local `.env` defaults are supported via `python-dotenv`:

```bash
PARTICIPANTS_SOURCE=raceresult
PARTICIPANTS_SOURCE_URL=https://my.raceresult.com/123456/
RATING_PROVIDER=itra
CONTEST=ULTRA 70
GENDER=male
# Check only the first N filtered table rows. Leave empty to check all.
PARTICIPANTS_SOURCE_FIRST=
# Leave empty to include every filtered participant. Set to 20 for a top-20 report.
RATING_OUTPUT_LIMIT=
OUTPUT_FORMAT=md
OUTPUT_PATH=output/results.md
CACHE_DIR=.cache/
CACHE_DISABLED=false
CACHE_REFRESH=false
RATING_REBUILD=false
LOG_LEVEL=info
ITRA_REQUEST_DELAY=0.5
RATING_REQUEST_INSECURE=false
```

Clean local dependencies and rebuild the environment from scratch:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pip check
```

## Usage

```bash
source .venv/bin/activate
PYTHONPATH=src python -m trail_rating_builder.cli 'https://my.raceresult.com/123456/' \
  --source raceresult \
  --provider itra \
  --contest 'ULTRA 70' \
  --gender male \
  --first 20 \
  --output output/ultra70_live_itra.md
```

With `.env` configured, this is enough:

```bash
source .venv/bin/activate
PYTHONPATH=src python -m trail_rating_builder.cli
```

Useful options:

```bash
--source raceresult         # participant source parser; currently only RaceResult is implemented
--provider itra             # rating provider; currently only ITRA is implemented
--contest 'ULTRA 70'       # race/contest name from RaceResult
--gender all|male|female   # participant filter
--first 10                 # check only first N filtered table rows
--limit 10                 # show top N after all filtered participants are checked
--format md|csv|json       # output format
--output PATH              # output file path; default includes event, contest, gender, and provider
--cache-dir PATH           # cache directory for computed rating rows
--no-cache                 # disable cache reads and writes
--refresh-cache            # ignore existing cache and write fresh data
--rebuild-rating           # rebuild rating rows but reuse cached provider responses
--log-level debug|info|warning|error
--itra-delay 0.5          # polite delay between ITRA searches
--insecure                 # disable TLS verification only if local CA setup is broken
```

Build-step logs are enabled at `info` by default. Use `--log-level warning` for quieter runs or `--log-level debug` to include cache key details.

## Cache

The CLI uses two cache layers.

First, it caches complete computed rating rows. The cache key includes the effective request parameters:

- participant source URL
- participant source
- rating provider
- contest
- gender
- `--first`

This means a previous request for `MARATHON` + `male` can be reused without refetching the participant source or querying ITRA again. Output-only settings such as `--limit`, `--format`, and `--output` are not part of the cache key, so `--limit 10` followed by `--limit 3` reuses the same built rating and only changes the written report.

Second, it caches individual provider search responses under `provider_responses/`. This cache is keyed by rating provider, search name, and requested result count. It lets related reports reuse runner lookups even when the full report cache key is different. For example:

- `--first 10` followed by `--first 3` can reuse the first three runner searches.
- `--gender male` followed by `--gender all` can reuse the male runner searches and request only the missing female runners.

If the participant table changed and you want a new report while keeping previous runner lookups, rebuild only the computed rating rows:

```bash
PYTHONPATH=src python -m trail_rating_builder.cli \
  --rebuild-rating \
  'https://my.raceresult.com/123456/' \
  --source raceresult \
  --provider itra \
  --contest 'MARATHON' \
  --gender all
```

Request fresh data without reading or writing cache:

```bash
PYTHONPATH=src python -m trail_rating_builder.cli \
  --no-cache \
  'https://my.raceresult.com/123456/' \
  --source raceresult \
  --provider itra \
  --contest 'MARATHON' \
  --gender male
```

Refresh an existing cache entry and save the new result:

```bash
PYTHONPATH=src python -m trail_rating_builder.cli --refresh-cache
```

`--no-cache` disables both cache layers. `--rebuild-rating` ignores only the complete rating-row cache. `--refresh-cache` ignores existing entries in both layers and writes fresh data.

## Docker

Build the image:

```bash
docker build -t trail-rating-builder .
```

Run it and write reports into the local `output/` folder:

```bash
mkdir -p output
docker run --rm -v "$PWD/output:/app/output" trail-rating-builder \
  'https://my.raceresult.com/123456/' \
  --source raceresult \
  --provider itra \
  --contest 'ULTRA 70' \
  --gender male \
  --first 20 \
  --output output/ultra70_live_itra.md
```

## Tests

The unit tests avoid live network calls and cover parsing, matching, ranking, and ITRA payload decryption.

```bash
source .venv/bin/activate
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
```

## Notes

ITRA does not appear to publish a documented public runner-search API. The ITRA provider uses the same internal endpoint called by `https://itra.run/Runners/FindARunner`, including CSRF handling and AES-CBC response decryption. If ITRA changes that frontend contract, the provider may need an update.

Additional participant sources should live under `src/trail_rating_builder/sources/`. Additional rating providers should live under `src/trail_rating_builder/providers/`.
