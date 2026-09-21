"""La boucle de jeu contre un Zork miniature : deux pièces, une lampe, de quoi tourner en rond."""

import pytest

from jev_zork.game import Snapshot, StepResult
from jev_zork.judges import Judgement, JudgeError
from jev_zork.runner import (
    BUDGET,
    ERROR,
    GAME_OVER,
    INTERRUPTED,
    STEPS,
    VICTORY,
    Settings,
    cost_of,
    play,
)

ROOMS = {1: "West of House", 2: "North of House"}


class MiniZork:
    def __init__(self, ending=None):
        self.room = 1
        self.lamp = False
        self.moves = 0
        self.score = 0
        self.ending = ending

    def reset(self):
        return "Revision 88 / Serial number 840726\n\nWest of House\nThere is a small mailbox here."

    def snapshot(self):
        actions = ["north"] if self.room == 1 else ["south"]
        if self.room == 1 and not self.lamp:
            actions.append("take lamp")
        return Snapshot(
            location_id=self.room,
            location=ROOMS[self.room],
            description="An open field.",
            dark=False,
            inventory=("lamp",) if self.lamp else (),
            score=self.score,
            max_score=350,
            moves=self.moves,
            world_hash=f"{self.room}-{self.lamp}",
            valid_actions=tuple(actions),
        )

    def step(self, action):
        self.moves += 1
        if self.ending and action == self.ending[0]:
            return StepResult("The End.", 0, self.score, self.moves, True, self.ending[1])
        if action == "take lamp":
            self.lamp = True
            self.score += 5
            return StepResult("Taken.", 5, self.score, self.moves, False, False)
        self.room = 2 if action == "north" else 1
        return StepResult(ROOMS[self.room], 0, self.score, self.moves, False, False)


class Walker:
    """Juge qui adore marcher : 0,7 pour les déplacements, le reste se partage 0,3."""

    kind = "test"
    errors = (JudgeError,)

    def __init__(self, tokens=100, fail_at=None, interrupt_at=None):
        self.tokens = tokens
        self.fail_at = fail_at
        self.interrupt_at = interrupt_at
        self.calls = []

    def judge(self, state, questions, options):
        self.calls.append((state, questions))
        if len(self.calls) == self.fail_at:
            raise JudgeError("réponse inutilisable")
        if len(self.calls) == self.interrupt_at:
            raise KeyboardInterrupt
        walks = [option for option in options if option in ("north", "south")]
        others = [option for option in options if option not in walks]
        share = 1.0 if not others else 0.7
        probabilities = {option: share / len(walks) for option in walks}
        probabilities.update({option: (1 - share) / len(others) for option in others})
        choice = max(options, key=probabilities.get)
        return Judgement(
            choice=choice,
            probabilities=probabilities,
            confidence=0.4,
            danger=0.1,
            intent={"explore": 1.0},
            latency_ms=5,
            input_tokens=self.tokens,
            output_tokens=10,
            model="test",
        )


def run(game=None, judge=None, sleep=None, **settings):
    records = []
    outcome = play(
        game or MiniZork(),
        judge or Walker(),
        Settings(**settings),
        on_turn=records.append,
        sleep=sleep or (lambda seconds: None),
    )
    return outcome, records


def test_the_anti_loop_breaks_the_walk_back_and_forth():
    judge = Walker()
    outcome, records = run(judge=judge, steps=5)
    assert [record["action"] for record in records] == ["north", "south", "north", "south", "take lamp"]
    assert records[4]["choice"] == "north"
    assert records[4]["overridden"] is True
    assert records[4]["tries"] == {"north": 2}
    fifth_questions = judge.calls[4][1]
    assert fifth_questions["action"]["criteria"]["north"] == "leads to North of House (visited 2 times)"
    assert outcome.reason == STEPS
    assert (outcome.turns, outcome.score, outcome.moves) == (5, 5, 5)


def test_the_first_turn_sees_the_intro_and_later_turns_see_the_last_command():
    judge = Walker()
    _, records = run(judge=judge, steps=2)
    assert records[0]["observation"] == "West of House\nThere is a small mailbox here."
    second_state = judge.calls[1][0]
    assert second_state["last_command"] == "north"
    assert second_state["last_response"] == "North of House"
    assert second_state["recent_turns"][0]["command"] == "north"


def test_a_lost_game_stops_the_loop():
    outcome, records = run(game=MiniZork(ending=("north", False)), steps=10)
    assert outcome.reason == GAME_OVER
    assert len(records) == 1
    assert records[0]["done"] is True


def test_a_won_game_stops_the_loop():
    outcome, _ = run(game=MiniZork(ending=("north", True)), steps=10)
    assert outcome.reason == VICTORY


def test_the_budget_stops_the_loop():
    outcome, records = run(judge=Walker(tokens=10_000_000), steps=10, budget_usd=0.25)
    assert outcome.reason == BUDGET
    assert len(records) == 1
    assert outcome.cost_usd == pytest.approx(0.42)


def test_a_judge_error_ends_the_game_cleanly():
    outcome, records = run(judge=Walker(fail_at=2), steps=10)
    assert outcome.reason == ERROR
    assert outcome.error == "réponse inutilisable"
    assert outcome.turns == 1
    assert len(records) == 1


def test_ctrl_c_ends_the_game_cleanly():
    outcome, records = run(judge=Walker(interrupt_at=3), steps=10)
    assert outcome.reason == INTERRUPTED
    assert outcome.turns == 2
    assert len(records) == 2


def test_the_delay_is_applied_between_turns_only():
    pauses = []
    run(steps=3, delay=0.5, sleep=pauses.append)
    assert pauses == [0.5, 0.5]


def test_tokens_add_up_and_cost_follows_the_published_price():
    outcome, records = run(judge=Walker(tokens=1000), steps=3)
    assert (outcome.input_tokens, outcome.output_tokens) == (3000, 30)
    assert outcome.cost_usd == pytest.approx(3000 * 0.042 / 1_000_000)
    assert records[0]["cost_usd"] == pytest.approx(cost_of(1000))


@pytest.mark.parametrize(
    "settings",
    [
        {"steps": 0},
        {"delay": -1.0},
        {"history": -1},
        {"penalty": 0.0},
        {"penalty": 1.5},
        {"floor": -0.01},
        {"budget_usd": 0.0},
    ],
)
def test_invalid_settings_are_refused(settings):
    with pytest.raises(ValueError):
        Settings(**settings)
