from collections import Counter, defaultdict
from dataclasses import dataclass, field

from chessstats.models import UNKNOWN_OPENING, Game

# Safety cap on branch length, in plies (half-moves).
MAX_PLIES = 30

# A branch stops once this share of its games have the same opening family.
# chess.com names some games after a transposed move order, so 100% is too strict.
DOMINANT_SHARE = 0.9

# How many of each branch's most recent games to keep, e.g. for links to them.
RECENT_GAMES = 5


@dataclass
class TreeNode:
    """The games that reached one position, and the moves played from it.

    `moves` is the full move sequence from the start to this node. `top_family` is
    the most common opening family among its games and `top_share` its share (0-1).
    `family` is set only where the branch stops because one family dominates.
    `recent_games` holds up to RECENT_GAMES of its games, newest first.
    """

    moves: tuple[str, ...]
    games: int
    wins: int
    draws: int
    losses: int
    top_family: str
    top_share: float
    family: str | None = None
    children: list["TreeNode"] = field(default_factory=list)
    recent_games: list[Game] = field(default_factory=list)

    @property
    def win_pct(self) -> float:
        return 100 * self.wins / self.games

    @property
    def score_pct(self) -> float:
        return 100 * (self.wins + 0.5 * self.draws) / self.games


def build_tree(games: list[Game], max_plies: int = MAX_PLIES) -> TreeNode:
    """Branch the games move by move until each branch is essentially one opening family.

    The root holds every game and always splits on the first move. A branch stops
    when at least DOMINANT_SHARE of its games (ignoring unknown openings) share a
    family. Games that end before a branch stops are counted there but go no deeper.
    """
    return _build([g for g in games if g.moves], (), max_plies)


def _build(games: list[Game], path: tuple[str, ...], max_plies: int) -> TreeNode:
    results = [g.result for g in games]
    top_family, top_share = _top_family(games)
    node = TreeNode(
        moves=path,
        games=len(games),
        wins=results.count("win"),
        draws=results.count("draw"),
        losses=results.count("loss"),
        top_family=top_family,
        top_share=top_share,
        recent_games=sorted(games, key=lambda g: g.end_time, reverse=True)[:RECENT_GAMES],
    )

    if path and top_share >= DOMINANT_SHARE:
        node.family = top_family
        return node
    if len(path) >= max_plies:
        return node

    by_move: dict[str, list[Game]] = defaultdict(list)
    for game in games:
        if len(game.moves) > len(path):
            by_move[game.moves[len(path)]].append(game)

    node.children = [_build(group, path + (move,), max_plies) for move, group in by_move.items()]
    node.children.sort(key=lambda child: (-child.games, child.moves[-1]))
    return node


def _top_family(games: list[Game]) -> tuple[str, float]:
    """Most common known opening family and its share; unknown openings don't count."""
    known = Counter(g.opening_family for g in games if g.opening_family != UNKNOWN_OPENING)
    if not known:
        return UNKNOWN_OPENING, 1.0
    family, count = known.most_common(1)[0]
    return family, count / sum(known.values())
