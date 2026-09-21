"""Ce que Jev voit (le state) et ce qu'on lui demande (les questions).

Jev lit mieux l'anglais que le reste (docs.typesafe.ai/models) : le state et les
questions sont en anglais, l'affichage en français. La doc prévient aussi qu'un
state chargé de détails inutiles coûte de la précision : on n'envoie que le lieu,
ce qu'on y voit, la dernière réponse du jeu, l'inventaire, le score et les
derniers tours.
"""

from __future__ import annotations

import copy
from typing import Mapping, Optional, Protocol, Sequence

from jev_zork.memory import Memory
from jev_zork.text import truncate

ACTION = "action"
DANGER = "danger"
INTENT = "intent"

SURROUNDINGS_LIMIT = 700
LAST_RESPONSE_LIMIT = 700

GAME_BRIEF = (
    "Zork I, the classic text adventure. The player explores the Great Underground "
    "Empire, collects treasures and brings them back to the trophy case in the white "
    "house. Dying costs points, and a grue eats players who wander in the dark."
)

ACTION_INSTRUCTIONS = {
    "question": "Which command should the player type next to make progress in the game?",
    "advice": [
        "Go to places not visited yet.",
        "Take objects that look useful or valuable.",
        "Open, read or examine things that look important.",
        "Do not repeat a command that already failed in the same situation.",
        "Do not walk into darkness without a light source.",
    ],
}

DANGER_QUESTION = {
    "type": "noul",
    "instructions": "Is the player in immediate danger of dying?",
    "criteria": {
        "true": (
            "A hostile creature is attacking or about to attack, or the player "
            "is in the dark where a grue can strike."
        ),
        "false": "Nothing threatens the player right now.",
    },
}

# Les intentions du joueur, tour par tour : la matière du streamgraph du replay.
INTENTS = {
    "explore": "Go somewhere new",
    "collect": "Pick up useful items or treasures that are here",
    "investigate": "Examine, open, read or search something here",
    "puzzle": "Use an item to get past an obstacle",
    "fight": "Deal with a hostile creature",
    "escape": "Get out of darkness or danger",
}

INTENT_QUESTION = {
    "type": "choice",
    "instructions": "What should the player focus on right now?",
    "criteria": INTENTS,
}


class Scene(Protocol):
    """Ce que le state lit d'un instantané de partie (voir ``game.Snapshot``)."""

    @property
    def location_id(self) -> int: ...

    @property
    def location(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def dark(self) -> bool: ...

    @property
    def inventory(self) -> Sequence[str]: ...

    @property
    def score(self) -> int: ...

    @property
    def max_score(self) -> int: ...


def build_state(
    scene: Scene,
    memory: Memory,
    last_command: Optional[str],
    last_response: Optional[str],
) -> dict[str, object]:
    """Le state envoyé à Jev. Dans le noir, il ne sait pas où il est : le jeu ne le dit pas."""
    state: dict[str, object] = {
        "game": GAME_BRIEF,
        "location": "somewhere dark" if scene.dark else scene.location,
    }
    if scene.description:
        state["surroundings"] = truncate(scene.description, SURROUNDINGS_LIMIT)
    if last_command:
        state["last_command"] = last_command
    if last_response:
        state["last_response"] = truncate(last_response, LAST_RESPONSE_LIMIT)
    state["inventory"] = list(scene.inventory)
    state["score"] = f"{scene.score} of {scene.max_score} points"
    state["times_here"] = memory.visit_count(scene.location_id)
    history = memory.history_state()
    if history:
        state["recent_turns"] = history
    return state


def build_questions(actions: Sequence[str], notes: Mapping[str, str]) -> dict[str, dict]:
    """Un Choice sur les actions valides, un Noul « danger », un Choice « intention »."""
    if not actions:
        raise ValueError("aucune action valide à proposer à Jev")
    return {
        ACTION: {
            "type": "choice",
            "instructions": copy.deepcopy(ACTION_INSTRUCTIONS),
            "criteria": {action: notes.get(action) for action in actions},
        },
        DANGER: copy.deepcopy(DANGER_QUESTION),
        INTENT: copy.deepcopy(INTENT_QUESTION),
    }
