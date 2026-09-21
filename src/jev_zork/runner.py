"""La boucle de jeu : Jericho propose, Jev juge, le code décide, et tout est noté."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Optional

from jev_zork.journal import turn_record
from jev_zork.memory import Memory
from jev_zork.policy import decide
from jev_zork.questions import build_questions, build_state
from jev_zork.text import strip_intro

# jev-1.13.0 : 0,042 $ par million de tokens d'entrée, sortie gratuite
# (docs.typesafe.ai/models, lu le 2026-09-21).
PRICE_USD_PER_MTOK = 0.042

STEPS = "steps"
VICTORY = "victory"
GAME_OVER = "game_over"
BUDGET = "budget"
INTERRUPTED = "interrupted"
ERROR = "error"


def cost_of(input_tokens: int) -> float:
    return input_tokens * PRICE_USD_PER_MTOK / 1_000_000


@dataclass(frozen=True)
class Settings:
    steps: int = 150
    delay: float = 0.0
    history: int = 8
    penalty: float = 0.5
    floor: float = 0.01
    budget_usd: float = 0.25

    def __post_init__(self) -> None:
        if self.steps < 1:
            raise ValueError("--steps doit valoir au moins 1")
        if self.delay < 0:
            raise ValueError("--delay ne peut pas être négatif")
        if self.history < 0:
            raise ValueError("--history ne peut pas être négatif")
        if not 0 < self.penalty <= 1:
            raise ValueError("--penalty doit être dans ]0, 1] (0,5 divise par deux à chaque essai)")
        if self.floor < 0:
            raise ValueError("--floor ne peut pas être négatif")
        if not self.budget_usd > 0:
            raise ValueError("--budget-usd doit être strictement positif")


@dataclass(frozen=True)
class Outcome:
    reason: str
    turns: int = 0
    score: int = 0
    max_score: int = 0
    moves: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None

    @property
    def cost_usd(self) -> float:
        return cost_of(self.input_tokens)


def play(
    game: Any,
    judge: Any,
    settings: Settings,
    *,
    on_turn: Callable[[Mapping[str, Any]], None],
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Joue jusqu'à ``settings.steps`` coups, la fin de la partie, le budget ou une erreur.

    ``KeyboardInterrupt`` et les erreurs attendues du juge (``judge.errors``)
    terminent proprement la partie ; ``Outcome.reason`` dit pourquoi elle s'est arrêtée.
    """
    intro = game.reset()
    scene = game.snapshot()
    memory = Memory.start(scene, settings.history)
    outcome = Outcome(reason=STEPS, score=scene.score, max_score=scene.max_score, moves=scene.moves)
    last_command: Optional[str] = None
    last_response = strip_intro(intro)
    try:
        for turn in range(1, settings.steps + 1):
            state = build_state(scene, memory, last_command, last_response)
            notes = memory.annotations(scene, scene.valid_actions)
            questions = build_questions(scene.valid_actions, notes)
            judgement = judge.judge(state, questions, scene.valid_actions)
            decision = decide(
                judgement.probabilities,
                judgement.choice,
                memory.tries(scene, scene.valid_actions),
                penalty=settings.penalty,
                floor=settings.floor,
            )
            result = game.step(decision.action)
            next_scene = None if result.done else game.snapshot()
            memory = memory.after_turn(
                turn=turn, before=scene, command=decision.action, response=result.response, after=next_scene
            )
            outcome = replace(
                outcome,
                turns=turn,
                score=result.score,
                moves=result.moves,
                input_tokens=outcome.input_tokens + judgement.input_tokens,
                output_tokens=outcome.output_tokens + judgement.output_tokens,
            )
            on_turn(
                turn_record(
                    turn=turn,
                    scene=scene,
                    observation=last_response,
                    state=state,
                    notes=notes,
                    judgement=judgement,
                    decision=decision,
                    result=result,
                    cost_usd=cost_of(judgement.input_tokens),
                )
            )
            if next_scene is None:
                return replace(outcome, reason=VICTORY if result.victory else GAME_OVER)
            if outcome.cost_usd >= settings.budget_usd:
                return replace(outcome, reason=BUDGET)
            scene, last_command, last_response = next_scene, decision.action, result.response
            if settings.delay and turn < settings.steps:
                sleep(settings.delay)
    except KeyboardInterrupt:
        return replace(outcome, reason=INTERRUPTED)
    except judge.errors as error:
        return replace(outcome, reason=ERROR, error=str(error))
    return outcome
