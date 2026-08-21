#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/your/cloned/repository"
  exit 1
fi

SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$(cd "$1" && pwd)"

if [[ ! -d "$TARGET/.git" ]]; then
  echo "Error: target is not a Git repository: $TARGET"
  exit 1
fi

if [[ "$SOURCE" == "$TARGET" ]]; then
  echo "Error: extract this package outside the existing repository first."
  exit 1
fi

read -r -p "Delete all tracked working files in $TARGET except .git and replace them? [y/N] " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

find "$TARGET" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$SOURCE"/. "$TARGET"/
rm -rf "$TARGET/.git" 2>/dev/null || true

echo "Replacement complete. Next: cd '$TARGET' && git add -A && git commit && git push"
