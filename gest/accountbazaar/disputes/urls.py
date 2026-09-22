from django.urls import path

from . import views


app_name = "disputes"

urlpatterns = [
    path("create/", views.create_dispute, name="create"),
]