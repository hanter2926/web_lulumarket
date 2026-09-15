const STATIC_CACHE = 'nagri-static-v4';
const PAGE_CACHE = 'nagri-pages-v4';
const OFFLINE_URL = '/offline/';
const PRECACHE_URLS = [
  OFFLINE_URL,
  '/static/manifest.json',
  '/static/css/base/base.css',
  '/static/css/base/navbar.css',
  '/static/css/base/footer.css',
  '/static/css/navbar.css',
  '/static/css/navbar-responsive.css',
  '/static/css/pwa/offline.css',
  '/static/css/pwa/offline-status.css',
  '/static/js/base/main.js',
  '/static/js/base/navbar.js',
  '/static/js/pwa/indexeddb.js',
  '/static/js/pwa/sync-manager.js',
  '/static/js/pwa/pwa.js',
  '/static/images/icons/icon-192x192.png',
  '/static/images/icons/icon-512x512.png'
];

function isPrivateRequest(request) {
  const url = new URL(request.url);
  return url.pathname.startsWith('/admin/') ||
    url.pathname.startsWith('/accounts/') ||
    url.pathname.startsWith('/cart/') ||
    url.pathname.startsWith('/checkout/') ||
    url.pathname.startsWith('/orders/') ||
    url.pathname.startsWith('/payment/') ||
    url.pathname.startsWith('/wishlist/') ||
    url.pathname.startsWith('/sellers/') ||
    url.pathname.startsWith('/api/') ||
    documentCookieContainsPrivateSession(request);
}

function documentCookieContainsPrivateSession(request) {
  const cookie = request.headers.get('cookie') || '';
  return cookie.includes('sessionid=');
}

function isNavigation(request) {
  return request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html');
}

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(STATIC_CACHE).then(function (cache) {
    return Promise.all(PRECACHE_URLS.map(function (url) {
      return cache.add(url).catch(function () { return null; });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (key) {
      return ![STATIC_CACHE, PAGE_CACHE].includes(key);
    }).map(function (key) { return caches.delete(key); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (event) {
  const request = event.request;
  if (request.method !== 'GET') return;

  if (isNavigation(request)) {
    if (isPrivateRequest(request)) return;
    event.respondWith(fetch(request).then(function (response) {
      if (response.ok) {
        const copy = response.clone();
        caches.open(PAGE_CACHE).then(function (cache) { return cache.put(request, copy); });
      }
      return response;
    }).catch(function () {
      return caches.match(request).then(function (cached) {
        return cached || caches.match(OFFLINE_URL);
      });
    }));
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(request).then(function (cached) {
      return cached || fetch(request).then(function (response) {
        if (response.ok) {
          caches.open(STATIC_CACHE).then(function (cache) {
            return cache.put(request, response.clone());
          });
        }
        return response;
      });
    }));
  }
});

self.addEventListener('sync', function (event) {
  if (event.tag === 'nagri-sync') {
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clients) {
      clients.forEach(function (client) {
        client.postMessage({ type: 'nagri-sync' });
      });
    }));
  }
});
