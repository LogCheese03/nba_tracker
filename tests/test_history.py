"""History build, the move rule, status, and runs on the same day."""

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tracker import history, pipeline
from tracker.sources import BY_NAME, SOURCES, Source

FIX = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIX / f"{name}.json").read_bytes()


def write_day(raw, date, names, edit=None):
    d = raw / date
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        body = fixture(n)
        if edit:
            body = edit(n, body)
        (d / f"{n}.json.gz").write_bytes(gzip.compress(body, mtime=0))


ALL = [s.name for s in SOURCES]


def bump_okc(name, body):
    """Day-two data: Thunder title odds up, Lakers win % changes."""
    if name == "polymarket_title":
        data = json.loads(body)
        for m in data[0]["markets"]:
            if m["groupItemTitle"] == "Oklahoma City Thunder":
                m["outcomePrices"] = '["0.40", "0.60"]'
        return json.dumps(data).encode()
    if name == "espn_standings":
        data = json.loads(body)
        for e in data["children"][1]["standings"]["entries"]:
            if e["team"]["abbreviation"] == "LAL":
                for s in e["stats"]:
                    if s["name"] == "winPercent":
                        s["value"] = 0.5
        return json.dumps(data).encode()
    if name == "kalshi_roy":
        data = json.loads(body)
        data["markets"].append(dict(data["markets"][0], ticker="KXNBAROY-27-DHAR", yes_sub_title="Dylan Harper"))
        return json.dumps(data).encode()
    return body


def test_rows_sorted_and_unique(tmp_path):
    write_day(tmp_path, "2026-11-13", ALL)
    write_day(tmp_path, "2026-11-12", ALL)
    rows = history.build_rows(tmp_path)
    keys = [(r["date"], r["item_id"]) for r in rows]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))
    assert rows[0]["date"] == "2026-11-12"
    assert {r["source"] for r in rows} == set(ALL)
    assert all(r["item_id"].startswith(r["source"] + ":") for r in rows)


def test_missing_source_has_no_rows_that_day(tmp_path):
    write_day(tmp_path, "2026-11-12", ALL)
    write_day(tmp_path, "2026-11-13", [n for n in ALL if n != "kalshi_title"])
    rows = history.build_rows(tmp_path)
    day2 = {r["source"] for r in rows if r["date"] == "2026-11-13"}
    assert "kalshi_title" not in day2
    assert "kalshi_title" in {r["source"] for r in rows if r["date"] == "2026-11-12"}


def test_build_is_reproducible(tmp_path):
    raw = tmp_path / "raw"
    write_day(raw, "2026-11-12", ALL)
    write_day(raw, "2026-11-13", ALL, bump_okc)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    history.build(raw, a)
    history.build(raw, b)
    assert a.read_bytes() == b.read_bytes()
    header = a.read_text().splitlines()[0].split(",")
    assert header[:4] == ["date", "item_id", "item", "source"]
    # read back -> same values
    back = history.read_history(a)
    assert len(back) == len(history.build_rows(raw))


def test_empty_values_stay_empty(tmp_path):
    write_day(tmp_path, "2026-11-12", ["espn_standings"])
    out = tmp_path / "h.csv"
    history.build(tmp_path, out)
    row = history.read_history(out)[0]
    assert row["prob_pct"] is None and row["wins"] is not None


def test_move_rule(tmp_path):
    write_day(tmp_path, "2026-11-12", ALL)
    write_day(tmp_path, "2026-11-13", ALL, bump_okc)
    moves = history.compute_moves(history.build_rows(tmp_path))
    assert (moves["latest"], moves["previous"]) == ("2026-11-13", "2026-11-12")
    top = moves["groups"]["title"]["moves"][0]
    assert top["item_id"] == "polymarket_title:OKC"
    assert top["old"] == pytest.approx(31) and top["new"] == pytest.approx(40)
    assert top["change"] == pytest.approx(9)
    st = moves["groups"]["standings"]["moves"][0]
    assert st["item_id"] == "espn_standings:LAL" and st["new"] == pytest.approx(0.5)
    assert all(len(g["moves"]) <= history.TOP_N for g in moves["groups"].values())
    assert moves["new"] == ["kalshi_roy:dylan-harper"]
    assert moves["gone"] == []


def test_failed_source_is_not_listed_as_gone(tmp_path):
    write_day(tmp_path, "2026-11-12", ALL)
    write_day(tmp_path, "2026-11-13", [n for n in ALL if n != "kalshi_mvp"])
    moves = history.compute_moves(history.build_rows(tmp_path))
    assert moves["gone"] == []


def test_no_change_day_still_has_groups(tmp_path):
    write_day(tmp_path, "2026-11-12", ALL)
    write_day(tmp_path, "2026-11-13", ALL)
    moves = history.compute_moves(history.build_rows(tmp_path))
    assert set(moves["groups"]) == {"title", "mvp", "roy", "standings"}
    assert all(m["change"] == 0 for g in moves["groups"].values() for m in g["moves"])


# ---------------------------------------------------------------- pipeline runs

def fake_sources(day_edit=None, fail=()):
    out = []
    for s in SOURCES:
        def fetch(name=s.name):
            if name in fail:
                raise ConnectionError("down")
            body = fixture(name)
            return day_edit(name, body) if day_edit else body
        out.append(Source(s.name, s.fmt, fetch, s.parse))
    return out


def run(tmp_path, when, **kw):
    return pipeline.run(now=when, raw_dir=tmp_path / "raw", history_path=tmp_path / "history.csv",
                        status_path=tmp_path / "status.json", issue=False, **kw)


def test_run_survives_failed_source_and_writes_status(tmp_path):
    st = run(tmp_path, datetime(2026, 11, 12, 13, 17, tzinfo=timezone.utc),
             sources=fake_sources(fail={"kalshi_title"}))
    saved = json.loads((tmp_path / "status.json").read_text())
    assert saved == st
    assert set(st) == {"run_time", "first_run_date", "days_with_success", "items", "new_today", "gone_today", "sources"}
    assert st["run_time"] == "2026-11-12T13:17:00Z"
    assert st["first_run_date"] == "2026-11-12" and st["days_with_success"] == 1
    by = {s["name"]: s for s in st["sources"]}
    assert by["kalshi_title"]["ok"] is False and by["kalshi_title"]["count"] == 0
    assert by["espn_standings"] == {"name": "espn_standings", "ok": True, "count": 5}
    assert not (tmp_path / "raw/2026-11-12/kalshi_title.json.gz").exists()
    assert (tmp_path / "raw/2026-11-12/espn_standings.json.gz").exists()
    assert st["items"] == sum(s["count"] for s in st["sources"])


def test_second_run_same_day_replaces_the_day(tmp_path):
    run(tmp_path, datetime(2026, 11, 12, 13, 0, tzinfo=timezone.utc), sources=fake_sources())
    run(tmp_path, datetime(2026, 11, 13, 13, 0, tzinfo=timezone.utc), sources=fake_sources())
    first = (tmp_path / "history.csv").read_text()
    # run again on Nov 13 with new numbers and one source down
    st = run(tmp_path, datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc),
             sources=fake_sources(bump_okc, fail={"kalshi_mvp"}))
    rows = history.read_history(tmp_path / "history.csv")
    day2 = [r for r in rows if r["date"] == "2026-11-13"]
    assert len({r["item_id"] for r in day2}) == len(day2)  # no duplicates
    okc = [r for r in day2 if r["item_id"] == "polymarket_title:OKC"]
    assert len(okc) == 1 and okc[0]["prob_pct"] == pytest.approx(40)
    assert not any(r["source"] == "kalshi_mvp" for r in day2)  # replaced, not kept
    assert not (tmp_path / "raw/2026-11-13/kalshi_mvp.json.gz").exists()
    assert st["days_with_success"] == 2
    assert first != (tmp_path / "history.csv").read_text()
    # day 1 untouched
    assert [r for r in rows if r["date"] == "2026-11-12"] == [
        r for r in history.read_history(tmp_path / "history.csv") if r["date"] == "2026-11-12"]


def test_build_command_matches_run_output(tmp_path):
    run(tmp_path, datetime(2026, 11, 12, tzinfo=timezone.utc), sources=fake_sources())
    run(tmp_path, datetime(2026, 11, 13, tzinfo=timezone.utc), sources=fake_sources(bump_okc))
    rebuilt = tmp_path / "rebuilt.csv"
    history.build(tmp_path / "raw", rebuilt)
    assert rebuilt.read_bytes() == (tmp_path / "history.csv").read_bytes()


def test_issue_body_lists_moves():
    from tracker.issues import issue_body
    moves = {"previous": "2026-11-12", "new": ["kalshi_roy:dylan-harper"], "gone": [],
             "groups": {"title": {"column": "prob_pct", "moves": [
                 {"item": "Oklahoma City Thunder", "source": "polymarket_title", "old": 31.0, "new": 40.0, "change": 9.0}]},
                 "standings": {"column": "win_pct", "moves": []}}}
    status = {"items": 10, "days_with_success": 2, "sources": [{"name": "x", "ok": True, "count": 1}]}
    body = issue_body("2026-11-13", moves, status)
    assert "31.0% | 40.0% | +9.0 pts" in body
    assert "kalshi_roy:dylan-harper" in body
    assert "No changes to compare." in body
