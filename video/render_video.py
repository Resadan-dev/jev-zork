# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.47,<2"]
# ///
"""Rend la vidéo d'une partie à partir de son journal, image par image.

Ouvre replay/index.html en mode capture dans un navigateur sans interface
(Chrome, Edge ou Chromium), pose le lecteur à chaque instant t, capture
l'écran et passe l'image à ffmpeg. Le rendu ne dépend pas de la vitesse du
poste : aucune image n'est sautée.

    uv run video/render_video.py runs/20260921-081503-jev.jsonl --to 30
    uv run video/render_video.py runs/20260921-081503-jev.jsonl --format carre --gif
    uv run video/render_video.py runs/20260921-081503-jev.jsonl --snapshot 12 --snapshot 40
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "replay" / "index.html"
OUT_DIR = ROOT / "video" / "out"
SIZES = {"paysage": (1920, 1080), "carre": (1080, 1080), "vertical": (1080, 1350)}
BROWSERS = ("chrome", "msedge", "chromium")
GIF_FILTER = (
    "fps=12,scale=720:-1:flags=lanczos,split[a][b];"
    "[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rend la vidéo d'une partie de jev-zork à partir de son journal.")
    parser.add_argument("journal", type=Path, help="journal JSONL écrit par jev-zork (dossier runs/)")
    parser.add_argument("--out", type=Path, help="fichier MP4 (défaut : video/out/<journal>-<format>.mp4)")
    parser.add_argument("--from", dest="first", type=int, default=1, help="premier tour montré (défaut : 1)")
    parser.add_argument("--to", dest="last", type=int, default=None, help="dernier tour montré (défaut : le dernier)")
    parser.add_argument(
        "--format", choices=sorted(SIZES), default="paysage", help="paysage 1920×1080 (défaut), carre, vertical"
    )
    parser.add_argument("--fps", type=int, default=30, help="images par seconde (défaut : 30)")
    parser.add_argument("--speed", type=float, default=1.0, help="rythme du replay : 2 va deux fois plus vite")
    parser.add_argument("--gif", action="store_true", help="produit aussi un GIF allégé (720 px, 12 images/s)")
    parser.add_argument(
        "--bare", action="store_true", help="sans carton d'ouverture ni de fin : pour un GIF court qui boucle"
    )
    parser.add_argument(
        "--snapshot",
        type=float,
        action="append",
        default=[],
        metavar="T",
        help="n'enregistre qu'une image PNG à l'instant T, en secondes (répétable), pour vérifier le rendu",
    )
    parser.add_argument(
        "--snapshot-turn",
        type=int,
        action="append",
        default=[],
        metavar="N",
        help="comme --snapshot, sur le tour N du journal, une fois la décision posée (répétable) : une image de couverture",
    )
    parser.add_argument(
        "--browser",
        choices=("auto", *BROWSERS),
        default="auto",
        help="navigateur sans interface : auto (défaut : Chrome, puis Edge, puis Chromium)",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg", help="chemin de ffmpeg (défaut : celui du PATH)")
    args = parser.parse_args(argv)
    if args.fps < 1 or args.speed <= 0:
        parser.error("--fps doit valoir au moins 1 et --speed être positif")
    return args


def launch(playwright, choice: str):
    """Lance le premier navigateur disponible : Chrome, Edge, puis le Chromium de Playwright."""
    channels = BROWSERS if choice == "auto" else (choice,)
    failures = []
    for channel in channels:
        try:
            if channel == "chromium":
                return playwright.chromium.launch()
            return playwright.chromium.launch(channel=channel)
        except Exception as error:  # Playwright ne lève qu'une Error générique ici.
            failures.append(f"  {channel} : {str(error).splitlines()[0]}")
    raise SystemExit(
        "Aucun navigateur utilisable :\n"
        + "\n".join(failures)
        + "\nInstallez Chrome, ou le Chromium de Playwright : uv run --with playwright playwright install chromium"
    )


def open_replay(page, text: str, name: str, first: int, last: int | None, speed: float, bare: bool) -> float:
    page.goto(f"{REPLAY.as_uri()}?capture=1")
    page.wait_for_function("() => window.JevReplay !== undefined")
    info = page.evaluate("([text, name]) => window.JevReplay.load(text, name)", [text, name])
    # Sans cartons, la vidéo commence sur l'action : c'est ce qu'il faut à un GIF qui boucle.
    pacing = {"speed": speed, **({"intro": 0, "outro": 0} if bare else {})}
    duration = page.evaluate(
        "([first, last, pacing]) => window.JevReplay.setRange(first, last, pacing)",
        [first, last or info["turns"], pacing],
    )
    page.evaluate("() => window.JevReplay.ready()")
    return float(duration)


def turn_targets(page, turns: list[int]) -> list[tuple[str, float]]:
    """Les instants des tours demandés ; un tour hors de l'extrait donne un message clair."""
    targets = []
    for turn in turns:
        try:
            instant = page.evaluate("(n) => window.JevReplay.turnTime(n)", turn)
        except Exception as error:  # Playwright ne lève qu'une Error générique ici.
            raise SystemExit(f"--snapshot-turn {turn} : {str(error).splitlines()[0]}") from error
        targets.append((f"tour{turn:03d}", instant))
    return targets


def snapshots(page, targets: list[tuple[str, float]], stem: str) -> list[Path]:
    """Une image PNG par cible (suffixe du nom, instant en secondes)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix, instant in targets:
        page.evaluate("(t) => window.JevReplay.renderAt(t)", instant)
        path = OUT_DIR / f"{stem}-{suffix}.png"
        page.screenshot(path=str(path))
        paths.append(path)
    return paths


def encode(page, duration: float, fps: int, out: Path, ffmpeg: str) -> None:
    frames = math.ceil(duration * fps) + 1
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
        # Les JPEG sont en plage complète : on repasse en yuv420p standard, lu partout (LinkedIn compris).
        "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-color_range", "tv",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-movflags", "+faststart", str(out),
    ]  # fmt: skip
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    started = time.monotonic()
    try:
        for index in range(frames):
            page.evaluate("(t) => window.JevReplay.renderAt(t)", index / fps)
            process.stdin.write(page.screenshot(type="jpeg", quality=95))
            if index % (fps * 10) == 0:
                print(f"  {index / fps:6.1f} s / {duration:.1f} s de vidéo", flush=True)
    finally:
        process.stdin.close()
        code = process.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg a échoué (code {code}) : {' '.join(command)}")
    print(f"{frames} images en {time.monotonic() - started:.0f} s → {out}")


def make_gif(ffmpeg: str, video: Path) -> Path:
    gif = video.with_suffix(".gif")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-vf", GIF_FILTER, str(gif)], check=True)
    print(f"GIF → {gif}")
    return gif


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.journal.is_file():
        raise SystemExit(f"Journal introuvable : {args.journal}")
    ffmpeg = shutil.which(args.ffmpeg)
    still_images = bool(args.snapshot or args.snapshot_turn)
    if not still_images and ffmpeg is None:
        raise SystemExit("ffmpeg introuvable : installez-le (winget install Gyan.FFmpeg) ou passez --ffmpeg.")
    from playwright.sync_api import sync_playwright

    width, height = SIZES[args.format]
    stem = f"{args.journal.stem}-{args.format}"
    out = args.out or OUT_DIR / f"{stem}.mp4"
    text = args.journal.read_text(encoding="utf-8")
    problems: list[str] = []
    with sync_playwright() as playwright:
        browser = launch(playwright, args.browser)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
        duration = open_replay(page, text, args.journal.name, args.first, args.last, args.speed, args.bare)
        print(f"Replay de {duration:.1f} s ({args.format}, {width}×{height}, {args.fps} images/s)")
        if still_images:
            targets = [(f"t{instant:07.2f}", instant) for instant in args.snapshot]
            targets += turn_targets(page, args.snapshot_turn)
            for path in snapshots(page, targets, stem):
                print(f"Image → {path}")
        else:
            encode(page, duration, args.fps, out, ffmpeg)
            if args.gif:
                make_gif(ffmpeg, out)
        browser.close()
    if problems:
        print("Erreurs relevées dans la page :", *problems, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
