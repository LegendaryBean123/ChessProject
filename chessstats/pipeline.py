"""Download a player's games and turn them into Games; shared by the CLI and the web server."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from chessstats.analysis import filter_games
from chessstats.models import Game, parse_games
from chessstats.storage import SyncResult, sync_games

# Ranges the web page offers, with the first month each one covers.
RANGE_LABELS = {"year": "This year", "12months": "Last 12 months", "all": "All time"}
DEFAULT_RANGE = "year"


@dataclass
class PlayerGames:
    display_name: str
    games: list[Game]
    sync: SyncResult


def load_games(
    client,
    username: str,
    data_dir: Path,
    since: tuple[int, int] | None = None,
    time_class: str | None = None,
    refresh: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> PlayerGames:
    """Sync the cache for `username`, then parse standard-chess games from their point of view.

    Raises PlayerNotFound, or requests/RuntimeError errors from the API client.
    """
    sync = sync_games(client, username, data_dir, since=since, refresh=refresh, on_progress=on_progress)
    games = filter_games(parse_games(sync.games, username), time_class)
    return PlayerGames(display_name(sync.games, username), games, sync)


def range_start(range_key: str, today: date) -> tuple[int, int] | None:
    """First (year, month) a web-page range covers; None means every month."""
    if range_key == "year":
        return today.year, 1
    if range_key == "12months":
        # The current month plus the 11 before it.
        months = today.year * 12 + today.month - 1 - 11
        return months // 12, months % 12 + 1
    if range_key == "all":
        return None
    raise ValueError(f"unknown range {range_key!r}")


def display_name(raw_games: list[dict], username: str) -> str:
    """The username with chess.com's capitalisation, e.g. 'LegendaryBean123'."""
    for raw in raw_games:
        for side in ("white", "black"):
            name = raw.get(side, {}).get("username", "")
            if name.lower() == username.lower():
                return name
    return username
