import argparse
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

import requests

from chessstats.analysis import COLORS, opening_stats
from chessstats.api import ChessComClient, PlayerNotFound
from chessstats.html_report import build_payload, write_report
from chessstats.insights import summarize
from chessstats.pipeline import load_games
from chessstats.report import render_openings, render_stats, render_tree
from chessstats.server import ReportServer
from chessstats.tree import build_tree

USER_AGENT = "ChessProject/0.1 (contact: ishaan1601@outlook.com)"
TIME_CLASSES = ("bullet", "blitz", "rapid", "daily")
DEFAULT_MIN_GAMES = {"tables": 1, "tree": 5, "html": 3}


def year_month(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got '{text}'")
    return int(match.group(1)), int(match.group(2))


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


EXAMPLES = """examples:
  python -m chessstats LegendaryBean123                     most played openings
  python -m chessstats LegendaryBean123 --stats             how games end, clock, streaks...
  python -m chessstats LegendaryBean123 --tree              move-by-move opening tree
  python -m chessstats LegendaryBean123 --time-class blitz --since 2026-01
  python -m chessstats LegendaryBean123 --html report.html --open
  python -m chessstats --serve --open                       website to search any player
"""

WELCOME = (
    "chessstats: statistics for any chess.com player.\n\n"
    "Type a chess.com username after the command to get started:\n\n"
    + EXAMPLES.removeprefix("examples:\n").rstrip()
    + "\n\nFor every option, run: python -m chessstats --help"
)

# Shown after a run, one at a time: the first feature that run didn't use.
TIPS = (
    ("stats", "add --stats to see how your games end, your clock use and streaks"),
    ("tree", "add --tree to see your openings move by move"),
    ("html", "add --html report.html --open for an interactive report with charts"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chessstats",
        description="Opening statistics and more for a chess.com player.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("username", nargs="?", help="chess.com username (optional with --serve)")

    show = parser.add_argument_group("what to show (default: opening tables)").add_mutually_exclusive_group()
    show.add_argument("--stats", action="store_true", help="how games end, game length, clock, rating gap, streaks, time of day")
    show.add_argument("--tree", action="store_true", help="show a move-by-move opening tree instead of tables")
    show.add_argument("--html", type=Path, metavar="PATH", help="write an interactive HTML report to PATH")
    show.add_argument("--serve", action="store_true", help="run the report as a local website where you can search any player")

    filters = parser.add_argument_group("filters")
    filters.add_argument("--time-class", choices=TIME_CLASSES, help="only count games of this speed")
    filters.add_argument("--since", type=year_month, metavar="YYYY-MM", help="only count games from this month on")
    filters.add_argument("--top", type=positive_int, default=10, help="openings to show per colour in tables (default 10)")
    filters.add_argument(
        "--min-games",
        type=positive_int,
        help="hide openings/branches with fewer games (default 1 for tables, 5 for --tree, 3 for --html/--serve)",
    )

    cache = parser.add_argument_group("download and cache")
    cache.add_argument("--refresh", action="store_true", help="recheck every cached month with chess.com")
    cache.add_argument("--data-dir", type=Path, default=Path("data"), help="cache folder (default ./data)")

    web = parser.add_argument_group("report and website")
    web.add_argument("--open", action="store_true", help="open the report in your browser (with --html or --serve)")
    web.add_argument("--port", type=positive_int, default=8000, help="port for --serve (default 8000)")
    return parser


def main(argv: list[str] | None = None) -> None:
    if not (sys.argv[1:] if argv is None else argv):
        print(WELCOME)
        return
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.open and not (args.html or args.serve):
        parser.error("--open needs --html PATH or --serve")
    if not args.username and not args.serve:
        parser.error("a username is required (except with --serve)")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # tree lines use box-drawing characters
    client = ChessComClient(USER_AGENT)

    if args.serve:
        serve(client, args)
        return

    def show_progress(done: int, total: int) -> None:
        print(f"\rDownloading archives... {done}/{total} months", end="", file=sys.stderr, flush=True)

    try:
        player = load_games(
            client,
            args.username,
            args.data_dir,
            since=args.since,
            time_class=args.time_class,
            refresh=args.refresh,
            on_progress=show_progress if sys.stderr.isatty() else None,
        )
    except PlayerNotFound as e:
        sys.exit(f"No chess.com player named '{e}'")
    except (requests.RequestException, RuntimeError) as e:
        sys.exit(f"Could not download games from chess.com: {e}")

    sync, games = player.sync, player.games
    months = sync.cached + sync.fetched
    print(f"\rDownloading archives... {months} months ({sync.cached} cached, {sync.fetched} fetched)", file=sys.stderr)
    scope = f"standard chess, {args.time_class} only" if args.time_class else "standard chess only"
    print(f"Analyzed {len(games):,} games ({scope})")
    if not games:
        return

    if args.html:
        min_games = args.min_games or DEFAULT_MIN_GAMES["html"]
        range_label = f"Since {args.since[0]}-{args.since[1]:02d}" if args.since else "All time"
        write_report(args.html, build_payload(player.display_name, games, min_games, range_label, args.since))
        print(f"Report written to {args.html.resolve()}")
        if args.open:
            webbrowser.open(args.html.resolve().as_uri())
        return

    print()
    if args.stats:
        print(render_stats(summarize(games, hours_per_bucket=3)))
    elif args.tree:
        min_games = args.min_games or DEFAULT_MIN_GAMES["tree"]
        trees = [render_tree(color, build_tree([g for g in games if g.color == color]), min_games) for color in COLORS]
        print("\n\n".join(trees))
    else:
        min_games = args.min_games or DEFAULT_MIN_GAMES["tables"]
        print(render_openings(opening_stats(games, min_games=min_games), top=args.top))
    if sys.stdout.isatty():
        print(f"\n{next_tip(args)}")


def next_tip(args: argparse.Namespace) -> str:
    """A one-line hint about the first feature this run didn't use."""
    for flag, tip in TIPS:
        if not getattr(args, flag):
            return f"Tip: {tip}. See every option with --help."
    return "Tip: run with --help to see every option."


def serve(client: ChessComClient, args: argparse.Namespace) -> None:
    min_games = args.min_games or DEFAULT_MIN_GAMES["html"]
    try:
        server = ReportServer(("127.0.0.1", args.port), client, args.data_dir, min_games)
    except OSError as e:
        sys.exit(f"Could not start the server on port {args.port}: {e}")

    url = f"http://127.0.0.1:{args.port}/"
    if args.username:
        url += f"?user={quote(args.username)}"
    print(f"Serving the chess report at {url}  (press Ctrl+C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
