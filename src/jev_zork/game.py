"""Zork I sous Jericho. Seul module qui importe Jericho (Linux, macOS ou WSL)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from jev_zork.text import clean, is_dark, split_room

MAX_OPTIONS = 255  # plafond d'options d'un Choice TypeSafe (docs.typesafe.ai/api)
FALLBACK_ACTIONS = ("look", "inventory", "north", "south", "east", "west", "up", "down")


@dataclass(frozen=True)
class Snapshot:
    """L'état de la partie au moment où Jev doit choisir."""

    location_id: int
    location: str
    description: str
    dark: bool
    inventory: tuple[str, ...]
    score: int
    max_score: int
    moves: int
    world_hash: str
    valid_actions: tuple[str, ...]
    fallback: bool = False


@dataclass(frozen=True)
class StepResult:
    response: str
    reward: int
    score: int
    moves: int
    done: bool
    victory: bool


EnvFactory = Callable[[str, Optional[int]], Any]


def jericho_env(rom: str, seed: Optional[int]) -> Any:
    try:
        from jericho import FrotzEnv
    except ImportError as error:
        raise RuntimeError(
            "Jericho n'est pas installé. Il ne tourne que sous Linux ou macOS : "
            "sous Windows, lancez scripts/setup_wsl.sh dans WSL."
        ) from error
    return FrotzEnv(rom, seed=seed)


def _unique(actions: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(action for action in actions if action))


class ZorkGame:
    """Une partie de Zork I. Jericho est à état : cette classe est la frontière avec lui."""

    def __init__(
        self, rom_path: Path, seed: Optional[int] = None, env_factory: EnvFactory = jericho_env
    ) -> None:
        if not rom_path.is_file():
            raise FileNotFoundError(f"ROM introuvable : {rom_path} (lancez scripts/setup_wsl.sh)")
        self._env = env_factory(str(rom_path), seed)
        self._titles: dict[int, str] = {}

    @property
    def seed(self) -> Optional[int]:
        """La graine réellement utilisée : sans graine, Jericho prend celle du walkthrough (12)."""
        return getattr(self._env, "_seed", None)

    @property
    def max_score(self) -> int:
        return int(self._env.get_max_score())

    def reset(self) -> str:
        observation, _info = self._env.reset()
        return clean(observation)

    def snapshot(self) -> Snapshot:
        env = self._env
        location = env.get_player_location()
        location_id = location.num if location is not None else -1
        look = self._probe("look")
        title, description = split_room(look)
        if title:
            self._titles[location_id] = title
        fallback_name = location.name if location is not None else "?"
        actions = _unique(env.get_valid_actions())
        return Snapshot(
            location_id=location_id,
            location=self._titles.get(location_id, fallback_name),
            description=description,
            dark=is_dark(look),
            inventory=tuple(item.name for item in env.get_inventory()),
            score=int(env.get_score()),
            max_score=self.max_score,
            moves=int(env.get_moves()),
            world_hash=env.get_world_state_hash(),
            valid_actions=actions[:MAX_OPTIONS] or FALLBACK_ACTIONS,
            fallback=not actions,
        )

    def step(self, action: str) -> StepResult:
        response, reward, done, info = self._env.step(action)
        return StepResult(
            response=clean(response),
            reward=int(reward),
            score=int(info["score"]),
            moves=int(info["moves"]),
            done=bool(done),
            victory=bool(self._env.victory()),
        )

    def close(self) -> None:
        self._env.close()

    def _probe(self, command: str) -> str:
        """Joue ``command`` puis restaure l'état : aucun effet sur la partie, hasard compris."""
        saved = self._env.get_state()
        try:
            text, *_ = self._env.step(command)
        finally:
            self._env.set_state(saved)
        return clean(text)
