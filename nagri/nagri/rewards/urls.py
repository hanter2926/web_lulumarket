from django.urls import path

from .views import claim_mystery_reward

urlpatterns = [
    path("mystery-box/claim/", claim_mystery_reward, name="mystery_box_claim"),
]