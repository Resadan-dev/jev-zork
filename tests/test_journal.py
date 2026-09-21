from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jev_zork.journal import (
    Journal,
    end_record,
    journal_path,
    read_journal,
    run_record,
    timestamp,
    turn_record,
)
from jev_zork.judges import Judgement
from jev_zork.policy import decide

MOMENT = datetime(2026, 9, 21, 8, 15, 3, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Scene:
    location_id: int = 180
    location: str = "West of House"
    dark: bool = False
    world_hash: str = "h-west"
    description: str = "You are standing in an open field."
    inventory: tuple[str, ...] = ()
    score: int = 0
    moves: int = 0
    valid_actions: tuple[str, ...] = ("open mailbox", "north")
    fallback: bool = False


@dataclass(frozen=True)
class Result:
    response: str = "Opening the small mailbox reveals a leaflet."
    reward: int = 0
    score: int = 0
    done: bool = False


@dataclass(frozen=True)
class Outcome:
    reason: str = "steps"
    turns: int = 1
    score: int = 0
    max_score: int = 350
    moves: int = 1
    input_tokens: int = 612
    output_tokens: int = 41
    cost_usd: float = 0.0000257
    error: str | None = None


def header():
    return run_record(
        moment=MOMENT,
        judge="jev",
        model="jev-latest",
        rom="zork1.z5",
        seed=12,
        max_score=350,
        settings={"steps": 1},
        price_usd_per_mtok=0.042,
        intents={"explore": "Go somewhere new"},
    )


def a_turn():
    judgement = Judgement(
        choice="open mailbox",
        probabilities={"open mailbox": 0.61, "north": 0.39},
        confidence=0.42,
        danger=0.03,
        intent={"explore": 1.0},
        latency_ms=250,
        input_tokens=612,
        output_tokens=41,
        model="jev-1.13.0",
        request_id="req_42",
    )
    decision = decide(judgement.probabilities, judgement.choice, {"north": 1})
    return turn_record(
        turn=1,
        scene=Scene(),
        observation="West of House",
        state={"location": "West of House"},
        notes={"north": "leads to North of House (visited once)"},
        judgement=judgement,
        decision=decision,
        result=Result(),
        cost_usd=0.0000257,
    )


def test_timestamp_and_path_use_utc():
    assert timestamp(MOMENT) == "2026-09-21T08:15:03Z"
    assert journal_path(Path("runs"), "jev", MOMENT) == Path("runs") / "20260921-081503-jev.jsonl"


def test_two_games_in_the_same_second_get_distinct_journals(tmp_path):
    first = journal_path(tmp_path, "mock", MOMENT)
    first.write_text("", encoding="utf-8")
    assert journal_path(tmp_path, "mock", MOMENT).name == "20260921-081503-mock-2.jsonl"


def test_a_journal_round_trips_with_accents(tmp_path):
    path = tmp_path / "runs" / "partie.jsonl"
    record = a_turn()
    record["response"] = "Jev hésite… « déjà tenté »"
    with Journal(path) as journal:
        journal.write(header())
        journal.write(record)
        journal.write(end_record(moment=MOMENT, outcome=Outcome()))
    content = read_journal(path)
    assert content.header["judge"] == "jev"
    assert content.turns[0]["response"] == "Jev hésite… « déjà tenté »"
    assert content.end["reason"] == "steps"
    assert "é" in path.read_text(encoding="utf-8")


def test_turn_record_keeps_what_jev_thought_and_what_was_played():
    record = a_turn()
    assert record["probabilities"] == {"open mailbox": 0.61, "north": 0.39}
    assert record["confidence"] == 0.42
    assert record["choice"] == "open mailbox"
    assert record["action"] == "open mailbox"
    assert record["tries"] == {"north": 1}
    assert record["overridden"] is False
    assert record["usage"] == {"input_tokens": 612, "output_tokens": 41}
    assert record["notes"]["north"].startswith("leads to")


def test_end_record_carries_the_error_when_there_is_one():
    assert "error" not in end_record(moment=MOMENT, outcome=Outcome())
    failed = end_record(moment=MOMENT, outcome=Outcome(reason="error", error="401"))
    assert failed["error"] == "401"


def test_a_journal_is_never_overwritten(tmp_path):
    path = tmp_path / "partie.jsonl"
    path.write_text("déjà là", encoding="utf-8")
    with pytest.raises(FileExistsError):
        Journal(path)


def test_an_unknown_record_type_is_refused(tmp_path):
    with Journal(tmp_path / "partie.jsonl") as journal, pytest.raises(ValueError):
        journal.write({"type": "chat"})


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        (['{"type":"run"}', "{oops"], "partie.jsonl:2"),
        (['{"type":"turn"}'], "commencer par l'en-tête"),
        (['{"type":"run"}', '{"type":"end"}', '{"type":"turn"}'], "après la fin"),
        (['{"type":"run"}', '{"type":"run"}'], "inattendu"),
        ([""], "journal vide"),
    ],
)
def test_read_journal_rejects_a_broken_journal(tmp_path, lines, message):
    path = tmp_path / "partie.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_journal(path)


def test_a_journal_without_end_is_readable(tmp_path):
    path = tmp_path / "partie.jsonl"
    with Journal(path) as journal:
        journal.write(header())
        journal.write(a_turn())
    content = read_journal(path)
    assert content.end is None
    assert len(content.turns) == 1
