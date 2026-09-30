from chessstats.analysis import OpeningStats
from chessstats.tree import TreeNode

OPENING_WIDTH = 32


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


def _truncate(text: str) -> str:
    if len(text) <= OPENING_WIDTH:
        return text
    return text[: OPENING_WIDTH - 3] + "..."
