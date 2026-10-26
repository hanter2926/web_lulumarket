import secrets
import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from requests import RequestException

from .email_delivery import send_account_email
from .models import (
    CustomUser,
    EmailOTPChallenge,
    EmailOTPThrottle,
    PendingSignup,
    UserProfile,
)

OTP_LIFETIME = timedelta(minutes=10)
OTP_RESEND_COOLDOWN = timedelta(seconds=30)
OTP_IP_REQUEST_WINDOW = timedelta(minutes=10)
OTP_IP_MAX_REQUESTS_PER_WINDOW = 30
OTP_MAX_ATTEMPTS = 10

logger = logging.getLogger(__name__)


class EmailOTPStatus(str, Enum):
    SUCCESS = "success"
    INCORRECT = "incorrect"
    EXPIRED = "expired"
    LOCKED = "locked"
    UNAVAILABLE = "unavailable"
    ACCOUNT_CREATION_FAILED = "account_creation_failed"


@dataclass(frozen=True)
class EmailOTPVerification:
    status: EmailOTPStatus
    user: CustomUser | None = None


def _email_digest(email):
    return salted_hmac(
        "accounts.email_otp",
        email.strip().casefold(),
        secret=settings.SECRET_KEY,
    ).hexdigest()


def consume_otp_ip_request(requester_ip):
    if not requester_ip:
        return True

    ip_digest = salted_hmac(
        "accounts.email_otp.ip_request",
        str(requester_ip).strip(),
        secret=settings.SECRET_KEY,
    ).hexdigest()
    now = timezone.now()
    purpose = EmailOTPChallenge.Purpose.SIGNUP
    with transaction.atomic():
        throttle, _ = EmailOTPThrottle.objects.get_or_create(
            email_digest=ip_digest,
            purpose=purpose,
            defaults={"window_started_at": now},
        )
        throttle = EmailOTPThrottle.objects.select_for_update().get(pk=throttle.pk)
        if now - throttle.window_started_at >= OTP_IP_REQUEST_WINDOW:
            throttle.window_started_at = now
            throttle.request_count = 0

        if throttle.request_count >= OTP_IP_MAX_REQUESTS_PER_WINDOW:
            return False

        throttle.request_count += 1
        throttle.last_requested_at = now
        throttle.save(
            update_fields=[
                "window_started_at",
                "request_count",
                "last_requested_at",
            ]
        )
    return True


def _eligible_user(email, purpose):
    if purpose == EmailOTPChallenge.Purpose.SIGNUP:
        pending_signup = PendingSignup.objects.filter(email__iexact=email).first()
        if pending_signup:
            return pending_signup

        # Keep OTP verification working for pending accounts created before staged signup.
        user = CustomUser.objects.filter(email__iexact=email).first()
        if (
            user
            and user.account_status == CustomUser.AccountStatus.PENDING_VERIFICATION
            and not user.is_active
            and not user.is_email_verified
            and user.has_usable_password()
        ):
            return user
        return None

    user = CustomUser.objects.filter(email__iexact=email).first()
    if not user:
        return None

    if purpose == EmailOTPChallenge.Purpose.PASSWORD_RESET and (
        user.account_status != CustomUser.AccountStatus.ACTIVE or not user.is_active
    ):
        return None

    if not user.has_usable_password():
        return None

    return user


def request_email_otp(email, purpose, requester_ip=None):
    if purpose not in (
        EmailOTPChallenge.Purpose.SIGNUP,
        EmailOTPChallenge.Purpose.PASSWORD_RESET,
    ):
        raise ValueError("Unsupported email OTP purpose.")

    normalized_email = email.strip()
    digest = _email_digest(normalized_email)
    eligible = _eligible_user(normalized_email, purpose)
    if not eligible:
        return "accepted"

    if not consume_otp_ip_request(requester_ip):
        return "throttled"

    recipient_email = eligible.email
    challenge_user = (
        eligible
        if isinstance(eligible, CustomUser)
        else None
    )
    now = timezone.now()
    with transaction.atomic():
        throttle, _ = EmailOTPThrottle.objects.get_or_create(
            email_digest=digest,
            purpose=purpose,
            defaults={"window_started_at": now},
        )
        throttle = EmailOTPThrottle.objects.select_for_update().get(pk=throttle.pk)

        if throttle.last_requested_at and now - throttle.last_requested_at < OTP_RESEND_COOLDOWN:
            return "throttled"

        throttle.last_requested_at = now
        throttle.save(update_fields=["last_requested_at"])

        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge, _ = EmailOTPChallenge.objects.update_or_create(
            email_digest=digest,
            purpose=purpose,
            defaults={
                "user": challenge_user,
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
        else "reset your password"
    )
    message = (
        f"Your NAGRI code to {purpose_text} is {code}.\n\n"
        "This code expires in 10 minutes and can only be used once. "
        "If you did not request it, you can ignore this email."
    )
    try:
        send_account_email("Your NAGRI verification code", message, recipient_email)
    except RequestException:
        # A timeout can happen after Brevo accepted the message, so keep its OTP usable.
        raise
    except Exception:
        EmailOTPChallenge.objects.filter(pk=challenge.pk).update(consumed_at=timezone.now())
        raise

    return "accepted"


def verify_email_otp(email, code, purpose):
    if purpose not in (
        EmailOTPChallenge.Purpose.SIGNUP,
        EmailOTPChallenge.Purpose.PASSWORD_RESET,
    ):
        raise ValueError("Unsupported email OTP purpose.")

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
            or not challenge.code_hash
        ):
            return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)
        if challenge.consumed_at is not None:
            status = (
                EmailOTPStatus.LOCKED
                if challenge.attempts >= OTP_MAX_ATTEMPTS
                else EmailOTPStatus.UNAVAILABLE
            )
            return EmailOTPVerification(status)

        user = challenge.user
        pending_signup = None
        if purpose == EmailOTPChallenge.Purpose.SIGNUP and not user:
            pending_signup = (
                PendingSignup.objects.select_for_update()
                .filter(email__iexact=email)
                .first()
            )
            if (
                not pending_signup
                or pending_signup.email.strip().casefold()
                != email.strip().casefold()
            ):
                return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)
        elif not user or user.email.strip().casefold() != email.strip().casefold():
            return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)

        if challenge.expires_at <= now:
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            return EmailOTPVerification(EmailOTPStatus.EXPIRED)

        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            return EmailOTPVerification(EmailOTPStatus.LOCKED)

        if not check_password(code, challenge.code_hash):
            challenge.attempts += 1
            if challenge.attempts >= OTP_MAX_ATTEMPTS:
                challenge.consumed_at = now
            challenge.save(update_fields=["attempts", "consumed_at"])
            if challenge.attempts >= OTP_MAX_ATTEMPTS:
                return EmailOTPVerification(EmailOTPStatus.LOCKED)
            return EmailOTPVerification(EmailOTPStatus.INCORRECT)

        if purpose == EmailOTPChallenge.Purpose.SIGNUP:
            if pending_signup:
                if CustomUser.objects.filter(email__iexact=email).exists():
                    return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)
                user = CustomUser(
                    email=pending_signup.email,
                    username=pending_signup.username,
                    password=pending_signup.password_hash,
                    phone=pending_signup.phone,
                    first_name=pending_signup.first_name,
                    last_name=pending_signup.last_name,
                    is_email_verified=True,
                    is_active=True,
                    account_status=CustomUser.AccountStatus.ACTIVE,
                )
                try:
                    with transaction.atomic():
                        user.save(force_insert=True)
                        UserProfile.objects.create(
                            user=user,
                            full_name=pending_signup.full_name,
                            phone=pending_signup.phone,
                            is_phone_verified=False,
                        )
                except IntegrityError as exc:
                    logger.error(
                        "Signup account creation failed during email OTP verification "
                        "(exception_type=%s)",
                        type(exc).__name__,
                    )
                    return EmailOTPVerification(
                        EmailOTPStatus.ACCOUNT_CREATION_FAILED
                    )
                pending_signup.delete()
                challenge.user = user
                challenge.consumed_at = now
                challenge.save(update_fields=["user", "consumed_at"])
                return EmailOTPVerification(EmailOTPStatus.SUCCESS, user)

            if (
                user.account_status != CustomUser.AccountStatus.PENDING_VERIFICATION
                or user.is_active
                or user.is_email_verified
            ):
                return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            user.is_email_verified = True
            user.is_active = True
            user.account_status = CustomUser.AccountStatus.ACTIVE
            user.save(update_fields=["is_email_verified", "is_active", "account_status", "updated_at"])
            return EmailOTPVerification(EmailOTPStatus.SUCCESS, user)

        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])
        if (
            user.account_status != CustomUser.AccountStatus.ACTIVE
            or not user.is_active
        ):
            return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)

        if not user.has_usable_password():
            return EmailOTPVerification(EmailOTPStatus.UNAVAILABLE)

        return EmailOTPVerification(EmailOTPStatus.SUCCESS, user)
