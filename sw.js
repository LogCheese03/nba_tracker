// Service worker: pages and assets come from the cache (refreshed in the background);
// data files come from the network first and fall back to the last copy when offline.
const VERSION = "nba-tracker-v2";
const SHELL = [
  "./", "index.html", "browse.html", "trends.html", "manifest.webmanifest",
  "assets/style.css", "assets/common.js", "assets/charts.js",
  "icons/icon-192.png", "icons/icon-512.png",
  "data/history.csv", "data/status.json",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const isData = url.pathname.includes("/data/");
  if (isData) {
    // network first
    e.respondWith(fetch(e.request, { cache: "no-store" }).then(res => {
      const copy = res.clone();
      caches.open(VERSION).then(c => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request, { ignoreSearch: true })));
  } else {
    // network first too, so new page versions show up; cache when offline
    e.respondWith(fetch(e.request).then(res => {
      const copy = res.clone();
      caches.open(VERSION).then(c => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || caches.match("index.html"))));
  }
});
