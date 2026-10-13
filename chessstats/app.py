"""--app: the report website in its own desktop window, using pywebview.

pywebview is imported only here, so everything else works without it installed.
On Windows it draws the page with Microsoft's WebView2 (part of Windows 11).
"""

import threading
from pathlib import Path
from urllib.parse import quote

from chessstats.server import ReportServer

WINDOW_TITLE = "chessstats"
WINDOW_SIZE = (1280, 900)
MIN_WINDOW_SIZE = (420, 500)


def app_url(port: int, username: str | None = None) -> str:
    url = f"http://127.0.0.1:{port}/"
    return f"{url}?user={quote(username)}" if username else url


def run_app(client, data_dir: Path, min_games: int, username: str | None = None) -> None:
    """Start the report server on a free port, show it in a window, and stop it when the window closes.

    Raises ImportError if pywebview isn't installed, before anything is started.
    """
    import webview

    server = ReportServer(("127.0.0.1", 0), client, data_dir, min_games)  # port 0: any free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        webview.create_window(
            WINDOW_TITLE,
            app_url(server.server_address[1], username),
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=MIN_WINDOW_SIZE,
            text_select=True,  # so commands and the copy fallback can select text
        )
        webview.start()  # returns when the window is closed
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
