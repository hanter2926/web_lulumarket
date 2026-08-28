const CACHE_NAME = 'nagri-cache-v2';

// Static resources we want to pre-cache (manifest + icons)
const PRECACHE_URLS = [
  '/static/manifest.json',
  '/static/images/icons/icon-192x192.png',
  '/static/images/icons/icon-512x512.png'
];

// Simple offline fallback HTML (used when network is down)
const OFFLINE_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>Offline</title></head><body><h1>Offline</h1><p>You appear to be offline. Please check your connection.</p></body></html>`;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch(() => {});
    })
  );
  // Activate new SW as soon as it's finished installing
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Clean up old caches and take control of clients immediately
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.map((key) => { if (key !== CACHE_NAME) return caches.delete(key); return null; })
    ))
    .then(() => self.clients.claim())
  );
});

// Helper: return true for navigation requests (HTML page navigations)
function isNavigationRequest(request){
  return request.mode === 'navigate' || (request.headers && request.headers.get && request.headers.get('accept') && request.headers.get('accept').includes('text/html'));
}

self.addEventListener('fetch', (event) => {
  // Only handle GET requests in the SW
  if (event.request.method !== 'GET') return;

  // Network-first for navigations (HTML pages)
  if (isNavigationRequest(event.request)){
    event.respondWith((async () => {
      try{
        // Try network first (include credentials for Django pages)
        const netResp = await fetch(event.request, { credentials: 'same-origin' });
        // Don't cache HTML navigation responses (avoid serving a cached '/' for other URLs)
        return netResp;
      }catch(err){
        // Network failed — try to find a cached response for the exact request (if any)
        const cache = await caches.open(CACHE_NAME);
        const cached = await cache.match(event.request);
        if (cached) return cached;
        // Return a simple offline page instead of returning the cached home page
        return new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html' } });
      }
    })());
    return;
  }

  // For other requests (static assets), use cache-first then network, and cache static resources
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(event.request);
    if (cached) return cached;
    try{
      const response = await fetch(event.request, { credentials: 'same-origin' });
      // Only cache non-HTML same-origin static assets (js, css, images, manifest)
      const contentType = response.headers.get('Content-Type') || '';
      const isHTML = contentType.includes('text/html');
      const isSameOrigin = new URL(event.request.url).origin === self.location.origin;
      if (!isHTML && isSameOrigin){
        try{ cache.put(event.request, response.clone()); } catch(e){}
      }
      return response;
    }catch(err){
      // If fetch fails, attempt to return an icon or manifest from cache as best-effort
      const fallback = await cache.match('/static/images/icons/icon-192x192.png');
      if (fallback) return fallback;
      return new Response('', { status: 503, statusText: 'Service Unavailable' });
    }
  })());
});
