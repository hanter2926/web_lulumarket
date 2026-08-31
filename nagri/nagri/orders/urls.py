from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .views import (
    OrderItemViewSet, OrderViewSet, order_list_view, order_detail_view,
    checkout_view, checkout_address_view, checkout_delivery_view,
    checkout_payment_view, checkout_review_view, order_confirmation_view
)

router = DefaultRouter()
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"order-items", OrderItemViewSet, basename="order-items")

urlpatterns = [
    # Checkout flow
    path("checkout/", checkout_view, name="checkout"),
    path("checkout/address/", checkout_address_view, name="checkout_address"),
    path("checkout/delivery/", checkout_delivery_view, name="checkout_delivery"),
    path("checkout/payment/", checkout_payment_view, name="checkout_payment"),
    path("checkout/review/", checkout_review_view, name="checkout_review"),
    path("checkout/confirmation/<int:order_id>/", order_confirmation_view, name="order_confirmation"),
    path("payment/<int:order_id>/", views.payment_page_view, name="payment_page"),
    path("payment/<int:order_id>/upi-submit/", views.upi_submit_view, name="upi_submit"),
    path("payment/success/<int:order_id>/", views.payment_success_view, name="payment_success"),
    path("payment/failed/<int:order_id>/", views.payment_failed_view, name="payment_failed"),
    
    # Order management
    path("", order_list_view, name="order_list"),
    path("<int:order_id>/", order_detail_view, name="order_detail"),
    
    # Payment
    path("verify-payment/", views.verify_payment, name="verify_payment"),
    path("payment-webhook/", views.payment_webhook, name="payment_webhook"),
    
    # API
    *router.urls,
]
