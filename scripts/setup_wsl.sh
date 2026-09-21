#!/usr/bin/env bash
# Sets up everything needed to make Jev play Zork, in WSL (Ubuntu), on Linux or on macOS.
# No sudo: uv installs into ~/.local/bin and brings its own Python 3.12.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${JEV_ZORK_VENV:-$HOME/.venvs/jev-zork}"
ROM="$ROOT/roms/zork1.z5"
ROM_URL="https://raw.githubusercontent.com/BYU-PCCL/z-machine-games/master/jericho-game-suite/zork1.z5"
# The hash Jericho recognizes: without it, no valid actions.
ROM_MD5="b732a93a6244ddd92a9b9a3e3a46c687"

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
md5_of() { if command -v md5sum >/dev/null; then md5sum "$1" | cut -d' ' -f1; else md5 -q "$1"; fi; }

for tool in gcc make curl; do
  command -v "$tool" >/dev/null || fail "$tool is missing (Jericho is compiled). On Ubuntu: sudo apt install build-essential curl"
done

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  say "Installing uv into ~/.local/bin (no sudo)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

say "Python environment in $VENV: Jericho, TypeSafe SDK, spaCy"
cd "$ROOT"
UV_PROJECT_ENVIRONMENT="$VENV" uv sync --python 3.12

if [[ -f "$ROM" && "$(md5_of "$ROM")" == "$ROM_MD5" ]]; then
  say "Zork I ROM already in place"
else
  say "Downloading Zork I from Jericho's game suite"
  mkdir -p "$ROOT/roms"
  curl -fsSL "$ROM_URL" -o "$ROM.part"
  if [[ "$(md5_of "$ROM.part")" != "$ROM_MD5" ]]; then
    rm -f "$ROM.part"
    fail "unexpected MD5 for zork1.z5: file rejected"
  fi
  mv "$ROM.part" "$ROM"
fi

say "Checking: the tests, including real Zork moves under Jericho"
"$VENV/bin/python" -m pytest -q -p no:cacheprovider

cat <<EOF

Ready. To play:
  scripts/play.sh --mock --steps 20          no key: random draw, this is NOT Jev
  scripts/play.sh --delay 0.6 --steps 150    with TYPESAFE_API_KEY in .env
EOF
