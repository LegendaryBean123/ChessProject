import json
from pathlib import Path

import pytest

from chessstats.models import (
    normalize_result,
    opening_family,
    opening_name,
    opening_slug,
    parse_game,
    parse_games,
    pgn_moves,
)

FIXTURE = Path(__file__).parent / "fixtures" / "month.json"
USER = "LegendaryBean123"


@pytest.fixture
def raw_games():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["games"]


def test_parse_games_skips_variants(raw_games):
    games = parse_games(raw_games, USER)
    assert len(raw_games) == 8
    assert len(games) == 7  # the three-check game is dropped


def test_parse_game_from_players_point_of_view(raw_games):
    by_url = {g.url: g for g in parse_games(raw_games, USER)}

    white_win = by_url["https://www.chess.com/game/live/100264913410"]
    assert (white_win.color, white_win.result) == ("white", "win")
    assert (white_win.my_rating, white_win.opp_rating) == (425, 374)
    assert white_win.opening_family == "Petrov's Defense"
    assert white_win.eco == "C42"

    black_loss = by_url["https://www.chess.com/game/live/100230811906"]
    assert (black_loss.color, black_loss.result) == ("black", "loss")
    assert black_loss.opening_family == "Scandinavian Defense"

    draw = by_url["https://www.chess.com/game/live/53978943495"]
    assert draw.result == "draw"

    abandoned = by_url["https://www.chess.com/game/live/100767110076"]
    assert abandoned.result == "loss"


def test_username_match_is_case_insensitive(raw_games):
    assert parse_games(raw_games, USER.lower()) == parse_games(raw_games, USER.upper())


def test_game_without_player_is_skipped(raw_games):
    assert parse_game(raw_games[0], "someone-else") is None


def test_undefined_opening_is_unknown(raw_games):
    by_url = {g.url: g for g in parse_games(raw_games, USER)}
    game = by_url["https://www.chess.com/game/live/100230842972"]
    assert game.opening == game.opening_family == "Unknown"


def test_missing_eco_is_unknown(raw_games):
    raw = dict(raw_games[0])
    del raw["eco"]
    assert parse_game(raw, USER).opening_family == "Unknown"


@pytest.mark.parametrize(
    "result, expected",
    [
        ("win", "win"),
        ("agreed", "draw"),
        ("repetition", "draw"),
        ("stalemate", "draw"),
        ("insufficient", "draw"),
        ("50move", "draw"),
        ("timevsinsufficient", "draw"),
        ("checkmated", "loss"),
        ("resigned", "loss"),
        ("timeout", "loss"),
        ("abandoned", "loss"),
    ],
)
def test_normalize_result(result, expected):
    assert normalize_result(result) == expected


@pytest.mark.parametrize(
    "slug, family",
    [
        ("Sicilian-Defense-Alapin-Variation", "Sicilian Defense"),
        ("Italian-Game-Two-Knights-Defense", "Italian Game"),
        ("Four-Knights-Game-Spanish-Variation-Classical-Variation", "Four Knights Game"),
        ("Queens-Gambit-Accepted-Central-Variation", "Queen's Gambit Accepted"),
        ("Queens-Gambit-Declined-3.e3", "Queen's Gambit Declined"),
        ("Queens-Gambit", "Queen's Gambit"),
        ("Kings-Pawn-Opening-1...e5", "King's Pawn Opening"),
        ("Kings-Indian-Attack...3.Bg2-e5", "King's Indian Attack"),
        ("Queens-Pawn-Opening-Accelerated-London-System", "Queen's Pawn Opening"),
        ("Englund-Gambit-2.dxe5", "Englund Gambit"),
        ("Van-t-Kruijs-Opening-1...e5", "Van't Kruijs Opening"),
        ("Caro-Kann-Defense-Advance-Variation", "Caro-Kann Defense"),
        ("Modern-Defense-with-1-d4-2.c4-Bg7", "Modern Defense"),
        ("Italian-Game-Traxler-Counterattack", "Italian Game"),
        ("Giuoco-Piano-Game-Four-Knights-Game-5.O-O", "Italian Game"),
        ("Alapin-Sicilian-Defense-2...d5", "Sicilian Defense"),
        ("Closed-Sicilian-Defense-Grand-Prix-Attack", "Sicilian Defense"),
        ("Bogo-Indian-Defense", "Bogo-Indian Defense"),
    ],
)
def test_opening_family(slug, family):
    assert opening_family(slug) == family


def test_opening_name_keeps_variation():
    slug = opening_slug("https://www.chess.com/openings/Petrovs-Defense-Classical-Variation")
    assert opening_name(slug) == "Petrov's Defense Classical Variation"


def test_pgn_moves_strips_numbers_clocks_and_result():
    pgn = (
        '[Event "Live Chess"]\n[Result "0-1"]\n\n'
        "1. e4 {[%clk 0:09:56.9]} 1... e6 {[%clk 0:09:59]} 2. Nf3 {[%clk 0:09:55.4]} "
        "2... Nf6 {[%clk 0:09:57.9]} 3. O-O-O {[%clk 0:09:54.3]} 3... Nxe4+ 0-1\n"
    )
    assert pgn_moves(pgn) == ("e4", "e6", "Nf3", "Nf6", "O-O-O", "Nxe4+")


def test_pgn_moves_empty_for_custom_start_position():
    pgn = '[SetUp "1"]\n[FEN "8/8/8/8/8/8/8/K6k w - - 0 1"]\n\n1. Kb2 *'
    assert pgn_moves(pgn) == ()


def test_parsed_game_has_moves(raw_games):
    assert all(game.moves[:1] == ("e4",) for game in parse_games(raw_games, USER))


@pytest.mark.parametrize(
    "url",
    [None, "", "https://www.chess.com/openings/Undefined", "https://example.com/other"],
)
def test_opening_slug_invalid(url):
    assert opening_slug(url) is None
