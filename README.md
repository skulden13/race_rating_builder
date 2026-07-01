# ITRA Rating Builder 🏃‍♂️🏔🕵️‍♂️

Build a ranked participant report from a RaceResult event page using ITRA Performance Index data from ITRA's "Find a Runner" page.

The default output is Markdown because it matches the existing human-readable report style in `output/results.md`. CSV and JSON are also available for spreadsheets or later processing.

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
PARTICIPANTS_LIST_URL=https://my.raceresult.com/407493/
CONTEST=ULTRA 70
GENDER=male
# Check only the first N filtered table rows. Leave empty to check all.
PARTICIPANTS_LIST_FIRST=
# Leave empty to include every filtered participant. Set to 20 for a top-20 report.
ITRA_RATING_LIMIT=
OUTPUT_FORMAT=md
OUTPUT_PATH=output/results.md
ITRA_REQUEST_DELAY=0.35
ITRA_REQUEST_INSECURE=false
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
python itra_rating_builder.py 'https://my.raceresult.com/407493/' \
  --contest 'ULTRA 70' \
  --gender male \
  --first 20 \
  --output output/ultra70_live_itra.md
```

With `.env` configured, this is enough:

```bash
source .venv/bin/activate
python itra_rating_builder.py
```

Useful options:

```bash
--contest 'ULTRA 70'       # race/contest name from RaceResult
--gender all|male|female   # participant filter
--first 10                 # check only first N filtered table rows
--limit 10                 # show top N after all filtered participants are checked
--format md|csv|json       # output format
--output PATH              # output file path
--itra-delay 0.35          # polite delay between ITRA searches
--insecure                 # disable TLS verification only if local CA setup is broken
```

## Docker

Build the image:

```bash
docker build -t itra-rating-builder .
```

Run it and write reports into the local `output/` folder:

```bash
mkdir -p output
docker run --rm -v "$PWD/output:/app/output" itra-rating-builder \
  'https://my.raceresult.com/407493/' \
  --contest 'ULTRA 70' \
  --gender male \
  --first 20 \
  --output output/ultra70_live_itra.md
```

## Tests

The unit tests avoid live network calls and cover parsing, matching, ranking, and ITRA payload decryption.

```bash
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
```

## Notes

ITRA does not appear to publish a documented public runner-search API. This script uses the same internal endpoint called by `https://itra.run/Runners/FindARunner`, including CSRF handling and AES-CBC response decryption. If ITRA changes that frontend contract, this script may need an update.
