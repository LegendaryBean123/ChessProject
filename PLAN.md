# Chess Opening Stats Analyzer — Plan

Download every game a chess.com player has played and report their most-played
openings with win/draw/loss records.

## Decisions
- **Interface:** command line first (a web UI is a later extension).
- **Grouping:** by opening *family* ("Four Knights Game"); exact variations come later via `--detailed`.
- **Language:** Python 3, `requests` for HTTP, `pytest` for tests.

## Target output (v1)
```
> python -m chessstats LegendaryBean123
Downloading archives... 30 months (29 cached, 1 fetched)
Analyzed 2,450 games (standard chess only)

Most played openings, as White
  Opening                          Games   W / D / L     Win%
  Italian Game                       312   160/ 8/144    51.3%
```

## Architecture
Each layer has one job and only talks to the layer below it.

```
chessstats/
  api.py        # Layer 1: HTTP to chess.com (User-Agent, 429 backoff, ETags)
  storage.py    # Layer 2: monthly JSON cache on disk; decides what to fetch
  models.py     # Layer 3: raw JSON -> Game objects from the player's point of view
  analysis.py   # Layer 4: pure functions, Games -> opening stats
  tree.py       # Layer 4: Games -> move tree that stops where the opening is decided
  insights.py   # Layer 4: Games -> endings, clock, rating-gap, activity, time-of-day, streak stats
  report.py     # Layer 5: prints tables and trees
  html_report.py        # Layer 5: builds the HTML report's data (positions via python-chess)
  templates/report.html # the report page: layout, CSS and JavaScript, no external files
  pipeline.py   # download + parse one player's games; shared by the CLI and the server
  server.py     # --serve: local website with a player search (JSON API over the pipeline)
  app.py        # --app: the same website in its own desktop window (pywebview)
  __main__.py   # glue: argparse + pipeline
tests/
data/           # cache (git-ignored)
```

## Phases
Each phase ends with something runnable. Finish the checkpoint before moving on.

- [x] **Phase 0: Setup.** Create the venv, requirements, .gitignore and package skeleton.
  *Checkpoint:* `python -m chessstats` runs.
- [x] **Phase 1: API client** (`api.py`). `ChessComClient` with `get_profile`,
  `get_archives`, `get_month(url, etag)`; raises `PlayerNotFound` on 404; retries 429 with backoff.
  *Checkpoint:* print the archive list for any username.
- [x] **Phase 2: Cache** (`storage.py`). Save to `data/{user}/{YYYY-MM}.json` with its ETag.
  A month is final once it was downloaded more than an hour after it ended; final months are read
  from disk with no request, and anything else is revalidated with `If-None-Match`. Fetch serially.
  *Checkpoint:* the second run makes about 2 requests. ✔ 2 requests, 0.1s.
- [x] **Phase 3: Parse** (`models.py`). Normalise results to win/draw/loss from the player's side;
  get the opening name from the `eco` URL; `opening_family()` ends the name at the first
  Opening/Game/Defense/Gambit/Attack/System word (keeping Accepted/Declined) and merges chess.com's
  split names (Giuoco Piano → Italian Game, Alapin/Closed Sicilian → Sicilian Defense);
  keep only `rules == "chess"`; a missing or "Undefined" eco becomes "Unknown".
  *Checkpoint:* unit tests using a saved month as a fixture. ✔ `tests/fixtures/month.json`
- [x] **Phase 4: Analysis** (`analysis.py`). Per family and colour: games, W/D/L, win %,
  score % (win = 1, draw = 0.5), average opponent rating.
  *Checkpoint:* tests using hand-made Games.
- [x] **Phase 5: CLI + report.** `chessstats USERNAME [--time-class] [--since YYYY-MM]
  [--top N] [--min-games N] [--refresh] [--data-dir PATH]`.
  *Checkpoint:* the full run on LegendaryBean123. ✔
- [x] **Phase 6: Opening tree** (`tree.py`, `--tree`). One tree per colour built from the actual
  moves in each PGN. A branch keeps splitting move by move until 90% of its games share one opening
  family, then stops and shows that name. Branches with fewer than `--min-games` games (default 5
  for the tree) are folded into "(other lines: N)"; runs where every game played the same move are
  folded onto one line; mixed branches that can't go deeper show "mixed: mostly X (NN%)".
  *Checkpoint:* `--tree` run on LegendaryBean123. ✔
- [x] **Phase 7: HTML report** (`html_report.py`, `templates/report.html`, `--html PATH [--open]`).
  One self-contained file that works offline. Python works out the stats and trees for "all" and each
  speed, the board position at every tree branch (python-chess), and rating history (last rated game
  per day), and embeds them as JSON. The page has: speed and colour filters, summary cards (record,
  score, current ratings, best/worst opening with 10+ games), a rating-over-time chart (SVG, hover
  tooltips, breaks at gaps over 45 days), win/draw/loss bars for the top 10 openings, a sortable
  openings table, and an expandable opening tree next to a board that shows the selected position,
  its stats and links to the 5 most recent games in that line. It follows the system's light/dark
  mode and stacks into one column on phones. Tree branches need 3+ games by default.
  *Checkpoint:* report generated for LegendaryBean123 and Hikaru; every tree row clicked under every
  filter with no JavaScript errors; checked in light, dark and phone-width screenshots. ✔
- [x] **Phase 8: Player search, loading screen, flat rating gaps** (`pipeline.py`, `server.py`, `--serve`).
  `python -m chessstats --serve --open` runs a local website (127.0.0.1 only) with a search bar:
  username + range (This year by default / Last 12 months / All time). The page calls
  `/api/report?user=&range=` (the same pipeline and cache as the CLI) and polls `/api/progress` to show
  a loading screen with "Downloading month N of M". One chess.com download runs at a time. Saved
  `--html` files show the search bar too, and explain how to start the server. On the rating chart a
  gap of 30+ days without rated games is drawn as a dashed flat line at the old rating (unchanged),
  and the tooltip in a gap says "unchanged since <date>".
- [x] **Phase 9: How games end** (`models.py`, `insights.py`, `--stats`). *(Extension 6)*
  - `Game` gets new fields, all parsed from data we already download:
    - `end_reason`: checkmate / resignation / time / abandoned / draw type. For losses and draws it
      comes from the player's result code; for wins it comes from the opponent's.
    - `plies`: the game's length.
    - `base_seconds` / `increment`: from `time_control`, e.g. "180+2". Daily games get none.
    - `my_clock` / `opp_clock`: the last `[%clk]` time of each side.
    - `material_diff`: my material minus the opponent's in the final `fen`
      (P=1, N=B=3, R=5, Q=9).
  - New module `insights.py` (Layer 4, pure functions: Games in, numbers out):
    - `ending_stats`: wins and losses split by how they ended (checkmate, resignation, time,
      abandoned), and draws split by type.
    - `length_stats`: W/D/L by game length in moves (1–20, 21–30, 31–40, 41–60, 61+).
    - `clock_stats`, for timed games only:
      - Low on time: the player's last clock is under 10% of the starting time. Count these games and
        the player's score in them.
      - Average time left in wins vs losses.
      - Lost on time while 3+ points of material ahead.
      - Won on time while 3+ points behind.
  - CLI: `--stats` prints these as text tables, like `--tree`.
  - Help for users:
    - `README.md`: install, a first run, one example per feature, where the cache lives.
    - `--help` sorts flags under headings (What to show / Filters / Download and cache / Report and website) and
      ends with example commands.
    - Running with no arguments prints a short welcome with example commands instead of an error.
    - After a normal run, one line suggests a feature that run didn't use, only when stdout is a terminal.
  - *Checkpoint:* unit tests with hand-made Games and the fixture month; `--stats` on LegendaryBean123;
    `--help` and the no-arguments message checked by eye. ✔ The fixture's PGNs are cut to one move, so
    clock parsing is tested with hand-written PGNs and checked against real cached games.
- [x] **Phase 10: More charts in the HTML report** (`insights.py`, `html_report.py`, `report.html`). *(like Extension 3)*
  - New stats, each added to every speed view in the payload and printed by `--stats`:
    - **Score vs opponent rating:** buckets by rating gap (≤−200, −199…−100, −99…−25, ±24, +25…+99,
      +100…+199, ≥+200). Each bucket shows the player's actual score next to the Elo-expected score,
      so you can tell whether they beat the rating odds.
    - **Activity:** games per month as stacked W/D/L bars.
    - **Time of day:** games and score per hour, in the computer's local time zone. Bar height is the
      number of games; bar colour is the score.
    - **Streaks and tilt:**
      - Longest win and loss streaks, and the current streak.
      - Score in the next game after a win vs after a loss, counting only a next game that ended
        within an hour of the previous one (no daily games).
    - chess.com stores ratings from *after* each game (in 1,534 of 1,575 rated games the rating moved
      the way that game went), so the winner always looked stronger. `pregame_ratings` estimates the
      ratings before the game: the player's from their previous rated game at the same speed, the
      opponent's as their after-game rating plus what the player gained.
  - Page layout, a "How your games go" section after the rating chart and before the openings table:
    - New cards: "How you lose" (the most common ending) and "Low on time" (count and score).
    - "How games end" (losses grow left, wins right) next to "Game length".
    - "Clock" next to "Streaks & tilt".
    - "Score vs rating gap" next to "Time of day".
    - "Activity by month" across the full width, since all-time players can have 150+ months.
    - Columns with fewer than 10 games are drawn faded.
  - The new panels follow the speed filter and cover both colours; the colour filter still only
    changes the openings and the tree.
  - The footer shows the terminal command for the current view (player, speed, range) with a copy
    button, and updates as the filters change.
  - README: a section on the web report and what each chart means.
  - The charts are hand-made SVG like the rating chart, with hover tooltips and light/dark mode. They
    stack into one column on phones.
  - *Checkpoint:* payload tests; report generated for LegendaryBean123 and Hikaru; no JavaScript errors
    under any filter; screenshots in light, dark and phone width. ✔ Every speed × colour clicked and
    every new chart hovered in Edge (Playwright) with no errors or sideways scrolling; the new data adds
    about 85 KB to Hikaru's 18 MB report.
- [x] **Phase 11: Terminal look and a command bar** (`report.html` only; no Python changes).
  - **Terminal theme**, the new default:
    - Monospace font (Cascadia Mono / Consolas / Menlo; no downloads, so saved files still work offline).
    - Near-black background, light grey text, phosphor-green accents and headings. Win/draw/loss keep
      green/grey/red.
    - Panels drawn as boxes with the title set into the top border, like `┌─ How games end ───┐`.
    - The loading screen becomes terminal output, e.g. `Downloading month 3 of 31  [######......]`.
  - **Classic theme:** today's look stays available.
    - Switch with a `[terminal|classic]` toggle or the `theme` command. The choice is remembered in the
      browser.
    - Only classic follows the system's light/dark mode; the terminal theme is always dark.
    - Both themes share the same colour variables, so the charts work unchanged.
  - **Room for more themes:** a theme is a palette (`data-theme`) plus a family (`data-family`) that
    sets the structure: terminal boxes or classic cards. Adding one later means one block of colour
    variables and one line in the `THEMES` list, e.g. an amber terminal.
  - **Command bar** at the top of the page, a `>` prompt with a blinking cursor. `/` focuses it from
    anywhere.
    - Commands are plain words; a reply or error shows on the line below the prompt:
      - `NAME` or `user NAME [year|12months|all]`: look up a player. This needs `--serve`/`--app`; a
        saved file explains that, as the search box does now.
      - `blitz` / `speed blitz` / `speed all`: speed filter.
      - `white` / `black`: colour filter.
      - `go stats|rating|openings|tree`: scroll to that section.
      - `range year|12months|all`: reload the current player with another range.
      - `theme terminal|classic`, `help` (lists every command), `clear`.
    - ↑/↓ cycle through earlier commands; Tab completes command words, speeds and colours.
    - The filter buttons and the search box still work; the bar is an extra way in, not a replacement.
  - *Checkpoint:* both themes in Edge (Playwright) at desktop and phone width; every command typed in a
    saved report and in `--serve`; no JavaScript errors; existing payload tests still pass. ✔ 29
    scripted checks (commands, errors, history, Tab, `/`, theme memory, lookups on the server).
    A bare unknown word is treated as a username; `foo bar` (not a range) is an unknown command.
- [x] **Phase 12: Desktop app** (`app.py`, `--app`).
  - `python -m chessstats --app [NAME]` opens the site in its own window ("chessstats"), with no
    browser tabs or address bar:
    - The report server starts on a free port on 127.0.0.1 in a background thread.
    - pywebview opens a 1280×900 window on it, loading NAME if given.
    - Closing the window stops the server.
  - pywebview uses Microsoft's WebView2 on Windows, which is already installed on Windows 11.
  - Add `pywebview>=6` to requirements.txt, but import it only inside `--app`. Without it, `--app` exits
    with "run pip install pywebview" and everything else still works.
  - Links to chess.com games open in the normal browser, not inside the app window.
  - The Copy button already falls back to selecting the text if the window blocks clipboard access.
  - README: an "App" section; `--help` and the welcome message list `--app`.
  - *Checkpoint:*
    - Unit test with a fake pywebview: the server starts on a free port, the window gets the right URL,
      and the server stops when the window closes.
    - Manual run: search, loading screen, the command bar, a game link opening in the browser, and
      closing the window ends the process.
  - ✔ pywebview 6.2.1 installs on Python 3.14. The real window was driven via WebView2's debugging
    port (`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333`): it loaded a player,
    ran commands, looked up Hikaru, and the Copy button worked. Closing the window exited with code 0.
    Game links weren't clicked in the test (that opens the real browser); pywebview's
    `OPEN_EXTERNAL_LINKS_IN_BROWSER` (on by default) handles them.
- [ ] **Phase 13: Revise the command bar's commands.** Details to be decided with the user after
  trying Phase 11's first version.

- [x] **The website on GitHub Pages** (`--pages DIR`, done 2026-10-15 between phases). The search
  page runs chessstats in the browser with Pyodide (`browser.py`, `templates/pages_worker.js`,
  `pages.py`); `report_response` in `server.py` is shared so both give the same answers and errors.
  - ✔ Tested in headless Edge: LegendaryBean123 loaded in ~6 s (1.8 s again from the browser's
    cache), a missing player showed the server's error, and the time zone matched the computer.

## Set aside for later
- Review Phases 9–10 (committed in 32f8402; Phases 11–12 are built on top of them).
- A double-clickable `.exe` (PyInstaller) for people without Python.
- More themes (Phase 11 makes them one CSS block + one list entry each).

## Running it
```
venv\Scripts\activate
python -m chessstats LegendaryBean123
python -m chessstats LegendaryBean123 --time-class blitz --since 2026-01 --top 5 --min-games 5
python -m chessstats LegendaryBean123 --tree
python -m chessstats LegendaryBean123 --tree --time-class rapid --min-games 10
python -m chessstats LegendaryBean123 --stats
python -m chessstats LegendaryBean123 --stats --time-class blitz --since 2026-01
python -m chessstats LegendaryBean123 --html report.html --open
python -m chessstats --serve --open                   # search any player in the browser
python -m chessstats --app                            # the same, in a desktop window
python -m chessstats LegendaryBean123 --serve --open  # ...starting with this one
python -m pytest
```

## Known limitations
- Opening names are what chess.com assigns, so they describe the game, not the player's choice:
  "Englund Gambit" in the White table means the player faced it as White.
- Family grouping is rule-based; new odd names can be fixed in `FAMILY_ALIASES` / `NAME_FIXES` in `models.py`.
- The tree branches on move order, so transpositions (the same position reached by different moves)
  show up as separate branches. chess.com sometimes names a game after the transposed line, which is
  why a branch stops at 90% agreement rather than 100% (`DOMINANT_SHARE` in `tree.py`).
- Ratings before each game are estimates (chess.com only stores the rating after it), and a range's
  first rated game at each speed has no earlier game to estimate from, so it is left out of the
  rating-gap stats.
- Time of day uses the time zone of the computer that builds the report and the time games *ended*.
- "Ahead on material" counts pieces in the final position only; it can't see a mate threat or a
  passed pawn. Engine analysis (Extension 9) would be needed for that.

## Extensions (after v1)
1. Export to CSV/JSON
2. ~~Best and worst openings~~ (done in the HTML cards, Phase 7)
3. ~~Rating-over-time chart~~ (done as SVG, Phase 7; more charts in Phase 10)
4. How the opening repertoire changes month to month
5. `--detailed` variation view; merge transposed tree branches by position (python-chess)
6. ~~Where games are lost: move number, clock, termination~~ (Phase 9)
7. SQLite storage
8. Compare players / opponent prep
9. Stockfish blunder analysis
10. Put the `--serve` site online for other people (needs a real web server, and a job queue for long downloads)

## API rules to follow
- Always send a User-Agent (a request without one returns 403).
- Make requests one at a time; back off on 429.
- Cache aggressively; use ETags; request gzip.
- Lowercase usernames; use `.get()` for optional fields; set `timeout=` on every request.
