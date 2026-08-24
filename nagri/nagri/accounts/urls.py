from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .views import AddressViewSet, PaymentMethodViewSet, UserProfileViewSet, UserViewSet, dashboard

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")
router.register(r"profiles", UserProfileViewSet, basename="profiles")
router.register(r"addresses", AddressViewSet, basename="addresses")
router.register(r"payment-methods", PaymentMethodViewSet, basename="payment-methods")

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard-page/", views.dashboard_page, name="dashboard_page"),
    path("auth/", views.login_page, name="login_page"),
    path("login/", views.email_login_view, name="email_login"),
    path("register/", views.signup_form_view, name="signup_form"),
    path("signup/", views.signup_page, name="signup_page"),
    path("signup-submit/", views.signup_submit, name="signup_submit"),
    path("logout/", views.logout_view, name="logout_page"),
    path("request-otp/", views.request_otp, name="request_otp"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("otp-login/", views.otp_login_page, name="otp_login_page"),
    *router.urls,
]
