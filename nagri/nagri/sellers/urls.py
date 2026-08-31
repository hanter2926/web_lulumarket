from django.urls import path
from . import views

app_name = "sellers"

urlpatterns = [
    path("apply/", views.apply_start, name="apply_start"),
    path("send-otp/", views.send_email_otp, name="send_otp"),
    path("verify-email/", views.verify_email_otp, name="verify_email"),
    path("documents/", views.documents, name="documents"),
    path("categories/", views.categories, name="categories"),
    path("status/", views.status_view, name="status"),
    path("document/<int:pk>/<str:field>/", views.protected_document_view, name="protected_document"),
    path("admin-marketplace/dashboard/", views.owner_dashboard, name="owner_dashboard"),
    path("admin-marketplace/sellers/", views.owner_seller_list, name="owner_seller_list"),
    path("admin-marketplace/sellers/<int:user_id>/", views.owner_seller_detail, name="owner_seller_detail"),
    path("admin-marketplace/sellers/<int:user_id>/action/", views.owner_seller_action, name="owner_seller_action"),
    path("admin-marketplace/top-sellers/", views.owner_top_sellers, name="owner_top_sellers"),
    path("products/", views.product_list, name="product_list"),
    path("products/add/", views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("products/<int:pk>/toggle/", views.product_toggle_active, name="product_toggle_active"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("orders/", views.orders_list, name="orders_list"),
    path("orders/<int:item_id>/", views.order_item_detail, name="order_item_detail"),
    path("orders/<int:item_id>/status/", views.order_item_status, name="order_item_status"),
    path("reports/", views.reports, name="reports"),
    path("products/performance/", views.product_performance, name="product_performance"),
]
