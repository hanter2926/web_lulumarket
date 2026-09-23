"""Shared application constants."""

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
}

SEAMLESS_LANGUAGE_CODES = {
    "en": "eng",
    "eng": "eng",
    "hi": "hin",
    "hin": "hin",
    "es": "spa",
    "spa": "spa",
    "fr": "fra",
    "fra": "fra",
}


def normalize_language_code(value: str) -> str:
    normalized = value.strip().lower()
    try:
        return SEAMLESS_LANGUAGE_CODES[normalized]
    except KeyError as exc:
        raise ValueError("Unsupported language") from exc
