"""NBA team lookup: maps any team name a source uses to one ESPN abbreviation.

ESPN abbreviations are the team key (``subject``) for every source, so the same
team lines up across ESPN, Polymarket and Kalshi and from one day to the next.
"""

from __future__ import annotations

import re
import unicodedata

# (ESPN abbreviation, city, nickname, conference, extra aliases)
TEAMS = [
    ("ATL", "Atlanta", "Hawks", "East", []),
    ("BOS", "Boston", "Celtics", "East", []),
    ("BKN", "Brooklyn", "Nets", "East", ["BRK"]),
    ("CHA", "Charlotte", "Hornets", "East", ["CHO"]),
    ("CHI", "Chicago", "Bulls", "East", []),
    ("CLE", "Cleveland", "Cavaliers", "East", ["Cavs"]),
    ("DAL", "Dallas", "Mavericks", "West", ["Mavs"]),
    ("DEN", "Denver", "Nuggets", "West", []),
    ("DET", "Detroit", "Pistons", "East", []),
    ("GS", "Golden State", "Warriors", "West", ["GSW"]),
    ("HOU", "Houston", "Rockets", "West", []),
    ("IND", "Indiana", "Pacers", "East", []),
    ("LAC", "LA", "Clippers", "West", ["Los Angeles C", "LA C", "Los Angeles Clippers"]),
    ("LAL", "Los Angeles", "Lakers", "West", ["Los Angeles L", "LA L", "LA Lakers"]),
    ("MEM", "Memphis", "Grizzlies", "West", []),
    ("MIA", "Miami", "Heat", "East", []),
    ("MIL", "Milwaukee", "Bucks", "East", []),
    ("MIN", "Minnesota", "Timberwolves", "West", ["Wolves"]),
    ("NO", "New Orleans", "Pelicans", "West", ["NOP"]),
    ("NY", "New York", "Knicks", "East", ["NYK"]),
    ("OKC", "Oklahoma City", "Thunder", "West", []),
    ("ORL", "Orlando", "Magic", "East", []),
    ("PHI", "Philadelphia", "76ers", "East", ["Sixers"]),
    ("PHX", "Phoenix", "Suns", "West", ["PHO"]),
    ("POR", "Portland", "Trail Blazers", "West", ["Blazers"]),
    ("SAC", "Sacramento", "Kings", "West", []),
    ("SA", "San Antonio", "Spurs", "West", ["SAS"]),
    ("TOR", "Toronto", "Raptors", "East", []),
    ("UTAH", "Utah", "Jazz", "West", ["UTA"]),
    ("WSH", "Washington", "Wizards", "East", ["WAS"]),
]

ABBRS = {t[0] for t in TEAMS}
CONFERENCE = {t[0]: t[3] for t in TEAMS}
FULL_NAME = {t[0]: (f"{t[1]} {t[2]}" if t[0] != "LAC" else "LA Clippers") for t in TEAMS}


def norm(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def slug(text: str) -> str:
    """Player key: 'Nikola Jokić' -> 'nikola-jokic'."""
    return norm(text).replace(" ", "-")


_EXACT: dict[str, str] = {}
for _abbr, _city, _nick, _conf, _aliases in TEAMS:
    for _name in [_abbr, _nick, f"{_city} {_nick}", *_aliases]:
        _EXACT[norm(_name)] = _abbr
    if _city not in ("Los Angeles", "LA"):  # the only shared city
        _EXACT[norm(_city)] = _abbr


def team_abbr(name: str | None, code: str | None = None) -> str | None:
    """Return the ESPN abbreviation for a team name, or None if it isn't a team.

    ``code`` is an optional short code (e.g. the end of a Kalshi ticker).
    """
    n = norm(name or "")
    if n in _EXACT:
        return _EXACT[n]
    # nickname anywhere in the text ("Will the Thunder win...", "OKC Thunder")
    for abbr, _city, nick, _conf, aliases in TEAMS:
        for word in [nick, *[a for a in aliases if len(a) > 4]]:
            if re.search(rf"\b{re.escape(norm(word))}\b", n):
                return abbr
    if code:
        c = norm(code).upper().replace(" ", "")
        if c in ABBRS:
            return c
        if norm(c) in _EXACT:
            return _EXACT[norm(c)]
    return None
