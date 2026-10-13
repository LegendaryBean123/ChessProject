from datetime import datetime, timedelta, timezone

import pytest

from chessstats.insights import (
    Record,
    clock_stats,
    ending_stats,
    expected_score,
    hourly_stats,
    length_stats,
    monthly_stats,
    pregame_ratings,
    rating_gap_stats,
    streak_stats,
    summarize,
)
from chessstats.models import Game

START = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)


def make_game(
    result="win",
    end_reason="checkmate",
    minutes=0,
    plies=40,
    time_class="blitz",
    rated=True,
    my_rating=1000,
    opp_rating=1000,
    base_seconds=180,
    my_clock=90.0,
    material_diff=0,
):
    return Game(
        url=f"https://www.chess.com/game/live/{minutes}",
        end_time=START + timedelta(minutes=minutes),
        time_class=time_class,
        rated=rated,
        color="white",
        result=result,
        my_rating=my_rating,
        opp_rating=opp_rating,
        opening="Italian Game",
        opening_family="Italian Game",
        eco=None,
        pgn="",
        moves=("e4",) * plies,
        opponent="rival",
        end_reason=end_reason,
        base_seconds=base_seconds,
        my_clock=my_clock,
        material_diff=material_diff,
    )


def test_record_score():
    r = Record("x", wins=2, draws=1, losses=1)
    assert (r.games, r.score_pct) == (4, 62.5)
    assert Record("empty").score_pct is None


def test_ending_stats_most_common_first():
    games = [
        make_game("win", "time"),
        make_game("win", "checkmate"),
        make_game("win", "checkmate"),
        make_game("loss", "resignation"),
        make_game("draw", "stalemate"),
    ]
    endings = ending_stats(games)
    assert endings.wins == [("checkmate", 2), ("time", 1)]
    assert endings.losses == [("resignation", 1)]
    assert endings.draws == [("stalemate", 1)]


def test_length_stats_buckets_by_full_moves():
    games = [
        make_game(plies=39),  # 20 moves
        make_game(plies=41, result="loss"),  # 21 moves
        make_game(plies=200, result="draw"),
        make_game(plies=0),  # no moves: left out
    ]
    lengths = {r.label: r for r in length_stats(games)}
    assert list(lengths) == ["1-20", "21-30", "31-40", "41-60", "61+"]
    assert (lengths["1-20"].wins, lengths["21-30"].losses, lengths["61+"].draws) == (1, 1, 1)
    assert sum(r.games for r in lengths.values()) == 3


def test_clock_stats():
    games = [
        make_game("win", my_clock=90),  # 50% left
        make_game("loss", "time", my_clock=0, material_diff=5),  # flagged while ahead
        make_game("loss", "time", my_clock=0, material_diff=1),
        make_game("win", "time", my_clock=10, material_diff=-4),  # low on time, won while behind
        make_game("win", time_class="daily", base_seconds=None, my_clock=None),  # not timed
    ]
    clock = clock_stats(games)
    assert clock.games == 4
    assert (clock.low_time.games, clock.low_time.wins, clock.low_time.losses) == (3, 1, 2)
    assert clock.avg_left_win_pct == pytest.approx((50 + 100 * 10 / 180) / 2)
    assert clock.avg_left_loss_pct == 0
    assert (clock.lost_on_time, clock.lost_on_time_ahead) == (2, 1)
    assert (clock.won_on_time, clock.won_on_time_behind) == (1, 1)


def test_clock_stats_with_no_timed_games():
    clock = clock_stats([make_game(time_class="daily", base_seconds=None, my_clock=None)])
    assert clock.games == 0 and clock.avg_left_win_pct is None


def test_expected_score():
    assert expected_score(1000, 1000) == 0.5
    assert expected_score(1400, 1000) == pytest.approx(10 / 11)


def test_pregame_ratings_undo_the_games_rating_change():
    games = [
        make_game("win", minutes=0, my_rating=1008, opp_rating=992),  # first game: no rating before it
        make_game("loss", minutes=5, my_rating=1000, opp_rating=1058),  # lost 8 points
        make_game("win", minutes=10, rated=False, my_rating=1000, opp_rating=1200),
    ]
    assert [(mine, opp) for _, mine, opp in pregame_ratings(games)] == [
        (1008, 1050),
        (1000, 1200),
    ]


def test_rating_gap_stats():
    games = [
        make_game(minutes=0, my_rating=1000),
        make_game("loss", minutes=5, my_rating=992, opp_rating=1308),  # opponent 300 above before the game
        make_game("win", minutes=10, my_rating=1000, opp_rating=995),  # 3 below
    ]
    buckets = {b.record.label: b for b in rating_gap_stats(games)}
    assert list(buckets)[0] == "-200 or less" and list(buckets)[-1] == "+200 or more"
    assert buckets["+200 or more"].record.losses == 1
    assert buckets["±24"].record.wins == 1
    assert buckets["±24"].expected_pct == pytest.approx(100 * expected_score(992, 1003))
    assert buckets["-99 to -25"].expected_pct is None


def test_monthly_stats_fills_gaps():
    games = [
        make_game(minutes=0),
        make_game("loss", minutes=60 * 24 * 62),  # two months later
    ]
    months = monthly_stats(games)
    assert [(r.label, r.games) for r in months] == [("2026-03", 1), ("2026-04", 0), ("2026-05", 1)]
    assert monthly_stats([]) == []


def test_hourly_stats_uses_time_zone_and_skips_daily():
    games = [
        make_game(minutes=0),  # 12:00 UTC
        make_game("loss", minutes=60),  # 13:00 UTC
        make_game(time_class="daily"),
    ]
    hours = hourly_stats(games, tz=timezone(timedelta(hours=-5)))
    assert len(hours) == 24
    assert (hours[7].wins, hours[8].losses) == (1, 1)
    blocks = hourly_stats(games, tz=timezone.utc, hours_per_bucket=3)
    assert [r.label for r in blocks] == ["0", "3", "6", "9", "12", "15", "18", "21"]
    assert blocks[4].games == 2


def test_streak_stats():
    results = ["win", "win", "win", "loss", "draw", "loss", "loss"]
    games = [make_game(result, minutes=10 * i) for i, result in enumerate(results)]
    streaks = streak_stats(games)
    assert (streaks.longest_win, streaks.longest_loss, streaks.current) == (3, 2, ("loss", 2))
    assert (streaks.after_win.wins, streaks.after_win.losses) == (2, 1)
    assert (streaks.after_loss.draws, streaks.after_loss.losses) == (1, 1)


def test_tilt_ignores_games_after_a_long_break():
    games = [make_game("loss", minutes=0), make_game("win", minutes=61)]
    assert streak_stats(games).after_loss.games == 0


def test_summarize_on_no_games():
    insights = summarize([])
    assert insights.months == [] and insights.streaks.current is None
    assert all(r.games == 0 for r in insights.lengths + insights.hours)
