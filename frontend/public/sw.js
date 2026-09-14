/**
 * Offline mode, part 2: the app shell.
 *
 * A hand-written, dependency-free service worker rather than Workbox/
 * next-pwa - this project's build pipeline doesn't already include a
 * precache-manifest generator, and adding one is a real build-tooling
 * decision (see FUTURE_WORK.md) that's out of scope for this pass. What
 * this DOES give, honestly: same-origin GET responses (Next.js's static
 * JS/CSS chunks, the manifest, the icon, the page shell) are cached
 * opportunistically as the farmer browses, cache-first, so a second visit
 * with no signal still loads the wizard instead of a browser error page.
 *
 * Deliberately NEVER touches anything under /api/ - POST /api/regenerate
 * and friends always go straight to the network; the "last successful
 * report" fallback for THOSE is lib/offlineCache.ts (localStorage), not
 * this file. A cache in front of a POST endpoint would be actively wrong.
 */

const CACHE_NAME = "kisan-mitra-shell-v1";
const CORE_ASSETS = ["/", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(CORE_ASSETS))
      .catch(() => {
        /* offline on first install, or one of the core assets 404s - fine, fetch handler still opportunistically caches later */
      }),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // leave the backend (different origin/port) alone entirely
  if (url.pathname.startsWith("/api/")) return; // never intercept the API - see module docstring

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => caches.match("/"));
    }),
  );
});
