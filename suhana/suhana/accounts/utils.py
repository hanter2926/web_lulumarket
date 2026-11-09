import secrets

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail


def generate_otp():
    """Generate a secure 6-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp):
    """Hash OTP before storing it."""
    return make_password(otp)


def verify_otp(otp, otp_hash):
    """Verify entered OTP against stored hash."""
    return check_password(otp, otp_hash)


def hash_user_password(password):
    """Hash password before storing it in PendingSignup."""
    return make_password(password)


def send_signup_otp(email, otp):
    """Send signup OTP through Gmail SMTP."""

    subject = "Suhana - Email Verification OTP"

    message = f"""
Hello,

Your Suhana registration OTP is: {otp}

This OTP is valid for 10 minutes.

Do not share this OTP with anyone.

If you did not request this OTP, please ignore this email.

Regards,
Suhana Team
"""

    return send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )


def send_password_reset_otp(email, otp):
    return send_mail(
        "Suhana - Password Reset OTP",
        (
            f"Your Suhana password reset OTP is: {otp}\n\n"
            "This OTP is valid for 10 minutes. If you did not request it, ignore this email."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )