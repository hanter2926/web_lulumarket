from django.urls import path

from . import views


app_name = "disputes"

urlpatterns = [
    path("orders/<int:order_id>/create/", views.create_dispute, name="create"),
    path("<int:dispute_id>/", views.detail, name="detail"),
    path("report/<str:target_type>/<int:target_id>/", views.create_report, name="report"),
    path("moderation/", views.moderation, name="moderation"),
]