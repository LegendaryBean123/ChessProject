"""Pure functions from Games to stats beyond openings: endings, clocks, ratings, activity, streaks."""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta, tzinfo

from chessstats.models import Game

# Endings in display order; anything else is counted under "other".
WIN_LOSS_ENDINGS = ("checkmate", "resignation", "time", "abandoned")

# Game length buckets in moves, inclusive; None means no upper limit.
LENGTH_BUCKETS = ((1, 20), (21, 30), (31, 40), (41, 60), (61, None))

# A player is low on time with less than this share of the starting clock left.
LOW_TIME_SHARE = 0.1

# Material lead (in pawns) that counts as clearly ahead when a game is lost or won on time.
AHEAD_MATERIAL = 3

# Opponent rating minus the player's, inclusive; None means no limit.
RATING_GAP_BUCKETS = ((None, -200), (-199, -100), (-99, -25), (-24, 24), (25, 99), (100, 199), (200, None))

# The next game only counts toward "after a win/loss" if it ended within this long of the previous one.
TILT_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class Record:
    """Win/draw/loss counts for one group of games, e.g. one game length."""

    label: str
    wins: int = 0
    draws: int = 0
    losses: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def score_pct(self) -> float | None:
        if not self.games:
            return None
        return 100 * (self.wins + 0.5 * self.draws) / self.games


def record(label: str, games: list[Game]) -> Record:
    results = Counter(game.result for game in games)
    return Record(label, results["win"], results["draw"], results["loss"])


@dataclass(frozen=True)
class EndingStats:
    """How games ended: (ending, count) pairs, most common first."""

    wins: list[tuple[str, int]]
    losses: list[tuple[str, int]]
    draws: list[tuple[str, int]]


def ending_stats(games: list[Game]) -> EndingStats:
    def counts(result: str) -> list[tuple[str, int]]:
        counter = Counter(game.end_reason for game in games if game.result == result)
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))

    return EndingStats(counts("win"), counts("loss"), counts("draw"))


def length_stats(games: list[Game]) -> list[Record]:
    """W/D/L per game length. Games with no moves are left out."""
    return [
        record(_range_label(low, high), [g for g in games if g.moves and _in_range(g.full_moves, low, high)])
        for low, high in LENGTH_BUCKETS
    ]


@dataclass(frozen=True)
class ClockStats:
    """Clock stats for timed (non-daily) games that have clock times.

    `avg_left_win_pct` / `avg_left_loss_pct` are the average share of the starting
    clock the player had left, in percent. `low_time` covers games where the player
    finished with less than LOW_TIME_SHARE of it.
    """

    games: int
    low_time: Record
    avg_left_win_pct: float | None
    avg_left_loss_pct: float | None
    lost_on_time: int
    lost_on_time_ahead: int
    won_on_time: int
    won_on_time_behind: int


def clock_stats(games: list[Game]) -> ClockStats:
    timed = [g for g in games if g.base_seconds and g.my_clock is not None]

    def left_pct(game: Game) -> float:
        return 100 * min(game.my_clock / game.base_seconds, 1)

    def average_left(result: str) -> float | None:
        shares = [left_pct(g) for g in timed if g.result == result]
        return sum(shares) / len(shares) if shares else None

    lost_on_time = [g for g in timed if g.result == "loss" and g.end_reason == "time"]
    won_on_time = [g for g in timed if g.result == "win" and g.end_reason == "time"]
    return ClockStats(
        games=len(timed),
        low_time=record("Low on time", [g for g in timed if left_pct(g) < 100 * LOW_TIME_SHARE]),
        avg_left_win_pct=average_left("win"),
        avg_left_loss_pct=average_left("loss"),
        lost_on_time=len(lost_on_time),
        lost_on_time_ahead=sum(1 for g in lost_on_time if (g.material_diff or 0) >= AHEAD_MATERIAL),
        won_on_time=len(won_on_time),
        won_on_time_behind=sum(1 for g in won_on_time if (g.material_diff or 0) <= -AHEAD_MATERIAL),
    )


@dataclass(frozen=True)
class GapBucket:
    """Results against opponents rated `record.label` points above (or below) the player.

    `expected_pct` is the score the Elo formula predicts for these games.
    """

    record: Record
    expected_pct: float | None


def rating_gap_stats(games: list[Game]) -> list[GapBucket]:
    pregame = pregame_ratings(games)
    buckets = []
    for low, high in RATING_GAP_BUCKETS:
        group = [(g, mine, opp) for g, mine, opp in pregame if _in_range(opp - mine, low, high)]
        expected = [expected_score(mine, opp) for _, mine, opp in group]
        buckets.append(
            GapBucket(
                record(_gap_label(low, high), [g for g, _, _ in group]),
                100 * sum(expected) / len(expected) if expected else None,
            )
        )
    return buckets


def pregame_ratings(games: list[Game]) -> list[tuple[Game, int, int]]:
    """(game, player's rating, opponent's rating) before each game, where it can be worked out.

    chess.com stores ratings from after the game, so the winner always looks stronger.
    The player's rating before a rated game is the one after their previous rated game
    at the same speed; games with no earlier one are left out. The opponent is assumed
    to have lost what the player gained. Unrated games don't change ratings.
    """
    previous: dict[str, int] = {}
    ratings = []
    for game in sorted(games, key=lambda g: g.end_time):
        if not (game.my_rating and game.opp_rating):
            continue
        if not game.rated:
            ratings.append((game, game.my_rating, game.opp_rating))
            continue
        before = previous.get(game.time_class)
        previous[game.time_class] = game.my_rating
        if before is not None:
            ratings.append((game, before, game.opp_rating + game.my_rating - before))
    return ratings


def expected_score(my_rating: int, opp_rating: int) -> float:
    """The Elo formula's expected score (0-1) against an opponent."""
    return 1 / (1 + 10 ** ((opp_rating - my_rating) / 400))


def monthly_stats(games: list[Game]) -> list[Record]:
    """W/D/L per month labelled 'YYYY-MM', from the first game's month to the last, gaps included."""
    if not games:
        return []
    by_month: dict[tuple[int, int], list[Game]] = {}
    for game in games:
        by_month.setdefault((game.end_time.year, game.end_time.month), []).append(game)

    first, last = min(by_month), max(by_month)
    months = []
    year, month = first
    while (year, month) <= last:
        months.append(record(f"{year}-{month:02d}", by_month.get((year, month), [])))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def hourly_stats(games: list[Game], tz: tzinfo | None = None, hours_per_bucket: int = 1) -> list[Record]:
    """W/D/L by the hour each game ended, in `tz` (default: this computer's time zone).

    Daily games are left out because their end time says little about when they were played.
    Labels are start hours, e.g. "9" for 9:00-9:59 (or 9:00-11:59 with 3 hours per bucket).
    """
    live = [g for g in games if g.time_class != "daily"]
    hours = [g.end_time.astimezone(tz).hour for g in live]
    return [
        record(str(start), [g for g, hour in zip(live, hours) if start <= hour < start + hours_per_bucket])
        for start in range(0, 24, hours_per_bucket)
    ]


@dataclass(frozen=True)
class StreakStats:
    """Win/loss streaks (a draw ends both) and results in the game after a win or a loss.

    `current` is ("win" | "loss" | "draw", length) for the most recent games.
    `after_win` / `after_loss` only count a next game that ended within TILT_WINDOW
    of the previous one, and leave out daily games.
    """

    longest_win: int
    longest_loss: int
    current: tuple[str, int] | None
    after_win: Record
    after_loss: Record


def streak_stats(games: list[Game]) -> StreakStats:
    ordered = sorted(games, key=lambda g: g.end_time)
    longest = {"win": 0, "loss": 0, "draw": 0}
    current: tuple[str, int] | None = None
    for game in ordered:
        length = current[1] + 1 if current and current[0] == game.result else 1
        current = (game.result, length)
        longest[game.result] = max(longest[game.result], length)

    live = [g for g in ordered if g.time_class != "daily"]
    pairs = [(prev, nxt) for prev, nxt in zip(live, live[1:]) if nxt.end_time - prev.end_time <= TILT_WINDOW]
    return StreakStats(
        longest_win=longest["win"],
        longest_loss=longest["loss"],
        current=current,
        after_win=record("After a win", [nxt for prev, nxt in pairs if prev.result == "win"]),
        after_loss=record("After a loss", [nxt for prev, nxt in pairs if prev.result == "loss"]),
    )


@dataclass(frozen=True)
class Insights:
    endings: EndingStats
    lengths: list[Record]
    clock: ClockStats
    rating_gaps: list[GapBucket]
    months: list[Record]
    hours: list[Record]
    streaks: StreakStats


def summarize(games: list[Game], tz: tzinfo | None = None, hours_per_bucket: int = 1) -> Insights:
    """Every stat in this module for one set of games."""
    return Insights(
        endings=ending_stats(games),
        lengths=length_stats(games),
        clock=clock_stats(games),
        rating_gaps=rating_gap_stats(games),
        months=monthly_stats(games),
        hours=hourly_stats(games, tz, hours_per_bucket),
        streaks=streak_stats(games),
    )


def _in_range(value: int, low: int | None, high: int | None) -> bool:
    return (low is None or value >= low) and (high is None or value <= high)


def _range_label(low: int, high: int | None) -> str:
    return f"{low}+" if high is None else f"{low}-{high}"


def _gap_label(low: int | None, high: int | None) -> str:
    if low is None:
        return f"{high} or less"
    if high is None:
        return f"+{low} or more"
    if low == -high:
        return f"±{high}"
    sign = "+" if low > 0 else ""
    return f"{sign}{low} to {sign}{high}"
