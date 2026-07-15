#!/usr/bin/env bash
set -euo pipefail

BRANCH="${GH_PAGES_BRANCH:-gh-pages}"
REMOTE="${GH_PAGES_REMOTE:-origin}"
OUTPUT_DIR="${1:-output}"
COMMIT_MESSAGE="${GH_PAGES_COMMIT_MESSAGE:-Update reports}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ ! -d "$OUTPUT_DIR" ]; then
  echo "Output directory not found: $OUTPUT_DIR" >&2
  echo "Generate reports first, for example: PYTHONPATH=src python -m trail_rating_builder.cli" >&2
  exit 1
fi

if [ ! -f "$OUTPUT_DIR/index.html" ]; then
  echo "Warning: $OUTPUT_DIR/index.html was not found. The site will not have a report index." >&2
fi

WORKTREE="$(mktemp -d)"

cleanup() {
  git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || rm -rf "$WORKTREE"
}
trap cleanup EXIT

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$WORKTREE" "$BRANCH"
elif git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
  git fetch "$REMOTE" "$BRANCH:$BRANCH"
  git worktree add "$WORKTREE" "$BRANCH"
else
  git worktree add --detach "$WORKTREE"
  git -C "$WORKTREE" switch --orphan "$BRANCH"
fi

find "$WORKTREE" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$OUTPUT_DIR"/. "$WORKTREE"/
touch "$WORKTREE/.nojekyll"

git -C "$WORKTREE" add -A
if git -C "$WORKTREE" diff --cached --quiet; then
  echo "No changes to publish."
  exit 0
fi

git -C "$WORKTREE" commit -m "$COMMIT_MESSAGE"
git -C "$WORKTREE" push "$REMOTE" "$BRANCH"

echo "Published $OUTPUT_DIR to $REMOTE/$BRANCH."
