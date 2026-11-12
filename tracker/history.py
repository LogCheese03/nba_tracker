"""Build data/history.csv from data/raw/ alone, and compute moves and status."""

from __future__ import annotations

import csv
import gzip
import io
import re
from pathlib import Path

from .sources import BY_NAME

COLUMNS = [
    "date", "item_id", "item", "source",
    "market", "subject", "team", "conference",
    "wins", "losses", "win_pct", "games_back", "ppg", "opp_ppg", "point_diff", "streak",
    "prob_pct", "bid_pct", "ask_pct", "last_pct",
    "volume_usd", "liquidity_usd", "volume_contracts", "open_interest",
]
NUMERIC = COLUMNS[8:]
ODDS_MARKETS = ("title", "mvp", "roy")
TOP_N = 5
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def raw_dates(raw_dir: Path) -> list[str]:
    if not raw_dir.exists():
        return []
    return sorted(p.name for p in raw_dir.iterdir()
                  if p.is_dir() and DATE_RE.match(p.name) and any(p.glob("*.gz")))


def read_raw(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes())


def rows_for_day(day_dir: Path) -> list[dict]:
    """Convert one day's raw files into rows with the common columns."""
    date = day_dir.name
    out: dict[str, dict] = {}
    for f in sorted(day_dir.glob("*.gz")):
        source = f.name.split(".", 1)[0]
        src = BY_NAME.get(source)
        if src is None:
            continue
        for r in src.parse(read_raw(f)):
            item_id = f"{source}:{r['subject']}"
            if item_id in out:  # one row per item per day: keep the first
                continue
            row = {c: r.get(c) for c in COLUMNS}
            row.update(date=date, item_id=item_id, source=source)
            out[item_id] = row
    return list(out.values())


def build_rows(raw_dir: Path) -> list[dict]:
    rows = []
    for d in raw_dates(raw_dir):
        rows.extend(rows_for_day(raw_dir / d))
    rows.sort(key=lambda r: (r["date"], r["item_id"]))
    return rows


def fmt(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(v)


def write_history(rows: list[dict], path: Path) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([fmt(r.get(c)) for c in COLUMNS])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8")


def read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for c in NUMERIC:
            r[c] = float(r[c]) if r.get(c) not in (None, "") else None
    return rows


def build(raw_dir: Path, history_path: Path) -> list[dict]:
    rows = build_rows(raw_dir)
    write_history(rows, history_path)
    return rows


# --------------------------------------------------------------------------- moves


def latest_and_previous(rows: list[dict]) -> tuple[str | None, str | None]:
    dates = sorted({r["date"] for r in rows})
    if not dates:
        return None, None
    return dates[-1], (dates[-2] if len(dates) > 1 else None)


def compute_moves(rows: list[dict]) -> dict:
    """The move rule.

    Compare the latest date in the history with the date before it.
    * Odds (title, MVP, ROY): change in prob_pct, in percentage points. The
      TOP_N largest absolute changes per market, both exchanges pooled.
    * Standings: change in win_pct; the TOP_N largest absolute changes.
    * New / gone: item_ids on the latest date but not the previous one, and the
      reverse. Gone items only count for sources that reported on the latest
      date, so one failed download does not list a whole source as gone.
    """
    latest, prev = latest_and_previous(rows)
    result = {"latest": latest, "previous": prev, "groups": {}, "new": [], "gone": []}
    if latest is None:
        return result
    now = {r["item_id"]: r for r in rows if r["date"] == latest}
    before = {r["item_id"]: r for r in rows if r["date"] == prev} if prev else {}
    sources_now = {r["source"] for r in now.values()}
    if prev:
        result["new"] = sorted(i for i in now if i not in before)
        result["gone"] = sorted(i for i, r in before.items() if i not in now and r["source"] in sources_now)

    def top(market: str, col: str) -> list[dict]:
        moves = []
        for i, r in now.items():
            b = before.get(i)
            if r["market"] != market or b is None or r[col] is None or b[col] is None:
                continue
            moves.append({"item_id": i, "item": r["item"], "source": r["source"],
                          "old": b[col], "new": r[col], "change": r[col] - b[col]})
        moves.sort(key=lambda m: (-abs(m["change"]), m["item_id"]))
        return moves[:TOP_N]

    for m in ODDS_MARKETS:
        result["groups"][m] = {"column": "prob_pct", "moves": top(m, "prob_pct")}
    result["groups"]["standings"] = {"column": "win_pct", "moves": top("standings", "win_pct")}
    return result


def status(rows: list[dict], raw_dir: Path, run_time: str, results: list[dict]) -> dict:
    dates = raw_dates(raw_dir)
    moves = compute_moves(rows)
    latest = moves["latest"]
    return {
        "run_time": run_time,
        "first_run_date": dates[0] if dates else None,
        "days_with_success": len(dates),
        "items": sum(1 for r in rows if r["date"] == latest),
        "new_today": moves["new"],
        "gone_today": moves["gone"],
        "sources": results,
    }
