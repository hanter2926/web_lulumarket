"""Reusable email helper for Django views.

This helper uses the EMAIL_BACKEND configured in settings.py (Brevo via Anymail
when BREVO_API_KEY is configured).
"""
import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_message(to_email, subject, message, html_message=None):
    """Send an email; return True on success, False if sending fails.

    to_email can be one email address or a list/tuple of addresses.
    """
    recipients = [to_email] if isinstance(to_email, str) else list(to_email or [])
    recipients = [email for email in recipients if email]

    if not recipients:
        logger.warning("Email not sent: no recipient address was provided.")
        return False

    if not settings.DEFAULT_FROM_EMAIL:
        logger.error("Email not sent: DEFAULT_FROM_EMAIL is not configured.")
        return False

    if (
        settings.EMAIL_BACKEND == "anymail.backends.brevo.EmailBackend"
        and not getattr(settings, "BREVO_API_KEY", "")
    ):
        logger.error("Email not sent: BREVO_API_KEY is not configured.")
        return False

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False,
        )
        return sent_count == 1
    except Exception:
        logger.exception("Email sending failed.")
        return False
