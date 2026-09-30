import time

import requests


class PlayerNotFound(Exception):
    """Raised when chess.com has no player with the given username."""


class ChessComClient:
    BASE_URL = "https://api.chess.com/pub"

    def __init__(self, user_agent: str, retries: int = 3):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.retries = retries

    def get_profile(self, username: str) -> dict:
        username = username.lower()
        try:
            data, _ = self._get(f"{self.BASE_URL}/player/{username}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                raise PlayerNotFound(username) from e
            raise
        return data

    def get_archives(self, username: str) -> list[str]:
        username = username.lower()
        try:
            data, _ = self._get(f"{self.BASE_URL}/player/{username}/games/archives")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                raise PlayerNotFound(username) from e
            raise
        return data["archives"]

    def get_month(self, url: str, etag: str | None = None) -> tuple[dict | None, str | None]:
        """Return (data, etag); data is None when chess.com answers 304 Not Modified."""
        return self._get(url, etag=etag)

    def _get(self, url: str, etag: str | None = None) -> tuple[dict | None, str | None]:
        headers = {"if-none-match": etag} if etag else {}
        for attempt in range(self.retries):
            r = self.session.get(url, headers=headers, timeout=10)
            if r.status_code == 429:
                if attempt < self.retries - 1:
                    time.sleep(2**attempt)
                continue
            if r.status_code == 304:
                return None, etag
            r.raise_for_status()
            return r.json(), r.headers.get("etag")
        raise RuntimeError("still rate-limited after retries")
