"""--pages: the searchable website as plain files, for GitHub Pages or any static host.

A static host can't run Python, so the site runs it in each visitor's browser with Pyodide
(see browser.py). It is three files:
    index.html       the report page, with the player search
    worker.js        starts Python in the browser and does the look-ups
    chessstats.zip   this package and python-chess, for Python in the browser
"""

import zipfile
from importlib.resources import files
from pathlib import Path

import chess

from chessstats.html_report import render_page

PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/"
WORKER_TEMPLATE = "templates/pages_worker.js"
# A fixed date for every file in the zip, so rebuilding an unchanged site changes nothing.
ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def build_site(out_dir: Path, min_games: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_page(None, server=True, worker="worker.js"), encoding="utf-8")
    worker = files("chessstats").joinpath(WORKER_TEMPLATE).read_text(encoding="utf-8")
    worker = worker.replace("__PYODIDE_URL__", PYODIDE_URL).replace("__MIN_GAMES__", str(min_games))
    (out_dir / "worker.js").write_text(worker, encoding="utf-8")
    # python-chess only publishes source code (no wheel), so Pyodide can't install it: bundle it.
    with zipfile.ZipFile(out_dir / "chessstats.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for package in (Path(__file__).parent, Path(chess.__file__).parent):
            for path in sorted(package.glob("*.py")):
                info = zipfile.ZipInfo(f"{package.name}/{path.name}", ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
