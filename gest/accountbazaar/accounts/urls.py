from django.urls import path

from .views import AccountLoginView, account_logout, register


app_name = "accounts"

urlpatterns = [
    path("login/", AccountLoginView.as_view(), name="login"),
    path("register/", register, name="register"),
    path("logout/", account_logout, name="logout"),
]
