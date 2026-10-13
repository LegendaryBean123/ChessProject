import json
from pathlib import Path

import pytest

from chessstats import __main__ as cli
from chessstats.api import PlayerNotFound

FIXTURE = Path(__file__).parent / "fixtures" / "month.json"
ARCHIVE = "https://api.chess.com/pub/player/legendarybean123/games/2024/05"


class FakeClient:
    def __init__(self, user_agent):
        pass

    def get_archives(self, username):
        if username != "legendarybean123":
            raise PlayerNotFound(username)
        return [ARCHIVE]

    def get_month(self, url, etag=None):
        return json.loads(FIXTURE.read_text(encoding="utf-8")), '"etag"'


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    monkeypatch.setattr(cli, "ChessComClient", FakeClient)


def test_full_report(tmp_path, capsys):
    cli.main(["LegendaryBean123", "--data-dir", str(tmp_path)])
    out, err = capsys.readouterr()
    assert "1 months (0 cached, 1 fetched)" in err
    assert "Analyzed 7 games (standard chess only)" in out
    assert "Most played openings, as White" in out
    assert "Petrov's Defense" in out
    assert "Most played openings, as Black" in out


def test_time_class_filter_with_no_games(tmp_path, capsys):
    cli.main(["LegendaryBean123", "--time-class", "bullet", "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    assert "Analyzed 0 games (standard chess, bullet only)" in out
    assert "Most played" not in out


def test_top_limits_rows(tmp_path, capsys):
    cli.main(["LegendaryBean123", "--top", "1", "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    white = out.split("as White")[1].split("Most played")[0].strip().splitlines()
    assert len(white) == 2  # header + one opening


def test_tree_flag(tmp_path, capsys):
    cli.main(["LegendaryBean123", "--tree", "--min-games", "1", "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    assert "Opening tree, as White (branches with at least 1 games)" in out
    assert "Opening tree, as Black" in out
    assert "1.e4" in out
    assert "Most played openings" not in out


def test_tree_default_min_games(tmp_path, capsys):
    cli.main(["LegendaryBean123", "--tree", "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    assert "(branches with at least 5 games)" in out


def test_unknown_player_exits_with_message(tmp_path):
    with pytest.raises(SystemExit, match="No chess.com player named 'nobody'"):
        cli.main(["nobody", "--data-dir", str(tmp_path)])


@pytest.mark.parametrize("args", [["x", "--since", "2026-13"], ["x", "--top", "0"], ["x", "--time-class", "fast"]])
def test_bad_arguments_rejected(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_html_report(tmp_path, capsys):
    out_file = tmp_path / "report.html"
    cli.main(["legendarybean123", "--html", str(out_file), "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    assert f"Report written to {out_file.resolve()}" in out
    html = out_file.read_text(encoding="utf-8")
    assert '"player":"LegendaryBean123"' in html  # chess.com's capitalisation, not what was typed
    assert "Most played openings" not in out


def test_html_report_notes_the_range(tmp_path):
    out_file = tmp_path / "report.html"
    cli.main(["legendarybean123", "--since", "2024-01", "--html", str(out_file), "--data-dir", str(tmp_path)])
    assert '"rangeLabel":"Since 2024-01"' in out_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "args",
    [
        ["x", "--open"],  # --open needs --html or --serve
        ["x", "--serve", "--html", "r.html"],  # one or the other
        ["--tree"],  # a username is required without --serve
    ],
)
def test_invalid_flag_combinations(tmp_path, args):
    with pytest.raises(SystemExit) as exc:
        cli.main([*args, "--data-dir", str(tmp_path)])
    assert exc.value.code == 2


def test_serve_starts_the_server(tmp_path, monkeypatch, capsys):
    started = {}

    class FakeServer:
        def __init__(self, address, client, data_dir, min_games):
            started.update(address=address, data_dir=data_dir, min_games=min_games)

        def serve_forever(self):
            raise KeyboardInterrupt  # stop immediately, as Ctrl+C would

        def server_close(self):
            started["closed"] = True

    monkeypatch.setattr(cli, "ReportServer", FakeServer)
    cli.main(["LegendaryBean123", "--serve", "--port", "8123", "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    assert started == {"address": ("127.0.0.1", 8123), "data_dir": tmp_path, "min_games": 3, "closed": True}
    assert "http://127.0.0.1:8123/?user=LegendaryBean123" in out


def test_stats_flag(tmp_path, capsys):
    cli.main(["LegendaryBean123", "--stats", "--data-dir", str(tmp_path)])
    out, _ = capsys.readouterr()
    for title in ["How games end", "Game length", "Clock (", "Score vs opponent rating", "Streaks", "Time of day", "Activity"]:
        assert title in out
    assert "Most played openings" not in out


def test_stats_and_tree_cannot_be_combined(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["x", "--stats", "--tree", "--data-dir", str(tmp_path)])
    assert exc.value.code == 2


def test_no_arguments_prints_a_welcome(capsys):
    cli.main([])
    out, _ = capsys.readouterr()
    assert "Type a chess.com username" in out
    assert "python -m chessstats LegendaryBean123 --stats" in out


def test_help_lists_groups_and_examples(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out, _ = capsys.readouterr()
    for heading in ["what to show", "filters:", "download and cache:", "examples:"]:
        assert heading in out


def test_tip_only_in_a_terminal(tmp_path, capsys, monkeypatch):
    cli.main(["LegendaryBean123", "--data-dir", str(tmp_path)])
    assert "Tip:" not in capsys.readouterr().out  # captured output is not a terminal

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    cli.main(["LegendaryBean123", "--data-dir", str(tmp_path)])
    assert "Tip: add --stats" in capsys.readouterr().out
    cli.main(["LegendaryBean123", "--stats", "--data-dir", str(tmp_path)])
    assert "Tip: add --tree" in capsys.readouterr().out
