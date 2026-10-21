import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .email_delivery import send_account_email
from .models import CustomUser, EmailOTPChallenge, EmailOTPThrottle, UserProfile

OTP_LIFETIME = timedelta(minutes=5)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_REQUEST_WINDOW = timedelta(hours=1)
OTP_MAX_REQUESTS_PER_WINDOW = 5
OTP_MAX_ATTEMPTS = 5


def _email_digest(email):
    return salted_hmac(
        "accounts.email_otp",
        email.strip().casefold(),
        secret=settings.SECRET_KEY,
    ).hexdigest()


def _eligible_user(email, purpose):
    user = CustomUser.objects.filter(email__iexact=email).first()
    if not user:
        return None

    if purpose == EmailOTPChallenge.Purpose.SIGNUP:
        if user.is_active or user.is_email_verified or not user.has_usable_password():
            return None
    elif not user.is_active:
        return None

    if purpose == EmailOTPChallenge.Purpose.LOGIN:
        profile = UserProfile.objects.filter(user=user).only("is_phone_verified").first()
        if not profile or not (profile.is_phone_verified or user.is_email_verified):
            return None
    elif not user.has_usable_password():
        return None

    return user


def request_email_otp(email, purpose):
    normalized_email = email.strip()
    digest = _email_digest(normalized_email)
    user = _eligible_user(normalized_email, purpose)
    if not user:
        return "accepted"

    now = timezone.now()
    with transaction.atomic():
        throttle, _ = EmailOTPThrottle.objects.get_or_create(
            email_digest=digest,
            purpose=purpose,
            defaults={"window_started_at": now},
        )
        throttle = EmailOTPThrottle.objects.select_for_update().get(pk=throttle.pk)

        if now - throttle.window_started_at >= OTP_REQUEST_WINDOW:
            throttle.window_started_at = now
            throttle.request_count = 0
            throttle.last_requested_at = None

        if (
            throttle.request_count >= OTP_MAX_REQUESTS_PER_WINDOW
            or (
                throttle.last_requested_at
                and now - throttle.last_requested_at < OTP_RESEND_COOLDOWN
            )
        ):
            return "throttled"

        throttle.request_count += 1
        throttle.last_requested_at = now
        throttle.save(
            update_fields=[
                "window_started_at",
                "request_count",
                "last_requested_at",
            ]
        )

        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge, _ = EmailOTPChallenge.objects.update_or_create(
            email_digest=digest,
            purpose=purpose,
            defaults={
                "user": user,
                "code_hash": make_password(code),
                "created_at": now,
                "expires_at": now + OTP_LIFETIME,
                "attempts": 0,
                "consumed_at": None,
            },
        )

    purpose_text = (
        "verify your email address"
        if purpose == EmailOTPChallenge.Purpose.SIGNUP
        else "sign in"
        if purpose == EmailOTPChallenge.Purpose.LOGIN
        else "reset your password"
    )
    message = (
        f"Your NAGRI code to {purpose_text} is {code}.\n\n"
        "This code expires in 5 minutes and can only be used once. "
        "If you did not request it, you can ignore this email."
    )
    try:
        send_account_email("Your NAGRI email verification code", message, user.email)
    except Exception:
        EmailOTPChallenge.objects.filter(pk=challenge.pk).update(consumed_at=timezone.now())
        raise

    return "accepted"


def verify_email_otp(email, code, purpose):
    digest = _email_digest(email.strip())
    now = timezone.now()

    with transaction.atomic():
        challenge = (
            EmailOTPChallenge.objects.select_for_update()
            .select_related("user")
            .filter(email_digest=digest, purpose=purpose)
            .order_by("-created_at", "-pk")
            .first()
        )
        if (
            not challenge
            or challenge.consumed_at is not None
            or not challenge.code_hash
        ):
            return None

        if challenge.expires_at <= now or challenge.attempts >= OTP_MAX_ATTEMPTS:
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            return None

        if not check_password(code, challenge.code_hash):
            challenge.attempts += 1
            if challenge.attempts >= OTP_MAX_ATTEMPTS:
                challenge.consumed_at = now
            challenge.save(update_fields=["attempts", "consumed_at"])
            return None

        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])
        user = challenge.user
        if not user:
            return None

        if purpose == EmailOTPChallenge.Purpose.SIGNUP:
            if user.is_active or user.is_email_verified:
                return None
            user.is_email_verified = True
            user.is_active = True
            user.save(update_fields=["is_email_verified", "is_active", "updated_at"])
            return user

        if not user.is_active:
            return None

        if purpose == EmailOTPChallenge.Purpose.LOGIN:
            profile = UserProfile.objects.filter(user=user).only("is_phone_verified").first()
            if not profile or not (profile.is_phone_verified or user.is_email_verified):
                return None
        elif not user.has_usable_password():
            return None

        return user
