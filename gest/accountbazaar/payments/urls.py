from django.urls import path

from . import views


app_name = "payments"

urlpatterns = [
    path("", views.payment_page, name="payment-page"),
    path("listings/<int:listing_id>/checkout/", views.checkout_start, name="checkout-start"),
    path("listings/<int:listing_id>/order/", views.create_order_view, name="create-order"),
    path("orders/<int:order_id>/summary/", views.order_summary, name="order-summary"),
    path("orders/<int:order_id>/proceed/", views.proceed_to_payment, name="proceed-payment"),
    path("orders/<int:order_id>/payment/", views.payment_checkout, name="payment"),
    path("orders/<int:order_id>/demo-pay/", views.demo_payment, name="demo-payment"),
    path("orders/<int:order_id>/demo-failed/", views.demo_payment_failed, name="demo-payment-failed"),
    path("orders/<int:order_id>/payment-success-page/", views.payment_success_page, name="payment-success-page"),
    path("orders/<int:order_id>/payment-success/", views.payment_success, name="payment-success"),
    path("orders/<int:order_id>/", views.order_detail, name="order-detail"),
    path("orders/", views.my_orders, name="my-orders"),
    path("seller-orders/", views.seller_orders, name="seller-orders"),
    path("orders/<int:order_id>/transfer-start/", views.transfer_start, name="transfer-start"),
    path("orders/<int:order_id>/transfer-sent/", views.transfer_sent, name="transfer-sent"),
    path("orders/<int:order_id>/transfer-received/", views.transfer_received, name="transfer-received"),
    path("orders/<int:order_id>/refund/", views.refund_request, name="refund-request"),
    path("orders/<int:order_id>/dispute/", views.dispute_request, name="dispute-request"),
    path("orders/<int:order_id>/review/", views.review_request, name="review-request"),
    path("webhooks/razorpay/", views.razorpay_webhook, name="razorpay-webhook"),
]