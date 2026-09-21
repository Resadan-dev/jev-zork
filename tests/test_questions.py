import json
from dataclasses import dataclass

import pytest

from jev_zork.memory import Memory
from jev_zork.questions import ACTION, DANGER, INTENT, INTENTS, build_questions, build_state


@dataclass(frozen=True)
class Scene:
    location_id: int = 180
    location: str = "West of House"
    world_hash: str = "h-west"
    description: str = "You are standing in an open field west of a white house."
    dark: bool = False
    inventory: tuple[str, ...] = ()
    score: int = 0
    max_score: int = 350


def test_the_first_state_has_no_history_and_no_last_command():
    scene = Scene()
    state = build_state(scene, Memory.start(scene), None, "West of House\nThere is a small mailbox here.")
    assert state["location"] == "West of House"
    assert state["surroundings"].startswith("You are standing")
    assert state["last_response"] == "West of House There is a small mailbox here."
    assert state["inventory"] == []
    assert state["score"] == "0 of 350 points"
    assert state["times_here"] == 1
    assert "last_command" not in state
    assert "recent_turns" not in state


def test_a_later_state_carries_the_last_command_and_recent_turns():
    scene = Scene(inventory=("leaflet",))
    memory = Memory.start(scene).after_turn(
        turn=1, before=scene, command="take leaflet", response="Taken.", after=scene
    )
    state = build_state(scene, memory, "take leaflet", "Taken.")
    assert state["last_command"] == "take leaflet"
    assert state["inventory"] == ["leaflet"]
    assert state["recent_turns"] == [
        {"turn": 1, "location": "West of House", "command": "take leaflet", "response": "Taken."}
    ]


def test_in_the_dark_jev_is_not_told_where_it_is():
    scene = Scene(dark=True, description="It is pitch black. You are likely to be eaten by a grue.")
    state = build_state(scene, Memory.start(scene), "down", "You have moved into a dark place.")
    assert state["location"] == "somewhere dark"
    assert "grue" in state["surroundings"]


def test_the_state_is_json_serializable():
    scene = Scene()
    json.dumps(build_state(scene, Memory.start(scene), None, None))


def test_build_questions_offers_every_valid_action_with_its_note():
    questions = build_questions(
        ["open mailbox", "north", "south"], {"north": "leads to North of House (visited once)"}
    )
    action = questions[ACTION]
    assert action["type"] == "choice"
    assert list(action["criteria"]) == ["open mailbox", "north", "south"]
    assert action["criteria"]["north"] == "leads to North of House (visited once)"
    assert action["criteria"]["open mailbox"] is None
    assert questions[DANGER]["type"] == "noul"
    assert questions[INTENT]["criteria"] == INTENTS


def test_build_questions_returns_copies_that_callers_can_change_safely():
    first = build_questions(["north"], {})
    first[INTENT]["criteria"]["explore"] = "changed"
    first[ACTION]["instructions"]["advice"].append("changed")
    second = build_questions(["north"], {})
    assert second[INTENT]["criteria"]["explore"] == "Go somewhere new"
    assert "changed" not in second[ACTION]["instructions"]["advice"]


def test_build_questions_needs_at_least_one_action():
    with pytest.raises(ValueError):
        build_questions([], {})
