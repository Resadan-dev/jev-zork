"""Le code garde la main : l'anti-boucle corrige la distribution de Jev avant de jouer.

Jev ne fait que juger. Chaque action déjà tentée dans le même état du monde voit
sa probabilité divisée par deux (``penalty``) à chaque essai. Sans cela,
n'importe quel agent tourne en rond dans la forêt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

DEFAULT_PENALTY = 0.5
DEFAULT_FLOOR = 0.01


@dataclass(frozen=True)
class Decision:
    """L'action jouée, et ce que l'anti-boucle a changé à l'avis de Jev."""

    action: str
    jev_choice: str
    adjusted: Mapping[str, float]
    tries: Mapping[str, int]

    @property
    def overridden(self) -> bool:
        return self.action != self.jev_choice


def normalize(weights: Mapping[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if not total > 0:
        raise ValueError("la somme des poids doit être strictement positive")
    return {key: value / total for key, value in weights.items()}


def adjust(
    probabilities: Mapping[str, float],
    tries: Mapping[str, int],
    *,
    penalty: float = DEFAULT_PENALTY,
    floor: float = DEFAULT_FLOOR,
) -> dict[str, float]:
    """Divise la probabilité d'une action par ``1/penalty`` à chaque essai déjà fait.

    Le plancher ``floor`` empêche une probabilité nulle de le rester : sans lui,
    une action notée 1,0 par Jev gagnerait quel que soit le nombre d'essais,
    puisque toutes les autres resteraient à zéro.
    """
    if not 0 < penalty <= 1:
        raise ValueError("penalty doit être dans ]0, 1]")
    if floor < 0:
        raise ValueError("floor doit être positif ou nul")
    weights = {
        action: max(probability, floor) * penalty ** tries.get(action, 0)
        for action, probability in probabilities.items()
    }
    return normalize(weights)


def decide(
    probabilities: Mapping[str, float],
    jev_choice: str,
    tries: Mapping[str, int],
    *,
    penalty: float = DEFAULT_PENALTY,
    floor: float = DEFAULT_FLOOR,
) -> Decision:
    """Joue le maximum de la distribution corrigée.

    À égalité, on garde le choix de Jev s'il en fait partie ; sinon l'ordre des
    options (celui des actions valides de Jericho), pour qu'une partie se rejoue
    à l'identique.
    """
    adjusted = adjust(probabilities, tries, penalty=penalty, floor=floor)
    best = max(adjusted.values())
    tied = [
        action
        for action, weight in adjusted.items()
        if math.isclose(weight, best, rel_tol=1e-9, abs_tol=1e-12)
    ]
    action = jev_choice if jev_choice in tied else tied[0]
    return Decision(
        action=action,
        jev_choice=jev_choice,
        adjusted=MappingProxyType(adjusted),
        tries=MappingProxyType({name: count for name, count in tries.items() if count > 0}),
    )


def choice_confidence(probabilities: Mapping[str, float]) -> float:
    """Confiance d'un Choice selon l'approximation publiée par TypeSafe : (n·max − 1)/(n − 1).

    Sert au juge ``--mock``. Pour Jev, on affiche la confiance que renvoie l'API.
    """
    count = len(probabilities)
    if count == 0:
        raise ValueError("aucune option")
    if count == 1:
        return 1.0
    peak = max(probabilities.values())
    return min(1.0, max(0.0, (count * peak - 1) / (count - 1)))
