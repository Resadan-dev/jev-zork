"""Affichage terminal : ce que Jev voit, ce qu'il pense, ce qu'il joue.

L'affichage lit les enregistrements du journal (``journal.turn_record``) : ce
qu'on voit à l'écran est exactement ce qui est enregistré.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

HESITANT = 0.5  # sous ce seuil de confiance, on dit que Jev hésite
SURE = 0.8
BAR_WIDTH = 24
ACTION_WIDTH = 22  # avec BAR_WIDTH, tient dans un terminal de 80 colonnes
_EIGHTHS = "▏▎▍▌▋▊▉"
_PHOSPHOR = "green3"
_NARROW_SPACE = " "

END_REASONS = {
    "steps": "nombre de coups atteint",
    "victory": "victoire !",
    "game_over": "partie perdue",
    "budget": "budget atteint",
    "interrupted": "interrompue",
    "error": "erreur",
}


def confidence_verdict(confidence: float) -> tuple[str, str]:
    """Le verdict affiché et son style, selon la confiance que Jev renvoie."""
    if confidence < HESITANT:
        return "Jev hésite", "bold red"
    if confidence < SURE:
        return "Jev penche", "bold yellow"
    return "Jev est sûr de lui", "bold green"


def bar(value: float, width: int = BAR_WIDTH) -> tuple[str, str]:
    """Une barre au huitième de caractère près : (partie pleine, reste du rail)."""
    clamped = min(max(value, 0.0), 1.0)
    full, remainder = divmod(round(clamped * width * 8), 8)
    filled = "█" * full + (_EIGHTHS[remainder - 1] if remainder else "")
    return filled, "·" * (width - len(filled))


def percent(value: float) -> str:
    return f"{round(value * 100):>3d} %"


def euros_style(amount: float) -> str:
    """Un montant en dollars à la française : 0,0123 $."""
    return f"{amount:.4f}".replace(".", ",") + f"{_NARROW_SPACE}$"


def thousands(count: int) -> str:
    return f"{count:,}".replace(",", _NARROW_SPACE)


class TerminalDisplay:
    def __init__(self, console: Console, *, top: int = 6, quiet: bool = False) -> None:
        self._console = console
        self._top = top
        self._quiet = quiet
        self._max_score = 0
        self._mock = False

    def start(self, header: Mapping[str, Any]) -> None:
        self._max_score = header["max_score"]
        self._mock = header["judge"] == "mock"
        if header["judge"] == "mock":
            warning = Text(
                "MODE MOCK : tirage au hasard. Ce n'est PAS Jev qui joue.",
                style="bold black on yellow",
                justify="center",
            )
            self._console.print(Panel(warning, border_style="yellow"))
            return
        self._console.print(Text(f"Jev ({header['model']}) joue à {header['game']}.", style="bold"))

    def turn(self, record: Mapping[str, Any]) -> None:
        if self._quiet:
            return
        console = self._console
        console.rule(self._title(record), style="grey42")
        if record["observation"]:
            console.print(Padding(Text(record["observation"], style=_PHOSPHOR), (0, 2)))
        console.print(Padding(self._verdict(record), (1, 2, 0, 2)))
        console.print(Padding(self._options(record), (0, 2)))
        console.print(Padding(self._command(record), (1, 2)))

    def end(self, record: Mapping[str, Any], journal: Path) -> None:
        reason = END_REASONS.get(record["reason"], record["reason"])
        cost = (
            "aucun appel payant (mock)"
            if self._mock
            else f"{euros_style(record['cost_usd'])} pour {thousands(record['input_tokens'])} tokens d'entrée"
        )
        summary = Text.assemble(
            ("Fin de partie : ", "bold"),
            f"{reason} · score {record['score']}/{record['max_score']} · {record['turns']} tours",
        )
        self._console.rule(style="grey42")
        self._console.print(summary)
        # Deux lignes : dans un terminal de 80 colonnes, une seule coupait « 2 422 tokens » en deux.
        self._console.print(f"Coût : {cost}")
        if record.get("error"):
            self._console.print(Text(f"Erreur : {record['error']}", style="bold red"))
        self._console.print(f"Journal : {journal}")
        self._console.print("Replay : ouvrez replay/index.html et déposez-y ce journal.")

    def _title(self, record: Mapping[str, Any]) -> str:
        title = f"Tour {record['turn']} · {record['location']} · score {record['score']}/{self._max_score}"
        if record.get("danger") is not None:
            title += f" · danger {round(record['danger'] * 100)} %"
        return title

    def _verdict(self, record: Mapping[str, Any]) -> Text:
        label, style = confidence_verdict(record["confidence"])
        return Text.assemble((label, style), f" · confiance {record['confidence']:.2f}")

    def _options(self, record: Mapping[str, Any]) -> Table:
        probabilities: Mapping[str, float] = record["probabilities"]
        ranked = sorted(probabilities, key=lambda option: -probabilities[option])
        shown = ranked[: self._top]
        table = Table.grid(padding=(0, 1))
        table.add_column(width=1)
        # Largeur fixe : les barres restent alignées d'un tour à l'autre.
        table.add_column(width=ACTION_WIDTH, no_wrap=True, overflow="ellipsis")
        table.add_column(width=BAR_WIDTH, no_wrap=True)
        table.add_column(width=5, justify="right")
        table.add_column()
        for option in shown:
            filled, rail = bar(probabilities[option])
            played = option == record["action"]
            marker = "›" if played else ("★" if option == record["choice"] else " ")
            tries = record["tries"].get(option, 0)
            table.add_row(
                Text(marker, style="bold"),
                Text(option, style="bold" if played else ""),
                Text.assemble((filled, _PHOSPHOR if played else "grey70"), (rail, "grey27")),
                Text(percent(probabilities[option])),
                Text(f"↺ déjà tenté {tries}×" if tries else "", style="yellow"),
            )
        hidden = len(ranked) - len(shown)
        if hidden:
            table.add_row("", Text(f"+ {hidden} autre{'s' if hidden > 1 else ''}", style="grey50"))
        return table

    def _command(self, record: Mapping[str, Any]) -> Text:
        command = Text(f"> {record['action']}", style=f"bold {_PHOSPHOR}")
        if record["overridden"]:
            command.append(f"   (anti-boucle : Jev préférait « {record['choice']} »)", style="yellow")
        return command
