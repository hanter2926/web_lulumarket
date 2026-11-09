from django.urls import path

from . import views

app_name = "tools"

urlpatterns = [
    path("convert/", views.convert_units, name="convert_units"),
    path("compare/", views.compare_files, name="compare_files"),
    path("reports/", views.reports, name="reports"),
]
