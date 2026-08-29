from pathlib import Path
from django.conf import settings

try:
    import azure.cognitiveservices.speech as speechsdk
except Exception:
    speechsdk = None

def synthesize_hindi_text(text: str, output_path: str, voice: str = None) -> bool:
    """Synthesize text into Hindi audio using configured TTS provider.

    Provider: Azure (default). Falls back to gTTS when Azure SDK not configured.
    """
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    provider = getattr(settings, 'TTS_PROVIDER', 'azure')

    if provider == 'azure':
        if speechsdk is None:
            raise RuntimeError('Azure speech SDK is not installed.')
        key = getattr(settings, 'TTS_API_KEY', '')
        region = getattr(settings, 'TTS_REGION', '')
        tts_voice = voice or getattr(settings, 'TTS_VOICE', None)
        if not key or not region:
            raise RuntimeError('Azure TTS API key or region not configured.')

        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        if tts_voice:
            speech_config.speech_synthesis_voice_name = tts_voice
        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(p))
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return True
        else:
            return False

    # Fallback using gTTS (note: requires internet, not as natural)
    try:
        from gtts import gTTS
        t = gTTS(text=text, lang='hi')
        t.save(str(p))
        return True
    except Exception:
        return False
