import random
import string

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class MysteryRewardConfig(models.Model):
    is_enabled = models.BooleanField(default=True)
    claim_expiry_days = models.PositiveIntegerField(default=7)
    display_title = models.CharField(max_length=120, default="Daily Mystery Reward Box")
    display_subtitle = models.CharField(max_length=255, default="Open once per day and claim a surprise reward.")
    button_label = models.CharField(max_length=80, default="Open Mystery Box")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mystery Reward Box Config"
        verbose_name_plural = "Mystery Reward Box Config"

    def __str__(self):
        return "Mystery Reward Box Config"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "is_enabled": True,
                "claim_expiry_days": 7,
                "display_title": "Daily Mystery Reward Box",
                "display_subtitle": "Open once per day and claim a surprise reward.",
                "button_label": "Open Mystery Box",
            },
        )
        return obj


class MysteryRewardType(models.Model):
    AMOUNT_OFF = "amount_off"
    PERCENT_OFF = "percent_off"
    FREE_DELIVERY = "free_delivery"

    REWARD_KIND_CHOICES = [
        (AMOUNT_OFF, "Amount Off"),
        (PERCENT_OFF, "Percent Off"),
        (FREE_DELIVERY, "Free Delivery"),
    ]

    name = models.CharField(max_length=120)
    reward_kind = models.CharField(max_length=20, choices=REWARD_KIND_CHOICES)
    amount_off = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    percent_off = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True)
    weight = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(reward_kind="free_delivery")
                    | Q(amount_off__gte=0)
                    | Q(percent_off__gte=0)
                ),
                name="rewards_valid_kind_values",
            )
        ]

    def __str__(self):
        return self.name

    def reward_label(self):
        if self.reward_kind == self.AMOUNT_OFF:
            return f"₹{self.amount_off:.0f} OFF"
        if self.reward_kind == self.PERCENT_OFF:
            return f"{self.percent_off}% OFF"
        return "Free Delivery"

    reward_label.short_description = "Reward Label"

    def effect_summary(self):
        if self.reward_kind == self.AMOUNT_OFF:
            return f"₹{self.amount_off:.0f} off your order"
        if self.reward_kind == self.PERCENT_OFF:
            return f"{self.percent_off}% off your order"
        return "Free delivery on your order"

    effect_summary.short_description = "Effect Summary"


class MysteryRewardClaim(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mystery_reward_claims")
    reward_type = models.ForeignKey(MysteryRewardType, on_delete=models.PROTECT, related_name="claims")
    reward_code = models.CharField(max_length=32, unique=True, db_index=True)
    claimed_date = models.DateField(default=timezone.localdate, db_index=True)
    claimed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    used_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    used_order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mystery_reward_claims",
    )

    class Meta:
        ordering = ["-claimed_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "claimed_date"], name="uniq_daily_mystery_reward_claim")
        ]

    def __str__(self):
        return f"{self.user} - {self.reward_code}"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def display_state(self):
        if self.is_used:
            return "Used"
        if self.is_expired:
            return "Expired"
        return "Active"

    @staticmethod
    def generate_code(prefix="MRB"):
        token = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"{prefix}-{token}"