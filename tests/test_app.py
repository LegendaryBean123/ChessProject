import json
import sys
import types
import urllib.request

import pytest

from chessstats import __main__ as cli
from chessstats.app import WINDOW_TITLE, app_url, run_app


class FakeWebview(types.ModuleType):
    """Stands in for pywebview: records the window and loads the page as the real window would."""

    def __init__(self):
        super().__init__("webview")
        self.window = None
        self.page = None

    def create_window(self, title, url, **options):
        self.window = {"title": title, "url": url, **options}

    def start(self):
        # The server must be answering while the window is open.
        with urllib.request.urlopen(self.window["url"], timeout=5) as response:
            self.page = response.read().decode("utf-8")


@pytest.fixture
def webview(monkeypatch):
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


def test_app_url():
    assert app_url(8123) == "http://127.0.0.1:8123/"
    assert app_url(8123, "Legendary Bean") == "http://127.0.0.1:8123/?user=Legendary%20Bean"


def test_run_app_serves_the_page_while_the_window_is_open(webview, tmp_path):
    run_app(client=None, data_dir=tmp_path, min_games=3, username="LegendaryBean123")
    window = webview.window
    assert window["title"] == WINDOW_TITLE and window["text_select"] is True
    assert window["url"].startswith("http://127.0.0.1:") and window["url"].endswith("/?user=LegendaryBean123")
    assert ":0/" not in window["url"]  # a real free port, not 0
    config = json.loads(webview.page.split('<script id="config" type="application/json">')[1].split("</script>")[0])
    assert config["server"] is True


def test_server_stops_when_the_window_closes(webview, tmp_path):
    run_app(client=None, data_dir=tmp_path, min_games=3)
    with pytest.raises(OSError):
        urllib.request.urlopen(webview.window["url"], timeout=2)


def test_cli_app_flag(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(cli, "ChessComClient", lambda user_agent: "client")
    monkeypatch.setattr(cli, "run_app", lambda *args: calls.setdefault("args", args))
    cli.main(["--app", "--data-dir", str(tmp_path)])
    assert calls["args"] == ("client", tmp_path, 3, None)


def test_cli_app_without_pywebview(monkeypatch, tmp_path):
    def missing(*args):
        raise ImportError("No module named 'webview'")

    monkeypatch.setattr(cli, "run_app", missing)
    with pytest.raises(SystemExit, match="pip install pywebview"):
        cli.main(["--app", "--data-dir", str(tmp_path)])
