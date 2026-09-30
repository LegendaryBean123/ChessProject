from collections import defaultdict
from dataclasses import dataclass

from chessstats.models import Game

COLORS = ("white", "black")


@dataclass(frozen=True)
class OpeningStats:
    opening: str
    color: str
    games: int
    wins: int
    draws: int
    losses: int
    avg_opp_rating: float

    @property
    def win_pct(self) -> float:
        return 100 * self.wins / self.games

    @property
    def score_pct(self) -> float:
        """Chess scoring: a win is worth 1 point, a draw 0.5."""
        return 100 * (self.wins + 0.5 * self.draws) / self.games


def filter_games(games: list[Game], time_class: str | None = None) -> list[Game]:
    if time_class is None:
        return list(games)
    return [game for game in games if game.time_class == time_class]


def opening_stats(games: list[Game], min_games: int = 1) -> dict[str, list[OpeningStats]]:
    """Stats per opening family, split by colour and sorted by games played (most first)."""
    groups: dict[tuple[str, str], list[Game]] = defaultdict(list)
    for game in games:
        groups[(game.color, game.opening_family)].append(game)

    by_color: dict[str, list[OpeningStats]] = {color: [] for color in COLORS}
    for (color, opening), group in groups.items():
        if len(group) < min_games:
            continue
        by_color[color].append(_summarize(opening, color, group))

    for stats in by_color.values():
        stats.sort(key=lambda s: (-s.games, s.opening))
    return by_color


def _summarize(opening: str, color: str, games: list[Game]) -> OpeningStats:
    results = [game.result for game in games]
    return OpeningStats(
        opening=opening,
        color=color,
        games=len(games),
        wins=results.count("win"),
        draws=results.count("draw"),
        losses=results.count("loss"),
        avg_opp_rating=sum(game.opp_rating for game in games) / len(games),
    )
