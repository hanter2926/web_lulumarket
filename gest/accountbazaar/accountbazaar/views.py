from django.shortcuts import render


from django.http import HttpResponse

from marketplace.models import Listing


def home(request):
    return render(request, "home.html", {
        "featured_listings": Listing.objects.filter(is_verified=True).exclude(status__iexact="sold").select_related("seller").order_by("-created_at")[:3],
    })


def service_worker(request):
    return HttpResponse(
        """const CACHE_NAME = 'accountbazaar-shell-v1';
const SHELL = ['/','/static/css/base.css','/static/css/navbar.css','/static/css/footer.css'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => { const path = new URL(event.request.url).pathname; const privatePath = /\\/(accounts|payments|orders|notifications|wallet|disputes)\\//.test(path); if (event.request.method !== 'GET' || privatePath) return; event.respondWith(fetch(event.request).catch(() => caches.match(event.request))); });""",
        content_type="application/javascript",
    )
