from pathlib import Path

from rich.console import Console

from jev_zork.display import TerminalDisplay, bar, confidence_verdict, euros_style, percent

HEADER = {"judge": "jev", "model": "jev-latest", "game": "Zork I", "max_score": 350}

RECORD = {
    "turn": 1,
    "location": "West of House",
    "score": 0,
    "danger": 0.03,
    "observation": "West of House\nThere is a small mailbox here.",
    "confidence": 0.42,
    "probabilities": {"open mailbox": 0.61, "north": 0.35, "south": 0.04, "west": 0.0},
    "choice": "open mailbox",
    "action": "open mailbox",
    "overridden": False,
    "tries": {"north": 1},
}


def recording_console():
    return Console(record=True, width=120, color_system=None)


def test_confidence_verdict_has_three_levels():
    assert confidence_verdict(0.42)[0] == "Jev hésite"
    assert confidence_verdict(0.6)[0] == "Jev penche"
    assert confidence_verdict(0.95)[0] == "Jev est sûr de lui"


def test_bar_fills_in_eighths_of_a_character():
    assert bar(0.0, 4) == ("", "····")
    assert bar(1.0, 4) == ("████", "")
    assert bar(0.5, 4) == ("██", "··")
    assert bar(1 / 32, 4) == ("▏", "···")
    assert bar(2.0, 4) == ("████", "")


def test_percent_and_amounts_are_french():
    assert percent(0.614) == " 61 %"
    assert euros_style(0.01234) == "0,0123 $"


def test_a_turn_shows_jev_hesitating_between_options():
    console = recording_console()
    display = TerminalDisplay(console, top=3)
    display.start(HEADER)
    display.turn(RECORD)
    text = console.export_text()
    assert "Jev (jev-latest) joue à Zork I." in text
    assert "Tour 1 · West of House · score 0/350 · danger 3 %" in text
    assert "Jev hésite · confiance 0.42" in text
    assert "open mailbox" in text and "61 %" in text
    assert "↺ déjà tenté 1×" in text
    assert "+ 1 autre" in text
    assert "> open mailbox" in text


def test_an_override_by_the_anti_loop_is_explained():
    console = recording_console()
    display = TerminalDisplay(console)
    display.start(HEADER)
    display.turn({**RECORD, "choice": "north", "action": "open mailbox", "overridden": True})
    assert "anti-boucle : Jev préférait « north »" in console.export_text()


def test_the_mock_mode_is_announced_loudly():
    console = recording_console()
    TerminalDisplay(console).start({**HEADER, "judge": "mock"})
    assert "Ce n'est PAS Jev" in console.export_text()


def test_quiet_mode_hides_the_turns():
    console = recording_console()
    display = TerminalDisplay(console, quiet=True)
    display.start(HEADER)
    display.turn(RECORD)
    assert "Tour 1" not in console.export_text()


def test_a_mock_game_does_not_pretend_to_cost_anything():
    console = recording_console()
    display = TerminalDisplay(console)
    display.start({**HEADER, "judge": "mock"})
    end = {"reason": "steps", "score": 0, "max_score": 350, "turns": 3, "cost_usd": 0.0, "input_tokens": 0}
    display.end(end, Path("runs/20260921-081503-mock.jsonl"))
    assert "aucun appel payant (mock)" in console.export_text()


def test_the_end_summarizes_the_game_and_points_to_the_replay():
    console = recording_console()
    display = TerminalDisplay(console)
    end = {
        "reason": "error",
        "score": 5,
        "max_score": 350,
        "turns": 12,
        "cost_usd": 0.0003,
        "input_tokens": 7400,
        "error": "401 Invalid API key",
    }
    display.end(end, Path("runs/20260921-081503-jev.jsonl"))
    text = console.export_text()
    assert "erreur · score 5/350 · 12 tours" in text
    assert "Coût : 0,0003 $ pour 7 400 tokens d'entrée" in text
    assert "401 Invalid API key" in text
    assert "replay/index.html" in text
