from __future__ import annotations

import random
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import MysteryRewardClaim, MysteryRewardConfig, MysteryRewardType


def get_reward_config():
    return MysteryRewardConfig.get_solo()


def get_active_reward_types():
    return list(MysteryRewardType.objects.filter(is_active=True).order_by("display_order", "name"))


def get_latest_claim_for_user(user):
    if not user or not user.is_authenticated:
        return None
    return (
        MysteryRewardClaim.objects.filter(user=user)
        .select_related("reward_type", "used_order")
        .order_by("-claimed_at")
        .first()
    )


def get_today_claim_for_user(user):
    if not user or not user.is_authenticated:
        return None
    today = timezone.localdate()
    return (
        MysteryRewardClaim.objects.filter(user=user, claimed_date=today)
        .select_related("reward_type", "used_order")
        .first()
    )


def get_available_claim_for_checkout(user):
    if not user or not user.is_authenticated:
        return None
    now = timezone.now()
    return (
        MysteryRewardClaim.objects.filter(user=user, is_active=True, is_used=False, expires_at__gt=now)
        .select_related("reward_type")
        .order_by("-claimed_at")
        .first()
    )


def get_claim_for_user_and_code(user, reward_code):
    if not user or not user.is_authenticated or not reward_code:
        return None
    return (
        MysteryRewardClaim.objects.filter(user=user, reward_code=reward_code)
        .select_related("reward_type", "used_order")
        .first()
    )


def _generate_unique_code():
    for _ in range(20):
        code = MysteryRewardClaim.generate_code()
        if not MysteryRewardClaim.objects.filter(reward_code=code).exists():
            return code
    raise RuntimeError("Unable to generate unique reward code.")


def claim_daily_reward(user):
    if not user or not user.is_authenticated:
        return None, False, "Please log in to claim your reward."

    config = get_reward_config()
    if not config.is_enabled:
        return None, False, "The Mystery Reward Box is currently disabled."

    today = timezone.localdate()
    existing = get_today_claim_for_user(user)
    if existing:
        return existing, False, "You have already claimed today's reward. Come back tomorrow!"

    reward_types = get_active_reward_types()
    if not reward_types:
        return None, False, "No mystery rewards are available right now."

    weights = [max(reward.weight, 1) for reward in reward_types]
    chosen_reward = random.choices(reward_types, weights=weights, k=1)[0]

    with transaction.atomic():
        try:
            claim = MysteryRewardClaim.objects.create(
                user=user,
                reward_type=chosen_reward,
                reward_code=_generate_unique_code(),
                claimed_date=today,
                expires_at=timezone.now() + timedelta(days=config.claim_expiry_days),
                is_active=True,
            )
        except IntegrityError:
            claim = get_today_claim_for_user(user)
            return claim, False, "You have already claimed today's reward. Come back tomorrow!"

    return claim, True, "Your mystery reward has been claimed successfully!"


def format_reward_value(claim):
    if not claim:
        return ""

    reward = claim.reward_type
    if reward.reward_kind == MysteryRewardType.AMOUNT_OFF:
        return f"₹{reward.amount_off:.0f} OFF"
    if reward.reward_kind == MysteryRewardType.PERCENT_OFF:
        return f"{reward.percent_off}% OFF"
    return "Free Delivery"


def calculate_reward_adjustment(claim, discounted_subtotal, delivery_charge):
    subtotal = Decimal(discounted_subtotal or 0)
    delivery = Decimal(delivery_charge or 0)
    reward_discount = Decimal("0.00")
    free_delivery = False

    if not claim or claim.is_used or claim.is_expired or not claim.is_active:
        return {
            "reward_discount": reward_discount,
            "delivery_charge": delivery,
            "free_delivery": free_delivery,
        }

    reward = claim.reward_type
    if reward.reward_kind == MysteryRewardType.AMOUNT_OFF:
        reward_discount = min(Decimal(reward.amount_off or 0), subtotal)
    elif reward.reward_kind == MysteryRewardType.PERCENT_OFF:
        reward_discount = (subtotal * Decimal(reward.percent_off or 0) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reward_discount = min(reward_discount, subtotal)
    elif reward.reward_kind == MysteryRewardType.FREE_DELIVERY:
        free_delivery = True
        delivery = Decimal("0.00")

    return {
        "reward_discount": reward_discount,
        "delivery_charge": delivery,
        "free_delivery": free_delivery,
    }


def use_reward_claim(claim, order):
    if not claim or claim.is_used:
        return claim

    claim.is_used = True
    claim.used_at = timezone.now()
    claim.used_order = order
    claim.save(update_fields=["is_used", "used_at", "used_order"])
    return claim


def mark_reward_claim_used_for_order(order):
    if not order or not getattr(order, "coupon_code", None):
        return None

    claim = get_claim_for_user_and_code(order.user, order.coupon_code)
    if not claim or claim.is_used:
        return claim

    return use_reward_claim(claim, order)