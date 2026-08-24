from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from nagri import views as site_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("unyan.urls")),
    path("accounts/", include("accounts.urls")),
    path("products/", include("products.urls")),
    path("orders/", include("orders.urls")),
    path("cart/", include("cart.urls")),
    path("wishlist/", include("wishlist.urls")),
]

handler400 = site_views.bad_request
handler403 = site_views.permission_denied
handler404 = site_views.page_not_found
handler500 = site_views.server_error

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


    
