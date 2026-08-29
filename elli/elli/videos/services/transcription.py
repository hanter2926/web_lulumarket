from typing import List, Dict
from pathlib import Path
from django.conf import settings
import whisper


def transcribe_with_whisper(audio_path: str) -> List[Dict]:
    """Transcribe audio using local Whisper and return segments with timestamps.

    Returns list of segments: {"start": float, "end": float, "text": str}
    """
    model_name = getattr(settings, 'WHISPER_MODEL', 'small')
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language='en')
    segments = []
    for seg in result.get('segments', []):
        segments.append({
            'start': float(seg.get('start', 0.0)),
            'end': float(seg.get('end', seg.get('start', 0.0))),
            'text': seg.get('text', '').strip(),
        })
    return segments
