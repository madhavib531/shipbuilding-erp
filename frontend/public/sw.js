// Keeps the app shell (HTML, scripts, styles, icons) available offline. Network first, cache as fallback.
// API calls are never handled here: the app keeps its own read cache and refuses changes while offline.
const CACHE = "dockyard-shell-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/health") return;
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request.mode === "navigate" ? "/" : request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request.mode === "navigate" ? "/" : request).then((hit) => hit || Response.error())),
  );
});
