#!/usr/bin/env bash
# Lance une partie : scripts/play.sh [options de jev-zork]. Voir jev-zork --help.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${JEV_ZORK_VENV:-$HOME/.venvs/jev-zork}"

if [[ ! -x "$VENV/bin/jev-zork" ]]; then
  echo "Environnement absent : lancez d'abord scripts/setup_wsl.sh" >&2
  exit 2
fi

# jev-zork lit .env et écrit runs/ dans le dossier courant : la racine du projet.
cd "$ROOT"
exec "$VENV/bin/jev-zork" "$@"
