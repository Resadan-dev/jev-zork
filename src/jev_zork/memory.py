"""Mémoire de la partie, tenue par le code : Jev ne retient rien d'un coup à l'autre.

Tout ce qui ressemble à un souvenir vit ici : les derniers tours, les sorties
déjà empruntées, les lieux visités, les actions déjà tentées dans le même état
du monde. Ces souvenirs repartent vers Jev dans le state et dans la description
des options, et nourrissent l'anti-boucle (``policy.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Protocol

from jev_zork.text import truncate

RESPONSE_LIMIT = 220
_DEATH_MARKER = "you have died"


class Place(Protocol):
    """Ce que la mémoire lit d'un instantané de partie."""

    @property
    def location_id(self) -> int: ...

    @property
    def location(self) -> str: ...

    @property
    def world_hash(self) -> str: ...


@dataclass(frozen=True)
class TurnRecord:
    turn: int
    location: str
    command: str
    response: str

    def as_state(self) -> dict[str, object]:
        return {
            "turn": self.turn,
            "location": self.location,
            "command": self.command,
            "response": truncate(self.response, RESPONSE_LIMIT),
        }


def _frozen(mapping: Mapping) -> Mapping:
    return MappingProxyType(dict(mapping))


def _empty() -> Mapping:
    return MappingProxyType({})


def _times(count: int) -> str:
    return "once" if count == 1 else f"{count} times"


@dataclass(frozen=True)
class Memory:
    """Souvenirs immuables : chaque tour produit une nouvelle ``Memory``."""

    history_size: int = 8
    history: tuple[TurnRecord, ...] = ()
    tried: Mapping[tuple[str, str], int] = field(default_factory=_empty)
    exits: Mapping[tuple[int, str], int] = field(default_factory=_empty)
    visits: Mapping[int, int] = field(default_factory=_empty)
    names: Mapping[int, str] = field(default_factory=_empty)

    def __post_init__(self) -> None:
        if self.history_size < 0:
            raise ValueError("history_size doit être positif ou nul")

    @classmethod
    def start(cls, place: Place, history_size: int = 8) -> "Memory":
        return cls(history_size=history_size).arrive(place)

    def arrive(self, place: Place) -> "Memory":
        visits = {**self.visits, place.location_id: self.visits.get(place.location_id, 0) + 1}
        names = {**self.names, place.location_id: place.location}
        return replace(self, visits=_frozen(visits), names=_frozen(names))

    def after_turn(
        self,
        *,
        turn: int,
        before: Place,
        command: str,
        response: str,
        after: Optional[Place],
    ) -> "Memory":
        """Retient le tour joué. ``after`` vaut None quand la partie est finie."""
        key = (before.world_hash, command)
        tried = {**self.tried, key: self.tried.get(key, 0) + 1}
        record = TurnRecord(turn, before.location, command, response)
        history = (self.history + (record,))[-self.history_size :] if self.history_size else ()
        updated = replace(self, tried=_frozen(tried), history=history)
        if after is None:
            return updated
        updated = replace(updated, names=_frozen({**updated.names, after.location_id: after.location}))
        if after.location_id == before.location_id:
            return updated
        # Une mort ramène le joueur ailleurs : ce n'est pas une sortie de la pièce.
        if _DEATH_MARKER not in response.lower():
            exits = {**updated.exits, (before.location_id, command): after.location_id}
            updated = replace(updated, exits=_frozen(exits))
        return updated.arrive(after)

    def tries(self, place: Place, actions: Iterable[str]) -> dict[str, int]:
        """Nombre d'essais de chaque action dans l'état du monde de ``place``."""
        return {action: self.tried.get((place.world_hash, action), 0) for action in actions}

    def visit_count(self, location_id: int) -> int:
        return self.visits.get(location_id, 0)

    def history_state(self) -> list[dict[str, object]]:
        return [record.as_state() for record in self.history]

    def annotations(self, place: Place, actions: Iterable[str]) -> dict[str, str]:
        """Ce que la mémoire sait de chaque action, en anglais, pour la description des options.

        La doc de Jev déconseille l'indirection : plutôt que de lister les sorties
        connues dans le state et de laisser Jev faire le rapprochement, on écrit
        directement sur l'option où elle mène.
        """
        notes: dict[str, str] = {}
        for action in actions:
            destination = self.exits.get((place.location_id, action))
            if destination is not None:
                name = self.names.get(destination, "a known place")
                notes[action] = f"leads to {name} (visited {_times(self.visit_count(destination))})"
                continue
            count = self.tried.get((place.world_hash, action), 0)
            if count:
                notes[action] = f"already tried {_times(count)} in this exact situation"
        return notes
