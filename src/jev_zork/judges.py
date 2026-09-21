"""Les juges : Jev (l'API TypeSafe System One) et un tirage au hasard pour tester sans clé.

Un juge reçoit le state, les questions et la liste des options, et rend un
``Judgement``. Il ne joue pas : c'est la boucle de jeu qui décide (``policy.py``).
"""

from __future__ import annotations

import math
import os
import random
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Sequence

from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeError
from typesafe_sdk.constants import API_KEY_ENV

from jev_zork.policy import choice_confidence, normalize
from jev_zork.questions import ACTION, DANGER, INTENT

JEV = "jev"
MOCK = "mock"
MOCK_MODEL = "mock-random"


class ConfigError(RuntimeError):
    """Configuration incomplète : le message s'adresse à l'utilisateur."""


class JudgeError(RuntimeError):
    """Réponse inutilisable : on arrête la partie plutôt que de jouer au hasard."""


@dataclass(frozen=True)
class Judgement:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float
    danger: Optional[float]
    intent: Mapping[str, float]
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    request_id: Optional[str] = None
    warnings: tuple[str, ...] = ()


class JevJudge:
    """Pose les questions à Jev par le SDK officiel, qui gère les reprises (429, 529)."""

    kind = JEV
    errors: tuple[type[BaseException], ...] = (JudgeError, TypeSafeError)

    def __init__(self, client: Any, clock: Callable[[], float] = time.perf_counter) -> None:
        self._client = client
        self._clock = clock

    @classmethod
    def from_env(cls, *, model: str, max_retries: int = 4) -> "JevJudge":
        if not os.environ.get(API_KEY_ENV):
            raise ConfigError(
                f"Clé TypeSafe absente. Copiez .env.example en .env et renseignez {API_KEY_ENV}, "
                "ou lancez avec --mock pour tester le harnais sans Jev."
            )
        return cls(TypeSafeClient(model=model, retry=RetryPolicy(max_retries=max_retries)))

    def judge(
        self, state: Mapping[str, Any], questions: Mapping[str, Any], options: Sequence[str]
    ) -> Judgement:
        started = self._clock()
        response = self._client.system_one(state=state, questions=questions)
        latency_ms = round((self._clock() - started) * 1000)
        return read_answers(response, options, latency_ms)

    def close(self) -> None:
        self._client.close()


def read_answers(response: Any, options: Sequence[str], latency_ms: int) -> Judgement:
    """Vérifie la réponse de Jev avant de s'en servir.

    Une réponse fausse sur l'action arrête la partie (``JudgeError``). Le danger
    et l'intention ne servent qu'à l'affichage : une anomalie y est notée dans
    ``warnings`` et la valeur est laissée vide.
    """
    choices = response.choices
    if ACTION not in choices:
        raise JudgeError("Jev n'a pas répondu à la question « action ».")
    action = choices[ACTION]
    probabilities, warnings = _action_distribution(action.probabilities, options)
    if action.choice not in probabilities:
        raise JudgeError(f"Jev a choisi « {action.choice} », qui n'est pas une action valide.")
    confidence = _unit(action.confidence)
    if confidence is None:
        raise JudgeError(f"Confiance hors de [0, 1] : {action.confidence!r}.")
    danger, danger_warnings = _danger(response.nouls.get(DANGER))
    intent, intent_warnings = _intent(choices.get(INTENT))
    usage = response.usage
    return Judgement(
        choice=action.choice,
        probabilities=MappingProxyType(probabilities),
        confidence=confidence,
        danger=danger,
        intent=MappingProxyType(intent),
        latency_ms=latency_ms,
        input_tokens=int(usage.input_tokens),
        output_tokens=int(usage.output_tokens),
        model=str(response.model),
        request_id=response.request_id,
        warnings=warnings + danger_warnings + intent_warnings,
    )


def _unit(value: Any) -> Optional[float]:
    """La valeur si c'est un réel de [0, 1], sinon None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def _action_distribution(
    raw: Mapping[str, Any], options: Sequence[str]
) -> tuple[dict[str, float], tuple[str, ...]]:
    unknown = sorted(set(raw) - set(options))
    if unknown:
        raise JudgeError(f"Jev a renvoyé des options inconnues : {', '.join(unknown)}.")
    values: dict[str, float] = {}
    for option in options:
        value = _unit(raw.get(option, 0.0))
        if value is None:
            raise JudgeError(f"Probabilité invalide pour « {option} » : {raw.get(option)!r}.")
        values[option] = value
    if not sum(values.values()) > 0:
        raise JudgeError("Jev a renvoyé des probabilités toutes nulles.")
    missing = [option for option in options if option not in raw]
    warnings = (
        (f"{len(missing)} option(s) sans probabilité, comptée(s) à zéro : {', '.join(missing)}",)
        if missing
        else ()
    )
    return normalize(values), warnings


def _danger(answer: Any) -> tuple[Optional[float], tuple[str, ...]]:
    if answer is None:
        return None, ("pas de réponse à la question « danger »",)
    value = _unit(answer.noul)
    if value is None:
        return None, (f"danger hors de [0, 1] : {answer.noul!r}",)
    return value, ()


def _intent(answer: Any) -> tuple[dict[str, float], tuple[str, ...]]:
    if answer is None:
        return {}, ("pas de réponse à la question « intent »",)
    values = {name: _unit(value) for name, value in answer.probabilities.items()}
    if any(value is None for value in values.values()) or not sum(v or 0.0 for v in values.values()) > 0:
        return {}, ("distribution d'intentions invalide",)
    return normalize({name: value or 0.0 for name, value in values.items()}), ()


class MockJudge:
    """Tirage au hasard (Dirichlet uniforme) pour tester le harnais sans clé. Ce n'est PAS Jev."""

    kind = MOCK
    errors: tuple[type[BaseException], ...] = (JudgeError,)

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

    def judge(
        self, state: Mapping[str, Any], questions: Mapping[str, Any], options: Sequence[str]
    ) -> Judgement:
        if not options:
            raise JudgeError("aucune option à tirer au sort")
        probabilities = self._dirichlet(options)
        best = max(probabilities.values())
        choice = next(option for option in options if probabilities[option] == best)
        intents = list(questions.get(INTENT, {}).get("criteria", {}))
        return Judgement(
            choice=choice,
            probabilities=MappingProxyType(probabilities),
            confidence=choice_confidence(probabilities),
            danger=round(self._rng.random() ** 3, 2),
            intent=MappingProxyType(self._dirichlet(intents) if intents else {}),
            latency_ms=0,
            model=MOCK_MODEL,
        )

    def _dirichlet(self, options: Sequence[str]) -> dict[str, float]:
        return normalize({option: self._rng.gammavariate(1.0, 1.0) for option in options})

    def close(self) -> None:
        return None
