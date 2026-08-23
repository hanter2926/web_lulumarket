from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("policies/privacy/", views.privacy_policy, name="privacy_policy"),
    path("policies/terms/", views.terms_conditions, name="terms_conditions"),
    path("policies/refund/", views.refund_policy, name="refund_policy"),
    path("policies/shipping/", views.shipping_policy, name="shipping_policy"),
    path("policies/returns/", views.return_policy, name="return_policy"),
    path("policies/cancellation/", views.cancellation_policy, name="cancellation_policy"),
    path("support/help-center/", views.help_center, name="help_center"),
    path("support/contact/", views.contact_support, name="contact_support"),
]
