"""Look up players inside a web browser, for the GitHub Pages site that --pages builds.

This runs in Pyodide (Python compiled to WebAssembly) from templates/pages_worker.js. There
is no server: the browser downloads from chess.com itself, which allows it, and keeps the
downloaded months in its own storage between visits.
"""

import json
from datetime import date
from pathlib import Path
from typing import Callable

from chessstats.api import ChessComClient, PlayerNotFound
from chessstats.html_report import build_payload
from chessstats.pipeline import RANGE_LABELS, load_games, range_start
from chessstats.server import report_response

# pages_worker.js saves this folder in the browser's storage (IndexedDB).
DATA_DIR = Path("/data")


class BrowserClient:
    """The parts of ChessComClient that sync_games uses, over requests made by the browser.

    `get(url)` returns (status, body text); status 0 means there was no answer. Pages can't
    set a User-Agent, and the browser's own cache already rechecks months with chess.com,
    so this sends neither.
    """

    def __init__(self, get: Callable[[str], tuple[int, str]]):
        self.get = get

    def get_archives(self, username: str) -> list[str]:
        username = username.lower()
        return self._get(f"{ChessComClient.BASE_URL}/player/{username}/games/archives", username)["archives"]

    def get_month(self, url: str, etag: str | None = None) -> tuple[dict, None]:
        return self._get(url), None

    def _get(self, url: str, username: str | None = None) -> dict:
        status, body = self.get(url)
        if status == 404 and username:
            raise PlayerNotFound(username)
        if status == 429:
            raise RuntimeError("chess.com is limiting requests, try again in a minute")
        if status == 0:
            raise RuntimeError("no answer, check your internet connection")
        if status != 200:
            raise RuntimeError(f"chess.com answered {status}")
        return json.loads(body)


def report_json(
    get: Callable[[str], tuple[int, str]],
    username: str,
    range_key: str,
    min_games: int,
    on_progress: Callable[[int, int], None] | None = None,
    today: date | None = None,
    data_dir: Path = DATA_DIR,
) -> str:
    """The JSON the server's /api/report would answer with; failures have an "error" key."""

    def build(username: str, range_key: str) -> dict:
        since = range_start(range_key, today or date.today())
        player = load_games(BrowserClient(get), username, data_dir, since=since, on_progress=on_progress)
        return build_payload(player.display_name, player.games, min_games, RANGE_LABELS[range_key], since)

    _, body = report_response(username, range_key, build)
    return json.dumps(body, separators=(",", ":"))
