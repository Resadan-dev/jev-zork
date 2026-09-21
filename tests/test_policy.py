import pytest

from jev_zork.policy import adjust, choice_confidence, decide, normalize


def test_adjust_halves_the_probability_for_each_previous_try():
    adjusted = adjust({"north": 0.5, "south": 0.5}, {"north": 1}, floor=0.0)
    assert adjusted == pytest.approx({"north": 1 / 3, "south": 2 / 3})


def test_adjust_compounds_the_penalty_over_repeated_tries():
    adjusted = adjust({"north": 0.8, "south": 0.2}, {"north": 2}, floor=0.0)
    assert adjusted == pytest.approx({"north": 0.5, "south": 0.5})


def test_the_floor_lets_the_penalty_beat_a_certain_answer():
    adjusted = adjust({"open mailbox": 1.0, "north": 0.0}, {"open mailbox": 7}, floor=0.01)
    assert adjusted["north"] > 0.5


def test_untried_actions_keep_jev_ranking():
    raw = {"a": 0.6, "b": 0.3, "c": 0.1}
    assert adjust(raw, {}) == pytest.approx(raw)


def test_decide_follows_jev_when_nothing_was_tried():
    decision = decide({"open mailbox": 0.61, "north": 0.39}, "open mailbox", {})
    assert decision.action == "open mailbox"
    assert not decision.overridden
    assert decision.tries == {}


def test_decide_overrides_jev_when_its_choice_loops():
    decision = decide({"north": 0.6, "south": 0.4}, "north", {"north": 1, "south": 0})
    assert decision.action == "south"
    assert decision.overridden
    assert decision.tries == {"north": 1}


def test_decide_keeps_jev_choice_on_a_tie():
    decision = decide({"north": 0.8, "south": 0.2}, "north", {"north": 2}, floor=0.0)
    assert decision.action == "north"


def test_decide_breaks_other_ties_in_option_order():
    decision = decide({"a": 0.3, "b": 0.3, "c": 0.4}, "c", {"c": 1})
    assert decision.action == "a"


@pytest.mark.parametrize("penalty", [0.0, -0.5, 1.5])
def test_adjust_rejects_an_invalid_penalty(penalty):
    with pytest.raises(ValueError):
        adjust({"a": 1.0}, {}, penalty=penalty)


def test_adjust_rejects_a_negative_floor():
    with pytest.raises(ValueError):
        adjust({"a": 1.0}, {}, floor=-0.1)


def test_normalize_rejects_a_zero_total():
    with pytest.raises(ValueError):
        normalize({"a": 0.0})


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        ({"a": 1.0, "b": 0.0, "c": 0.0}, 1.0),
        ({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}, 0.0),
        ({"a": 0.9, "b": 0.06, "c": 0.04}, 0.85),
        ({"only": 1.0}, 1.0),
    ],
)
def test_choice_confidence_matches_the_typesafe_approximation(probabilities, expected):
    assert choice_confidence(probabilities) == pytest.approx(expected)


def test_choice_confidence_needs_options():
    with pytest.raises(ValueError):
        choice_confidence({})
