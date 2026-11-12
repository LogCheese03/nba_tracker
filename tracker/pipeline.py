"""The daily run: fetch every source, rebuild the history, write status, post the Issue."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import history
from .issues import post_issue
from .sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
HISTORY = DATA / "history.csv"
STATUS = DATA / "status.json"


def fetch_all(raw_dir: Path, date: str, sources=SOURCES) -> list[dict]:
    """Download every source into raw_dir/<date>/. A second run the same day
    replaces that day's raw files. One failing source never stops the run."""
    day = raw_dir / date
    if day.exists():
        shutil.rmtree(day)
    day.mkdir(parents=True)
    results = []
    for src in sources:
        entry = {"name": src.name, "ok": False, "count": 0}
        try:
            body = src.fetch()
            count = len(src.parse(body))
            if count == 0:
                raise RuntimeError("source returned no tracked items")
            (day / f"{src.name}.{src.fmt}.gz").write_bytes(gzip.compress(body, mtime=0))
            entry.update(ok=True, count=count)
        except Exception as e:  # noqa: BLE001 - record and keep going
            entry["error"] = f"{type(e).__name__}: {e}"[:300]
            traceback.print_exc()
        print(f"{src.name}: {'ok' if entry['ok'] else 'FAILED'} ({entry['count']})")
        results.append(entry)
    if not any(day.iterdir()):
        day.rmdir()
    return results


def run(now: datetime | None = None, raw_dir: Path = RAW, history_path: Path = HISTORY,
        status_path: Path = STATUS, sources=SOURCES, issue: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    results = fetch_all(raw_dir, date, sources)
    rows = history.build(raw_dir, history_path)
    st = history.status(rows, raw_dir, now.strftime("%Y-%m-%dT%H:%M:%SZ"), results)
    status_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    if issue and os.environ.get("GITHUB_TOKEN"):
        post_issue(date, history.compute_moves(rows), st)
    return st
