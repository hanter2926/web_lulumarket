"""
URL configuration for accountbazaar project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.urls import include, path
from django.conf.urls.static import static

from accountbazaar.dashboard import admin_dashboard
from accountbazaar.owner_dashboard import owner_dashboard
from accountbazaar.views import home, service_worker

urlpatterns = [
    path('', home, name='home'),
    path('service-worker.js', service_worker, name='service-worker'),
    path('accounts/', include('accounts.urls')),
    path('admin/dashboard/', admin_dashboard, name='admin-dashboard'),
    path('owner/dashboard/', owner_dashboard, name='owner-dashboard'),
    path('admin/', admin.site.urls),
    path('marketplace/', include('marketplace.urls')),
    path('payments/', include('payments.urls')),
    path('tournaments/', include('tournaments.urls')),
    path('notifications/', include('notifications.urls')),
    path('wallet/', include('wallet.urls')),
    path('disputes/', include('disputes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
