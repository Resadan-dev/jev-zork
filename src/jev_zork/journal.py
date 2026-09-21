"""Journal JSONL d'une partie : une ligne d'en-tête, une ligne par tour, une ligne de fin.

C'est la matière première du lecteur de replay (``replay/index.html``) et de la
vidéo. Le schéma vit ici, en un seul endroit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

FORMAT_VERSION = 1
RUN, TURN, END = "run", "turn", "end"
_DIGITS = 4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def journal_path(log_dir: Path, judge_kind: str, moment: datetime) -> Path:
    """Un nom libre : deux parties lancées dans la même seconde reçoivent -2, -3…"""
    stem = f"{moment.astimezone(timezone.utc):%Y%m%d-%H%M%S}-{judge_kind}"
    path = log_dir / f"{stem}.jsonl"
    rank = 2
    while path.exists():
        path = log_dir / f"{stem}-{rank}.jsonl"
        rank += 1
    return path


def _rounded(values: Mapping[str, float]) -> dict[str, float]:
    return {key: round(value, _DIGITS) for key, value in values.items()}


class Journal:
    """Écrit une ligne JSON par enregistrement et la pousse aussitôt sur le disque.

    Le fichier est créé en mode exclusif : un journal existant n'est jamais écrasé.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = path.open("x", encoding="utf-8", newline="\n")

    def write(self, record: Mapping[str, Any]) -> None:
        if record.get("type") not in (RUN, TURN, END):
            raise ValueError(f"type d'enregistrement inconnu : {record.get('type')!r}")
        self._file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@dataclass(frozen=True)
class JournalContent:
    header: Mapping[str, Any]
    turns: tuple[Mapping[str, Any], ...]
    end: Optional[Mapping[str, Any]]


def read_journal(path: Path) -> JournalContent:
    """Relit un journal et vérifie l'ordre : en-tête, tours, fin (absente si la partie a planté)."""
    header: Optional[Mapping[str, Any]] = None
    turns: list[Mapping[str, Any]] = []
    end: Optional[Mapping[str, Any]] = None
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number} : JSON invalide ({error.msg})") from error
            kind = record.get("type") if isinstance(record, dict) else None
            if end is not None:
                raise ValueError(f"{path}:{number} : enregistrement après la fin de partie")
            if header is None and kind != RUN:
                raise ValueError(f"{path}:{number} : le journal doit commencer par l'en-tête")
            if kind == RUN and header is None:
                header = record
            elif kind == TURN:
                turns.append(record)
            elif kind == END:
                end = record
            else:
                raise ValueError(f"{path}:{number} : enregistrement inattendu ({kind!r})")
    if header is None:
        raise ValueError(f"{path} : journal vide")
    return JournalContent(header=header, turns=tuple(turns), end=end)


def run_record(
    *,
    moment: datetime,
    judge: str,
    model: str,
    rom: str,
    seed: Optional[int],
    max_score: int,
    settings: Mapping[str, Any],
    price_usd_per_mtok: float,
    intents: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "type": RUN,
        "format": FORMAT_VERSION,
        "started_at": timestamp(moment),
        "judge": judge,
        "model": model,
        "game": "Zork I",
        "rom": rom,
        "seed": seed,
        "max_score": max_score,
        "settings": dict(settings),
        "price_usd_per_mtok": price_usd_per_mtok,
        "intents": dict(intents),
    }


class _Scene(Protocol):
    location_id: int
    location: str
    dark: bool
    world_hash: str
    description: str
    inventory: Sequence[str]
    score: int
    moves: int
    valid_actions: Sequence[str]
    fallback: bool


def turn_record(
    *,
    turn: int,
    scene: _Scene,
    observation: str,
    state: Mapping[str, Any],
    notes: Mapping[str, str],
    judgement: Any,
    decision: Any,
    result: Any,
    cost_usd: float,
) -> dict[str, Any]:
    """Un tour complet : ce que Jev a vu, ce qu'il a pensé, ce que le code a joué, ce qu'il en est sorti."""
    return {
        "type": TURN,
        "turn": turn,
        "location": scene.location,
        "location_id": scene.location_id,
        "dark": scene.dark,
        "world_hash": scene.world_hash,
        "observation": observation,
        "description": scene.description,
        "inventory": list(scene.inventory),
        "score": scene.score,
        "moves": scene.moves,
        "valid_actions": list(scene.valid_actions),
        "fallback_actions": scene.fallback,
        "notes": dict(notes),
        "probabilities": _rounded(judgement.probabilities),
        "confidence": round(judgement.confidence, _DIGITS),
        "choice": judgement.choice,
        "tries": dict(decision.tries),
        "adjusted": _rounded(decision.adjusted),
        "action": decision.action,
        "overridden": decision.overridden,
        "danger": None if judgement.danger is None else round(judgement.danger, _DIGITS),
        "intent": _rounded(judgement.intent),
        "response": result.response,
        "reward": result.reward,
        "score_after": result.score,
        "done": result.done,
        "latency_ms": judgement.latency_ms,
        "usage": {"input_tokens": judgement.input_tokens, "output_tokens": judgement.output_tokens},
        "cost_usd": round(cost_usd, 8),
        "model": judgement.model,
        "request_id": judgement.request_id,
        "warnings": list(judgement.warnings),
        "state": dict(state),
    }


def end_record(*, moment: datetime, outcome: Any) -> dict[str, Any]:
    record = {
        "type": END,
        "finished_at": timestamp(moment),
        "reason": outcome.reason,
        "turns": outcome.turns,
        "score": outcome.score,
        "max_score": outcome.max_score,
        "moves": outcome.moves,
        "input_tokens": outcome.input_tokens,
        "output_tokens": outcome.output_tokens,
        "cost_usd": round(outcome.cost_usd, 6),
    }
    if outcome.error:
        record["error"] = outcome.error
    return record
