import re


SENSITIVE_PUBLIC_VALUE = re.compile(
    r"(?:"
    r"password|passcode|one[\s_-]*time[\s_-]*password|otp|"
    r"recovery[\s_-]*(?:code|key)|backup[\s_-]*code|"
    r"2fa|two[\s_-]*factor|auth(?:entication)?[\s_-]*(?:token|code|key)|"
    r"access[\s_-]*token|bearer[\s_-]*token|session[\s_-]*(?:cookie|token)|"
    r"api[\s_-]*(?:key|token|secret)|secret[\s_-]*key|private[\s_-]*key|"
    r"login[\s_-]*(?:id|username|email)|username|email"
    r")",
    re.IGNORECASE,
)


def is_safe_public_text(value):
    return not value or not SENSITIVE_PUBLIC_VALUE.search(str(value))
