import json
import re
import threading
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
import requests

from chessstats.api import PlayerNotFound
from chessstats.server import ReportServer

FIXTURE = Path(__file__).parent / "fixtures" / "month.json"
BASE = "https://api.chess.com/pub/player/legendarybean123/games"


class FakeClient:
    """Serves the fixture month as May 2024 for LegendaryBean123; anyone else doesn't exist."""

    def __init__(self, months=("2024/05",)):
        self.months = [f"{BASE}/{m}" for m in months]
        self.server = None
        self.progress_seen = []
        self.error = None

    def get_archives(self, username):
        if self.error:
            raise self.error
        if username != "legendarybean123":
            raise PlayerNotFound(username)
        return self.months

    def get_month(self, url, etag=None):
        if self.server:
            self.progress_seen.append(self.server.get_progress("LegendaryBean123"))
        return json.loads(FIXTURE.read_text(encoding="utf-8")), '"etag"'


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def server(client, tmp_path):
    server = ReportServer(("127.0.0.1", 0), client, tmp_path, min_games=1, today=lambda: date(2024, 6, 15))
    client.server = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def get(server, path):
    """(status, content type, body) for a GET request to the test server."""
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    try:
        with urlopen(url, timeout=10) as response:
            return response.status, response.headers["Content-Type"], response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read().decode("utf-8")


def test_home_page_is_an_empty_report_that_can_search(server):
    status, content_type, html = get(server, "/")
    assert status == 200 and content_type.startswith("text/html")
    config = json.loads(re.search(r'<script id="config" type="application/json">(.*?)</script>', html).group(1))
    assert config["server"] is True
    assert re.search(r'<script id="data" type="application/json">null</script>', html)


def test_report_for_this_year(server):
    status, content_type, body = get(server, "/api/report?user=LegendaryBean123&range=year")
    payload = json.loads(body)
    assert status == 200 and content_type == "application/json"
    assert payload["player"] == "LegendaryBean123"
    assert payload["rangeLabel"] == "This year"
    assert payload["totalGames"] == 7


def test_range_defaults_to_this_year(server, client):
    server.today = lambda: date(2025, 3, 1)  # May 2024 is now last year
    payload = json.loads(get(server, "/api/report?user=legendarybean123")[2])
    assert payload["rangeLabel"] == "This year"
    assert payload["since"] == "2025-01"  # the page shows this in the terminal command
    assert payload["totalGames"] == 0

    payload = json.loads(get(server, "/api/report?user=legendarybean123&range=all")[2])
    assert payload["totalGames"] == 7
    assert payload["since"] is None


def test_unknown_player(server):
    status, _, body = get(server, "/api/report?user=nobody")
    assert status == 404
    assert json.loads(body) == {"error": "No chess.com player named 'nobody'."}


@pytest.mark.parametrize("query", ["user=", "user=bad%20name!", "user=x&range=decade"])
def test_bad_requests(server, query):
    status, _, body = get(server, f"/api/report?{query}")
    assert status == 400
    assert "error" in json.loads(body)


def test_chess_com_failure(server, client):
    client.error = requests.ConnectionError("offline")
    status, _, body = get(server, "/api/report?user=legendarybean123")
    assert status == 502
    assert "Could not download games from chess.com" in json.loads(body)["error"]


def test_progress_is_reported_during_a_download_and_cleared_after(server, client):
    client.months = [f"{BASE}/2024/04", f"{BASE}/2024/05"]
    server.today = lambda: date(2024, 12, 1)
    assert get(server, "/api/report?user=LegendaryBean123")[0] == 200
    assert client.progress_seen == [{"done": 0, "total": 0}, {"done": 1, "total": 2}]
    assert json.loads(get(server, "/api/progress?user=LegendaryBean123")[2]) == {}


def test_unknown_path(server):
    assert get(server, "/nope")[0] == 404
