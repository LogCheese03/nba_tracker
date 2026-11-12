# NBA Data Tracker

[![Tests](https://github.com/LogCheese03/nba_tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/LogCheese03/nba_tracker/actions/workflows/tests.yml)
[![Daily run](https://github.com/LogCheese03/nba_tracker/actions/workflows/daily.yml/badge.svg)](https://github.com/LogCheese03/nba_tracker/actions/workflows/daily.yml)

**Live site:** https://logcheese03.github.io/nba_tracker/

Every day, on its own, this tool downloads the NBA standings and the betting-market odds for the championship, MVP and Rookie of the Year from two prediction markets, Polymarket and Kalshi. It adds the day to a history (one row per item per day), opens a GitHub Issue listing what moved, and publishes the results to a website.

Financial Data Analytics — Data Tracker Project.

## How it runs

GitHub Actions runs `python -m tracker run` every day at 13:17 UTC (7:17 a.m. Central, after the night's games are final), with a backup run at 21:17 UTC. Each run:

1. Downloads every source and saves the response exactly as it came, gzipped, to `data/raw/<UTC date>/<source>.json.gz`. A source that fails writes no raw file that day, and the run carries on. Every source's result (ok / failed, item count, error) goes in the status file.
2. Rebuilds `data/history.csv` from the raw files only.
3. Writes `data/status.json`.
4. Opens a GitHub Issue titled with the date, listing the biggest moves and every item that appeared or disappeared, and closes the previous day's Issue. An Issue is posted every day, even with no changes.
5. Commits the raw files, history and status.

A second run on the same UTC date deletes that day's raw folder, downloads it again, rebuilds the history and updates that day's Issue, so each day counts once.

**Rebuild the history from the raw files:**

```bash
python -m tracker build
```

The build reads nothing but `data/raw/`, so running it again gives a byte-identical file, and a change to a parsing rule applies to every day of the history.

## Sources

All seven are JSON downloaded with no login and no API key.

| Source (`source` column) | What | Format | URL | What is kept |
|---|---|---|---|---|
| `espn_standings` | NBA standings, all 30 teams | JSON | `site.api.espn.com/apis/v2/sports/basketball/nba/standings` | Each team's wins, losses, win %, games back, points for/against per game, differential and streak. Other stats are ignored. |
| `polymarket_title` | "NBA Champion" market | JSON | `gamma-api.polymarket.com/events?slug=…` | Only this season's champion event. One row per open team market (price of "Yes", bid, ask, volume, liquidity). Closed or "Other" outcomes are dropped. |
| `polymarket_mvp` | "NBA MVP" market | JSON | same API | This season's MVP event, one row per open player market. |
| `polymarket_roy` | "NBA Rookie of the Year" market | JSON | same API | This season's ROY event, one row per open player market. |
| `kalshi_title` | Pro basketball champion series | JSON | `api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXNBA&status=open` | Open markets only, and only the event that closes last (this season). Bid, ask, last price, volume and open interest. |
| `kalshi_mvp` | NBA MVP series | JSON | same API, MVP series | Open markets for this season's MVP event. |
| `kalshi_roy` | NBA Rookie of the Year series | JSON | same API, ROY series | Open markets for this season's ROY event. |

The Polymarket event slug and Kalshi series ticker are looked up on each run (`tracker/sources.py`: a list of known slugs and tickers, then a search). That way the pipeline keeps working if a market is renamed, and if a source stops working it can be replaced in one place.

## History file: `data/history.csv`

One row per item per day, sorted by `date`, then `item_id`. A value that a source doesn't report for an item is left empty: for example, standings rows have no odds columns, and odds rows have no standings columns.

| Column | Meaning | Unit |
|---|---|---|
| `date` | UTC date of the run that downloaded the data | YYYY-MM-DD |
| `item_id` | Key that lines up the same item day after day: `<source>:<subject>`, e.g. `espn_standings:OKC`, `kalshi_title:OKC`, `polymarket_mvp:nikola-jokic` | text |
| `item` | Display name: team full name or player name | text |
| `source` | Which of the seven sources the row came from | text |
| `market` | `standings`, `title`, `mvp` or `roy` | text |
| `subject` | Team (ESPN abbreviation, e.g. `OKC`) or player (name slug with accents removed). Lets the same team or player be compared across sources. | text |
| `team` | Team abbreviation (team rows only) | text |
| `conference` | `East` or `West` (team rows only) | text |
| `wins` | Games won this season | games |
| `losses` | Games lost this season | games |
| `win_pct` | Wins ÷ games played | fraction 0–1 |
| `games_back` | Games behind the conference leader | games |
| `ppg` | Points scored per game | points |
| `opp_ppg` | Points allowed per game | points |
| `point_diff` | `ppg` − `opp_ppg` | points per game |
| `streak` | Current streak: positive = wins in a row, negative = losses (W3 = 3, L2 = −2) | games |
| `prob_pct` | Market-implied probability. Polymarket: price of "Yes" × 100. Kalshi: the midpoint of the yes bid and ask, or the last trade price if there is no two-sided quote. | percent 0–100 |
| `bid_pct` | Best bid for "Yes" | percent 0–100 |
| `ask_pct` | Best ask for "Yes" | percent 0–100 |
| `last_pct` | Last traded price (Kalshi only) | percent 0–100 |
| `volume_usd` | Total traded volume (Polymarket only) | US dollars |
| `liquidity_usd` | Liquidity on the order book (Polymarket only) | US dollars |
| `volume_contracts` | Total contracts traded (Kalshi only) | contracts |
| `open_interest` | Contracts currently held (Kalshi only) | contracts |

## Status file: `data/status.json`

`run_time` (UTC), `first_run_date` (date of the earliest raw folder), `days_with_success` (number of different dates with a raw file), `items` (rows on the latest date), `new_today` and `gone_today` (lists of `item_id`), and `sources` (one entry per source with `name`, `ok`, `count`, plus `error` when it failed).

## Move rule

Each item's value on the latest date is compared with its value on the previous date in the history.

- **Odds (title, MVP, ROY):** change in `prob_pct`, in percentage points. The Issue lists the **5 largest absolute changes in each market**, with Polymarket and Kalshi pooled.
- **Standings:** change in `win_pct`. The Issue lists the **5 largest absolute changes**.
- **Appeared / disappeared:** an `item_id` on the latest date but not the previous one is new, and the reverse is gone. Gone only counts for sources that reported on the latest date, so a single failed download doesn't list a whole source as gone. (The failure shows in the source status instead.)

The same rule is implemented in `tracker/history.py` (`compute_moves`) for the Issue and in `assets/common.js` (`computeMoves`) for the Today page.

## Site

Three pages share one nav bar, stylesheet, fonts and colors. Each page loads `data/history.csv` and `data/status.json` in the browser and does every calculation there.

- **Today** (`index.html`): last run time, each source's status, the status counts, the biggest moves, and every item's latest value with its change since the previous run.
- **Browse** (`browse.html`): the latest values, with filters for market, source and conference, a name search, sorting (up and down) on every numeric column, and a ★ shortlist saved in the browser's localStorage.
- **Trends** (`trends.html`): a chart of any numeric value over time, with a picker for which items to show. Below it, seven findings, each with a heading, numbers, an explanation of how they're computed, and a chart:
  1. Title-odds change since the first run.
  2. Where Polymarket and Kalshi disagree.
  3. The MVP race.
  4. The ROY race.
  5. How closely title odds track win %.
  6. The biggest day of movement.
  7. How far apart teams are by point differential.

The site installs as an app (`manifest.webmanifest` + `sw.js`). Online, data files are loaded from the network. Offline, the service worker serves the last copy it saved.

## Files

| Path | What it does |
|---|---|
| `tracker/__main__.py` | Command line: `python -m tracker run` (daily run) and `python -m tracker build` (rebuild history) |
| `tracker/pipeline.py` | The daily run: download all sources, save raw files, rebuild history, write status, post the Issue |
| `tracker/sources.py` | The seven sources: how each is downloaded (`fetch_*`) and converted to the common columns (`parse_*`) |
| `tracker/teams.py` | Team lookup: maps every team name or code to an ESPN abbreviation, and makes player slugs |
| `tracker/history.py` | Builds `history.csv` from `data/raw/`, the move rule, and the status contents |
| `tracker/issues.py` | Opens or updates the day's GitHub Issue and closes the previous one |
| `tests/test_sources.py` | Each source's conversion to the common columns, team-name mapping, slugs |
| `tests/test_history.py` | History build (sorting, missing sources, reproducibility), the move rule, status, a failed source, and a second run on the same day |
| `tests/fixtures/` | Sample responses for each source, used by the tests |
| `.github/workflows/daily.yml` | Scheduled daily run: tests, pipeline, commit |
| `.github/workflows/tests.yml` | Runs pytest on every push and pull request |
| `data/raw/<date>/<source>.json.gz` | Raw responses, exactly as downloaded, gzipped |
| `data/history.csv` | The history (see above) |
| `data/status.json` | The latest run's status (see above) |
| `index.html`, `browse.html`, `trends.html` | The three site pages |
| `assets/style.css` | Shared fonts, colors and layout |
| `assets/common.js` | Shared nav bar, CSV loading, move rule, formatting, shortlist storage |
| `assets/charts.js` | Small SVG line, bar and scatter charts (no external library, so offline works) |
| `manifest.webmanifest`, `sw.js`, `icons/` | Make the site installable and usable offline |
| `requirements.txt`, `pytest.ini` | Python dependencies and test settings |

## Run it locally

```bash
pip install -r requirements.txt
pytest -q
python -m tracker run      # downloads today's data (the Issue step is skipped without GITHUB_TOKEN)
python -m http.server      # then open http://localhost:8000
```
