"""Zork I pour de vrai, sous Jericho. Ces tests sautent si Jericho ou la ROM manquent."""

import pytest

from jev_zork.game import ZorkGame

pytestmark = pytest.mark.jericho


@pytest.fixture
def game(rom_path):
    zork = ZorkGame(rom_path)
    zork.reset()
    yield zork
    zork.close()


def test_the_game_starts_west_of_the_house_with_the_walkthrough_seed(rom_path):
    zork = ZorkGame(rom_path)
    try:
        intro = zork.reset()
    finally:
        zork.close()
    assert "West of House" in intro
    assert zork.seed == 12


def test_the_first_snapshot_offers_the_mailbox_and_three_exits(game):
    scene = game.snapshot()
    assert scene.location == "West of House"
    assert set(scene.valid_actions) == {"open mailbox", "north", "south", "west"}
    assert "mailbox" in scene.description
    assert (scene.score, scene.max_score, scene.moves) == (0, 350, 0)
    assert scene.inventory == ()
    assert not scene.dark
    assert not scene.fallback


def test_a_snapshot_does_not_play_a_move(game):
    before = game.snapshot()
    after = game.snapshot()
    assert after.moves == before.moves == 0
    assert after.world_hash == before.world_hash


def test_step_returns_the_response_of_the_game(game):
    result = game.step("open mailbox")
    assert "leaflet" in result.response
    assert result.moves == 1
    assert not result.done


def test_taking_the_egg_scores_five_points(game):
    for command in ("north", "north", "up"):
        game.step(command)
    result = game.step("take egg")
    assert (result.reward, result.score) == (5, 5)


def test_the_cellar_is_dark_and_jev_would_hear_about_the_grue(game):
    for command in ("north", "east", "open window", "west", "west", "move rug", "open trap door", "down"):
        game.step(command)
    scene = game.snapshot()
    assert scene.dark
    assert "grue" in scene.description
