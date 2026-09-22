from django.conf import settings
from django.db import models


class Listing(models.Model):

    CATEGORY_CHOICES = [
        ("game", "Game Account"),
        ("gaming", "Gaming"),
        ("social", "Social Media"),
        ("youtube", "YouTube"),
        ("website", "Website"),
        ("app", "App"),
        ("other", "Other Digital Asset"),
        ("software", "Software"),
    ]

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings"
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES
    )

    title = models.CharField(max_length=200)

    description = models.TextField()

    game_name = models.CharField(max_length=160, blank=True, null=True)
    game_id = models.CharField(max_length=160, blank=True, null=True)
    game_level = models.CharField(max_length=80, blank=True, null=True)
    game_rank = models.CharField(max_length=120, blank=True, null=True)
    website_name = models.CharField(max_length=160, blank=True, null=True)
    website_url = models.URLField(max_length=500, blank=True, null=True)
    app_name = models.CharField(max_length=160, blank=True, null=True)
    app_url = models.URLField(max_length=500, blank=True, null=True)
    platform = models.CharField(max_length=120, blank=True, null=True)
    features = models.TextField(blank=True, null=True)
    public_details = models.TextField(blank=True, null=True)

    image = models.ImageField(
        upload_to="listings/%Y/%m/",
        blank=True,
        null=True,
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    status = models.CharField(
        max_length=30,
        default="pending"
    )

    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
