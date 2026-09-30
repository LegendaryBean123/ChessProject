from datetime import datetime, timezone

from chessstats.models import Game
from chessstats.report import format_moves, render_tree
from chessstats.tree import build_tree


def make_game(moves: str, family: str, result: str = "win") -> Game:
    return Game(
        url="https://www.chess.com/game/live/1",
        end_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_class="blitz",
        rated=True,
        color="white",
        result=result,
        my_rating=1000,
        opp_rating=1000,
        opening=family,
        opening_family=family,
        eco=None,
        pgn="",
        moves=tuple(moves.split()),
    )


def child(node, move):
    return next(c for c in node.children if c.moves[-1] == move)


def test_splits_on_first_move_even_when_one_family():
    root = build_tree([make_game("e4 c5", "Sicilian Defense")] * 3)
    assert [c.moves for c in root.children] == [("e4",)]
    assert root.family is None


def test_branch_stops_where_family_is_decided():
    games = (
        [make_game("e4 e5 Nf3 Nc6 Bc4 Bc5", "Italian Game")] * 3
        + [make_game("e4 e5 Nf3 Nc6 Bb5 a6", "Ruy Lopez Opening")] * 2
        + [make_game("e4 c5 Nf3", "Sicilian Defense")]
    )
    e4 = child(build_tree(games), "e4")
    assert e4.games == 6 and e4.family is None

    sicilian = child(e4, "c5")
    assert (sicilian.family, sicilian.children) == ("Sicilian Defense", [])

    nc6 = child(child(child(e4, "e5"), "Nf3"), "Nc6")
    italian, ruy = nc6.children
    assert (italian.moves[-1], italian.family, italian.games) == ("Bc4", "Italian Game", 3)
    assert (ruy.moves[-1], ruy.family, ruy.games) == ("Bb5", "Ruy Lopez Opening", 2)


def test_stops_when_one_family_dominates_despite_transposed_names():
    games = [make_game("d4 d5 c4 dxc4", "Queen's Gambit Accepted")] * 9 + [
        make_game("d4 d5 c4 dxc4", "Queen's Gambit Declined")
    ]
    d4 = child(build_tree(games), "d4")
    assert d4.family == "Queen's Gambit Accepted"  # a 90% share is enough
    assert d4.children == []


def test_keeps_splitting_below_dominant_share():
    games = [make_game("d4 d5 c4", "Queen's Gambit Accepted")] * 8 + [make_game("d4 d5 Bf4", "London System")] * 2
    d4 = child(build_tree(games), "d4")
    assert d4.family is None
    assert d4.top_family == "Queen's Gambit Accepted" and d4.top_share == 0.8


def test_unknown_openings_do_not_block_a_branch():
    games = [make_game("e4 c5", "Sicilian Defense"), make_game("e4 c5", "Unknown")]
    assert child(build_tree(games), "e4").family == "Sicilian Defense"


def test_results_are_counted_per_node():
    games = [
        make_game("e4 e5", "A Game", "win"),
        make_game("e4 c5", "B Defense", "draw"),
        make_game("e4 c5", "B Defense", "loss"),
    ]
    e4 = child(build_tree(games), "e4")
    assert (e4.games, e4.wins, e4.draws, e4.losses) == (3, 1, 1, 1)
    assert e4.score_pct == 50.0


def test_games_without_moves_are_ignored():
    root = build_tree([make_game("", "Unknown"), make_game("d4", "Queen's Pawn Opening")])
    assert root.games == 1


def test_format_moves():
    assert format_moves(("e4", "e5", "Nf3"), 0) == "1.e4 e5 2.Nf3"
    assert format_moves(("e5", "Nf3", "Nc6"), 1) == "1...e5 2.Nf3 Nc6"
    assert format_moves(("Bc4",), 4) == "3.Bc4"


def test_render_tree_layout():
    games = (
        [make_game("e4 e5 Nf3 Nc6 Bc4", "Italian Game")] * 3
        + [make_game("e4 e5 Nf3 Nc6 Bb5", "Ruy Lopez Opening")] * 2
        + [make_game("e4 e5 Nf3 Nc6 d4", "Scotch Game")]
        + [make_game("d4 d5", "Queen's Pawn Opening")] * 2
    )
    text = render_tree("white", build_tree(games), min_games=2)
    lines = [line.rstrip() for line in text.splitlines()]

    assert lines[0] == "Opening tree, as White (branches with at least 2 games)"
    # Every 1.e4 game continued 1...e5 2.Nf3 Nc6, so those moves fold onto one line.
    assert any(line.lstrip().startswith("1.e4 e5 2.Nf3 Nc6 ") for line in lines)
    assert any("├─ 3.Bc4" in line and line.endswith("Italian Game") for line in lines)
    assert any("├─ 3.Bb5" in line and line.endswith("Ruy Lopez Opening") for line in lines)
    assert any("└─ (other lines: 1)" in line for line in lines)
    assert any(line.lstrip().startswith("1.d4") and line.endswith("Queen's Pawn Opening") for line in lines)


def test_render_tree_labels_mixed_dead_ends():
    games = [make_game("e4 e5 Nf3", "Italian Game")] * 3 + [make_game("e4 e5 Bc4", "Bishop's Opening")] * 2
    text = render_tree("white", build_tree(games), min_games=4)
    assert "1.e4 e5" in text
    assert "mixed: mostly Italian Game (60%)" in text
    assert "(other lines" not in text


def test_render_tree_with_nothing_big_enough():
    text = render_tree("black", build_tree([make_game("e4", "King's Pawn Opening")]), min_games=5)
    assert text.endswith("(no branches with at least 5 games)")
