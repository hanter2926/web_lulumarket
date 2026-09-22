from django.urls import path

from . import views


app_name = "payments"

urlpatterns = [
    path("listings/<int:listing_id>/order/", views.create_order_view, name="create-order"),
    path("orders/<int:order_id>/payment-success/", views.payment_success, name="payment-success"),
    path("orders/<int:order_id>/refund/", views.refund_request, name="refund-request"),
    path("orders/<int:order_id>/dispute/", views.dispute_request, name="dispute-request"),
    path("webhooks/razorpay/", views.razorpay_webhook, name="razorpay-webhook"),
]