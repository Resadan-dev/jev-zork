"""Mise en forme du texte renvoyé par Zork. Fonctions pures, sans Jericho."""

from __future__ import annotations

import re

_BLANK_RUNS = re.compile(r"\n{3,}")
_TITLE_MAX_LENGTH = 48
_DARKNESS_MARKERS = ("pitch black", "too dark to see")
_ELLIPSIS = "…"


def clean(text: str) -> str:
    """Normalise le texte du jeu : fins de ligne, espaces de fin, lignes vides en série."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in unified.split("\n")]
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()


def strip_intro(text: str) -> str:
    """Retire l'en-tête de copyright d'Infocom du premier écran, s'il est présent."""
    cleaned = clean(text)
    marker = cleaned.find("Serial number")
    if marker == -1:
        return cleaned
    end_of_line = cleaned.find("\n", marker)
    return "" if end_of_line == -1 else cleaned[end_of_line:].strip()


def is_dark(text: str) -> bool:
    """Vrai si le jeu dit au joueur qu'il est dans le noir."""
    lowered = text.lower()
    return any(marker in lowered for marker in _DARKNESS_MARKERS)


def split_room(look_text: str) -> tuple[str | None, str]:
    """Sépare le nom d'un lieu de sa description, dans la réponse à ``look``.

    Zork écrit le nom du lieu seul sur la première ligne. On ne le retient que
    s'il est court et sans ponctuation finale, pour ne pas prendre une phrase
    (« It is pitch black. ») pour un nom de lieu.
    """
    cleaned = clean(look_text)
    if not cleaned:
        return None, ""
    first, _, rest = cleaned.partition("\n")
    title = first.strip()
    looks_like_sentence = title.endswith((".", "!", "?", ":"))
    if len(title) > _TITLE_MAX_LENGTH or looks_like_sentence or is_dark(title):
        return None, cleaned
    return title, rest.strip()


def truncate(text: str, limit: int) -> str:
    """Aplatit les espaces et coupe à ``limit`` caractères au plus, sur une frontière de mot."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[: max(limit - 1, 0)]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:") + _ELLIPSIS
