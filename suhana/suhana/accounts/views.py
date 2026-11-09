import json
import logging

from datetime import timedelta

from smtplib import SMTPException

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.views.decorators.csrf import ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import PendingSignup
from .utils import (
    generate_otp,
    hash_otp,
    verify_otp,
    hash_user_password,
    send_signup_otp,
)

logger = logging.getLogger(__name__)

User = get_user_model()

OTP_VALIDITY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
MAX_OTP_ATTEMPTS = 5


def get_request_data(request):
    try:
        data = json.loads(request.body or "{}")

        if isinstance(data, dict):
            return data

        return None

    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@require_POST
def register(request):

    data = get_request_data(request)

    if data is None:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400,
        )

    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not username or not email or not isinstance(password, str) or not password:
        return JsonResponse(
            {"success": False, "message": "All fields are required."},
            status=400,
        )

    if len(username) > 150:
        return JsonResponse(
            {"success": False, "message": "Username is too long."},
            status=400,
        )

    try:
        validate_email(email)
        validate_password(password)
    except ValidationError as error:
        return JsonResponse(
            {"success": False, "message": error.messages},
            status=400,
        )

    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse(
            {"success": False, "message": "Username already exists."},
            status=409,
        )

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {"success": False, "message": "Email already registered."},
            status=409,
        )

    if PendingSignup.objects.filter(username__iexact=username).exists():
        return JsonResponse(
            {"success": False, "message": "Username registration is already pending."},
            status=409,
        )

    if PendingSignup.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {"success": False, "message": "Email registration is already pending. Please use Resend OTP."},
            status=409,
        )

    otp = generate_otp()

    pending = None
    try:
        pending = PendingSignup.objects.create(
            username=username,
            email=email,
            password_hash=hash_user_password(password),
            otp_hash=hash_otp(otp),
            otp_expiry=timezone.now() + timedelta(minutes=OTP_VALIDITY_MINUTES),
            failed_attempts=0,
        )

        email_sent = send_signup_otp(email, otp)

        if email_sent != 1:
            pending.delete()

            return JsonResponse(
                {"success": False, "message": "OTP email could not be sent."},
                status=500,
            )

    except IntegrityError:
        return JsonResponse(
            {"success": False, "message": "Registration is already pending."},
            status=409,
        )
    except (OSError, SMTPException):
        logger.exception("Signup OTP sending failed.")

        if pending is not None:
            pending.delete()

        return JsonResponse(
            {"success": False, "message": "Unable to send OTP. Please try again."},
            status=500,
        )

    return JsonResponse(
        {
            "success": True,
            "message": "OTP sent successfully. Please verify your email.",
            "email": email,
            "otp_expires_in_minutes": OTP_VALIDITY_MINUTES,
        },
        status=200,
    )


@require_POST
def verify_signup_otp(request):

    data = get_request_data(request)

    if data is None:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400,
        )

    email = str(data.get("email", "")).strip().lower()
    otp = str(data.get("otp", "")).strip()

    if not email or not otp:
        return JsonResponse(
            {"success": False, "message": "Email and OTP are required."},
            status=400,
        )

    if len(otp) != 6 or not otp.isdigit():
        return JsonResponse(
            {"success": False, "message": "Enter a valid 6-digit OTP."},
            status=400,
        )

    try:
        with transaction.atomic():

            pending = PendingSignup.objects.select_for_update().get(
                email__iexact=email
            )

            if pending.failed_attempts >= MAX_OTP_ATTEMPTS:
                pending.delete()

                return JsonResponse(
                    {"success": False, "message": "Too many attempts. Please register again."},
                    status=400,
                )

            if timezone.now() >= pending.otp_expiry:
                pending.delete()

                return JsonResponse(
                    {"success": False, "message": "OTP expired. Please register again."},
                    status=400,
                )

            if not verify_otp(otp, pending.otp_hash):

                pending.failed_attempts += 1
                pending.save(update_fields=["failed_attempts"])

                remaining = MAX_OTP_ATTEMPTS - pending.failed_attempts

                return JsonResponse(
                    {
                        "success": False,
                        "message": "Incorrect OTP.",
                        "attempts_remaining": remaining,
                    },
                    status=400,
                )

            if User.objects.filter(username__iexact=pending.username).exists():
                return JsonResponse(
                    {"success": False, "message": "Username is already in use."},
                    status=409,
                )

            if User.objects.filter(email__iexact=pending.email).exists():
                return JsonResponse(
                    {"success": False, "message": "Email is already registered."},
                    status=409,
                )

            user = User(
                username=pending.username,
                email=pending.email,
            )

            # Reuse the already-hashed password.
            user.password = pending.password_hash
            user.save()

            pending.delete()

    except PendingSignup.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "No pending registration found. Please register again."},
            status=404,
        )

    except IntegrityError:
        return JsonResponse(
            {"success": False, "message": "Account could not be created. Please try again."},
            status=409,
        )

    return JsonResponse(
        {
            "success": True,
            "message": "Email verified and account created successfully.",
            "username": user.username,
        },
        status=201,
    )


@require_POST
def resend_signup_otp(request):

    data = get_request_data(request)

    if data is None:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400,
        )

    email = str(data.get("email", "")).strip().lower()

    if not email:
        return JsonResponse(
            {"success": False, "message": "Email is required."},
            status=400,
        )

    try:
        with transaction.atomic():
            pending = PendingSignup.objects.select_for_update().get(
                email__iexact=email
            )
            now = timezone.now()
            elapsed = (now - pending.last_otp_sent_at).total_seconds()

            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                wait_seconds = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Please wait before requesting another OTP.",
                        "wait_seconds": wait_seconds,
                    },
                    status=429,
                )

            otp = generate_otp()
            email_sent = send_signup_otp(email, otp)
            if email_sent != 1:
                return JsonResponse(
                    {"success": False, "message": "OTP email could not be sent."},
                    status=500,
                )

            pending.otp_hash = hash_otp(otp)
            pending.otp_expiry = now + timedelta(minutes=OTP_VALIDITY_MINUTES)
            pending.last_otp_sent_at = now
            pending.failed_attempts = 0
            pending.save(
                update_fields=[
                    "otp_hash",
                    "otp_expiry",
                    "last_otp_sent_at",
                    "failed_attempts",
                ]
            )

    except PendingSignup.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "No pending registration found."},
            status=404,
        )
    except (OSError, SMTPException):
        logger.exception("Resend signup OTP failed.")
        return JsonResponse(
            {"success": False, "message": "Unable to resend OTP. Please try again."},
            status=500,
        )
    except IntegrityError:
        return JsonResponse(
            {"success": False, "message": "Unable to resend OTP. Please try again."},
            status=409,
        )

    return JsonResponse(
        {
            "success": True,
            "message": "New OTP sent successfully.",
            "otp_expires_in_minutes": OTP_VALIDITY_MINUTES,
        },
        status=200,
    )


@require_GET
@ensure_csrf_cookie
def csrf_token_view(request):
    return JsonResponse({"success": True, "csrfToken": get_token(request)})