#!/usr/bin/env bash
# Installe de quoi faire jouer Jev à Zork, dans WSL (Ubuntu), sous Linux ou sous macOS.
# Sans sudo : uv s'installe dans ~/.local/bin et apporte son propre Python 3.12.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${JEV_ZORK_VENV:-$HOME/.venvs/jev-zork}"
ROM="$ROOT/roms/zork1.z5"
ROM_URL="https://raw.githubusercontent.com/BYU-PCCL/z-machine-games/master/jericho-game-suite/zork1.z5"
# L'empreinte que Jericho reconnaît : sans elle, pas d'actions valides.
ROM_MD5="b732a93a6244ddd92a9b9a3e3a46c687"

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mErreur :\033[0m %s\n' "$*" >&2; exit 1; }
md5_of() { if command -v md5sum >/dev/null; then md5sum "$1" | cut -d' ' -f1; else md5 -q "$1"; fi; }

for tool in gcc make curl; do
  command -v "$tool" >/dev/null || fail "$tool manque (Jericho se compile). Sous Ubuntu : sudo apt install build-essential curl"
done

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  say "Installation de uv dans ~/.local/bin (sans sudo)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

say "Environnement Python dans $VENV : Jericho, SDK TypeSafe, spaCy"
cd "$ROOT"
UV_PROJECT_ENVIRONMENT="$VENV" uv sync --python 3.12

if [[ -f "$ROM" && "$(md5_of "$ROM")" == "$ROM_MD5" ]]; then
  say "ROM de Zork I déjà en place"
else
  say "Téléchargement de Zork I depuis la suite de jeux de Jericho"
  mkdir -p "$ROOT/roms"
  curl -fsSL "$ROM_URL" -o "$ROM.part"
  if [[ "$(md5_of "$ROM.part")" != "$ROM_MD5" ]]; then
    rm -f "$ROM.part"
    fail "empreinte MD5 inattendue pour zork1.z5 : fichier refusé"
  fi
  mv "$ROM.part" "$ROM"
fi

say "Vérification : les tests, dont de vrais coups de Zork sous Jericho"
"$VENV/bin/python" -m pytest -q -p no:cacheprovider

cat <<EOF

Prêt. Pour jouer :
  scripts/play.sh --mock --steps 20          sans clé : tirage au hasard, ce n'est PAS Jev
  scripts/play.sh --delay 0.6 --steps 150    avec TYPESAFE_API_KEY dans .env
EOF
