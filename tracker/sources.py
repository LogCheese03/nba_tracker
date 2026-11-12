"""The seven sources: how each one is downloaded and how its raw file becomes rows.

Every ``fetch_*`` function returns the exact bytes of the final response, which
the pipeline saves gzipped. Every ``parse_*`` function turns those bytes into a
list of rows with the common columns (see ``tracker.history.COLUMNS``). Parsers
use only the raw bytes, so the history can always be rebuilt from data/raw/.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

import requests

from .teams import CONFERENCE, FULL_NAME, slug, team_abbr

TIMEOUT = 30
HEADERS = {"User-Agent": "nba-tracker class project (github.com/LogCheese03/nba_tracker)"}

ESPN_STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _get(url: str, params: dict | None = None) -> requests.Response:
    last = None
    for _ in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # retry, then give up
            last = e
    raise last  # type: ignore[misc]


def _num(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


# --------------------------------------------------------------------------- ESPN


def fetch_espn_standings() -> bytes:
    return _get(ESPN_STANDINGS).content


def _streak(stat: dict) -> float | None:
    disp = str(stat.get("displayValue") or "")
    m = re.match(r"^\s*([WL])\s*(\d+)", disp, re.I)
    if m:
        n = int(m.group(2))
        return float(n if m.group(1).upper() == "W" else -n)
    return _num(stat.get("value"))


def parse_espn_standings(raw: bytes) -> list[dict]:
    data = json.loads(raw)
    rows = []
    groups = data.get("children") or [data]
    for group in groups:
        conf_name = (group.get("abbreviation") or group.get("name") or "")
        entries = (group.get("standings") or {}).get("entries") or []
        for e in entries:
            team = e.get("team") or {}
            abbr = team_abbr(team.get("displayName"), team.get("abbreviation"))
            if not abbr:
                continue
            stats = {s.get("name") or s.get("type"): s for s in e.get("stats") or []}

            def val(*names):
                for n in names:
                    if n in stats:
                        return _num(stats[n].get("value"))
                return None

            ppg, opp = val("avgPointsFor"), val("avgPointsAgainst")
            diff = val("differential")
            if diff is None and ppg is not None and opp is not None:
                diff = ppg - opp
            conf = "East" if "east" in conf_name.lower() else "West" if "west" in conf_name.lower() else CONFERENCE[abbr]
            rows.append({
                "subject": abbr,
                "item": team.get("displayName") or FULL_NAME[abbr],
                "market": "standings",
                "team": abbr,
                "conference": conf,
                "wins": val("wins"),
                "losses": val("losses"),
                "win_pct": val("winPercent", "winPct"),
                "games_back": val("gamesBehind"),
                "ppg": ppg,
                "opp_ppg": opp,
                "point_diff": diff,
                "streak": _streak(stats["streak"]) if "streak" in stats else None,
            })
    return rows


# --------------------------------------------------------------------- Polymarket

# Event slugs to try first; if none is open, the search below finds the event.
PM_SLUGS = {
    "title": ["2027-nba-champion", "nba-champion-2026-27", "2026-27-nba-champion"],
    "mvp": ["nba-mvp-2026-27", "2026-27-nba-mvp", "2027-nba-mvp", "nba-mvp-2027"],
    "roy": ["nba-rookie-of-the-year-2026-27", "2026-27-nba-rookie-of-the-year",
            "2027-nba-rookie-of-the-year", "nba-rookie-of-the-year-2027"],
}
PM_SEARCH = {
    "title": ("NBA Champion", r"\bnba champion\b"),
    "mvp": ("NBA MVP", r"\bmvp\b"),
    "roy": ("NBA Rookie of the Year", r"rookie of the year"),
}
SEASON_HINTS = ("2026-27", "2026–27", "2026/27", "2027")


def _pm_is_open(ev: dict) -> bool:
    return bool(ev.get("markets")) and not ev.get("closed") and ev.get("active", True)


def _pm_find_event(market: str) -> str:
    """Return the slug of the open Polymarket event for this market."""
    for s in PM_SLUGS[market]:
        evs = _get(f"{GAMMA}/events", {"slug": s}).json()
        if isinstance(evs, list) and evs and _pm_is_open(evs[0]):
            return s
    query, pattern = PM_SEARCH[market]
    found = _get(f"{GAMMA}/public-search", {"q": query, "events_status": "active"}).json()
    events = found.get("events") if isinstance(found, dict) else found
    cands = []
    for ev in events or []:
        title = (ev.get("title") or "").lower()
        if not re.search(pattern, title) or "nba" not in title and market != "title":
            continue
        if ev.get("closed"):
            continue
        if any(w in title for w in ("wnba", "finals mvp", "g league", "summer league", "conference")):
            continue
        season = any(h in title or h in (ev.get("slug") or "") for h in SEASON_HINTS)
        cands.append((season, ev.get("endDate") or "", ev.get("slug")))
    if not cands:
        raise RuntimeError(f"no open Polymarket event found for {market}")
    cands.sort(reverse=True)
    return cands[0][2]


def fetch_polymarket(market: str) -> Callable[[], bytes]:
    def fetch() -> bytes:
        s = _pm_find_event(market)
        r = _get(f"{GAMMA}/events", {"slug": s})
        if not r.json():
            raise RuntimeError(f"empty Polymarket event {s}")
        return r.content
    return fetch


def _jsonlist(x):
    if isinstance(x, list):
        return x
    try:
        return json.loads(x or "[]")
    except (TypeError, ValueError):
        return []


def parse_polymarket(market: str) -> Callable[[bytes], list[dict]]:
    def parse(raw: bytes) -> list[dict]:
        data = json.loads(raw)
        ev = data[0] if isinstance(data, list) else data
        rows = []
        for m in ev.get("markets") or []:
            if m.get("closed") or m.get("active") is False or m.get("archived"):
                continue
            name = (m.get("groupItemTitle") or m.get("question") or "").strip()
            if not name or norm_other(name):
                continue
            outcomes = [str(o).lower() for o in _jsonlist(m.get("outcomes"))]
            prices = _jsonlist(m.get("outcomePrices"))
            yes = None
            if prices:
                i = outcomes.index("yes") if "yes" in outcomes else 0
                yes = _num(prices[i])
            bid, ask = _num(m.get("bestBid")), _num(m.get("bestAsk"))
            row = {
                "market": market,
                "prob_pct": None if yes is None else yes * 100,
                "bid_pct": None if bid is None else bid * 100,
                "ask_pct": None if ask is None else ask * 100,
                "volume_usd": _num(m.get("volumeNum", m.get("volume"))),
                "liquidity_usd": _num(m.get("liquidityNum", m.get("liquidity"))),
            }
            if market == "title":
                abbr = team_abbr(name)
                if not abbr:
                    continue
                row.update(subject=abbr, item=FULL_NAME[abbr], team=abbr, conference=CONFERENCE[abbr])
            else:
                row.update(subject=slug(name), item=name)
            rows.append(row)
        return rows
    return parse


def norm_other(name: str) -> bool:
    n = name.lower()
    return n in ("other", "others", "field", "any other player", "another team") or n.startswith("player ") or n.startswith("team ")


# -------------------------------------------------------------------------- Kalshi

KALSHI_SERIES = {
    "title": ["KXNBA"],
    "mvp": ["KXNBAMVP"],
    "roy": ["KXNBAROY"],
}
KALSHI_SEARCH = {
    "title": r"\bnba\b.*(champion|finals winner|title)|pro basketball champion",
    "mvp": r"\bnba\b.*\bmvp\b|most valuable player",
    "roy": r"rookie of the year",
}


def _kalshi_markets(series: str) -> requests.Response:
    return _get(f"{KALSHI}/markets", {"series_ticker": series, "status": "open", "limit": 1000})


def fetch_kalshi(market: str) -> Callable[[], bytes]:
    def fetch() -> bytes:
        for s in KALSHI_SERIES[market]:
            r = _kalshi_markets(s)
            if r.json().get("markets"):
                return r.content
        series = _get(f"{KALSHI}/series", {"category": "Sports"}).json().get("series") or []
        for se in series:
            title = (se.get("title") or "")
            if re.search(KALSHI_SEARCH[market], title, re.I) and "wnba" not in title.lower() \
                    and "finals mvp" not in title.lower() and "college" not in title.lower():
                r = _kalshi_markets(se["ticker"])
                if r.json().get("markets"):
                    return r.content
        raise RuntimeError(f"no open Kalshi series found for {market}")
    return fetch


def _cents(m: dict, field: str) -> float | None:
    """Kalshi prices: '<field>_dollars' ("0.2500") in newer responses, cents in older."""
    d = _num(m.get(f"{field}_dollars"))
    if d is not None:
        return d * 100
    return _num(m.get(field))


def parse_kalshi(market: str) -> Callable[[bytes], list[dict]]:
    def parse(raw: bytes) -> list[dict]:
        data = json.loads(raw)
        markets = [m for m in data.get("markets") or [] if (m.get("status") or "active") in ("active", "open", "initialized")]
        # keep only the season's event (the one that closes last), if several are open
        if markets:
            last = max(markets, key=lambda m: m.get("close_time") or "")["event_ticker"] if all("event_ticker" in m for m in markets) else None
            if last:
                markets = [m for m in markets if m.get("event_ticker") == last]
        rows = []
        for m in markets:
            name = (m.get("yes_sub_title") or m.get("subtitle") or "").strip()
            code = (m.get("ticker") or "").rsplit("-", 1)[-1]
            bid, ask, last_px = _cents(m, "yes_bid"), _cents(m, "yes_ask"), _cents(m, "last_price")
            if bid and ask:
                prob = (bid + ask) / 2
            else:
                prob = last_px
            vol = _num(m.get("volume_fp")) if m.get("volume") is None else _num(m.get("volume"))
            oi = _num(m.get("open_interest_fp")) if m.get("open_interest") is None else _num(m.get("open_interest"))
            row = {
                "market": market,
                "prob_pct": prob,
                "bid_pct": bid,
                "ask_pct": ask,
                "last_pct": last_px,
                "volume_contracts": vol,
                "open_interest": oi,
            }
            if market == "title":
                abbr = team_abbr(name or m.get("title"), code)
                if not abbr:
                    continue
                row.update(subject=abbr, item=FULL_NAME[abbr], team=abbr, conference=CONFERENCE[abbr])
            else:
                if not name or norm_other(name):
                    continue
                row.update(subject=slug(name), item=name)
            rows.append(row)
        return rows
    return parse


# ------------------------------------------------------------------------ registry


@dataclass(frozen=True)
class Source:
    name: str
    fmt: str
    fetch: Callable[[], bytes]
    parse: Callable[[bytes], list[dict]]


SOURCES = [Source("espn_standings", "json", fetch_espn_standings, parse_espn_standings)]
for _m in ("title", "mvp", "roy"):
    SOURCES.append(Source(f"polymarket_{_m}", "json", fetch_polymarket(_m), parse_polymarket(_m)))
    SOURCES.append(Source(f"kalshi_{_m}", "json", fetch_kalshi(_m), parse_kalshi(_m)))
SOURCES.sort(key=lambda s: s.name)
BY_NAME = {s.name: s for s in SOURCES}
