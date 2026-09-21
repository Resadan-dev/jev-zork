"""Ligne de commande : ``jev-zork`` (ou ``python -m jev_zork``)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

from dotenv import load_dotenv
from rich.console import Console
from rich.markup import escape

from jev_zork import __version__
from jev_zork.display import TerminalDisplay
from jev_zork.game import ZorkGame
from jev_zork.journal import Journal, end_record, journal_path, run_record, utc_now
from jev_zork.judges import MOCK_MODEL, ConfigError, JevJudge, MockJudge
from jev_zork.questions import INTENTS
from jev_zork.runner import ERROR, INTERRUPTED, PRICE_USD_PER_MTOK, Settings, play

DEFAULT_ROM = Path("roms/zork1.z5")
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_INTERRUPTED = 130


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("doit valoir au moins 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jev-zork",
        description="Jev (TypeSafe) joue à Zork I : un Choice par coup sur les actions valides de Jericho.",
    )
    parser.add_argument("--steps", type=_positive_int, default=150, help="coups au plus (défaut : 150)")
    parser.add_argument(
        "--delay", type=float, default=0.0, help="pause entre deux coups, en secondes, pour pouvoir lire (ex. 0.6)"
    )
    parser.add_argument(
        "--mock", action="store_true", help="tirage au hasard au lieu de Jev, pour tester sans clé (ce n'est PAS Jev)"
    )
    parser.add_argument("--model", default="jev-latest", help="modèle TypeSafe (défaut : jev-latest)")
    parser.add_argument(
        "--seed", type=int, default=None, help="graine de Jericho et du tirage --mock (défaut Jericho : 12)"
    )
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM, help="ROM de Zork I (défaut : roms/zork1.z5)")
    parser.add_argument("--history", type=int, default=8, help="tours envoyés à Jev dans le state (défaut : 8)")
    parser.add_argument(
        "--penalty", type=float, default=0.5, help="facteur appliqué par essai déjà fait, anti-boucle (défaut : 0.5)"
    )
    parser.add_argument(
        "--floor", type=float, default=0.01, help="probabilité plancher avant l'anti-boucle (défaut : 0.01)"
    )
    parser.add_argument(
        "--budget-usd", type=float, default=0.25, help="arrête la partie au-delà de ce coût (défaut : 0.25)"
    )
    parser.add_argument("--log-dir", type=Path, default=Path("runs"), help="dossier des journaux (défaut : runs)")
    parser.add_argument("--top", type=_positive_int, default=6, help="options affichées par coup (défaut : 6)")
    parser.add_argument("--quiet", action="store_true", help="n'affiche que le début et la fin")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="fichier de clé (défaut : .env)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _env_hint(env_file: Path) -> str:
    """Windows cache les extensions : « .env » enregistré depuis le Bloc-notes devient « .env.txt »."""
    stray = env_file.with_name(env_file.name + ".txt")
    if env_file.is_file() or not stray.is_file():
        return ""
    return f" Windows a nommé votre fichier « {stray.name} » : renommez-le en « {env_file.name} »."


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    if args.env_file.is_file():
        # utf-8-sig : le Bloc-notes de Windows peut écrire un BOM en tête de fichier.
        load_dotenv(args.env_file, override=False, encoding="utf-8-sig")
    try:
        settings = Settings(
            steps=args.steps,
            delay=args.delay,
            history=args.history,
            penalty=args.penalty,
            floor=args.floor,
            budget_usd=args.budget_usd,
        )
        judge = MockJudge(seed=args.seed) if args.mock else JevJudge.from_env(model=args.model)
    except (ValueError, ConfigError) as error:
        hint = _env_hint(args.env_file) if isinstance(error, ConfigError) else ""
        console.print(f"[bold red]{escape(str(error) + hint)}[/bold red]")
        return EXIT_CONFIG
    try:
        game = ZorkGame(args.rom, seed=args.seed)
    except (FileNotFoundError, RuntimeError) as error:
        judge.close()
        console.print(f"[bold red]{escape(str(error))}[/bold red]")
        return EXIT_CONFIG
    try:
        return _play_and_log(args, settings, judge, game, console)
    finally:
        game.close()
        judge.close()


def _play_and_log(args, settings, judge, game, console) -> int:
    display = TerminalDisplay(console, top=args.top, quiet=args.quiet)
    started = utc_now()
    with Journal(journal_path(args.log_dir, judge.kind, started)) as journal:
        header = run_record(
            moment=started,
            judge=judge.kind,
            model=MOCK_MODEL if args.mock else args.model,
            rom=args.rom.name,
            seed=game.seed,
            max_score=game.max_score,
            settings=asdict(settings),
            price_usd_per_mtok=PRICE_USD_PER_MTOK,
            intents=INTENTS,
        )
        journal.write(header)
        display.start(header)

        def on_turn(record):
            journal.write(record)
            display.turn(record)

        outcome = play(game, judge, settings, on_turn=on_turn)
        end = end_record(moment=utc_now(), outcome=outcome)
        journal.write(end)
        display.end(end, journal.path)
    return {INTERRUPTED: EXIT_INTERRUPTED, ERROR: EXIT_ERROR}.get(outcome.reason, EXIT_OK)
