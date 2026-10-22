#!/usr/bin/env bash
# Remove configured paths from every commit, then verify.
#
# Usage:
#   scripts/maintenance/purge-history.sh [paths-file]
#
# The paths file defaults to scripts/maintenance/purge-paths.txt. Every path,
# glob, or regex is passed to git-filter-repo in invert mode, so the rewrite
# drops it from all commits and branches.
#
# Always run on a clean tree. The script writes a bundle backup next to the
# repository before rewriting, and refuses to run when the working tree is
# dirty.
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

CONFIG=${1:-scripts/maintenance/purge-paths.txt}
if [ ! -f "$CONFIG" ]; then
  echo "missing paths file: $CONFIG" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "working tree is dirty; commit or stash first" >&2
  exit 1
fi

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo is required (brew install git-filter-repo)" >&2
  exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="../$(basename "$ROOT")-backup-$STAMP.bundle"
git bundle create "$BACKUP" --all
echo "backup: $BACKUP"

git filter-repo --invert-paths --paths-from-file "$CONFIG" --force

# filter-repo drops origin; restore it so a force-push is possible.
ORIGIN_URL=$(git config --get remote.origin.url || true)
if [ -n "${ORIGIN_URL:-}" ] && ! git remote | grep -qx origin; then
  git remote add origin "$ORIGIN_URL"
fi

echo
echo "verification (each command should print nothing):"
echo "  git log --all --oneline -- qa/reference"
echo "  git log --all --oneline -- docs/figures"
echo "  git rev-list --objects --all | grep -E '\.(png|jpg|jpeg)$'"
echo
echo "Publish with: git push --force-with-lease origin main"
echo "Note: hosting caches keep unreachable blobs until garbage collection;"
echo "for a public repository, recreate it or ask the host to purge."
