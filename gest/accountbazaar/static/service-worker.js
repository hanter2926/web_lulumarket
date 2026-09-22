const CACHE_NAME = "accountbazaar-shell-v2";
const SHELL = ["/", "/static/css/base.css", "/static/css/navbar.css", "/static/css/footer.css"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  const privatePath = /\/(accounts|payments|orders|notifications|wallet|disputes)(\/|$)/.test(requestUrl.pathname);
  if (event.request.method !== "GET" || privatePath || event.request.destination === "document") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
