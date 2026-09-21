from dataclasses import dataclass

import pytest

from jev_zork.memory import RESPONSE_LIMIT, Memory, TurnRecord


@dataclass(frozen=True)
class Spot:
    location_id: int
    location: str
    world_hash: str


WEST = Spot(180, "West of House", "h-west")
NORTH = Spot(81, "North of House", "h-north")


def test_start_counts_the_first_visit_and_names_the_place():
    memory = Memory.start(WEST)
    assert memory.visit_count(180) == 1
    assert memory.names[180] == "West of House"


def test_after_turn_returns_a_new_memory_and_leaves_the_old_one_untouched():
    start = Memory.start(WEST)
    opened = Spot(180, "West of House", "h-west-open")
    after = start.after_turn(
        turn=1,
        before=WEST,
        command="open mailbox",
        response="Opening the small mailbox reveals a leaflet.",
        after=opened,
    )
    assert start.tried == {}
    assert start.history == ()
    assert after.tries(WEST, ["open mailbox", "north"]) == {"open mailbox": 1, "north": 0}
    assert after.history == (
        TurnRecord(1, "West of House", "open mailbox", "Opening the small mailbox reveals a leaflet."),
    )
    assert after.visit_count(180) == 1


def test_moving_records_the_exit_and_the_visit():
    memory = Memory.start(WEST).after_turn(
        turn=1, before=WEST, command="north", response="North of House", after=NORTH
    )
    assert memory.exits[(180, "north")] == 81
    assert memory.visit_count(81) == 1


def test_annotations_describe_known_exits_first():
    memory = (
        Memory.start(WEST)
        .after_turn(turn=1, before=WEST, command="north", response="North of House", after=NORTH)
        .after_turn(turn=2, before=NORTH, command="west", response="West of House", after=WEST)
    )
    notes = memory.annotations(WEST, ["north", "south", "open mailbox"])
    assert notes == {"north": "leads to North of House (visited once)"}
    assert memory.visit_count(180) == 2


def test_annotations_mention_actions_repeated_in_the_same_world_state():
    holding = Spot(180, "West of House", "h-holding")
    memory = (
        Memory.start(WEST)
        .after_turn(turn=1, before=WEST, command="take leaflet", response="Taken.", after=holding)
        .after_turn(turn=2, before=holding, command="drop leaflet", response="Dropped.", after=WEST)
    )
    assert memory.annotations(WEST, ["take leaflet"]) == {
        "take leaflet": "already tried once in this exact situation"
    }


def test_annotations_count_several_tries():
    memory = Memory.start(WEST)
    for turn in (1, 2):
        memory = memory.after_turn(turn=turn, before=WEST, command="wait", response="Time passes.", after=WEST)
    assert memory.annotations(WEST, ["wait"]) == {"wait": "already tried 2 times in this exact situation"}


def test_a_death_is_not_recorded_as_an_exit():
    dark = Spot(20, "Cellar", "h-dark")
    forest = Spot(10, "Forest", "h-forest")
    death = "Oh, no! You have walked into the slavering fangs of a lurking grue!\n\n****  You have died  ****"
    memory = Memory.start(dark).after_turn(turn=1, before=dark, command="north", response=death, after=forest)
    assert (20, "north") not in memory.exits
    assert memory.visit_count(10) == 1


def test_the_name_of_a_place_is_refreshed_when_it_changes():
    unlit = Spot(20, "Cellar", "h-dark")
    lit = Spot(20, "Cellar (lit)", "h-lit")
    memory = Memory.start(unlit).after_turn(
        turn=1, before=unlit, command="turn on lamp", response="The lamp is now on.", after=lit
    )
    assert memory.names[20] == "Cellar (lit)"
    assert memory.visit_count(20) == 1


def test_history_keeps_the_last_turns_with_truncated_responses():
    memory = Memory.start(WEST, history_size=2)
    for turn in range(1, 5):
        memory = memory.after_turn(turn=turn, before=WEST, command=f"c{turn}", response="x " * 200, after=WEST)
    assert [record.turn for record in memory.history] == [3, 4]
    assert all(len(entry["response"]) <= RESPONSE_LIMIT for entry in memory.history_state())


def test_a_zero_history_keeps_nothing():
    memory = Memory.start(WEST, history_size=0).after_turn(
        turn=1, before=WEST, command="look", response="West of House", after=WEST
    )
    assert memory.history == ()


def test_a_negative_history_is_rejected():
    with pytest.raises(ValueError):
        Memory(history_size=-1)


def test_the_last_turn_of_a_game_keeps_the_try_without_arrival():
    memory = Memory.start(WEST).after_turn(turn=1, before=WEST, command="north", response="...", after=None)
    assert memory.tries(WEST, ["north"]) == {"north": 1}
    assert memory.exits == {}
