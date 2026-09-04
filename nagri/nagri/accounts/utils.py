import os
import re
import secrets

OTP_TTL_MINUTES = 5
# Use 60 seconds cooldown for normal user OTP resend to match requirements
OTP_RESEND_COOLDOWN_SECONDS = 60


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
    print("====================================")
    print(f"OTP for {phone_number} is: {otp}")
    print("====================================")
    return {"provider": "console", "status": "sent", "phone_number": phone_number, "otp": otp}


def send_otp_via_twilio(phone_number, otp, account_sid=None, auth_token=None, from_number=None):
    account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = from_number or os.environ.get("TWILIO_PHONE_NUMBER")

    if not account_sid or not auth_token or not from_number:
        raise ValueError("Twilio SMS configuration is incomplete. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER.")

    try:
        from twilio.rest import Client
    except ImportError:
        raise RuntimeError("Twilio dependency is not installed. Install 'twilio' to use the Twilio provider.")

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=f"Your Nagri OTP is {otp}",
        from_=from_number,
        to=phone_number,
    )
    return {"provider": "twilio", "status": "sent", "sid": getattr(message, "sid", None), "phone_number": phone_number}


def send_otp_via_fast2sms(phone_number, otp, api_key=None):
    api_key = api_key or os.environ.get("FAST2SMS_API_KEY")
    if not api_key:
        raise ValueError("Fast2SMS API key is missing. Set FAST2SMS_API_KEY.")

    try:
        import requests
    except ImportError:
        raise RuntimeError("Requests dependency is not installed. Install 'requests' to use Fast2SMS.")

    payload = {
        "sender_id": os.environ.get("FAST2SMS_SENDER_ID", "FSTSMS"),
        "message": f"Your Nagri OTP is {otp}",
        "language": "english",
        "route": "v3",
        "numbers": phone_number,
        "flash": 0,
        "apikey": api_key,
    }

    response = requests.post("https://www.fast2sms.com/dev/bulkV2", data=payload, timeout=20)
    response.raise_for_status()
    return {"provider": "fast2sms", "status": "sent", "response": response.json(), "phone_number": phone_number}


def send_otp_to_phone(phone_number, otp, provider=None):
    provider_name = (provider or os.environ.get("SMS_PROVIDER", "console")).lower()

    if provider_name == "twilio":
        return send_otp_via_twilio(phone_number, otp)
    if provider_name == "fast2sms":
        return send_otp_via_fast2sms(phone_number, otp)

    return send_otp_via_console(phone_number, otp)
