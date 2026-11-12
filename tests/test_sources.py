"""Each source's raw file converts to the common columns."""

from pathlib import Path

import pytest

from tracker.history import COLUMNS
from tracker.sources import BY_NAME, SOURCES
from tracker.teams import slug, team_abbr

FIX = Path(__file__).parent / "fixtures"


def parse(name):
    return BY_NAME[name].parse((FIX / f"{name}.json").read_bytes())


def by_subject(rows):
    return {r["subject"]: r for r in rows}


def test_every_source_has_a_fixture_and_known_columns():
    assert len(SOURCES) == 7
    for src in SOURCES:
        rows = src.parse((FIX / f"{src.name}.json").read_bytes())
        assert rows, src.name
        for r in rows:
            assert set(r) <= set(COLUMNS), set(r) - set(COLUMNS)
            assert r["subject"] and r["item"] and r["market"]


def test_espn_standings():
    rows = by_subject(parse("espn_standings"))
    assert set(rows) == {"BOS", "NY", "OKC", "LAL", "LAC"}
    okc = rows["OKC"]
    assert okc["market"] == "standings" and okc["conference"] == "West"
    assert (okc["wins"], okc["losses"]) == (10, 1)
    assert okc["win_pct"] == pytest.approx(0.9091)
    assert okc["point_diff"] == pytest.approx(16.5)
    assert okc["streak"] == 6
    assert rows["LAL"]["streak"] == -2
    assert rows["BOS"]["conference"] == "East"


def test_polymarket_title_maps_teams_and_drops_other_and_closed():
    rows = by_subject(parse("polymarket_title"))
    assert set(rows) == {"OKC", "BOS", "LAL", "LAC"}
    assert rows["OKC"]["prob_pct"] == pytest.approx(31)
    assert rows["OKC"]["bid_pct"] == pytest.approx(30)
    assert rows["OKC"]["volume_usd"] == 1500000
    assert rows["LAC"]["item"] == "LA Clippers"


def test_polymarket_players_are_slugged():
    rows = by_subject(parse("polymarket_mvp"))
    assert set(rows) == {"shai-gilgeous-alexander", "nikola-jokic", "luka-doncic"}
    assert rows["nikola-jokic"]["item"] == "Nikola Jokić"
    assert rows["nikola-jokic"]["prob_pct"] == pytest.approx(25)
    assert by_subject(parse("polymarket_roy"))["cooper-flagg"]["prob_pct"] == pytest.approx(55)


def test_kalshi_title_keeps_current_season_and_uses_midpoint():
    rows = by_subject(parse("kalshi_title"))
    assert set(rows) == {"OKC", "BOS", "LAL", "LAC"}
    assert rows["OKC"]["prob_pct"] == pytest.approx(30)  # (29 + 31) / 2
    assert rows["OKC"]["volume_contracts"] == 500000
    assert rows["LAC"]["prob_pct"] == pytest.approx(2)  # no bid/ask -> last price
    assert rows["LAL"]["item"] == "Los Angeles Lakers"


def test_kalshi_dollar_fields():
    rows = by_subject(parse("kalshi_mvp"))
    assert rows["nikola-jokic"]["prob_pct"] == pytest.approx(28)
    assert rows["shai-gilgeous-alexander"]["bid_pct"] == pytest.approx(38)
    assert rows["shai-gilgeous-alexander"]["open_interest"] == 20000
    assert by_subject(parse("kalshi_roy"))["cooper-flagg"]["prob_pct"] == pytest.approx(54)


@pytest.mark.parametrize("name,abbr", [
    ("Oklahoma City Thunder", "OKC"), ("Thunder", "OKC"), ("Oklahoma City", "OKC"),
    ("Los Angeles L", "LAL"), ("Los Angeles C", "LAC"), ("LA Clippers", "LAC"),
    ("Portland Trail Blazers", "POR"), ("Philadelphia 76ers", "PHI"), ("New York", "NY"),
    ("Golden State", "GS"), ("Will the Spurs win the 2027 NBA Finals?", "SA"),
])
def test_team_names(name, abbr):
    assert team_abbr(name) == abbr


def test_team_codes_and_non_teams():
    assert team_abbr("", "GSW") == "GS"
    assert team_abbr("Los Angeles") is None  # ambiguous on its own
    assert team_abbr("Other") is None


def test_slug():
    assert slug("Luka Dončić") == "luka-doncic"
    assert slug("Shai Gilgeous-Alexander") == "shai-gilgeous-alexander"
