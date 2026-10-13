"""Build the data for the HTML report and write it into the page template."""

import json
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path

import chess

from chessstats.analysis import COLORS, OpeningStats, filter_games, opening_stats
from chessstats.insights import AHEAD_MATERIAL, LOW_TIME_SHARE, Insights, Record, summarize
from chessstats.models import Game
from chessstats.pipeline import DEFAULT_RANGE, RANGE_LABELS
from chessstats.report import format_moves
from chessstats.tree import TreeNode, build_tree

TEMPLATE = "templates/report.html"
DATA_PLACEHOLDER = "__CHESSSTATS_DATA__"
CONFIG_PLACEHOLDER = "__CHESSSTATS_CONFIG__"

# Openings need at least this many games to count as a best or worst opening.
BEST_WORST_MIN_GAMES = 10


def build_payload(
    username: str,
    games: list[Game],
    min_games: int,
    range_label: str | None = None,
    since: tuple[int, int] | None = None,
) -> dict:
    """Everything the page shows, for "all" games and for each speed played.

    `range_label` describes which months were included, e.g. "This year", and `since`
    is the first of them as (year, month), or None for every month.
    """
    time_classes = sorted({g.time_class for g in games}, key=_time_class_order)
    dates = [g.end_time for g in games]
    return {
        "player": username,
        "rangeLabel": range_label,
        "since": f"{since[0]}-{since[1]:02d}" if since else None,
        "timeZone": _utc_offset(),
        "lowTimePct": round(100 * LOW_TIME_SHARE),
        "aheadMaterial": AHEAD_MATERIAL,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totalGames": len(games),
        "firstDate": min(dates).date().isoformat() if dates else None,
        "lastDate": max(dates).date().isoformat() if dates else None,
        "minGames": min_games,
        "bestWorstMinGames": BEST_WORST_MIN_GAMES,
        "timeClasses": ["all", *time_classes],
        "views": {
            tc: _view(filter_games(games, None if tc == "all" else tc), min_games)
            for tc in ["all", *time_classes]
        },
        "ratings": _rating_history(games),
    }


def render_page(payload: dict | None, server: bool) -> str:
    """The report page. `payload` may be None for an empty page that asks for a username.

    `server` tells the page whether it can look up other players from the local server.
    """
    config = {"server": server, "ranges": RANGE_LABELS, "defaultRange": DEFAULT_RANGE}
    template = files("chessstats").joinpath(TEMPLATE).read_text(encoding="utf-8")
    return template.replace(CONFIG_PLACEHOLDER, _json_for_html(config)).replace(
        DATA_PLACEHOLDER, _json_for_html(payload)
    )


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_page(payload, server=False), encoding="utf-8")


def _view(games: list[Game], min_games: int) -> dict:
    stats = opening_stats(games)
    results = [g.result for g in games]
    view = {
        "games": len(games),
        "wins": results.count("win"),
        "draws": results.count("draw"),
        "losses": results.count("loss"),
        **_best_and_worst(stats),
        "insights": _insights(summarize(games)),
    }
    for color in COLORS:
        color_games = [g for g in games if g.color == color]
        root = build_tree(color_games)
        view[color] = {
            "games": len(color_games),
            "openings": [_stats_row(s) for s in stats[color]],
            "tree": [_tree_node(child, 0, chess.Board(), min_games) for child in root.children if child.games >= min_games],
            "otherFirstMoves": _other(root, min_games),
        }
    return view


def _best_and_worst(stats: dict[str, list[OpeningStats]]) -> dict:
    candidates = [s for color in COLORS for s in stats[color] if s.games >= BEST_WORST_MIN_GAMES]
    if not candidates:
        return {"best": None, "worst": None}
    ranked = sorted(candidates, key=lambda s: (s.score_pct, s.games))
    return {"best": _stats_row(ranked[-1]), "worst": _stats_row(ranked[0])}


def _insights(insights: Insights) -> dict:
    clock, streaks = insights.clock, insights.streaks
    return {
        "endings": {
            "wins": [list(pair) for pair in insights.endings.wins],
            "losses": [list(pair) for pair in insights.endings.losses],
            "draws": [list(pair) for pair in insights.endings.draws],
        },
        "lengths": [_record(r) for r in insights.lengths],
        "clock": {
            "games": clock.games,
            "lowTime": _record(clock.low_time),
            "avgLeftWin": _round(clock.avg_left_win_pct),
            "avgLeftLoss": _round(clock.avg_left_loss_pct),
            "lostOnTime": clock.lost_on_time,
            "lostOnTimeAhead": clock.lost_on_time_ahead,
            "wonOnTime": clock.won_on_time,
            "wonOnTimeBehind": clock.won_on_time_behind,
        },
        "ratingGaps": [{**_record(b.record), "expectedPct": _round(b.expected_pct)} for b in insights.rating_gaps],
        "months": [_record(r) for r in insights.months],
        "hours": [_record(r) for r in insights.hours],
        "streaks": {
            "longestWin": streaks.longest_win,
            "longestLoss": streaks.longest_loss,
            "current": list(streaks.current) if streaks.current else None,
            "afterWin": _record(streaks.after_win),
            "afterLoss": _record(streaks.after_loss),
        },
    }


def _record(r: Record) -> dict:
    return {
        "label": r.label,
        "games": r.games,
        "wins": r.wins,
        "draws": r.draws,
        "losses": r.losses,
        "scorePct": _round(r.score_pct),
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _utc_offset() -> str:
    """This computer's offset from UTC, e.g. 'UTC-04:00'; time-of-day stats use this time zone."""
    offset = datetime.now().astimezone().utcoffset() or timedelta()
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _stats_row(s: OpeningStats) -> dict:
    return {
        "opening": s.opening,
        "color": s.color,
        "games": s.games,
        "wins": s.wins,
        "draws": s.draws,
        "losses": s.losses,
        "winPct": round(s.win_pct, 1),
        "scorePct": round(s.score_pct, 1),
        "avgOpp": round(s.avg_opp_rating),
    }


def _tree_node(node: TreeNode, start_ply: int, board: chess.Board, min_games: int) -> dict:
    """One visible tree row. `board` holds the position before this row's moves."""
    # Fold runs where every game played the same next move into one row, as in the text tree.
    while node.family is None and len(node.children) == 1 and node.children[0].games == node.games:
        node = node.children[0]

    board = board.copy(stack=False)
    last_move = None
    try:
        for san in node.moves[start_ply:]:
            last_move = board.push_san(san)
        fen = board.fen()
    except ValueError:
        fen = None  # chess.com move text we can't replay; the page shows no board

    visible = [c for c in node.children if c.games >= min_games]
    return {
        "label": format_moves(node.moves[start_ply:], start_ply),
        "line": format_moves(node.moves, 0),
        "games": node.games,
        "wins": node.wins,
        "draws": node.draws,
        "losses": node.losses,
        "scorePct": round(node.score_pct, 1),
        "family": node.family,
        "topFamily": node.top_family,
        "topShare": round(node.top_share, 2),
        "fen": fen,
        "lastMove": [chess.square_name(last_move.from_square), chess.square_name(last_move.to_square)]
        if last_move and fen
        else None,
        "recent": [_game_link(g) for g in node.recent_games],
        "children": [_tree_node(c, len(node.moves), board, min_games) for c in visible] if fen else [],
        "other": _other(node, min_games) if fen and visible else None,
    }


def _other(node: TreeNode, min_games: int) -> dict | None:
    hidden = [c for c in node.children if c.games < min_games]
    if not hidden:
        return None
    return {"lines": len(hidden), "games": sum(c.games for c in hidden)}


def _game_link(game: Game) -> dict:
    return {
        "url": game.url,
        "result": game.result,
        "date": game.end_time.date().isoformat(),
        "opponent": game.opponent,
        "oppRating": game.opp_rating,
        "timeClass": game.time_class,
    }


def _rating_history(games: list[Game]) -> dict[str, list[list]]:
    """Per speed, the rating after the last rated game of each day: [[YYYY-MM-DD, rating], ...]."""
    by_day: dict[str, dict[str, tuple[datetime, int]]] = {}
    for game in games:
        if not game.rated:
            continue
        day = game.end_time.date().isoformat()
        latest = by_day.setdefault(game.time_class, {}).get(day)
        if latest is None or game.end_time > latest[0]:
            by_day[game.time_class][day] = (game.end_time, game.my_rating)
    return {
        tc: [[day, rating] for day, (_, rating) in sorted(days.items())]
        for tc, days in sorted(by_day.items(), key=lambda item: _time_class_order(item[0]))
    }


def _time_class_order(time_class: str) -> int:
    order = ["bullet", "blitz", "rapid", "daily"]
    return order.index(time_class) if time_class in order else len(order)


def _json_for_html(payload: dict) -> str:
    """JSON that is safe inside a <script> tag: no '<', '>' or '&' can end it early."""
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
