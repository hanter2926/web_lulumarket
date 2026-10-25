import logging
import re
import smtplib

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.db import OperationalError


logger = logging.getLogger(__name__)
BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"

BREVO_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
BREVO_OTP_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")
BREVO_AUTH_HEADER_PATTERN = re.compile(
    r"\b(?:proxy-)?authorization\s*[:=]\s*[^\r\n,;]+",
    re.IGNORECASE,
)
BREVO_BEARER_PATTERN = re.compile(
    r"\bbearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
BREVO_CREDENTIAL_PATTERN = re.compile(
    r"\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|token|"
    r"password|secret|otp)\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)

class EmailDeliveryConfigurationError(RuntimeError):
    pass


class BrevoAPIError(RuntimeError):
    def __init__(
        self,
        status_code,
        failure_class,
        response_code=None,
        response_message=None,
    ):
        self.status_code = status_code
        self.failure_class = failure_class
        super().__init__(failure_class)
        self.response_code = response_code
        self.response_message = response_message


def classify_email_delivery_error(exc):
def _redact_brevo_response_value(value, max_length=240):
    if not isinstance(value, str):
        return None

    sanitized = "".join(
        " " if ord(character) < 32 or ord(character) == 127 else character
        for character in value
    )
    sensitive_values = [
        settings.BREVO_API_KEY,
        settings.ANYMAIL.get("BREVO_API_KEY", ""),
        settings.EMAIL_HOST_PASSWORD,
        settings.SECRET_KEY,
        settings.DATABASES.get("default", {}).get("PASSWORD", ""),
    ]
    for sensitive_value in sorted(
        {item for item in sensitive_values if item},
        key=len,
        reverse=True,
    ):
        sanitized = sanitized.replace(sensitive_value, "[redacted]")

    sanitized = BREVO_AUTH_HEADER_PATTERN.sub("Authorization: [redacted]", sanitized)
    sanitized = BREVO_BEARER_PATTERN.sub("Bearer [redacted]", sanitized)
    sanitized = BREVO_CREDENTIAL_PATTERN.sub(r"\1=[redacted]", sanitized)
    sanitized = BREVO_EMAIL_PATTERN.sub("[email redacted]", sanitized)
    sanitized = BREVO_OTP_PATTERN.sub("[code redacted]", sanitized)
    return sanitized[:max_length]


def _brevo_response_details(response):
    try:
        response_data = response.json()
    except ValueError:
        return None, None

    if not isinstance(response_data, dict):
        return None, None
    return (
        _redact_brevo_response_value(response_data.get("code"), max_length=80),
        _redact_brevo_response_value(response_data.get("message")),
    )


    if isinstance(exc, BrevoAPIError):
        return exc.failure_class, exc.status_code
    if isinstance(exc, requests.Timeout):
        return "brevo_timeout", None
    if isinstance(exc, requests.ConnectionError):
        return "brevo_connection", None
    if isinstance(exc, OperationalError):
        return "database_operational", None
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
    provider = settings.EMAIL_PROVIDER
    if provider == "brevo":
        if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
            raise EmailDeliveryConfigurationError(
                "Brevo email configuration is incomplete"
            )
        return

    if provider != "smtp":
        raise EmailDeliveryConfigurationError(
            "EMAIL_PROVIDER must be set to brevo or smtp"
        )

    backend = settings.EMAIL_BACKEND.strip().lower()
    if (
        settings.DEBUG
        and backend == "django.core.mail.backends.locmem.emailbackend"
    ):
        return

    if backend != "django.core.mail.backends.smtp.emailbackend":
        raise EmailDeliveryConfigurationError(
            "SMTP provider requires Django's SMTP email backend"
        )

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
        and not settings.EMAIL_USE_SSL
    ):
        raise EmailDeliveryConfigurationError(
            "Gmail SMTP requires TLS or SSL"
        )


def _send_via_brevo(subject, body, recipient, html_body):
    payload = {
        "sender": {
            "email": settings.BREVO_SENDER_EMAIL,
            "name": settings.BREVO_SENDER_NAME or "NAGRI",
        },
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": body,
    }
    if html_body:
        payload["htmlContent"] = html_body

    response = requests.post(
        BREVO_EMAIL_URL,
        headers={
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
        json=payload,
        timeout=(3.05, 10),
        allow_redirects=False,
    )

    if not 200 <= response.status_code < 300:
        status_code = response.status_code
        failure_class = {
            401: "brevo_unauthorized",
            403: "brevo_forbidden",
        }.get(status_code, "brevo_api_rejected")
        response_code, response_message = _brevo_response_details(response)
        raise BrevoAPIError(
            status_code,
            failure_class,
            response_code=response_code,
            response_message=response_message,
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise BrevoAPIError(response.status_code, "brevo_malformed_response") from exc

    if not isinstance(result, dict) or not isinstance(result.get("messageId"), str):
        raise BrevoAPIError(response.status_code, "brevo_malformed_response")

    logger.info("Transactional email accepted by Brevo API")


def send_account_email(subject, body, recipient, html_body=None, from_email=None):
    validate_email_delivery_configuration()

    if settings.EMAIL_PROVIDER == "brevo":
        _send_via_brevo(subject, body, recipient, html_body)
        return

    if html_body:
        message = EmailMultiAlternatives(
            subject,
            body,
            from_email or settings.DEFAULT_FROM_EMAIL,
            [recipient],
        )
        message.attach_alternative(html_body, "text/html")
        sent_count = message.send(fail_silently=False)
    else:
        sent_count = send_mail(
            subject,
            body,
            from_email or settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )

    if sent_count != 1:
        raise RuntimeError("Configured email backend did not accept the message")

    logger.info("Transactional email accepted by configured email backend")
