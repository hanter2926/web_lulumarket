from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .views import OrderItemViewSet, OrderViewSet

router = DefaultRouter()
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"order-items", OrderItemViewSet, basename="order-items")

urlpatterns = [
    path("verify-payment/", views.verify_payment, name="verify_payment"),
    path("payment-webhook/", views.payment_webhook, name="payment_webhook"),
    *router.urls,
]
