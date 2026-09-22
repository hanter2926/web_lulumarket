from django.urls import path

from . import views


app_name = "marketplace"

urlpatterns = [
    path("", views.listings, name="listings"),
    path("sell/", views.sell_account, name="sell-account"),
    path("<int:listing_id>/", views.listing_detail, name="listing-detail"),
]
