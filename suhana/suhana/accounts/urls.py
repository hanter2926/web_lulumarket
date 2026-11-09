from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
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

