# Repository Guidelines

## Project Structure & Module Organization

`src/trail_rating_builder/` contains the Python CLI and application logic. Participant parsers belong in `sources/`, rating clients in `providers/`, and shared records in `models.py`. Keep matching/ranking, caching, HTTP handling, and report rendering in their existing modules. Currently, RaceResult and ITRA are the implemented integrations.

`tests/` mirrors these responsibilities, with provider tests under `tests/providers/` and reusable fakes in `tests/helpers.py`. Generated reports live in `output/`; cached data lives in `.cache/`. Both are ignored by Git. `avatar.jpg` is the README image, and `scripts/gh-pages-publish.sh` publishes reports.

## Build, Test, and Development Commands

Create and activate a local environment, then install pinned dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

- `PYTHONPATH=src python -m trail_rating_builder.cli --help`: inspect CLI options.
- `PYTHONPATH=src python -m trail_rating_builder.cli`: generate reports using `.env` settings.
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests`: run the offline unit suite.
- `docker build -t trail-rating-builder .`: build the Python 3.12 container.

Run commands from the repository root; local module execution requires `PYTHONPATH=src`.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions/modules, `PascalCase` classes, and uppercase constants. Follow existing type annotations, dataclasses, and double-quoted strings. Keep integration-specific parsing inside its source or provider module. No formatter or linter is configured; match surrounding code and avoid unrelated formatting changes.

## Testing Guidelines

Use standard-library `unittest`, with `test_*.py` files and descriptive `test_*` methods. Mock HTTP calls with `unittest.mock` and reuse helper fakes; tests must not require live services. Cover changed parsing, matching, cache, and output behavior, including failure cases. No numeric coverage threshold is configured.

## Commit & Pull Request Guidelines

History uses short, descriptive subjects, often prefixed by an area, such as `gh-pages: rename script`. Follow that pattern and keep commits focused. PRs should explain the behavior change, list validation commands/results, and link relevant issues. Include sample output for report changes and update README examples when CLI behavior changes.

## Configuration & Publishing

Copy `.env.example` to `.env` for local defaults. Keep secrets and caches untracked, preserve TLS verification, and respect provider request delays. Run `./scripts/gh-pages-publish.sh` only when publishing is intended: it commits and pushes `output/` to the remote `gh-pages` branch.
