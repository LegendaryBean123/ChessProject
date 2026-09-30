import json
import time
from datetime import datetime, timezone

import pytest

from chessstats import storage
from chessstats.storage import sync_games

BASE = "https://api.chess.com/pub/player/tester/games"


class FakeClient:
    """Stands in for ChessComClient: serves canned months and records every request."""

    def __init__(self, months: dict[str, list[dict]]):
        self.months = months
        self.etags = {url: f'"etag-{i}"' for i, url in enumerate(months)}
        self.requests: list[tuple[str, str | None]] = []

    def get_archives(self, username):
        return list(self.months)

    def get_month(self, url, etag=None):
        self.requests.append((url, etag))
        if etag == self.etags[url]:
            return None, etag
        return {"games": self.months[url]}, self.etags[url]


@pytest.fixture
def client():
    return FakeClient(
        {
            f"{BASE}/2024/05": [{"id": 1}],
            f"{BASE}/2024/12": [{"id": 2}, {"id": 3}],
            f"{BASE}/2025/01": [{"id": 4}],
        }
    )


def test_first_run_downloads_everything(client, tmp_path):
    result = sync_games(client, "Tester", tmp_path)
    assert [g["id"] for g in result.games] == [1, 2, 3, 4]
    assert (result.cached, result.fetched) == (0, 3)
    assert sorted(p.name for p in (tmp_path / "tester").iterdir()) == [
        "2024-05.json",
        "2024-12.json",
        "2025-01.json",
    ]


def test_second_run_uses_cache(client, tmp_path):
    sync_games(client, "tester", tmp_path)
    client.requests.clear()

    result = sync_games(client, "tester", tmp_path)
    assert [g["id"] for g in result.games] == [1, 2, 3, 4]
    assert (result.cached, result.fetched) == (3, 0)
    assert client.requests == []


def test_month_downloaded_before_it_ended_is_revalidated_with_etag(client, tmp_path, monkeypatch):
    # Pretend the first download happened mid-January 2025, while that month was still in progress.
    mid_january = datetime(2025, 1, 15, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(time, "time", lambda: mid_january)
    sync_games(client, "tester", tmp_path)
    monkeypatch.undo()
    client.requests.clear()

    result = sync_games(client, "tester", tmp_path)
    assert client.requests == [(f"{BASE}/2025/01", client.etags[f"{BASE}/2025/01"])]
    assert (result.cached, result.fetched) == (2, 1)
    assert [g["id"] for g in result.games] == [1, 2, 3, 4]


def test_304_keeps_saved_games_and_marks_month_complete(client, tmp_path, monkeypatch):
    mid_january = datetime(2025, 1, 15, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(time, "time", lambda: mid_january)
    sync_games(client, "tester", tmp_path)
    monkeypatch.undo()

    sync_games(client, "tester", tmp_path)  # 304 now, after January has ended
    client.requests.clear()
    sync_games(client, "tester", tmp_path)
    assert client.requests == []


def test_new_games_in_current_month_are_picked_up(client, tmp_path):
    sync_games(client, "tester", tmp_path, refresh=True)
    url = f"{BASE}/2025/01"
    client.months[url] = [{"id": 4}, {"id": 5}]
    client.etags[url] = '"changed"'

    result = sync_games(client, "tester", tmp_path, refresh=True)
    assert [g["id"] for g in result.games] == [1, 2, 3, 4, 5]


def test_since_skips_earlier_months(client, tmp_path):
    result = sync_games(client, "tester", tmp_path, since=(2024, 12))
    assert [g["id"] for g in result.games] == [2, 3, 4]
    assert all("2024/05" not in url for url, _ in client.requests)


def test_refresh_revalidates_every_month(client, tmp_path):
    sync_games(client, "tester", tmp_path)
    client.requests.clear()
    result = sync_games(client, "tester", tmp_path, refresh=True)
    assert len(client.requests) == 3
    assert all(etag is not None for _, etag in client.requests)
    assert [g["id"] for g in result.games] == [1, 2, 3, 4]


def test_corrupt_cache_file_is_redownloaded(client, tmp_path):
    sync_games(client, "tester", tmp_path)
    (tmp_path / "tester" / "2024-05.json").write_text("{not json")
    client.requests.clear()

    result = sync_games(client, "tester", tmp_path)
    assert client.requests == [(f"{BASE}/2024/05", None)]
    assert [g["id"] for g in result.games] == [1, 2, 3, 4]


def test_saved_file_contents(client, tmp_path):
    sync_games(client, "tester", tmp_path)
    saved = json.loads((tmp_path / "tester" / "2024-05.json").read_text())
    assert saved["etag"] == client.etags[f"{BASE}/2024/05"]
    assert saved["games"] == [{"id": 1}]
    assert not list((tmp_path / "tester").glob("*.tmp"))


def test_progress_callback(client, tmp_path):
    calls = []
    sync_games(client, "tester", tmp_path, on_progress=lambda done, total: calls.append((done, total)))
    assert calls == [(1, 3), (2, 3), (3, 3)]


@pytest.mark.parametrize(
    "fetched_at, year, month, complete",
    [
        (datetime(2024, 5, 20, tzinfo=timezone.utc), 2024, 5, False),
        (datetime(2024, 6, 1, 0, 30, tzinfo=timezone.utc), 2024, 5, False),  # inside the buffer
        (datetime(2024, 6, 1, 2, tzinfo=timezone.utc), 2024, 5, True),
        (datetime(2024, 12, 31, tzinfo=timezone.utc), 2024, 12, False),
        (datetime(2025, 1, 1, 2, tzinfo=timezone.utc), 2024, 12, True),  # December rolls into next year
    ],
)
def test_is_complete(fetched_at, year, month, complete):
    assert storage._is_complete({"fetched_at": fetched_at.timestamp()}, year, month) is complete
