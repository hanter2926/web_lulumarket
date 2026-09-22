from django.urls import path

from .views import AccountLoginView, account_logout, profile, register, switch_account


app_name = "accounts"

urlpatterns = [
    path("login/", AccountLoginView.as_view(), name="login"),
    path("register/", register, name="register"),
    path("profile/", profile, name="profile"),
    path("logout/", account_logout, name="logout"),
    path("switch/<int:account_id>/", switch_account, name="switch-account"),
]
