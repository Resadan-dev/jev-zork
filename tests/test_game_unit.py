"""La logique de ``ZorkGame`` sans Jericho : un faux environnement suffit."""

import sys

import pytest

from jev_zork.game import FALLBACK_ACTIONS, MAX_OPTIONS, ZorkGame, jericho_env


class Thing:
    def __init__(self, num, name):
        self.num = num
        self.name = name


class FakeEnv:
    _seed = 12

    def __init__(self, look="West of House\nAn open field.", valid=("north", "north", "south")):
        self.look = look
        self.valid = list(valid)
        self.location = Thing(180, "West House")
        self.restored = []
        self.played = []
        self.closed = False

    def reset(self):
        return "Revision 88 / Serial number 840726\r\n\r\nWest of House\r\n", {"moves": 0, "score": 0}

    def get_player_location(self):
        return self.location

    def get_state(self):
        return ("saved", len(self.played))

    def set_state(self, state):
        self.restored.append(state)

    def step(self, command):
        self.played.append(command)
        if command == "look":
            return self.look, 0, False, {"moves": 0, "score": 0}
        return "Taken.\n\n", 5, False, {"moves": 1, "score": 5}

    def get_valid_actions(self):
        return list(self.valid)

    def get_inventory(self):
        return [Thing(7, "leaflet")]

    def get_score(self):
        return 0

    def get_max_score(self):
        return 350

    def get_moves(self):
        return 0

    def get_world_state_hash(self):
        return "h-west"

    def victory(self):
        return False

    def close(self):
        self.closed = True


def make_game(tmp_path, env):
    rom = tmp_path / "zork1.z5"
    rom.write_bytes(b"\0")
    return ZorkGame(rom, env_factory=lambda path, seed: env)


def test_a_snapshot_reads_the_room_title_and_restores_the_state(tmp_path):
    env = FakeEnv()
    scene = make_game(tmp_path, env).snapshot()
    assert scene.location == "West of House"
    assert scene.description == "An open field."
    assert env.played == ["look"]
    assert env.restored == [("saved", 0)]
    assert scene.valid_actions == ("north", "south")
    assert scene.inventory == ("leaflet",)
    assert not scene.fallback


def test_in_the_dark_the_last_known_title_is_kept(tmp_path):
    env = FakeEnv()
    game = make_game(tmp_path, env)
    game.snapshot()
    env.look = "It is pitch black. You are likely to be eaten by a grue."
    scene = game.snapshot()
    assert scene.dark
    assert scene.location == "West of House"
    assert "grue" in scene.description


def test_an_unknown_dark_place_falls_back_to_the_object_name(tmp_path):
    env = FakeEnv(look="It is pitch black.")
    assert make_game(tmp_path, env).snapshot().location == "West House"


def test_no_valid_action_falls_back_to_basic_commands(tmp_path):
    scene = make_game(tmp_path, FakeEnv(valid=())).snapshot()
    assert scene.valid_actions == FALLBACK_ACTIONS
    assert scene.fallback


def test_options_are_capped_at_the_choice_limit(tmp_path):
    many = [f"take thing {index}" for index in range(300)]
    scene = make_game(tmp_path, FakeEnv(valid=many)).snapshot()
    assert len(scene.valid_actions) == MAX_OPTIONS


def test_reset_step_and_close_go_through_the_environment(tmp_path):
    env = FakeEnv()
    game = make_game(tmp_path, env)
    assert game.reset() == "Revision 88 / Serial number 840726\n\nWest of House"
    result = game.step("take leaflet")
    assert (result.response, result.reward, result.score, result.moves) == ("Taken.", 5, 5, 1)
    assert not result.done and not result.victory
    assert game.seed == 12 and game.max_score == 350
    game.close()
    assert env.closed


def test_a_missing_rom_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="ROM introuvable"):
        ZorkGame(tmp_path / "absente.z5", env_factory=lambda path, seed: FakeEnv())


def test_without_jericho_the_error_says_to_use_wsl(monkeypatch):
    monkeypatch.setitem(sys.modules, "jericho", None)
    with pytest.raises(RuntimeError, match="WSL"):
        jericho_env("zork1.z5", None)
