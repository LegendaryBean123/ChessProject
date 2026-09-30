"""A local web server: the report page, plus a JSON API that looks up any player."""

import json
import re
import threading
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import requests

from chessstats.api import PlayerNotFound
from chessstats.html_report import build_payload, render_page
from chessstats.pipeline import DEFAULT_RANGE, RANGE_LABELS, load_games, range_start

# chess.com usernames are letters, digits, "-" and "_".
USERNAME = re.compile(r"[A-Za-z0-9_-]{1,50}")


class ReportServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        client,
        data_dir: Path,
        min_games: int,
        today: Callable[[], date] = date.today,
    ):
        super().__init__(address, ReportHandler)
        self.client = client
        self.data_dir = data_dir
        self.min_games = min_games
        self.today = today
        # chess.com asks for one request at a time, so only one lookup downloads at once.
        self.download_lock = threading.Lock()
        self.progress: dict[str, dict] = {}
        self.progress_lock = threading.Lock()

    def build_report(self, username: str, range_key: str) -> dict:
        key = username.lower()
        self._set_progress(key, {"done": 0, "total": 0})
        try:
            with self.download_lock:
                player = load_games(
                    self.client,
                    username,
                    self.data_dir,
                    since=range_start(range_key, self.today()),
                    on_progress=lambda done, total: self._set_progress(key, {"done": done, "total": total}),
                )
            return build_payload(player.display_name, player.games, self.min_games, RANGE_LABELS[range_key])
        finally:
            with self.progress_lock:
                self.progress.pop(key, None)

    def get_progress(self, username: str) -> dict | None:
        with self.progress_lock:
            return self.progress.get(username.lower())

    def _set_progress(self, key: str, value: dict) -> None:
        with self.progress_lock:
            self.progress[key] = value


class ReportHandler(BaseHTTPRequestHandler):
    server: ReportServer

    def do_GET(self) -> None:
        url = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        if url.path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", render_page(None, server=True).encode("utf-8"))
        elif url.path == "/api/report":
            self._report(params)
        elif url.path == "/api/progress":
            self._json(HTTPStatus.OK, self.server.get_progress(params.get("user", "")) or {})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _report(self, params: dict[str, str]) -> None:
        username = params.get("user", "").strip()
        range_key = params.get("range", DEFAULT_RANGE)
        if not USERNAME.fullmatch(username):
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "Enter a chess.com username (letters, numbers, - and _)."})
        if range_key not in RANGE_LABELS:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": f"Unknown range '{range_key}'."})
        try:
            payload = self.server.build_report(username, range_key)
        except PlayerNotFound:
            return self._json(HTTPStatus.NOT_FOUND, {"error": f"No chess.com player named '{username}'."})
        except (requests.RequestException, RuntimeError) as e:
            return self._json(HTTPStatus.BAD_GATEWAY, {"error": f"Could not download games from chess.com: {e}"})
        self._json(HTTPStatus.OK, payload)

    def _json(self, status: HTTPStatus, body: dict) -> None:
        self._send(status, "application/json", json.dumps(body, separators=(",", ":")).encode("utf-8"))

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass  # keep the terminal quiet; errors reach the page as JSON
