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
    return Game(
        url=raw["url"],
        end_time=datetime.fromtimestamp(raw["end_time"], tz=timezone.utc),
        time_class=raw["time_class"],
        rated=raw.get("rated", False),
        color=color,
        result=normalize_result(me["result"]),
        my_rating=me.get("rating", 0),
        opp_rating=opp.get("rating", 0),
        opening=opening_name(slug),
        opening_family=opening_family(slug),
        eco=pgn_header(pgn, "ECO"),
        pgn=pgn,
        moves=pgn_moves(pgn),
        opponent=opp.get("username", ""),
    )


def normalize_result(result: str) -> str:
    if result == "win":
        return "win"
    if result in DRAW_RESULTS:
        return "draw"
    return "loss"


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
