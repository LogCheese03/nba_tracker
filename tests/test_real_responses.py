"""Conversion of real responses saved from the first run (2026-11-12)."""

from pathlib import Path

import pytest

from tracker.sources import BY_NAME
from tracker.teams import ABBRS

REAL = Path(__file__).parent / "fixtures" / "real"


def parse(name):
    return BY_NAME[name].parse((REAL / f"{name}.json").read_bytes())


def test_espn_real_has_all_30_teams():
    rows = parse("espn_standings")
    assert {r["subject"] for r in rows} == ABBRS
    for r in rows:
        assert r["wins"] is not None and r["losses"] is not None
        assert 0 <= r["win_pct"] <= 1
        assert r["point_diff"] == pytest.approx(r["ppg"] - r["opp_ppg"])
        assert r["conference"] in ("East", "West")


def test_kalshi_title_real_maps_all_30_teams():
    rows = parse("kalshi_title")
    assert {r["subject"] for r in rows} == ABBRS
    assert 90 < sum(r["prob_pct"] for r in rows) < 115  # probabilities add up to about 100%


@pytest.mark.parametrize("name,minimum", [
    ("kalshi_mvp", 10), ("kalshi_roy", 10), ("polymarket_mvp", 10), ("polymarket_roy", 10)])
def test_award_markets_real(name, minimum):
    rows = parse(name)
    subjects = [r["subject"] for r in rows]
    assert len(rows) >= minimum
    assert len(subjects) == len(set(subjects))
    assert not any(s.startswith("tie") for s in subjects)
    assert all(r["prob_pct"] is not None and 0 <= r["prob_pct"] <= 100 for r in rows)


def test_exchanges_line_up_on_the_same_players():
    pm = {r["subject"] for r in parse("polymarket_mvp")}
    ks = {r["subject"] for r in parse("kalshi_mvp")}
    assert len(pm & ks) >= 20


def test_polymarket_title_real_maps_all_30_teams():
    rows = parse("polymarket_title")
    assert {r["subject"] for r in rows} == ABBRS
    assert 90 < sum(r["prob_pct"] for r in rows) < 115
    kalshi = {r["subject"]: r["prob_pct"] for r in parse("kalshi_title")}
    # the two exchanges should roughly agree on every team
    assert all(abs(r["prob_pct"] - kalshi[r["subject"]]) < 10 for r in rows)
