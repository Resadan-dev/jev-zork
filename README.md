# Jev plays Zork

Jev, the System One model from [TypeSafe](https://typesafe.ai), plays Zork I. On
every turn, [Jericho](https://github.com/microsoft/jericho) provides the valid
actions and Jev answers a single Choice: which command to type. You can see its
confidence, and the moment it hesitates between "open mailbox" and "north".

> **Language.** The documentation is in English. The game dashboard, meaning
> everything you watch while Jev plays (the terminal display, the replay player
> and the videos), is in French. So are the messages printed by the command-line
> tools (errors, warnings) and, for now, the code comments. What Zork itself
> says is in English, of course. The words you will meet on the dashboard:
>
> | French | English |
> |---|---|
> | Jev hésite / Jev penche / Jev est sûr de lui | Jev hesitates / leans towards one option / is sure |
> | Confiance | Confidence |
> | Danger | Danger |
> | Carte | Map |
> | Intentions | Intents: what Jev judges most important right now |
> | Tour, coup | Turn, move |
> | Lieu | Location |
> | Coût | Cost |
> | Anti-boucle | Anti-loop |
> | Fin de partie, fin de l'extrait | End of the game, end of the excerpt |
> | Tableau | Table: the whole game, turn by turn |

Three parts:

- **`jev-zork`**, the harness: it makes Jev play and shows its confidence bars
  in the terminal. Every turn is recorded in a JSONL log.
- **`replay/index.html`**, the replay player: it replays a log with the map of
  the places discovered, the confidence curve and the intents, turn by turn.
- **`video/render_video.py`**, the video renderer: it films the player frame by
  frame and produces an MP4 (and a GIF) ready for LinkedIn.

## How it works

```
Jericho ──► valid actions ──┐
                            ├─► state + 3 questions ──► Jev ──► probabilities, confidence
memory (last 8 turns) ──────┘                                          │
                                                                       ▼
Zork ◄── command played ◄── anti-loop (the code stays in charge) ◄── distribution
```

- **Jev only judges.** Each turn asks three questions in a single request:
  - a **Choice** over the valid actions: the options are the keys of
    `criteria`, at most 255;
  - a **Noul** "danger";
  - a **Choice** "intent" (explore, collect, investigate, solve, fight, escape).

  The last two are only used for the visualization.
- **Memory and the anti-loop live in the code.** The last 8 turns go into the
  state. An action already tried in the same world state has its probability
  halved on every try: without this, any agent walks in circles in the forest.
  When the code departs from Jev's opinion, the terminal, the log and the replay
  say so.
- **Options describe themselves.** An exit already taken carries its
  destination ("leads to North of House (visited 2 times)"). Jev's documentation
  advises against making it look elsewhere in the state.
- **The state is in English, the display in French.** Jev reads English better.
  In the dark, it does not know where it is, because the game does not say.

## Installation (Windows + WSL)

Jericho only runs on Linux or macOS. On Windows, everything goes through WSL
(Ubuntu), without `sudo`: `uv` installs into `~/.local/bin` and brings its own
Python 3.12.

```bat
play install
```

(In PowerShell, type `.\play` instead of `play`.)

The script `scripts/setup_wsl.sh` does everything:

- it installs `uv` if needed;
- it creates the Python environment in `~/.venvs/jev-zork` (Jericho, TypeSafe
  SDK, spaCy and its model);
- it downloads `roms/zork1.z5` from Jericho's game suite, checking its MD5
  hash;
- it runs the tests.

On Linux or macOS: `scripts/setup_wsl.sh`, then `scripts/play.sh` instead of
`play`.

The ROM is not versioned. You need `gcc` and `make`, because Jericho is
compiled. On Ubuntu: `sudo apt install build-essential`.

## The TypeSafe key

Copy `.env.example` to `.env` and paste your key in it
(<https://console.typesafe.ai/keys>):

```
TYPESAFE_API_KEY=…
```

`.env` is never versioned, nor are its variants (`.env.*`, except
`.env.example`). Without a key, `jev-zork` stops and says so.

On Windows, Notepad likes to add `.txt` to a name without an extension: the file
becomes `.env.txt` and is not read. `jev-zork` detects this and tells you to
rename it.

`jev-zork` only reads `TYPESAFE_API_KEY` from `.env`, and the environment
variable of the shell, if it exists, wins. A `.env` slipped into a cloned folder
therefore cannot redirect the API (`TYPESAFE_BASE_URL`) to steal your real key.
Any other `TYPESAFE_*` variable found in `.env` is ignored, and `jev-zork` says
so: set it in your shell instead.

## Playing

```bat
play --mock --steps 20          :: no key: random draw, this is NOT Jev
play --delay 0.6 --steps 150    :: Jev, with a pause so you can read
```

| Option | Role | Default |
|---|---|---|
| `--steps` | maximum number of moves | 150 |
| `--delay` | pause between two moves, in seconds | 0 |
| `--mock` | random draw instead of Jev, to test without a key | off |
| `--model` | TypeSafe model | `jev-latest` |
| `--seed` | seed for Jericho (and for the `--mock` draw) | 12, the walkthrough's |
| `--history` | turns sent to Jev in the state | 8 |
| `--penalty` | factor applied per past try (anti-loop) | 0.5 |
| `--floor` | floor probability before the anti-loop | 0.01 |
| `--budget-usd` | stop the game beyond this cost | 0.25 |
| `--top` | options shown per move | 6 |
| `--quiet` | only show the start and the end | off |

`--mock` is announced everywhere: in the terminal, in the log and in the video.
It never stands in for a Jev game.

**Don't expect a high score.** Zork I is worth 350 points, and Jev plans
nothing: it judges each move from what it sees. In the reference game (see
"Measurements"), it scored 44 points in 150 moves without dying, but it took
116 moves to get into the house. That is exactly what makes the confidence bars
worth watching.

## The log

Each game writes `runs/YYYYMMDD-HHMMSS-<jev|mock>.jsonl` (the time is UTC):

- a header line (`run`): model, seed, settings, price;
- one line per turn (`turn`): what Jev saw (`observation`, `state`), the options
  and their notes, its `probabilities`, its `confidence`, its `choice`, the
  distribution corrected by the anti-loop (`adjusted`, `tries`), the `action`
  played, `danger`, `intent`, the game's response, latency, tokens, cost and the
  `request_id`;
- an end line (`end`): the reason the game stopped, the score and the total
  cost.

The file is written line by line: an interrupted game keeps its turns.

## The replay

Open `replay/index.html` by double-clicking it and drop a log onto it. No server
is needed.

- Space: play or pause. Arrows: previous or next turn.
- Hover the curves to read the values, click to jump to a turn.
- "Tableau": the whole game as a table, turn by turn.

With a local server, a log can also be opened by its address: run
`python -m http.server 8841`, then open
<http://127.0.0.1:8841/replay/index.html?log=../runs/….jsonl>.

## The video

On Windows, with `uv`, Chrome (or Edge) and `ffmpeg`. For a game saved as
`runs\20260921-101451-jev.jsonl`:

```bat
uv run video/render_video.py runs\20260921-101451-jev.jsonl --from 110 --to 138 --speed 1.2 --format square
```

The log name is only an example: the reference game's log is not published, so
use one of your own.

The script opens the player in a headless Chrome. It sets it to each instant and
pipes every frame to ffmpeg: no frame is skipped, whatever the speed of the
machine. A sure move goes by quickly, a hesitation lingers.

| Option | Role |
|---|---|
| `--from`, `--to` | the excerpt shown, as turn numbers of the log. For LinkedIn, 25 to 30 moves make about 1 min 30 |
| `--format` | `landscape` (1920×1080), `square` (1080×1080) or `vertical` (1080×1350) |
| `--speed` | pace of the replay: 1.5 goes one and a half times faster |
| `--gif` | also produces a light GIF (720 px, 12 frames/s) |
| `--bare` | no opening or closing card: for a short GIF that loops |
| `--snapshot T` | only saves a PNG image at instant T, to check the rendering |
| `--snapshot-turn N` | like `--snapshot`, at turn N of the log once the decision is made: a cover image |

Files land in `video/out/`, which is not versioned. Measured durations: the 29
moves from 110 to 138, at speed 1.2, make 88 s of video; rendering takes about
3 min 15 s in square and 4 min 20 s in landscape. A 15 s teaser
(`--from 133 --to 138 --bare --gif`) takes 28 s.

Pick the excerpt from the log: the moves where Jev hesitates (`confidence` below
0.5), where the anti-loop corrects it (`overridden`) or where the score moves
(`reward`) make the best images. The video always says where the excerpt comes
from ("coups 110 à 138 sur 150", that is moves 110 to 138 out of 150).

A cruder route: record the terminal with `asciinema` and convert it to a GIF
with `agg`.

## Cost

Jev 1.13 costs $0.042 per million input tokens, and output is free
(<https://docs.typesafe.ai/models>). Measured on the real API: 1,186 input
tokens per move on average (753 on the first move, 1,607 at most), so **$0.0075
for a 150-move game**. The log records the real tokens of each turn.
`--budget-usd` stops the game if the cost goes over budget.

## Measurements

A reference game, on 2026-09-21, against `jev-1.13.0` (`jev-latest`), seed 12
(Jericho's), 150 moves:

| Measure | Value |
|---|---|
| Game duration, WSL and Jericho startup included | 61 s, about 0.4 s per move |
| Jev's latency per decision | 262 ms on average, 316 ms at the 95th percentile, 714 ms at most |
| Cost | $0.0075 for 177,915 input tokens |
| Score | 44 out of 350, without dying or changing the seed |
| Confidence | average 0.37; below 0.5 for 65 moves out of 150; 0.8 or more for only 11 |
| Anti-loop | 12 corrections of Jev's choice |
| Anomalies | no refused answer, no warning, no fallback action |

The log stayed in `runs/` on the machine that played the game: it is not
versioned, so it is not in this repository. The 44 points were scored between
moves 116 and 150: getting into the house through the window (+10), the
living-room trap door down to the cellar (+25), the painting in the gallery
(+4), the east exit of the troll room (+5). `--delay` is only for watching a game
live: the video sets its own pace from the log, so do not use it to prepare one.

## Tests

```bat
wsl -d Ubuntu --cd . --exec bash -lc "~/.venvs/jev-zork/bin/python -m pytest --cov"
node --test "replay/tests/*.test.js"
```

- **Python**: the pure modules, the Jev judge through the real SDK against a
  fake HTTP server, and real Zork moves under Jericho.
- **JavaScript**: the replay logic (log, pacing, map, intents).

## Known limits

- Jericho proposes the actions that **change the state of the world**: it does
  not propose `look`, `inventory` or the magic words. If it finds nothing, the
  harness proposes basic commands and notes it in the log (`fallback_actions`).
- The map places a location according to the direction taken to reach it. Zork's
  geography is not Euclidean: the forest and the maze produce links that cross.
- The "danger" Noul and the "intent" Choice drive nothing. They are readings of
  the situation, for the visualization.

## License

The code in this repository is under the MIT license (see `LICENSE`).

- **Jericho is under GPL-2.0 or later.** The project uses it without containing
  it: everyone installs it on their own with `scripts/setup_wsl.sh`. A
  distribution that bundled the two together (Docker image, executable) would
  have to respect the GPL for the whole.
- The other dependencies are under MIT or BSD: TypeSafe SDK, rich,
  python-dotenv, spaCy and its model.
- **Zork I** is a work by Infocom, now owned by Activision. Its source code is
  published under the MIT license in the `historicalsource/zork1` repository.
  This repository does not contain the ROM: `scripts/setup_wsl.sh` downloads it
  from Jericho's game suite, checking its MD5 hash.
- The replay player loads the IBM Plex fonts (SIL OFL license) from Google
  Fonts: opening `replay/index.html` therefore sends a request to Google.
- Independent project, not affiliated with TypeSafe or Activision. "Jev" is the
  name of TypeSafe's model.

## Security

The TypeSafe key only lives in `.env`, which is never versioned (nor are its
`.env.*` variants). Game logs, the ROM and the videos are not versioned either.
To report a vulnerability, see `SECURITY.md`.

## Layout

```
src/jev_zork/      the harness: game (Jericho), questions (state and questions),
                   judges (Jev and mock), policy (anti-loop), memory, journal,
                   display (terminal), runner (game loop), cli
tests/             Python tests (pytest)
replay/            replay player: index.html, replay.css, replay-core.js
                   (pure logic, tested), replay-ui.js (display)
video/             render_video.py (Playwright + ffmpeg)
scripts/           setup_wsl.sh, play.sh
play.cmd           Windows launcher for WSL
LICENSE            MIT license
SECURITY.md        security policy
```
