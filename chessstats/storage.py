import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# A month counts as final only if it was downloaded at least this long after it
# ended, so games chess.com records slightly late aren't missed.
COMPLETE_BUFFER_SECONDS = 60 * 60


@dataclass
class SyncResult:
    games: list[dict] = field(default_factory=list)
    cached: int = 0
    fetched: int = 0


def sync_games(
    client,
    username: str,
    data_dir: Path,
    since: tuple[int, int] | None = None,
    refresh: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> SyncResult:
    """Download every archive month for `username`, reusing the on-disk cache.

    Finished months that are already cached are read from disk with no request.
    Anything else is fetched with its saved ETag, so unchanged months cost a 304.
    `since` is a (year, month) tuple; earlier months are skipped entirely.
    `refresh` revalidates every cached month with chess.com.
    """
    username = username.lower()
    urls = client.get_archives(username)
    if since is not None:
        urls = [url for url in urls if _month_key(url) >= since]

    result = SyncResult()
    for i, url in enumerate(urls, start=1):
        year, month = _month_key(url)
        path = _month_path(data_dir, username, year, month)
        saved = _load_month(path)

        if saved is not None and not refresh and _is_complete(saved, year, month):
            games = saved["games"]
            result.cached += 1
        else:
            data, etag = client.get_month(url, saved["etag"] if saved else None)
            games = saved["games"] if data is None else data["games"]
            _save_month(path, games, etag)
            result.fetched += 1

        result.games.extend(games)
        if on_progress:
            on_progress(i, len(urls))
    return result


def _month_key(url: str) -> tuple[int, int]:
    year, month = url.rstrip("/").split("/")[-2:]
    return int(year), int(month)


def _month_path(data_dir: Path, username: str, year: int, month: int) -> Path:
    return data_dir / username / f"{year:04d}-{month:02d}.json"


def _load_month(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_month(path: Path, games: list[dict], etag: str | None) -> None:
    record = {"etag": etag, "fetched_at": time.time(), "games": games}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    tmp.replace(path)


def _is_complete(saved: dict, year: int, month: int) -> bool:
    """True if this copy was downloaded after the month ended, so it can't change."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return saved.get("fetched_at", 0) >= next_month.timestamp() + COMPLETE_BUFFER_SECONDS
