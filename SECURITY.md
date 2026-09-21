# Security policy

## Reporting a vulnerability

Please do not open a public issue. Use the **Report a vulnerability** button in
the **Security** tab of the repository: the report stays private between you and
the maintainer. Describe what you saw, how to reproduce it and the impact you
imagine.

This project is maintained by one person, so a reply can take a few days.

## What is in scope

- the `jev-zork` harness (`src/jev_zork/`), the replay player (`replay/`) and
  the video renderer (`video/render_video.py`);
- the setup scripts (`scripts/`, `play.cmd`).

## Secrets

- The TypeSafe API key goes in `.env`, never in code, an issue or a screenshot.
  `.env` and its variants (`.env.*`, except `.env.example`) are ignored by git.
- `jev-zork` only reads `TYPESAFE_API_KEY` from `.env`, and the environment
  variable of the shell, if it is set, wins. A booby-trapped `.env` therefore
  cannot redirect the API to another server.
- Game logs (`runs/*.jsonl`) contain the game text, request ids and token counts,
  never the key. They are not versioned.
- If you find a key in the history of the repository, in an issue or in a log,
  report it privately as described above, and regenerate it at
  console.typesafe.ai/keys.

## Supported versions

Only the latest version of the `main` branch receives fixes.
