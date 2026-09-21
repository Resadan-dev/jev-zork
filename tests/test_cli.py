import os

import pytest

from jev_zork.cli import EXIT_CONFIG, EXIT_OK, main
from jev_zork.journal import read_journal


def no_env(tmp_path):
    return ["--env-file", str(tmp_path / "absent.env"), "--log-dir", str(tmp_path)]


@pytest.fixture
def no_key(monkeypatch):
    """Retire TYPESAFE_API_KEY, et la retire encore à la fin si un test la recharge depuis un .env.

    ``delenv(raising=False)`` n'enregistre rien quand la variable est absente : la clé
    chargée par ``main`` resterait alors dans l'environnement des tests suivants.
    """
    monkeypatch.setenv("TYPESAFE_API_KEY", "a-retirer")
    monkeypatch.delenv("TYPESAFE_API_KEY")


@pytest.mark.jericho
def test_a_mock_game_on_the_real_rom_writes_a_complete_journal(tmp_path, rom_path):
    code = main(["--mock", "--steps", "3", "--seed", "3", "--rom", str(rom_path), "--quiet", *no_env(tmp_path)])
    assert code == EXIT_OK
    [path] = tmp_path.glob("*-mock.jsonl")
    content = read_journal(path)
    assert content.header["judge"] == "mock"
    assert content.header["model"] == "mock-random"
    assert content.header["max_score"] == 350
    assert len(content.turns) == 3
    assert set(content.turns[0]["valid_actions"]) == {"open mailbox", "north", "south", "west"}
    assert content.end["reason"] == "steps"


def test_without_a_key_the_cli_explains_what_to_do(tmp_path, no_key, capsys):
    assert main(["--steps", "1", *no_env(tmp_path)]) == EXIT_CONFIG
    assert "--mock" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.jsonl"))


@pytest.mark.parametrize("prefix", [b"", b"\xef\xbb\xbf"], ids=["plain", "bom"])
def test_the_env_file_provides_the_key(tmp_path, no_key, capsys, prefix):
    env_file = tmp_path / ".env"
    env_file.write_bytes(prefix + b"TYPESAFE_API_KEY=cle-de-test\n")
    code = main(["--rom", str(tmp_path / "absente.z5"), "--env-file", str(env_file), "--log-dir", str(tmp_path)])
    assert os.environ["TYPESAFE_API_KEY"] == "cle-de-test"
    assert code == EXIT_CONFIG
    assert "ROM introuvable" in capsys.readouterr().out


def _forget(monkeypatch, *names):
    """Enregistre l'absence de ces variables : si le code les crée, elles disparaissent en fin de test."""
    for name in names:
        monkeypatch.setenv(name, "a-retirer")
        monkeypatch.delenv(name)


def test_only_the_key_is_read_from_the_env_file(tmp_path, no_key, monkeypatch, capsys):
    # Un .env piégé ne doit pas pouvoir rediriger l'API ni changer la journalisation.
    others = ("TYPESAFE_BASE_URL", "TYPESAFE_LOG_LEVEL", "TYPESAFE_DEFAULT_MODEL")
    _forget(monkeypatch, *others)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TYPESAFE_API_KEY=cle-de-test\nTYPESAFE_BASE_URL=https://pirate.example\n"
        "TYPESAFE_LOG_LEVEL=debug\nTYPESAFE_DEFAULT_MODEL=autre\n",
        encoding="utf-8",
    )
    main(["--rom", str(tmp_path / "absente.z5"), "--env-file", str(env_file), "--log-dir", str(tmp_path)])
    assert os.environ["TYPESAFE_API_KEY"] == "cle-de-test"
    for name in others:
        assert name not in os.environ
    # Elles sont ignorées, mais l'utilisateur en est prévenu, sans que la valeur soit affichée.
    out = " ".join(capsys.readouterr().out.split())
    assert "seule TYPESAFE_API_KEY y est lue" in out
    assert "TYPESAFE_BASE_URL, TYPESAFE_LOG_LEVEL, TYPESAFE_DEFAULT_MODEL" in out
    assert "pirate.example" not in out


def test_a_clean_env_file_raises_no_warning(tmp_path, no_key, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text("TYPESAFE_API_KEY=cle-de-test\n", encoding="utf-8")
    main(["--rom", str(tmp_path / "absente.z5"), "--env-file", str(env_file), "--log-dir", str(tmp_path)])
    assert "ignorées" not in capsys.readouterr().out


def test_the_key_from_the_shell_wins_over_the_env_file(tmp_path, no_key, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "cle-du-shell")
    env_file = tmp_path / ".env"
    env_file.write_text("TYPESAFE_API_KEY=cle-du-fichier\n", encoding="utf-8")
    main(["--rom", str(tmp_path / "absente.z5"), "--env-file", str(env_file), "--log-dir", str(tmp_path)])
    assert os.environ["TYPESAFE_API_KEY"] == "cle-du-shell"


def test_a_key_saved_as_env_dot_txt_gets_a_hint(tmp_path, no_key, capsys):
    (tmp_path / ".env.txt").write_text("TYPESAFE_API_KEY=cle-de-test\n", encoding="utf-8")
    code = main(["--env-file", str(tmp_path / ".env"), "--log-dir", str(tmp_path)])
    out = " ".join(capsys.readouterr().out.split())
    assert code == EXIT_CONFIG
    assert "Windows a nommé votre fichier « .env.txt » : renommez-le en « .env »." in out


def test_no_hint_when_there_is_no_stray_file(tmp_path, no_key, capsys):
    main(["--env-file", str(tmp_path / ".env"), "--log-dir", str(tmp_path)])
    assert "Windows" not in capsys.readouterr().out


def test_a_missing_rom_is_reported(tmp_path, capsys):
    assert main(["--mock", "--rom", str(tmp_path / "absente.z5"), *no_env(tmp_path)]) == EXIT_CONFIG
    assert "ROM introuvable" in capsys.readouterr().out


def test_a_path_with_brackets_is_printed_as_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", "300")  # rich replie les longues lignes : le chemin doit rester d'un bloc
    rom = tmp_path / "[demo]" / "absente.z5"
    assert main(["--mock", "--rom", str(rom), *no_env(tmp_path)]) == EXIT_CONFIG
    assert "[demo]" in capsys.readouterr().out


def test_invalid_settings_are_refused(tmp_path, capsys):
    assert main(["--mock", "--penalty", "0", *no_env(tmp_path)]) == EXIT_CONFIG
    assert "--penalty" in capsys.readouterr().out


def test_argparse_refuses_zero_steps():
    with pytest.raises(SystemExit):
        main(["--steps", "0"])
