from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-reset/request/", views.password_reset_request, name="password_reset_request"),
    path("password-reset/confirm/", views.password_reset_confirm, name="password_reset_confirm"),
    path("csrf/", views.csrf_token_view, name="csrf"),

    path(
        "verify-otp/",
        views.verify_signup_otp,
        name="verify_signup_otp",
    ),

    path(
        "resend-otp/",
        views.resend_signup_otp,
        name="resend_signup_otp",
    ),
]
