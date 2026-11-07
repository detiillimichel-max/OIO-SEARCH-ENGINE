const CACHE_NAME = "oio-media-player-v3";
const APP_FILES = ["./", "./index.html", "./style.css", "./manifest.json"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_FILES)));
  self.skipWaiting();
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("oio-media-player-") && key !== CACHE_NAME).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith(".js") || url.pathname.endsWith(".json") || url.pathname.endsWith(".html")) {
    event.respondWith(fetch(request, {cache:"no-store"}).catch(() => caches.match(request)));
    return;
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
});
