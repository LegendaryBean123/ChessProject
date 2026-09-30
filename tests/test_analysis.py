from datetime import datetime, timezone

import pytest

from chessstats.analysis import filter_games, opening_stats
from chessstats.models import Game


def make_game(color="white", result="win", family="Italian Game", opp_rating=1000, time_class="blitz"):
    return Game(
        url="https://www.chess.com/game/live/1",
        end_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_class=time_class,
        rated=True,
        color=color,
        result=result,
        my_rating=1000,
        opp_rating=opp_rating,
        opening=family,
        opening_family=family,
        eco=None,
        pgn="",
    )


def test_counts_and_percentages():
    games = [
        make_game(result="win", opp_rating=900),
        make_game(result="win", opp_rating=1000),
        make_game(result="draw", opp_rating=1100),
        make_game(result="loss", opp_rating=1200),
    ]
    [italian] = opening_stats(games)["white"]
    assert (italian.games, italian.wins, italian.draws, italian.losses) == (4, 2, 1, 1)
    assert italian.win_pct == 50.0
    assert italian.score_pct == 62.5
    assert italian.avg_opp_rating == 1050


def test_split_by_colour_and_sorted_by_games():
    games = [
        make_game(color="white", family="Italian Game"),
        make_game(color="white", family="London System"),
        make_game(color="white", family="London System"),
        make_game(color="black", family="Sicilian Defense"),
    ]
    stats = opening_stats(games)
    assert [s.opening for s in stats["white"]] == ["London System", "Italian Game"]
    assert [s.opening for s in stats["black"]] == ["Sicilian Defense"]


def test_ties_sorted_by_name():
    games = [make_game(family="Zebra Opening"), make_game(family="Alpha Opening")]
    assert [s.opening for s in opening_stats(games)["white"]] == ["Alpha Opening", "Zebra Opening"]


def test_min_games_hides_small_samples():
    games = [make_game(family="Italian Game")] * 3 + [make_game(family="Bird's Opening")]
    assert [s.opening for s in opening_stats(games, min_games=2)["white"]] == ["Italian Game"]


def test_no_games_gives_empty_colours():
    assert opening_stats([]) == {"white": [], "black": []}


@pytest.mark.parametrize("time_class, expected", [(None, 3), ("blitz", 2), ("rapid", 1), ("daily", 0)])
def test_filter_games_by_time_class(time_class, expected):
    games = [make_game(time_class="blitz"), make_game(time_class="blitz"), make_game(time_class="rapid")]
    assert len(filter_games(games, time_class)) == expected
