# chessstats

Statistics for any chess.com player: which openings they play and how they score with them,
how their games end, how they use the clock, and more. It runs in the terminal or as an
interactive web page.

## Install

You need Python 3.10 or newer.

```
python -m venv venv
venv\Scripts\activate          (on macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

## Your first run

```
python -m chessstats LegendaryBean123
```

Replace `LegendaryBean123` with any chess.com username. The first run downloads every game the
player has played, which can take a minute for active players. Later runs only fetch new games.

Not sure what to type? Run `python -m chessstats` on its own for a few examples, or
`python -m chessstats --help` for every option.

## What you can see

| Command | What it shows |
|---|---|
| `python -m chessstats NAME` | Most played openings as White and as Black, with win/draw/loss and score |
| `python -m chessstats NAME --stats` | How games end, game length, clock use, score vs rating gap, streaks, time of day, monthly activity |
| `python -m chessstats NAME --tree` | The openings move by move, until each line settles into a named opening |
| `python -m chessstats NAME --html report.html --open` | An interactive report with charts and a chessboard, saved as one file |
| `python -m chessstats --serve --open` | A local website where you can look up any player |
| `python -m chessstats --app` | The same website in its own desktop window |

Filters work with every view:

| Option | Example | Meaning |
|---|---|---|
| `--time-class` | `--time-class blitz` | Only bullet, blitz, rapid or daily games |
| `--since` | `--since 2026-01` | Only games from this month on |
| `--top` | `--top 5` | How many openings each table lists |
| `--min-games` | `--min-games 10` | Hide openings and tree lines with fewer games |

For example, to see how your blitz games have gone this year:

```
python -m chessstats NAME --stats --time-class blitz --since 2026-01
```

## The `--stats` numbers

- **How games end:** wins and losses by checkmate, resignation, time and abandonment; draws by type.
- **Game length:** results grouped by the number of moves.
- **Clock:** how much of the starting time you have left in wins and losses, and how you score when
  you finish with under 10% of it. It also counts games lost on time while 3+ pawns of material
  ahead, and games won on time while 3+ behind. Daily games have no clock and are left out.
- **Score vs opponent rating:** your score against opponents rated above or below you, next to the
  score the Elo formula expects. chess.com records ratings *after* each game, so the ratings
  *before* the game are estimated from your previous game at the same speed.
- **Streaks:** your longest winning and losing streaks, the current streak, and how you score in a
  game played within an hour of a win compared with a loss.
- **Time of day:** results by the hour games ended, in your computer's time zone.
- **Activity:** games per month (the last 12 months in the terminal; all of them in the web report).

## The web report

`--html` and `--serve` show everything above as charts. The report also has:

- a rating-over-time chart for each speed,
- the openings table and the opening tree, with a board showing each position and links to recent
  games in that line.

The speed buttons filter the whole page. The White/Black buttons change only the opening sections.
The footer shows the terminal command that prints the same stats, with a copy button.

The page works on phones.

### Themes

The report has two looks, switched with the buttons at the top right or the `theme` command:

- **Terminal** (the default): monospace text, a dark background and boxed panels.
- **Classic:** rounded cards that follow your system's light or dark mode.

Your browser remembers the choice.

### Command bar

The `>` prompt at the top of the page lets you drive the report from the keyboard. Press `/` from
anywhere to jump to it.

| Type | What happens |
|---|---|
| `hikaru` or `user hikaru all` | Look up a player (optionally with a range: `year`, `12months`, `all`) |
| `blitz`, `rapid`, `all`, ... | Filter by speed |
| `white` / `black` | Choose the colour for the openings and the tree |
| `tree`, `stats`, `rating`, `openings` | Jump to that section |
| `range 12months` | Reload the current player with another range |
| `theme classic` | Change the look |
| `help` / `clear` | List every command / clear the output |

Tab completes words, and ↑/↓ bring back earlier commands. Looking up players needs `--serve` or
`--app`; in a saved `--html` file, the filters and sections still work.

## The desktop app

```
python -m chessstats --app                    # opens a window with the player search
python -m chessstats --app LegendaryBean123   # ...starting with this player
```

It's the same report as `--serve`, in its own window with no browser tabs or address bar. Links to
chess.com games open in your normal browser. Closing the window stops the app.

`--app` needs the `pywebview` package (included in `requirements.txt`). On Windows it uses Microsoft
WebView2, which comes with Windows 11.

## Where games are stored

Downloaded games are saved in `data/` (change it with `--data-dir`). Finished months are never
downloaded again; use `--refresh` to recheck everything with chess.com.

## Running the tests

```
python -m pytest
```
