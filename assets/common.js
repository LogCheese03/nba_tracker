// Shared by all three pages: nav bar, data loading, CSV parsing, the move rule, formatting.
"use strict";

const NUMERIC = ["wins", "losses", "win_pct", "games_back", "ppg", "opp_ppg", "point_diff", "streak",
  "prob_pct", "bid_pct", "ask_pct", "last_pct", "volume_usd", "liquidity_usd", "volume_contracts", "open_interest"];
const LABEL = {
  wins: "Wins", losses: "Losses", win_pct: "Win %", games_back: "Games back", ppg: "Points/game",
  opp_ppg: "Opp points/game", point_diff: "Point diff", streak: "Streak", prob_pct: "Implied prob %",
  bid_pct: "Bid %", ask_pct: "Ask %", last_pct: "Last trade %", volume_usd: "Volume $", liquidity_usd: "Liquidity $",
  volume_contracts: "Volume (contracts)", open_interest: "Open interest",
};
const MARKET_LABEL = { standings: "Standings", title: "Title odds", mvp: "MVP odds", roy: "Rookie of the Year odds" };
const SOURCE_LABEL = {
  espn_standings: "ESPN standings", polymarket_title: "Polymarket title", kalshi_title: "Kalshi title",
  polymarket_mvp: "Polymarket MVP", kalshi_mvp: "Kalshi MVP", polymarket_roy: "Polymarket ROY", kalshi_roy: "Kalshi ROY",
};
const ODDS_MARKETS = ["title", "mvp", "roy"];
const TOP_N = 5;

function renderNav() {
  const page = document.body.dataset.page;
  const links = [["index.html", "Today", "today"], ["browse.html", "Browse", "browse"], ["trends.html", "Trends", "trends"]];
  const header = document.createElement("header");
  header.className = "site";
  header.innerHTML = `<div class="wrap">
    <a class="brand" href="index.html"><span class="ball"></span>NBA Tracker</a>
    <nav class="main">${links.map(([h, t, k]) => `<a href="${h}" class="${k === page ? "active" : ""}">${t}</a>`).join("")}</nav>
    <span class="offline-badge" id="net"></span></div>`;
  document.body.prepend(header);
  const net = () => { document.getElementById("net").textContent = navigator.onLine ? "" : "Offline — showing last loaded data"; };
  window.addEventListener("online", net); window.addEventListener("offline", net); net();
  const foot = document.createElement("footer");
  foot.innerHTML = `Data: ESPN, Polymarket, Kalshi · rebuilt daily by GitHub Actions · <a href="https://github.com/LogCheese03/nba_tracker">source</a>`;
  document.body.append(foot);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
}

function parseCSV(text) {
  const rows = []; let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') q = false;
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const head = rows.shift() || [];
  return rows.filter(r => r.length === head.length).map(r => {
    const o = {};
    head.forEach((h, i) => { o[h] = NUMERIC.includes(h) ? (r[i] === "" ? null : Number(r[i])) : r[i]; });
    return o;
  });
}

async function loadData() {
  const [h, s] = await Promise.all([fetch("data/history.csv"), fetch("data/status.json")]);
  if (!h.ok || !s.ok) throw new Error("NOT_STARTED");
  const rows = parseCSV(await h.text());
  const status = await s.json();
  return { rows, status, dates: [...new Set(rows.map(r => r.date))].sort() };
}

// Same rule as tracker/history.py compute_moves.
function computeMoves(rows) {
  const dates = [...new Set(rows.map(r => r.date))].sort();
  const latest = dates[dates.length - 1] || null, prev = dates.length > 1 ? dates[dates.length - 2] : null;
  const now = new Map(rows.filter(r => r.date === latest).map(r => [r.item_id, r]));
  const before = new Map(prev ? rows.filter(r => r.date === prev).map(r => [r.item_id, r]) : []);
  const top = (market, col) => {
    const m = [];
    for (const [id, r] of now) {
      const b = before.get(id);
      if (r.market !== market || !b || r[col] == null || b[col] == null) continue;
      m.push({ item_id: id, item: r.item, source: r.source, old: b[col], new: r[col], change: r[col] - b[col] });
    }
    m.sort((a, b) => Math.abs(b.change) - Math.abs(a.change) || (a.item_id < b.item_id ? -1 : 1));
    return m.slice(0, TOP_N);
  };
  const groups = {};
  ODDS_MARKETS.forEach(k => groups[k] = { column: "prob_pct", moves: top(k, "prob_pct") });
  groups.standings = { column: "win_pct", moves: top("standings", "win_pct") };
  return { latest, prev, now, before, groups };
}

function fmt(col, v) {
  if (v == null || Number.isNaN(v)) return "—";
  if (col === "win_pct") return v.toFixed(3);
  if (col === "streak") return v > 0 ? `W${v}` : v < 0 ? `L${-v}` : "—";
  if (col.endsWith("_pct")) return v.toFixed(1) + "%";
  if (col.endsWith("_usd")) return "$" + Math.round(v).toLocaleString();
  if (col === "volume_contracts" || col === "open_interest") return Math.round(v).toLocaleString();
  if (["wins", "losses"].includes(col)) return String(v);
  return v.toFixed(1);
}
function fmtChange(col, d) {
  if (d == null) return "";
  if (Math.abs(d) < 1e-9) return `<span class="muted">0</span>`;
  const cls = d > 0 ? "up" : "down", s = d > 0 ? "+" : "";
  const txt = col === "win_pct" ? d.toFixed(3) : col.endsWith("_pct") ? d.toFixed(1) + " pts" : col.endsWith("_usd") ? "$" + Math.round(d).toLocaleString() : (Math.round(d * 10) / 10).toString();
  return `<span class="${cls}">${s}${txt}</span>`;
}
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function mainValue(r) { return r.market === "standings" ? "win_pct" : "prob_pct"; }

// The shortlist (Browse page stars), stored in this browser.
const STAR_KEY = "nba-tracker-shortlist";
function getStars() { try { return new Set(JSON.parse(localStorage.getItem(STAR_KEY) || "[]")); } catch { return new Set(); } }
function setStars(s) { try { localStorage.setItem(STAR_KEY, JSON.stringify([...s])); } catch { /* storage unavailable */ } }

function mean(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : null; }
function pearson(xs, ys) {
  const n = xs.length; if (n < 3) return null;
  const mx = mean(xs), my = mean(ys);
  let sxy = 0, sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sx += (xs[i] - mx) ** 2; sy += (ys[i] - my) ** 2; }
  return sx && sy ? sxy / Math.sqrt(sx * sy) : null;
}

function showError(e) {
  const m = document.querySelector("main");
  if (e && e.message === "NOT_STARTED") {
    m.innerHTML = `<h1>Starting soon</h1><div class="panel">Daily data collection begins <b>Monday, November 16, 2026</b> at about 7:17 a.m. Central. The first run will fill in this page.</div>`;
    return;
  }
  m.insertAdjacentHTML("afterbegin", `<div class="panel">Could not load the data files (${esc(e.message || e)}). If you are offline, open the site once online first.</div>`);
}

renderNav();
