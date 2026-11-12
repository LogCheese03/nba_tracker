// Small SVG chart helpers (no library, so the site works offline).
"use strict";

const PALETTE = ["#f26b1d", "#4ea8ff", "#3ecf8e", "#ffcc33", "#c77dff", "#ff6b9a", "#5ee0e0", "#b5e35a", "#ff9e57", "#8f9bff", "#e0a96d", "#9aa3b2"];

function niceTicks(min, max, n = 5) {
  if (min === max) { min -= 1; max += 1; }
  const step0 = (max - min) / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= step0);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, t = [];
  for (let v = lo; v <= hi + step / 2; v += step) t.push(+v.toFixed(10));
  return t;
}
const tickFmt = v => Math.abs(v) >= 1000 ? (v / 1000).toLocaleString() + "k" : (+v.toFixed(3)).toString();

function legend(names) {
  return `<div class="legend">${names.map((n, i) => `<span><i style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(n)}</span>`).join("")}</div>`;
}

// series: [{name, points:[{x:"YYYY-MM-DD", y}]}]
function lineChart(el, series, { yLabel = "", height = 300 } = {}) {
  const W = 900, H = height, L = 56, R = 16, T = 14, B = 34;
  const xs = [...new Set(series.flatMap(s => s.points.map(p => p.x)))].sort();
  const ys = series.flatMap(s => s.points.map(p => p.y)).filter(v => v != null);
  if (!xs.length || !ys.length) { el.innerHTML = `<p class="empty">No data yet.</p>`; return; }
  const ticks = niceTicks(Math.min(...ys), Math.max(...ys));
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const X = i => xs.length === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (xs.length - 1);
  const Y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0 || 1));
  const every = Math.ceil(xs.length / 8);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img"><g class="grid">${ticks.map(t => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}"/>`).join("")}</g>`;
  s += `<g class="axis">${ticks.map(t => `<text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${tickFmt(t)}</text>`).join("")}`;
  s += xs.map((x, i) => i % every ? "" : `<text x="${X(i)}" y="${H - 12}" text-anchor="middle">${x.slice(5)}</text>`).join("");
  s += `<text x="12" y="${T + 4}" transform="rotate(-90 12 ${T + 4})" text-anchor="end">${esc(yLabel)}</text></g>`;
  series.forEach((ser, k) => {
    const c = PALETTE[k % PALETTE.length];
    const pts = ser.points.filter(p => p.y != null).map(p => [X(xs.indexOf(p.x)), Y(p.y), p]);
    if (pts.length > 1) s += `<polyline fill="none" stroke="${c}" stroke-width="2.2" points="${pts.map(p => p[0] + "," + p[1]).join(" ")}"/>`;
    s += pts.map(([x, y, p]) => `<circle cx="${x}" cy="${y}" r="3.2" fill="${c}"><title>${esc(ser.name)} · ${p.x}: ${tickFmt(p.y)}</title></circle>`).join("");
  });
  el.innerHTML = s + "</svg>" + legend(series.map(s => s.name));
}

// bars: [{label, value}] -> horizontal bars, negative values go left
function barChart(el, bars, { unit = "", height } = {}) {
  if (!bars.length) { el.innerHTML = `<p class="empty">No data yet.</p>`; return; }
  const W = 900, rowH = 24, L = 210, R = 70, T = 8, H = height || T * 2 + rowH * bars.length + 20;
  const vals = bars.map(b => b.value), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const X = v => L + ((v - lo) / ((hi - lo) || 1)) * (W - L - R);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img"><line x1="${X(0)}" x2="${X(0)}" y1="${T}" y2="${H - 20}" stroke="#2a3242"/>`;
  bars.forEach((b, i) => {
    const y = T + i * rowH, x0 = X(Math.min(0, b.value)), w = Math.abs(X(b.value) - X(0));
    const c = b.color || (b.value >= 0 ? "#f26b1d" : "#4ea8ff");
    s += `<text x="${L - 8}" y="${y + 16}" text-anchor="end" fill="#cfd5de" font-size="12">${esc(b.label)}</text>`;
    s += `<rect x="${x0}" y="${y + 4}" width="${Math.max(w, 1)}" height="${rowH - 8}" rx="3" fill="${c}"><title>${esc(b.label)}: ${tickFmt(b.value)}${unit}</title></rect>`;
    s += `<text x="${b.value >= 0 ? X(b.value) + 6 : X(0) + 6}" y="${y + 16}" fill="#9aa3b2" font-size="12">${(b.value > 0 && lo < 0 ? "+" : "") + tickFmt(+b.value.toFixed(2))}${unit}</text>`;
  });
  el.innerHTML = s + "</svg>";
}

// points: [{x, y, label}]
function scatterChart(el, points, { xLabel = "", yLabel = "" } = {}) {
  if (!points.length) { el.innerHTML = `<p class="empty">No data yet.</p>`; return; }
  const W = 900, H = 340, L = 56, R = 20, T = 14, B = 40;
  const xt = niceTicks(Math.min(...points.map(p => p.x)), Math.max(...points.map(p => p.x)));
  const yt = niceTicks(Math.min(...points.map(p => p.y)), Math.max(...points.map(p => p.y)));
  const X = v => L + (W - L - R) * (v - xt[0]) / ((xt[xt.length - 1] - xt[0]) || 1);
  const Y = v => T + (H - T - B) * (1 - (v - yt[0]) / ((yt[yt.length - 1] - yt[0]) || 1));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img"><g class="grid">${yt.map(t => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}"/>`).join("")}</g><g class="axis">`;
  s += yt.map(t => `<text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${tickFmt(t)}</text>`).join("");
  s += xt.map(t => `<text x="${X(t)}" y="${H - 22}" text-anchor="middle">${tickFmt(t)}</text>`).join("");
  s += `<text x="${(W + L) / 2}" y="${H - 4}" text-anchor="middle">${esc(xLabel)}</text>`;
  s += `<text x="12" y="${T + 4}" transform="rotate(-90 12 ${T + 4})" text-anchor="end">${esc(yLabel)}</text></g>`;
  s += points.map(p => `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="5" fill="#f26b1d" fill-opacity=".85"><title>${esc(p.label)}: ${tickFmt(p.x)}, ${tickFmt(p.y)}</title></circle>
    <text x="${X(p.x) + 7}" y="${Y(p.y) + 4}" fill="#9aa3b2" font-size="10">${esc(p.short || "")}</text>`).join("");
  el.innerHTML = s + "</svg>";
}
