import json
import re
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from chessstats.html_report import CONFIG_PLACEHOLDER, DATA_PLACEHOLDER, build_payload, render_page, write_report
from chessstats.models import Game


def make_game(moves, family, result="win", color="white", time_class="blitz", day=1, rating=1000, rated=True):
    return Game(
        url=f"https://www.chess.com/game/live/{day}",
        end_time=datetime(2026, 1, day, 12, tzinfo=timezone.utc),
        time_class=time_class,
        rated=rated,
        color=color,
        result=result,
        my_rating=rating,
        opp_rating=900,
        opening=family,
        opening_family=family,
        eco=None,
        pgn="",
        moves=tuple(moves.split()),
        opponent="rival",
    )


@pytest.fixture
def games():
    return (
        [make_game("e4 e5 Nf3 Nc6 Bc4", "Italian Game", day=d) for d in range(1, 4)]
        + [make_game("e4 e5 Nf3 Nc6 Bb5", "Ruy Lopez Opening", "loss", day=d) for d in range(4, 6)]
        + [make_game("d4 d5", "Queen's Pawn Opening", "draw", color="black", time_class="rapid", day=6)]
    )


def test_payload_summary(games):
    payload = build_payload("Tester", games, min_games=1)
    assert payload["player"] == "Tester"
    assert payload["totalGames"] == 6
    assert (payload["firstDate"], payload["lastDate"]) == ("2026-01-01", "2026-01-06")
    assert payload["timeClasses"] == ["all", "blitz", "rapid"]

    everything = payload["views"]["all"]
    assert (everything["games"], everything["wins"], everything["draws"], everything["losses"]) == (6, 3, 1, 2)
    assert everything["white"]["games"] == 5 and everything["black"]["games"] == 1
    assert [row["opening"] for row in everything["white"]["openings"]] == ["Italian Game", "Ruy Lopez Opening"]
    assert payload["views"]["rapid"]["white"]["games"] == 0


def test_tree_nodes_carry_positions(games):
    tree = build_payload("Tester", games, min_games=1)["views"]["all"]["white"]["tree"]
    [e4] = tree
    # Every 1.e4 game continued 1...e5 2.Nf3 Nc6, so the row folds those moves in.
    assert e4["label"] == "1.e4 e5 2.Nf3 Nc6"
    assert e4["fen"] == "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    assert e4["lastMove"] == ["b8", "c6"]

    italian, ruy = e4["children"]
    assert (italian["label"], italian["family"], italian["games"]) == ("3.Bc4", "Italian Game", 3)
    assert italian["line"] == "1.e4 e5 2.Nf3 Nc6 3.Bc4"
    assert italian["lastMove"] == ["f1", "c4"]
    assert (ruy["label"], ruy["family"], ruy["scorePct"]) == ("3.Bb5", "Ruy Lopez Opening", 0.0)


def test_recent_games_newest_first(games):
    [e4] = build_payload("Tester", games, min_games=1)["views"]["all"]["white"]["tree"]
    dates = [g["date"] for g in e4["recent"]]
    assert dates == ["2026-01-05", "2026-01-04", "2026-01-03", "2026-01-02", "2026-01-01"]
    assert e4["recent"][0] == {
        "url": "https://www.chess.com/game/live/5",
        "result": "loss",
        "date": "2026-01-05",
        "opponent": "rival",
        "oppRating": 900,
        "timeClass": "blitz",
    }


def test_small_branches_are_grouped(games):
    white = build_payload("Tester", games, min_games=3)["views"]["all"]["white"]
    [e4] = white["tree"]
    assert [c["label"] for c in e4["children"]] == ["3.Bc4"]
    assert e4["other"] == {"lines": 1, "games": 2}


def test_best_and_worst_need_enough_games(games):
    assert build_payload("Tester", games, min_games=1)["views"]["all"]["best"] is None

    many = [make_game("e4 c5", "Sicilian Defense", day=d % 28 + 1) for d in range(10)] + [
        make_game("d4 f5", "Dutch Defense", "loss", day=d % 28 + 1) for d in range(10)
    ]
    view = build_payload("Tester", many, min_games=1)["views"]["all"]
    assert view["best"]["opening"] == "Sicilian Defense"
    assert view["worst"]["opening"] == "Dutch Defense"


def test_rating_history_keeps_last_rated_game_per_day():
    games = [
        make_game("e4", "X", day=1, rating=1000),
        replace(make_game("e4", "X", day=1, rating=1010), end_time=datetime(2026, 1, 1, 18, tzinfo=timezone.utc)),
        make_game("e4", "X", day=2, rating=990),
        make_game("e4", "X", day=3, rating=500, rated=False),
        make_game("e4", "X", day=2, rating=1500, time_class="rapid"),
    ]
    ratings = build_payload("Tester", games, min_games=1)["ratings"]
    assert ratings == {"blitz": [["2026-01-01", 1010], ["2026-01-02", 990]], "rapid": [["2026-01-02", 1500]]}


def test_write_report_embeds_safe_json(tmp_path, games):
    games.append(make_game("e4", "</script><script>alert(1)</script>", day=7))
    path = tmp_path / "out" / "report.html"
    write_report(path, build_payload("Tester", games, min_games=1))

    html = path.read_text(encoding="utf-8")
    assert DATA_PLACEHOLDER not in html and CONFIG_PLACEHOLDER not in html
    data = embedded_json(html, "data")
    assert json.loads(data)["player"] == "Tester"
    assert "<" not in data  # nothing in the data can close the script tag
    assert html.count("</script>") == 3  # the config and data tags plus the page script
    assert json.loads(embedded_json(html, "config"))["server"] is False


def test_payload_records_range_label(games):
    assert build_payload("Tester", games, min_games=1)["rangeLabel"] is None
    assert build_payload("Tester", games, min_games=1, range_label="This year")["rangeLabel"] == "This year"


def test_page_without_a_player_for_the_server():
    html = render_page(None, server=True)
    assert json.loads(embedded_json(html, "data")) is None
    config = json.loads(embedded_json(html, "config"))
    assert config == {
        "server": True,
        "ranges": {"year": "This year", "12months": "Last 12 months", "all": "All time"},
        "defaultRange": "year",
    }


def embedded_json(html: str, tag_id: str) -> str:
    [text] = re.findall(rf'<script id="{tag_id}" type="application/json">(.*?)</script>', html, re.DOTALL)
    return text
