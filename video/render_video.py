# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.47,<2"]
# ///
"""Renders the video of a game from its log, frame by frame.

Opens replay/index.html in capture mode in a headless browser (Chrome, Edge or
Chromium), sets the player to each instant t, takes a screenshot and pipes the
image to ffmpeg. Rendering does not depend on the speed of the machine: no
frame is ever skipped.

    uv run video/render_video.py runs/<game>.jsonl --from 110 --to 138 --speed 1.2
    uv run video/render_video.py runs/<game>.jsonl --format square --gif
    uv run video/render_video.py runs/<game>.jsonl --snapshot 12 --snapshot 40
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
SIZES = {"landscape": (1920, 1080), "square": (1080, 1080), "vertical": (1080, 1350)}
BROWSERS = ("chrome", "msedge", "chromium")
GIF_FILTER = (
    "fps=12,scale=720:-1:flags=lanczos,split[a][b];"
    "[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Renders the video of a jev-zork game from its log.")
    parser.add_argument("journal", type=Path, help="JSONL log written by jev-zork (runs/ folder)")
    parser.add_argument("--out", type=Path, help="MP4 file (default: video/out/<log>-<format>.mp4)")
    parser.add_argument("--from", dest="first", type=int, default=1, help="first turn shown (default: 1)")
    parser.add_argument("--to", dest="last", type=int, default=None, help="last turn shown (default: the last one)")
    parser.add_argument(
        "--format",
        choices=sorted(SIZES),
        default="landscape",
        help="landscape 1920×1080 (default), square 1080×1080 or vertical 1080×1350",
    )
    parser.add_argument("--fps", type=int, default=30, help="frames per second (default: 30)")
    parser.add_argument("--speed", type=float, default=1.0, help="pace of the replay: 2 goes twice as fast")
    parser.add_argument("--gif", action="store_true", help="also produce a light GIF (720 px, 12 frames/s)")
    parser.add_argument(
        "--bare", action="store_true", help="no opening or closing card: for a short GIF that loops"
    )
    parser.add_argument(
        "--snapshot",
        type=float,
        action="append",
        default=[],
        metavar="T",
        help="only save a PNG image at instant T, in seconds (repeatable), to check the rendering",
    )
    parser.add_argument(
        "--snapshot-turn",
        type=int,
        action="append",
        default=[],
        metavar="N",
        help="like --snapshot, at turn N of the log, once the decision is made (repeatable): a cover image",
    )
    parser.add_argument(
        "--browser",
        choices=("auto", *BROWSERS),
        default="auto",
        help="headless browser: auto (default: Chrome, then Edge, then Chromium)",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg", help="path to ffmpeg (default: the one on PATH)")
    args = parser.parse_args(argv)
    if args.fps < 1 or args.speed <= 0:
        parser.error("--fps must be at least 1 and --speed must be positive")
    return args


def launch(playwright, choice: str):
    """Launches the first available browser: Chrome, Edge, then Playwright's Chromium."""
    channels = BROWSERS if choice == "auto" else (choice,)
    failures = []
    for channel in channels:
        try:
            if channel == "chromium":
                return playwright.chromium.launch()
            return playwright.chromium.launch(channel=channel)
        except Exception as error:  # Playwright only raises a generic Error here.
            failures.append(f"  {channel}: {str(error).splitlines()[0]}")
    raise SystemExit(
        "No usable browser:\n"
        + "\n".join(failures)
        + "\nInstall Chrome, or Playwright's Chromium: uv run --with playwright playwright install chromium"
    )


def open_replay(page, text: str, name: str, first: int, last: int | None, speed: float, bare: bool) -> float:
    page.goto(f"{REPLAY.as_uri()}?capture=1")
    page.wait_for_function("() => window.JevReplay !== undefined")
    info = page.evaluate("([text, name]) => window.JevReplay.load(text, name)", [text, name])
    # Without cards, the video starts on the action: what a looping GIF needs.
    pacing = {"speed": speed, **({"intro": 0, "outro": 0} if bare else {})}
    duration = page.evaluate(
        "([first, last, pacing]) => window.JevReplay.setRange(first, last, pacing)",
        [first, last or info["turns"], pacing],
    )
    page.evaluate("() => window.JevReplay.ready()")
    return float(duration)


def turn_targets(page, turns: list[int]) -> list[tuple[str, float]]:
    """The instants of the requested turns; a turn outside the excerpt gives a clear message."""
    targets = []
    for turn in turns:
        try:
            instant = page.evaluate("(n) => window.JevReplay.turnTime(n)", turn)
        except Exception as error:  # Playwright only raises a generic Error here.
            raise SystemExit(f"--snapshot-turn {turn}: {str(error).splitlines()[0]}") from error
        targets.append((f"turn{turn:03d}", instant))
    return targets


def snapshots(page, targets: list[tuple[str, float]], stem: str) -> list[Path]:
    """One PNG image per target (file name suffix, instant in seconds)."""
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
        # JPEG frames are full range: convert back to standard yuv420p (tv range), which plays everywhere.
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
                print(f"  {index / fps:6.1f} s / {duration:.1f} s of video", flush=True)
    finally:
        process.stdin.close()
        code = process.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg failed (code {code}): {' '.join(command)}")
    print(f"{frames} frames in {time.monotonic() - started:.0f} s → {out}")


def make_gif(ffmpeg: str, video: Path) -> Path:
    gif = video.with_suffix(".gif")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-vf", GIF_FILTER, str(gif)], check=True)
    print(f"GIF → {gif}")
    return gif


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.journal.is_file():
        raise SystemExit(f"Log not found: {args.journal}")
    ffmpeg = shutil.which(args.ffmpeg)
    still_images = bool(args.snapshot or args.snapshot_turn)
    if not still_images and ffmpeg is None:
        raise SystemExit("ffmpeg not found: install it (winget install Gyan.FFmpeg) or pass --ffmpeg.")
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
        print(f"Replay of {duration:.1f} s ({args.format}, {width}×{height}, {args.fps} frames/s)")
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
        print("Errors reported by the page:", *problems, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
