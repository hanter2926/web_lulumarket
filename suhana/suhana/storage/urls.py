from django.urls import path

from . import views

app_name = "storage"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("files/", views.list_files, name="list_files"),
    path("folders/", views.create_folder, name="create_folder"),
    path("folders/<int:folder_id>/rename/", views.rename_folder, name="rename_folder"),
    path("folders/<int:folder_id>/delete/", views.delete_folder, name="delete_folder"),
    path("files/upload/", views.upload_file, name="upload_file"),
    path("files/<int:file_id>/download/", views.download_file, name="download_file"),
    path("files/<int:file_id>/delete/", views.delete_file, name="delete_file"),
]
