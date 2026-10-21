import smtplib

from django.conf import settings
from django.core.mail import send_mail


class EmailDeliveryConfigurationError(RuntimeError):
    pass


def classify_email_delivery_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        failure_class = "smtp_authentication"
    elif isinstance(exc, smtplib.SMTPConnectError):
        failure_class = "smtp_connection"
    elif isinstance(exc, smtplib.SMTPServerDisconnected):
        failure_class = "smtp_disconnected"
    elif isinstance(exc, smtplib.SMTPRecipientsRefused):
        failure_class = "smtp_recipient_rejected"
    elif isinstance(exc, smtplib.SMTPSenderRefused):
        failure_class = "smtp_sender_rejected"
    elif isinstance(exc, smtplib.SMTPResponseException):
        failure_class = "smtp_response"
    elif isinstance(exc, (TimeoutError, OSError)):
        failure_class = "network_or_timeout"
    elif isinstance(exc, EmailDeliveryConfigurationError):
        failure_class = "email_configuration"
    else:
        failure_class = "email_backend"

    smtp_code = getattr(exc, "smtp_code", None)
    if not isinstance(smtp_code, int):
        smtp_code = None
    return failure_class, smtp_code


def validate_email_delivery_configuration():
    backend = settings.EMAIL_BACKEND.strip().lower()
    local_backends = (
        "django.core.mail.backends.console.emailbackend",
        "django.core.mail.backends.dummy.emailbackend",
        "django.core.mail.backends.locmem.emailbackend",
    )
    if not settings.DEBUG and backend in local_backends:
        raise EmailDeliveryConfigurationError(
            "A non-delivering email backend is configured for production"
        )

    if backend == "django.core.mail.backends.smtp.emailbackend":
        required = (
            settings.EMAIL_HOST,
            settings.EMAIL_PORT,
            settings.EMAIL_HOST_USER,
            settings.EMAIL_HOST_PASSWORD,
            settings.DEFAULT_FROM_EMAIL,
        )
        if not all(required):
            raise EmailDeliveryConfigurationError(
                "SMTP email configuration is incomplete"
            )
        if (
            settings.EMAIL_HOST.lower() == "smtp.gmail.com"
            and not settings.EMAIL_USE_TLS
        ):
            raise EmailDeliveryConfigurationError(
                "Gmail SMTP requires TLS"
            )


def send_account_email(subject, body, recipient):
    validate_email_delivery_configuration()
    sent_count = send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [recipient],
        fail_silently=False,
    )
    if sent_count != 1:
        raise RuntimeError("Configured email backend did not accept the message")
