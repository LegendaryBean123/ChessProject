from chessstats.analysis import OpeningStats
from chessstats.insights import AHEAD_MATERIAL, LOW_TIME_SHARE, WIN_LOSS_ENDINGS, Insights, Record
from chessstats.tree import TreeNode

OPENING_WIDTH = 32

# --stats shows this many of the most recent months of activity.
ACTIVITY_MONTHS = 12


def render_openings(by_color: dict[str, list[OpeningStats]], top: int) -> str:
    sections = [_render_table(color, stats[:top]) for color, stats in by_color.items()]
    return "\n\n".join(sections)


def _render_table(color: str, stats: list[OpeningStats]) -> str:
    lines = [f"Most played openings, as {color.capitalize()}"]
    if not stats:
        lines.append("  (no games)")
        return "\n".join(lines)

    lines.append(
        f"  {'Opening':<{OPENING_WIDTH}} {'Games':>5}   {'W / D / L':<13} {'Win%':>6} {'Score%':>7} {'Opp avg':>7}"
    )
    for s in stats:
        wdl = f"{s.wins}/{s.draws}/{s.losses}"
        lines.append(
            f"  {_truncate(s.opening):<{OPENING_WIDTH}} {s.games:>5}   {wdl:<13} "
            f"{s.win_pct:>5.1f}% {s.score_pct:>6.1f}% {s.avg_opp_rating:>7.0f}"
        )
    return "\n".join(lines)


def render_tree(color: str, root: TreeNode, min_games: int) -> str:
    """Draw the move tree as indented text, hiding branches with fewer than `min_games` games."""
    title = f"Opening tree, as {color.capitalize()} (branches with at least {min_games} games)"
    visible, hidden = _split_children(root, min_games)
    if not visible:
        return f"{title}\n  (no branches with at least {min_games} games)"

    rows: list[tuple[str, TreeNode | None, int]] = []
    for i, child in enumerate(visible):
        if i > 0:
            rows.append(("", None, 0))
        _tree_rows(child, 0, "", "", min_games, rows)
    if hidden:
        rows.append(("", None, 0))
        rows.append((f"(other first moves: {len(hidden)})", None, sum(c.games for c in hidden)))

    width = max(len(label) for label, _, _ in rows)
    lines = [title, f"  {'':<{width}}  {'Games':>5}   {'W / D / L':<13} {'Win%':>6} {'Score%':>7}  Opening"]
    for label, node, games in rows:
        if node is None:
            lines.append(f"  {label:<{width}}  {games:>5}" if games else "")
            continue
        wdl = f"{node.wins}/{node.draws}/{node.losses}"
        lines.append(
            f"  {label:<{width}}  {node.games:>5}   {wdl:<13} "
            f"{node.win_pct:>5.1f}% {node.score_pct:>6.1f}%  {_opening_label(node, min_games)}".rstrip()
        )
    return "\n".join(lines)


def format_moves(moves: tuple[str, ...], start_ply: int) -> str:
    """('e5', 'Nf3', 'Nc6') from ply 1 -> '1...e5 2.Nf3 Nc6'."""
    parts = []
    for ply, move in enumerate(moves, start=start_ply):
        number = ply // 2 + 1
        if ply % 2 == 0:
            parts.append(f"{number}.{move}")
        elif ply == start_ply:
            parts.append(f"{number}...{move}")
        else:
            parts.append(move)
    return " ".join(parts)


def _tree_rows(node, start_ply, lead, indent, min_games, rows) -> None:
    # Fold runs where every game played the same next move onto one line.
    while node.family is None and len(node.children) == 1 and node.children[0].games == node.games:
        node = node.children[0]
    rows.append((lead + format_moves(node.moves[start_ply:], start_ply), node, node.games))

    visible, hidden = _split_children(node, min_games)
    if not visible:
        return  # a lone "(other lines)" row would add nothing
    for i, child in enumerate(visible):
        last = i == len(visible) - 1 and not hidden
        _tree_rows(
            child,
            len(node.moves),
            indent + ("└─ " if last else "├─ "),
            indent + ("   " if last else "│  "),
            min_games,
            rows,
        )
    if hidden:
        label = f"(other lines: {len(hidden)})"
        rows.append((indent + "└─ " + label, None, sum(c.games for c in hidden)))


def _opening_label(node: TreeNode, min_games: int) -> str:
    """Name where the branch settles on an opening; for mixed dead ends, the most common one."""
    if node.family is not None:
        return node.family
    visible, _ = _split_children(node, min_games)
    if not visible:
        return f"mixed: mostly {node.top_family} ({node.top_share:.0%})"
    return ""


def _split_children(node: TreeNode, min_games: int) -> tuple[list[TreeNode], list[TreeNode]]:
    visible = [c for c in node.children if c.games >= min_games]
    hidden = [c for c in node.children if c.games < min_games]
    return visible, hidden


def render_stats(insights: Insights) -> str:
    """Every section of --stats as text."""
    sections = [
        _render_endings(insights),
        _render_records("Game length", "Moves", insights.lengths),
        _render_clock(insights),
        _render_rating_gaps(insights),
        _render_streaks(insights),
        _render_records(
            "Time of day (when games ended, this computer's time zone; daily games left out)",
            "Hours",
            [_hour_range(r, insights.hours) for r in insights.hours],
        ),
        _render_records(
            f"Activity (last {ACTIVITY_MONTHS} months)" if len(insights.months) > ACTIVITY_MONTHS else "Activity",
            "Month",
            insights.months[-ACTIVITY_MONTHS:],
        ),
    ]
    return "\n\n".join(sections)


def _render_endings(insights: Insights) -> str:
    endings = insights.endings
    wins, losses = dict(endings.wins), dict(endings.losses)
    names = [*WIN_LOSS_ENDINGS, *sorted((wins.keys() | losses.keys()) - set(WIN_LOSS_ENDINGS))]
    lines = ["How games end", f"  {'':<14} {'Wins':>6} {'Losses':>7}"]
    for name in names:
        lines.append(f"  {name.capitalize():<14} {wins.get(name, 0):>6} {losses.get(name, 0):>7}")
    if endings.draws:
        lines.append("  Draws: " + ", ".join(f"{count} {name}" for name, count in endings.draws))
    return "\n".join(lines)


def _render_clock(insights: Insights) -> str:
    clock = insights.clock
    title = f"Clock ({clock.games:,} timed games)"
    if not clock.games:
        return f"{title}\n  (no timed games with clock times)"
    low = clock.low_time
    return "\n".join(
        [
            title,
            "  Clock left at the end, as a share of the starting time: "
            f"{_pct(clock.avg_left_win_pct, 0)} in wins, {_pct(clock.avg_left_loss_pct, 0)} in losses",
            f"  Low on time (under {LOW_TIME_SHARE:.0%} left): {low.games} games, "
            f"{low.wins}/{low.draws}/{low.losses}, score {_pct(low.score_pct)}",
            f"  Lost on time: {clock.lost_on_time} games, "
            f"{clock.lost_on_time_ahead} while {AHEAD_MATERIAL}+ points of material ahead",
            f"  Won on time: {clock.won_on_time} games, "
            f"{clock.won_on_time_behind} while {AHEAD_MATERIAL}+ points of material behind",
        ]
    )


def _render_rating_gaps(insights: Insights) -> str:
    lines = [
        "Score vs opponent rating (ratings before each game, estimated)",
        f"  {'Opponent':<14} {'Games':>5}   {'W / D / L':<13} {'Score%':>7} {'Expected':>9}",
    ]
    for bucket in insights.rating_gaps:
        r = bucket.record
        lines.append(
            f"  {r.label:<14} {r.games:>5}   {_wdl(r):<13} {_pct(r.score_pct):>7} {_pct(bucket.expected_pct):>9}"
        )
    return "\n".join(lines)


def _render_streaks(insights: Insights) -> str:
    streaks = insights.streaks
    current = "none"
    if streaks.current:
        result, length = streaks.current
        current = f"{length} {result}{'' if length == 1 else 'es' if result == 'loss' else 's'}"
    after = [
        f"{r.label.lower()} {_wdl(r)} ({_pct(r.score_pct)})" for r in (streaks.after_win, streaks.after_loss)
    ]
    return "\n".join(
        [
            "Streaks",
            f"  Longest winning streak: {streaks.longest_win}   Longest losing streak: {streaks.longest_loss}"
            f"   Current: {current}",
            f"  Next game within an hour: {after[0]}, {after[1]}",
        ]
    )


def _render_records(title: str, label: str, records: list[Record]) -> str:
    lines = [title, f"  {label:<14} {'Games':>5}   {'W / D / L':<13} {'Win%':>6} {'Score%':>7}"]
    for r in records:
        win_pct = 100 * r.wins / r.games if r.games else None
        lines.append(f"  {r.label:<14} {r.games:>5}   {_wdl(r):<13} {_pct(win_pct):>6} {_pct(r.score_pct):>7}")
    return "\n".join(lines)


def _hour_range(r: Record, hours: list[Record]) -> Record:
    """Relabel an hour bucket "9" as "09:00-11:59" (for 3-hour buckets)."""
    start = int(r.label)
    end = start + 24 // len(hours) - 1
    return Record(f"{start:02d}:00-{end:02d}:59", r.wins, r.draws, r.losses)


def _wdl(r: Record) -> str:
    return f"{r.wins}/{r.draws}/{r.losses}"


def _pct(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}%"


def _truncate(text: str) -> str:
    if len(text) <= OPENING_WIDTH:
        return text
    return text[: OPENING_WIDTH - 3] + "..."
