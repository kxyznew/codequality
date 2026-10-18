#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to publish this repository." >&2
  exit 1
fi

if [[ -z "${REPO_URL:-}" ]]; then
  echo "Set REPO_URL to the empty GitHub repository URL, for example:" >&2
  echo "  REPO_URL=git@github.com:kxyznew/codequality.git bash bootstrap.sh" >&2
  exit 2
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init --initial-branch=main
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "main" ]]; then
  git branch -M main
fi

if git remote get-url origin >/dev/null 2>&1; then
  current_remote="$(git remote get-url origin)"
  if [[ "$current_remote" != "$REPO_URL" ]]; then
    echo "The existing origin is $current_remote, not $REPO_URL. Update it deliberately before retrying." >&2
    exit 3
  fi
else
  git remote add origin "$REPO_URL"
fi

git add -A
if ! git diff --cached --quiet; then
  if ! git var GIT_AUTHOR_IDENT >/dev/null 2>&1; then
    echo "Configure your Git author name and email before creating the first commit." >&2
    echo "  git config --global user.name \"Your Name\"" >&2
    echo "  git config --global user.email \"you@example.com\"" >&2
    exit 4
  fi
  git commit -m "Initial release v1.0.0"
fi

git push --set-upstream origin main
