from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "sellers"

router = DefaultRouter()
router.register(r"api/shopkeepers", views.ShopkeeperViewSet, basename="shopkeepers")
router.register(r"api/stores", views.StoreViewSet, basename="stores")
router.register(r"api/workers", views.DeliveryWorkerViewSet, basename="workers")
router.register(r"api/assignments", views.DeliveryAssignmentViewSet, basename="assignments")
router.register(r"api/areas", views.AreaViewSet, basename="areas")
router.register(r"api/local/incidents", views.DeliveryIncidentViewSet, basename="incidents")
router.register(r"api/local/route-issues", views.RouteIssueViewSet, basename="route-issues")

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
    path("admin/test-email/", views.admin_test_email, name="admin_test_email"),
    path("products/", views.product_list, name="product_list"),
    path("products/add/", views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("products/<int:pk>/toggle/", views.product_toggle_active, name="product_toggle_active"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("shopkeeper/dashboard/", views.shopkeeper_dashboard, name="shopkeeper_dashboard"),
    path("shopkeeper/stores/", views.shopkeeper_stores, name="shopkeeper_stores"),
    path("shopkeeper/stores/add/", views.shopkeeper_store_add, name="shopkeeper_store_add"),
    path("shopkeeper/stores/<int:pk>/", views.shopkeeper_store_detail, name="shopkeeper_store_detail"),
    path("shopkeeper/stores/<int:pk>/edit/", views.shopkeeper_store_edit, name="shopkeeper_store_edit"),
    path("shopkeeper/products/", views.shopkeeper_products, name="shopkeeper_products"),
    path("shopkeeper/products/add/", views.shopkeeper_product_add, name="shopkeeper_product_add"),
    path("shopkeeper/products/<int:pk>/edit/", views.shopkeeper_product_edit, name="shopkeeper_product_edit"),
    path("shopkeeper/delivery-workers/", views.shopkeeper_workers, name="shopkeeper_workers"),
    path("shopkeeper/delivery-workers/add/", views.shopkeeper_worker_add, name="shopkeeper_worker_add"),
    path("shopkeeper/delivery-workers/<int:pk>/edit/", views.shopkeeper_worker_edit, name="shopkeeper_worker_edit"),
    path("shopkeeper/delivery-assignments/", views.shopkeeper_assignments, name="shopkeeper_assignments"),
    path("shopkeeper/delivery-assignments/<int:pk>/assign/", views.shopkeeper_assignment_assign, name="shopkeeper_assignment_assign"),
    path("delivery/dashboard/", views.worker_dashboard, name="worker_dashboard"),
    path("delivery/report-problem/", views.worker_report_incident, name="worker_report_incident"),
    path("delivery/assignments/<int:assignment_id>/report-problem/", views.worker_report_incident, name="worker_assignment_report_incident"),
    path("delivery/assignments/", views.worker_assignments, name="worker_assignments"),
    path("delivery/assignments/<int:pk>/update/", views.worker_assignment_update, name="worker_assignment_update"),
    path("orders/", views.orders_list, name="orders_list"),
    path("orders/<int:item_id>/", views.order_item_detail, name="order_item_detail"),
    path("orders/<int:item_id>/status/", views.order_item_status, name="order_item_status"),
    path("reports/", views.reports, name="reports"),
    path("products/performance/", views.product_performance, name="product_performance"),
    *router.urls,
]
