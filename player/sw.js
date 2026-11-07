const CACHE_PREFIX = "oio-media-player-";
const CACHE_NAME = CACHE_PREFIX + "v4";
const APP_SHELL = [
  "./",
  "./index.html",
  "./style.css?v=1.2.0",
  "./player.js?v=1.2.0",
  "./manifest.json",
  "./icons/oio-media.svg"
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(APP_SHELL);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Always try the live catalog first; use cached data only when offline.
  if (url.pathname.endsWith("/data/catalog.json")) {
    event.respondWith((async () => {
      try {
        const response = await fetch(request, { cache: "no-store" });
        if (response.ok) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(request, response.clone());
        }
        return response;
      } catch {
        return (await caches.match(request)) || new Response("{}", {
          headers: { "Content-Type": "application/json" },
          status: 503
        });
      }
    })());
    return;
  }

  // HTML navigation: network-first, cached app shell as offline fallback.
  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put("./index.html", response.clone());
        }
        return response;
      } catch {
        return (await caches.match(request)) ||
          (await caches.match("./index.html")) ||
          (await caches.match("./"));
      }
    })());
    return;
  }

  // App assets: cache-first, then save successful same-origin responses.
  event.respondWith((async () => {
    const cached = await caches.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    }
    return response;
  })());
});
