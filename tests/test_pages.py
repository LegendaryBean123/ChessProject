import json
import re
import zipfile

from chessstats.pages import PYODIDE_URL, build_site


def test_site_files(tmp_path):
    build_site(tmp_path, min_games=3)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    config = json.loads(re.search(r'<script id="config" type="application/json">(.*?)</script>', html).group(1))
    assert config["server"] is True and config["worker"] == "worker.js"

    worker = (tmp_path / "worker.js").read_text(encoding="utf-8")
    assert f'const PYODIDE_URL = "{PYODIDE_URL}";' in worker
    assert "const MIN_GAMES = 3;" in worker
    assert not re.search(r"__[A-Z_]+__", worker)  # every placeholder was filled in


def test_zip_has_chessstats_and_python_chess(tmp_path):
    build_site(tmp_path, min_games=3)
    names = zipfile.ZipFile(tmp_path / "chessstats.zip").namelist()
    assert {"chessstats/browser.py", "chessstats/html_report.py", "chess/__init__.py", "chess/pgn.py"} <= set(names)
    assert all(name.endswith(".py") for name in names)


def test_rebuilding_gives_the_same_zip(tmp_path):
    build_site(tmp_path / "a", min_games=3)
    build_site(tmp_path / "b", min_games=3)
    assert (tmp_path / "a" / "chessstats.zip").read_bytes() == (tmp_path / "b" / "chessstats.zip").read_bytes()
