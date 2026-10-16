import json
from datetime import date
from pathlib import Path

import pytest

from chessstats.api import PlayerNotFound
from chessstats.browser import BrowserClient, report_json

FIXTURE = Path(__file__).parent / "fixtures" / "month.json"
ARCHIVES = "https://api.chess.com/pub/player/legendarybean123/games/archives"
MONTH = "https://api.chess.com/pub/player/legendarybean123/games/2024/05"


class FakeBrowser:
    """Answers like chess.com does through the browser: (status, body text)."""

    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if url == ARCHIVES:
            return 200, json.dumps({"archives": [MONTH]})
        if url == MONTH:
            return 200, FIXTURE.read_text(encoding="utf-8")
        return 404, '{"message": "not found"}'


def test_report_json_matches_the_server_report(tmp_path):
    progress = []
    body = json.loads(report_json(FakeBrowser(), "LegendaryBean123", "year", 1, lambda *p: progress.append(p),
                                  today=date(2024, 6, 15), data_dir=tmp_path))
    assert body["player"] == "LegendaryBean123"
    assert body["rangeLabel"] == "This year"
    assert body["totalGames"] == 7
    assert progress == [(1, 1)]


def test_months_are_cached_between_look_ups(tmp_path):
    browser = FakeBrowser()
    for _ in range(2):
        report_json(browser, "LegendaryBean123", "all", 1, today=date(2024, 6, 15), data_dir=tmp_path)
    assert browser.urls == [ARCHIVES, MONTH, ARCHIVES]  # May 2024 was over, so the second look-up reused it


@pytest.mark.parametrize(
    ("user", "range_key", "error"),
    [
        ("nobody", "year", "No chess.com player named 'nobody'."),
        ("bad name!", "year", "Enter a chess.com username"),
        ("LegendaryBean123", "decade", "Unknown range 'decade'."),
    ],
)
def test_errors(tmp_path, user, range_key, error):
    body = json.loads(report_json(FakeBrowser(), user, range_key, 1, data_dir=tmp_path))
    assert body["error"].startswith(error)


@pytest.mark.parametrize(
    ("status", "message"),
    [(429, "limiting requests"), (0, "no answer"), (500, "chess.com answered 500")],
)
def test_failed_requests(status, message):
    client = BrowserClient(lambda url: (status, ""))
    with pytest.raises(RuntimeError, match=message):
        client.get_archives("someone")


def test_missing_player():
    with pytest.raises(PlayerNotFound):
        BrowserClient(lambda url: (404, "")).get_archives("Nobody")
