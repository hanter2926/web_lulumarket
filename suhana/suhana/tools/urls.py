from django.urls import path

from . import views

app_name = "tools"

urlpatterns = [
    path("convert/", views.convert_units, name="convert_units"),
    path("compare/", views.compare_files, name="compare_files"),
    path("jobs/<uuid:job_id>/", views.comparison_job_status, name="comparison_job_status"),
    path("jobs/<uuid:job_id>/cancel/", views.cancel_comparison, name="cancel_comparison"),
    path("reports/", views.reports, name="reports"),
]
