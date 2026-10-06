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

Kazbegi Mountain Marathon participants are published through RaceResult too:

```bash
PYTHONPATH=src python -m trail_rating_builder.cli 'https://my4.raceresult.com/415501/' \
  --source raceresult \
  --provider itra \
  --contest 'Extreme - 35km' \
  --gender male
```

RaceResult events can publish a tab labeled "Participants" under a different path, such as `/results`. The source discovers that tab automatically when `/participants` is unavailable. An explicit tab URL is also supported.

For Lisi Trail Festival:

```bash
PYTHONPATH=src python -m trail_rating_builder.cli 'https://my1.raceresult.com/427872/' \
  --source raceresult \
  --provider itra \
  --contest 'ULTRA 62' \
  --gender male
```

With `.env` configured, this is enough:

```bash
source .venv/bin/activate
PYTHONPATH=src python -m trail_rating_builder.cli
```

### ITRA Browser Mode

If ITRA requires a security check, use a visible Chromium browser and complete the check manually. Install the optional browser dependencies in your virtual environment:

```bash
source .venv/bin/activate
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
```

```bash
PYTHONPATH=src python -m trail_rating_builder.cli 'https://my1.raceresult.com/427872/' \
  --source raceresult --provider itra \
  --contest 'ULTRA 62' --gender male \
  --itra-browser --itra-delay 3 --rebuild-rating
```

Complete any CAPTCHA in the opened browser window and leave it open. The script resumes when the Find a Runner page exposes its CSRF token, with a five-minute verification timeout. If the page loads but the script keeps waiting, search for a runner on the page: the script can also capture the CSRF header from that search. Searches run in the same browser session. If ITRA denies a search, the script reopens the page for verification and retries once. Verification can be required again; browser mode does not automatically solve CAPTCHAs or guarantee access. Failures report the current page URL/title and distinguish missing tokens from navigation errors or a closed page.

Existing provider responses are reused, and successful new responses are cached as usual. The browser opens only for uncached searches and closes when rating requests finish or fail. You can also set `ITRA_BROWSER=true` in `.env`.

Browser mode requires an interactive desktop. The existing Docker image supports the default HTTP mode; it does not include Chromium or a desktop display. Browser cookies are kept only for the current run.

Useful options:

Participant gender is read from the RaceResult age group (for example, `M35-39`), with gender groups as a fallback. Nationality codes such as `FRA` and `MAR` are not age groups. A known gender conflict between the participant and an ITRA profile is reported as `gender_mismatch` without an index or rank. Computed rating caches from the earlier parser are rebuilt automatically; cached provider responses remain reusable.

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

## Viewing Reports

When writing Markdown output, the CLI also refreshes `index.md` in the same output directory. GitHub Pages renders this file as the site homepage, with links to the generated `.md` reports.

## GitHub Pages

Generate or refresh reports first:

```bash
source .venv/bin/activate
PYTHONPATH=src python -m trail_rating_builder.cli
```

Publish `output/` to the `gh-pages` branch:

```bash
./scripts/gh-pages-publish.sh
```

The script uses a temporary Git worktree, copies `output/` into it, commits the static files, and pushes to `origin/gh-pages`. It does not switch your current branch or clean your working tree. It leaves Jekyll enabled so GitHub Pages can render `index.md`.

One-time GitHub setup:

```text
Repository -> Settings -> Pages
Source: Deploy from a branch
Branch: gh-pages
Folder: / root
```

Optional overrides:

```bash
GH_PAGES_BRANCH=pages ./scripts/publish-gh-pages.sh
GH_PAGES_REMOTE=origin ./scripts/publish-gh-pages.sh
GH_PAGES_COMMIT_MESSAGE="Publish reports" ./scripts/publish-gh-pages.sh
./scripts/publish-gh-pages.sh output
```

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

## Troubleshooting

If the progress bar stays at `0/N`, the first rating-provider request has not completed yet. For ITRA this can be the CSRF token request, the first runner search, or a temporary `403` from rate limiting/bot protection.

Useful options:

```bash
PYTHONPATH=src python -m trail_rating_builder.cli --log-level debug --rebuild-rating
PYTHONPATH=src python -m trail_rating_builder.cli --itra-delay 1.5 --rebuild-rating
```

`--rebuild-rating` reuses cached provider responses and requests only missing runner lookups. `--refresh-cache` ignores cached provider responses and can trigger many ITRA requests again.

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
