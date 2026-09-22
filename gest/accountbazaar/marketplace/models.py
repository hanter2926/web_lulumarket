from django.conf import settings
from django.db import models


class Listing(models.Model):

    CATEGORY_CHOICES = [
        ("gaming", "Gaming"),
        ("social", "Social Media"),
        ("youtube", "YouTube"),
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
