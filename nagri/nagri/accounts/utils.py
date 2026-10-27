import os
import re
import secrets
import logging

import requests
from django.conf import settings

OTP_TTL_MINUTES = 5
# Use 60 seconds cooldown for normal user OTP resend to match requirements
OTP_RESEND_COOLDOWN_SECONDS = 60
logger = logging.getLogger(__name__)


def normalize_phone_number(phone):
    if phone is None:
        return ""

    raw = re.sub(r"[\s\-()]", "", str(phone).strip())
    if not raw:
        return ""

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""

    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        if len(digits) == 10:
            return f"+91{digits}"
        return ""

    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"

    return ""


def get_phone_variants(phone):
    normalized = normalize_phone_number(phone)
    variants = {normalized} if normalized else set()
    digits = re.sub(r"\D", "", str(phone or ""))

    if digits:
        variants.add(digits)
        if len(digits) == 10:
            variants.add(f"91{digits}")
            variants.add(f"+91{digits}")
        elif len(digits) == 11 and digits.startswith("0"):
            variants.add(digits[1:])
            variants.add(f"91{digits[1:]}")
            variants.add(f"+91{digits[1:]}")
        elif len(digits) == 12 and digits.startswith("91"):
            variants.add(digits[2:])
            variants.add(f"+{digits}")

    return {variant for variant in variants if variant}


def generate_otp(length=6):
    if length <= 0:
        return "000000"
    return str(secrets.randbelow(10 ** length)).zfill(length)


def send_otp_via_console(phone_number, otp):
    logger.warning("Console SMS backend cannot deliver OTP messages")
    return {"provider": "console", "status": "failed"}


def send_otp_via_twilio(phone_number, otp, account_sid=None, auth_token=None, from_number=None):
    account_sid = (
        account_sid
        or getattr(settings, "TWILIO_ACCOUNT_SID", "")
        or os.environ.get("TWILIO_ACCOUNT_SID")
    )
    auth_token = (
        auth_token
        or getattr(settings, "TWILIO_AUTH_TOKEN", "")
        or os.environ.get("TWILIO_AUTH_TOKEN")
    )
    from_number = (
        from_number
        or getattr(settings, "TWILIO_PHONE_NUMBER", "")
        or os.environ.get("TWILIO_PHONE_NUMBER")
    )

    if not account_sid or not auth_token or not from_number:
        raise ValueError("Twilio SMS configuration is incomplete. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER.")

    try:
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            auth=(account_sid, auth_token),
            data={
                "Body": f"Your NAGRI verification code is {otp}. It expires in 5 minutes.",
                "From": from_number,
                "To": phone_number,
            },
            timeout=(5, 20),
        )
        response.raise_for_status()
    except Exception as exc:
        logger.error(
            "Twilio SMS delivery failed: error_type=%s status_code=%s",
            type(exc).__name__,
            getattr(getattr(exc, "response", None), "status_code", None),
        )
        raise

    response_data = response.json()
    return {
        "provider": "twilio",
        "status": "sent",
        "sid": response_data.get("sid"),
        "phone_number": phone_number,
    }


def send_otp_via_fast2sms(phone_number, otp, api_key=None):
    api_key = (
        api_key
        or getattr(settings, "FAST2SMS_API_KEY", "")
        or os.environ.get("FAST2SMS_API_KEY")
    )
    if not api_key:
        raise ValueError("Fast2SMS API key is missing. Set FAST2SMS_API_KEY.")

    payload = {
        "sender_id": (
            getattr(settings, "FAST2SMS_SENDER_ID", "")
            or os.environ.get("FAST2SMS_SENDER_ID", "FSTSMS")
        ),
        "message": f"Your NAGRI verification code is {otp}. It expires in 5 minutes.",
        "language": "english",
        "route": "v3",
        "numbers": re.sub(r"\D", "", phone_number)[-10:],
        "flash": 0,
        "apikey": api_key,
    }

    response = requests.post(
        "https://www.fast2sms.com/dev/bulkV2",
        data=payload,
        timeout=(5, 20),
    )
    response.raise_for_status()
    response_data = response.json()
    if response_data.get("return") is not True:
        raise RuntimeError("Fast2SMS did not confirm SMS delivery.")
    return {
        "provider": "fast2sms",
        "status": "sent",
        "request_id": response_data.get("request_id"),
        "phone_number": phone_number,
    }


def send_otp_to_phone(phone_number, otp, provider=None):
    provider_name = (
        provider
        or getattr(settings, "SMS_PROVIDER", "")
        or os.environ.get("SMS_PROVIDER", "")
    ).strip().lower()
    if not provider_name:
        twilio_is_configured = all(
            (
                getattr(settings, "TWILIO_ACCOUNT_SID", "")
                or os.environ.get("TWILIO_ACCOUNT_SID"),
                getattr(settings, "TWILIO_AUTH_TOKEN", "")
                or os.environ.get("TWILIO_AUTH_TOKEN"),
                getattr(settings, "TWILIO_PHONE_NUMBER", "")
                or os.environ.get("TWILIO_PHONE_NUMBER"),
            )
        )
        fast2sms_is_configured = (
            getattr(settings, "FAST2SMS_API_KEY", "")
            or os.environ.get("FAST2SMS_API_KEY")
        )
        provider_name = (
            "twilio"
            if twilio_is_configured
            else "fast2sms" if fast2sms_is_configured else "console"
        )

    if provider_name == "twilio":
        return send_otp_via_twilio(phone_number, otp)
    if provider_name == "fast2sms":
        return send_otp_via_fast2sms(phone_number, otp)
    if provider_name == "console":
        return send_otp_via_console(phone_number, otp)

    raise ValueError(f"Unsupported SMS provider: {provider_name}")
