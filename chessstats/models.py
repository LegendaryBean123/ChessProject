import re
from dataclasses import dataclass
from datetime import datetime, timezone

UNKNOWN_OPENING = "Unknown"

DRAW_RESULTS = {
    "agreed",
    "repetition",
    "stalemate",
    "insufficient",
    "50move",
    "timevsinsufficient",
}

# How a game ended, from chess.com's result codes. For a win the code comes from
# the loser's side ("checkmated", "timeout", ...); anything unlisted is "other".
END_REASONS = {
    "checkmated": "checkmate",
    "resigned": "resignation",
    "timeout": "time",
    "abandoned": "abandoned",
    "agreed": "agreement",
    "repetition": "repetition",
    "stalemate": "stalemate",
    "insufficient": "insufficient material",
    "50move": "50-move rule",
    "timevsinsufficient": "time vs insufficient material",
}

# Piece values for counting material in the final position.
PIECE_VALUES = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9}

# Words that end an opening's family name, e.g. "Sicilian Defense" in
# "Sicilian-Defense-Alapin-Variation".
FAMILY_END_WORDS = {
    "Opening",
    "Game",
    "Defense",
    "Gambit",
    "Attack",
    "System",
    "Countergambit",
    "Counterattack",
}

# chess.com's URL slugs drop apostrophes and hyphens from names.
NAME_FIXES = {
    "Queens ": "Queen's ",
    "Kings ": "King's ",
    "Bishops ": "Bishop's ",
    "Petrovs ": "Petrov's ",
    "Owens ": "Owen's ",
    "Alekhines ": "Alekhine's ",
    "Birds ": "Bird's ",
    "Van t ": "Van't ",
    "Caro Kann": "Caro-Kann",
    "Nimzo Indian": "Nimzo-Indian",
    "Semi Slav": "Semi-Slav",
    "Nimzowitsch Larsen": "Nimzowitsch-Larsen",
    "Richter Veresov": "Richter-Veresov",
    "Bogo Indian": "Bogo-Indian",
}

# chess.com names some lines as if they were separate openings.
FAMILY_ALIASES = {
    "Alapin Sicilian Defense": "Sicilian Defense",
    "Closed Sicilian Defense": "Sicilian Defense",
    "Giuoco Piano Game": "Italian Game",
}

# The move sequence in a slug starts at "..." or at a hyphen followed by a digit.
MOVES_START = re.compile(r"\.\.\.|-\d")

# PGN move text noise: {comments}, move numbers like "1." / "1...", and the result.
PGN_COMMENT = re.compile(r"\{[^}]*\}")
PGN_MOVE_NUMBER = re.compile(r"^\d+\.(\.\.)?$")
PGN_RESULTS = {"1-0", "0-1", "1/2-1/2", "*"}

# A move followed by its clock: "12. Nf3 {[%clk 0:02:31.4]}" (white) or "12... Nf6 {...}" (black).
PGN_CLOCK = re.compile(r"\d+\.(\.\.)? \S+ \{\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]\}")


@dataclass(frozen=True)
class Game:
    url: str
    end_time: datetime
    time_class: str
    rated: bool
    color: str
    result: str
    my_rating: int
    opp_rating: int
    opening: str
    opening_family: str
    eco: str | None
    pgn: str
    moves: tuple[str, ...] = ()
    opponent: str = ""
    end_reason: str = "other"
    base_seconds: int | None = None  # starting clock; None for daily games
    increment: int = 0
    my_clock: float | None = None  # seconds left after the player's last move
    opp_clock: float | None = None
    material_diff: int | None = None  # player's material minus the opponent's at the end

    @property
    def full_moves(self) -> int:
        """Game length in moves, e.g. 1.e4 e5 2.Nf3 is 2 moves."""
        return (len(self.moves) + 1) // 2


def parse_games(raw_games: list[dict], username: str) -> list[Game]:
    """Convert raw chess.com games into Games, keeping only standard chess."""
    games = (parse_game(raw, username) for raw in raw_games)
    return [game for game in games if game is not None]


def parse_game(raw: dict, username: str) -> Game | None:
    """Return the game from `username`'s point of view, or None if it should be skipped."""
    if raw.get("rules") != "chess":
        return None

    username = username.lower()
    if raw["white"]["username"].lower() == username:
        color, me, opp = "white", raw["white"], raw["black"]
    elif raw["black"]["username"].lower() == username:
        color, me, opp = "black", raw["black"], raw["white"]
    else:
        return None

    slug = opening_slug(raw.get("eco"))
    pgn = raw.get("pgn", "")
    result = normalize_result(me["result"])
    base_seconds, increment = parse_time_control(raw.get("time_control", ""))
    clocks = pgn_clocks(pgn)
    material = material_balance(raw.get("fen", ""))
    return Game(
        url=raw["url"],
        end_time=datetime.fromtimestamp(raw["end_time"], tz=timezone.utc),
        time_class=raw["time_class"],
        rated=raw.get("rated", False),
        color=color,
        result=result,
        my_rating=me.get("rating", 0),
        opp_rating=opp.get("rating", 0),
        opening=opening_name(slug),
        opening_family=opening_family(slug),
        eco=pgn_header(pgn, "ECO"),
        pgn=pgn,
        moves=pgn_moves(pgn),
        opponent=opp.get("username", ""),
        end_reason=END_REASONS.get(opp["result"] if result == "win" else me["result"], "other"),
        base_seconds=base_seconds,
        increment=increment,
        my_clock=clocks[color],
        opp_clock=clocks["black" if color == "white" else "white"],
        material_diff=None if material is None else material if color == "white" else -material,
    )


def normalize_result(result: str) -> str:
    if result == "win":
        return "win"
    if result in DRAW_RESULTS:
        return "draw"
    return "loss"


def parse_time_control(text: str) -> tuple[int | None, int]:
    """'180+2' -> (180, 2) and '600' -> (600, 0); daily games like '1/86400' -> (None, 0)."""
    match = re.fullmatch(r"(\d+)(?:\+(\d+))?", text)
    if not match:
        return None, 0
    return int(match.group(1)), int(match.group(2) or 0)


def pgn_clocks(pgn: str) -> dict[str, float | None]:
    """Seconds left on each side's clock after their last move; None if a side has no clock times."""
    clocks: dict[str, float | None] = {"white": None, "black": None}
    for match in PGN_CLOCK.finditer(pgn):
        black, hours, minutes, seconds = match.groups()
        clocks["black" if black else "white"] = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return clocks


def material_balance(fen: str) -> int | None:
    """White's material minus Black's in a FEN position (P=1, N=B=3, R=5, Q=9)."""
    if not fen:
        return None
    balance = 0
    for char in fen.split()[0]:
        value = PIECE_VALUES.get(char.lower(), 0)
        balance += value if char.isupper() else -value
    return balance


def opening_slug(eco_url: str | None) -> str | None:
    """'https://www.chess.com/openings/Italian-Game-...' -> 'Italian-Game-...'."""
    if not eco_url or "/openings/" not in eco_url:
        return None
    slug = eco_url.split("/openings/", 1)[1].strip("/")
    if not slug or slug == "Undefined":
        return None
    return slug


def opening_name(slug: str | None) -> str:
    """Full opening name including variation and moves."""
    if slug is None:
        return UNKNOWN_OPENING
    return _prettify(slug.replace("-", " "))


def opening_family(slug: str | None) -> str:
    """Opening name cut after the first family-ending word, e.g. 'Sicilian Defense'."""
    if slug is None:
        return UNKNOWN_OPENING
    match = MOVES_START.search(slug)
    words = (slug[: match.start()] if match else slug).split("-")

    family = []
    for i, word in enumerate(words):
        family.append(word)
        if word in FAMILY_END_WORDS:
            # Keep "Queen's Gambit Accepted" and "Declined" apart.
            if word == "Gambit" and i + 1 < len(words) and words[i + 1] in ("Accepted", "Declined"):
                family.append(words[i + 1])
            break
    name = _prettify(" ".join(family)) if family else UNKNOWN_OPENING
    return FAMILY_ALIASES.get(name, name)


def pgn_header(pgn: str, name: str) -> str | None:
    match = re.search(rf'^\[{name} "([^"]*)"\]', pgn, re.MULTILINE)
    return match.group(1) if match else None


def pgn_moves(pgn: str) -> tuple[str, ...]:
    """The game's moves in SAN, e.g. ('e4', 'e5', 'Nf3'). Empty for games from a custom position."""
    if pgn_header(pgn, "SetUp") == "1":
        return ()
    headers_end = pgn.find("\n\n")
    body = pgn[headers_end + 2 :] if headers_end != -1 else pgn
    tokens = PGN_COMMENT.sub(" ", body).split()
    return tuple(t for t in tokens if not PGN_MOVE_NUMBER.match(t) and t not in PGN_RESULTS)


def _prettify(name: str) -> str:
    name += " "
    for wrong, right in NAME_FIXES.items():
        name = name.replace(wrong, right)
    return name.strip()
