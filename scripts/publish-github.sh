#!/usr/bin/env bash
# Configure the existing site repository; never change its visibility.
set -euo pipefail
REPOSITORY="nathanieldlewis/garrison-neighborhood-safety"
command -v gh >/dev/null || { echo 'Install GitHub CLI and sign in first.' >&2; exit 2; }
gh auth status >/dev/null
VISIBILITY="$(gh repo view "$REPOSITORY" --json visibility --jq .visibility)"
[[ "$VISIBILITY" == "PUBLIC" ]] || { echo 'Expected the public site repository; review settings.' >&2; exit 2; }
if gh api "repos/$REPOSITORY/pages" >/dev/null 2>&1; then
  gh api --method PUT "repos/$REPOSITORY/pages" -f build_type=workflow >/dev/null
else
  gh api --method POST "repos/$REPOSITORY/pages" -f build_type=workflow >/dev/null
fi
gh workflow run daily-refresh.yml --repo "$REPOSITORY" --ref main
echo 'Workflow requested. Check Actions for refresh success and the Pages deployment URL.'
