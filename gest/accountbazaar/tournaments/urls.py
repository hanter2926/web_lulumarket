from django.urls import path

from . import views


app_name = "tournaments"

urlpatterns = [
    path("", views.tournament_list, name="list"),
    path("create/", views.create_tournament, name="create"),
    path("<int:tournament_id>/", views.tournament_detail, name="detail"),
    path("<int:tournament_id>/join/", views.join_tournament, name="join"),
    path("matches/<int:match_id>/result/", views.submit_result, name="submit-result"),
]
