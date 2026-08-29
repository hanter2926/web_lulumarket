from typing import List, Dict
from django.conf import settings

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

import openai


def translate_segments_to_hindi(segments: List[Dict]) -> List[Dict]:
    """Translate segments into Hindi preserving timing. Uses provider based on settings.

    Adds 'text_hindi' to each segment.
    """
    provider = getattr(settings, 'TRANSLATION_PROVIDER', 'openai')
    if provider == 'openai' and getattr(settings, 'OPENAI_API_KEY', ''):
        openai.api_key = settings.OPENAI_API_KEY
        for seg in segments:
            prompt = f"Translate the following English text to Hindi, preserving meaning: {seg.get('text', '')}"
            try:
                resp = openai.ChatCompletion.create(
                    model='gpt-3.5-turbo',
                    messages=[{'role': 'user', 'content': prompt}],
                    temperature=0.2,
                )
                text = resp.choices[0].message.content.strip()
            except Exception:
                text = seg.get('text', '')
            seg['text_hindi'] = text
        return segments

    # Fallback to GoogleTranslator if available
    if GoogleTranslator:
        translator = GoogleTranslator(source='auto', target='hi')
        for seg in segments:
            try:
                seg['text_hindi'] = translator.translate(seg.get('text', ''))
            except Exception:
                seg['text_hindi'] = seg.get('text', '')
        return segments

    # Final fallback: copy original
    for seg in segments:
        seg['text_hindi'] = seg.get('text', '')
    return segments
