"""Open (or update) today's GitHub Issue and close the previous day's."""

from __future__ import annotations

import os
import re

import requests

API = "https://api.github.com"
LABELS = {"title": "Title odds", "mvp": "MVP odds", "roy": "Rookie of the Year odds", "standings": "Standings (win %)"}


def _fmt(col: str, v: float) -> str:
    return f"{v:.3f}" if col == "win_pct" else f"{v:.1f}%"


def _chg(col: str, v: float) -> str:
    return f"{v:+.3f}" if col == "win_pct" else f"{v:+.1f} pts"


def issue_body(date: str, moves: dict, status: dict) -> str:
    lines = [f"Daily run for **{date}** (UTC). Compared with **{moves.get('previous') or 'no earlier run'}**.", ""]
    ok = sum(1 for s in status["sources"] if s["ok"])
    lines.append(f"Sources: {ok}/{len(status['sources'])} ok · items today: {status['items']} · days with data: {status['days_with_success']}")
    failed = [s["name"] for s in status["sources"] if not s["ok"]]
    if failed:
        lines.append(f"Failed today: {', '.join(failed)}")
    lines.append("")
    any_move = False
    for key in ("title", "mvp", "roy", "standings"):
        g = moves["groups"].get(key)
        if not g:
            continue
        lines.append(f"### {LABELS[key]}")
        if not g["moves"]:
            lines.append("No changes to compare.")
        else:
            any_move = True
            lines.append("| Item | Source | Old | New | Change |")
            lines.append("|---|---|---|---|---|")
            for m in g["moves"]:
                c = g["column"]
                lines.append(f"| {m['item']} | {m['source']} | {_fmt(c, m['old'])} | {_fmt(c, m['new'])} | {_chg(c, m['change'])} |")
        lines.append("")
    lines.append("### Appeared / disappeared")
    lines.append(f"New: {', '.join(moves['new']) or 'none'}")
    lines.append(f"Gone: {', '.join(moves['gone']) or 'none'}")
    if not any_move:
        lines += ["", "_No moves today._"]
    lines += ["", "Move rule: biggest absolute change since the previous run — percentage points of implied probability for odds (top 5 per market, both exchanges pooled), win % for standings (top 5)."]
    return "\n".join(lines)


def post_issue(date: str, moves: dict, status: dict) -> None:
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    body = issue_body(date, moves, status)
    issues = []
    for page in range(1, 6):
        r = requests.get(f"{API}/repos/{repo}/issues", headers=h, timeout=30,
                         params={"state": "all", "per_page": 100, "page": page})
        r.raise_for_status()
        batch = [i for i in r.json() if "pull_request" not in i]
        issues += batch
        if len(r.json()) < 100:
            break
    today = [i for i in issues if i["title"] == date]
    if today:
        requests.patch(f"{API}/repos/{repo}/issues/{today[0]['number']}", headers=h, timeout=30,
                       json={"body": body, "state": "open"}).raise_for_status()
    else:
        requests.post(f"{API}/repos/{repo}/issues", headers=h, timeout=30,
                      json={"title": date, "body": body}).raise_for_status()
    for i in issues:
        if i["state"] == "open" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", i["title"]) and i["title"] < date:
            requests.patch(f"{API}/repos/{repo}/issues/{i['number']}", headers=h, timeout=30,
                           json={"state": "closed"}).raise_for_status()
