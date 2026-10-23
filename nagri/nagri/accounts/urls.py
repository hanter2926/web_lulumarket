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
    path("verify-contacts/", views.verify_contacts, name="verify_contacts"),
    path("register/", views.signup_form_view, name="signup_form"),
    path("register/verify/", views.signup_email_verify, name="signup_email_verify"),
    path("register/verify/resend/", views.signup_email_verify_resend, name="signup_email_verify_resend"),
    path("signup/", views.signup_page, name="signup_page"),
    path("signup-submit/", views.signup_submit, name="signup_submit"),
    path("signup/otp/resend/", views.signup_phone_otp_resend, name="signup_phone_otp_resend"),
    path("logout/", views.logout_view, name="logout_page"),
    path("request-otp/", views.request_otp, name="request_otp"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("phone-change/request/", views.phone_change_request, name="phone_change_request"),
    path("phone-change/verify/", views.phone_change_verify, name="phone_change_verify"),
    path("phone-change/resend/", views.phone_change_resend, name="phone_change_resend"),
    path("otp-login/", views.otp_login_page, name="otp_login_page"),
    path("email-otp/", views.email_otp_login_page, name="email_otp_login"),
    path("email-otp/verify/", views.email_otp_login_verify, name="email_otp_login_verify"),
    path("password-reset/otp/", views.password_reset_otp_page, name="password_reset_otp"),
    path("password-reset/otp/verify/", views.password_reset_otp_verify, name="password_reset_otp_verify"),
    path("password-reset/otp/new/", views.password_reset_otp_new, name="password_reset_otp_new"),
    # Password reset using Django auth views
    path('password-reset/', views.PasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    *router.urls,
    path('settings/', views.account_settings, name='account_settings'),
    path('addresses/<int:pk>/edit/', views.edit_address, name='address_edit'),
    path('addresses/<int:pk>/delete/', views.delete_address, name='address_delete'),
    path('addresses/<int:pk>/set-default/', views.set_default_address, name='address_set_default'),
]

app_name = 'accounts'

# Owner slider management
urlpatterns += [
    path('owner/sliders/', views.owner_sliders_list, name='owner_sliders_list'),
    path('owner/sliders/add/', views.owner_sliders_add, name='owner_sliders_add'),
    path('owner/sliders/<int:pk>/edit/', views.owner_sliders_edit, name='owner_sliders_edit'),
    path('owner/sliders/<int:pk>/delete/', views.owner_sliders_delete, name='owner_sliders_delete'),
    path('owner/sliders/<int:pk>/toggle/', views.owner_sliders_toggle, name='owner_sliders_toggle'),
]
