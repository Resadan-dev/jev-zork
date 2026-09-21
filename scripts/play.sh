#!/usr/bin/env bash
# Starts a game: scripts/play.sh [jev-zork options]. See jev-zork --help.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${JEV_ZORK_VENV:-$HOME/.venvs/jev-zork}"

if [[ ! -x "$VENV/bin/jev-zork" ]]; then
  echo "Environment missing: run scripts/setup_wsl.sh first" >&2
  exit 2
fi

# jev-zork reads .env and writes runs/ in the current directory: the project root.
cd "$ROOT"
exec "$VENV/bin/jev-zork" "$@"
